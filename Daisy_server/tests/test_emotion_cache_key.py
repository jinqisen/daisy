"""
情绪分析缓存键的回归测试。

现象:同一用户连续多轮对话,每一轮的 top_emotions / ekman_scores 都与第 1 轮
完全相同(例如 4 轮都是 neutral 0.99998),第 2 轮起 analyze 节点只花 0.1 s ——
翻译与 GoEmotions 都没跑。workflow_traces 里 EmotionTranslator 的 llm_traces
数远少于 FinalResponseAgent(daisy.db 3 vs 28)就是它留下的痕迹。

根因:`cache_result` 以**被装饰方法的原样参数**调用 key_builder,即
`key_builder(self, text, **kw)`;而 emotion_key_builder 的签名曾写成
`(func, *args, **kwargs)`:self 被当成 func 吃掉、text 落到 args[0],代码却读
args[1] —— 任何输入都得到常量 "emotion:empty"。开启缓存(Redis 或嵌入模式的
进程内 KV)后所有文本命中同一条目,整条情绪链路静默退化成"永远是第 1 轮"。

这类缺陷日志正常、无异常、测试全绿,所以这里**按装饰器真实的调用形态**
把键的行为锁死,而不是直接调用一个顺手的签名。
"""

import asyncio
import inspect

import pytest

from app.core.local_kv import LocalKVAsync, reset_for_tests
from app.services.persona.emotion import EmotionService, emotion_key_builder


class _Svc:
    """占位 self:key_builder 收到的第一个位置参数就是服务实例。"""


def _key(text, **kw):
    """与 cache_result 完全相同的调用形态:(self, text, **kwargs)。"""
    return emotion_key_builder(_Svc(), text, **kw)


class TestKeyBuilder:

    def test_called_like_the_decorator_is_not_the_empty_key(self):
        """核心回归:按装饰器的形态调用,非空文本绝不能落到 "emotion:empty"。"""
        assert _key("今天好累,什么都不想做") != "emotion:empty"

    def test_different_texts_get_different_keys(self):
        assert _key("今天好开心") != _key("今天好难过")

    def test_same_text_gets_same_key(self):
        assert _key("今天好开心") == _key("今天好开心")

    def test_positional_and_keyword_forms_agree(self):
        """text 不管按位置还是按关键字传,都要落到同一个键,否则命中率随调用写法漂移。"""
        assert _key("hello") == emotion_key_builder(_Svc(), text="hello")

    @pytest.mark.parametrize("empty", ["", "   ", None])
    def test_empty_text_returns_the_empty_key(self, empty):
        assert _key(empty) == "emotion:empty"

    def test_same_input_in_different_context_gets_different_keys(self):
        """
        analyze 节点传进来的 text 是「最近 EMOTION_CONTEXT_TURNS 条历史 + 当前输入」
        合并后的 full_text。同一句"嗯"接在不同上下文后面情绪可能完全不同,
        键必须随上下文变化 —— 不能只看 original_text(仅当前输入)。
        """
        with_sad_context = _key("我的猫昨天走了 嗯", original_text="嗯")
        with_happy_context = _key("我升职了 嗯", original_text="嗯")
        assert with_sad_context != with_happy_context

    def test_per_request_metadata_does_not_change_the_key(self):
        """
        trigger_message_id / execution_id 每一轮都不同;若它们混进键,
        缓存就永远不会命中 —— 那是另一种静默失效。
        """
        a = _key("今天好开心", user_id="u1", trigger_message_id=1, execution_id="e1")
        b = _key("今天好开心", user_id="u2", trigger_message_id=2, execution_id="e2")
        assert a == b


class TestNodePassesContextMergedText:
    """
    键只由 text 决定,前提是节点传进来的 text 已经带上上下文。
    这里守住"第一个参数是 full_text 而不是裸 user_input"的接线。
    """

    def test_analyze_async_receives_full_text(self):
        from app.workflow.nodes import emotion as node

        src = inspect.getsource(node.analyze_emotion)
        assert "analyze_async(full_text" in src, \
            "analyze 节点不再把上下文合并后的 full_text 交给 analyze_async,缓存键会丢失上下文"


def _fake_service(calls):
    """
    不加载模型的 EmotionService:classifier 换成按文本返回不同标签的桩,
    并记录每次真实调用,用来区分"命中缓存"与"重新分析"。
    英文输入不会触发翻译,所以不碰 LLM。
    """
    svc = EmotionService.__new__(EmotionService)
    svc.model_name = "fake"

    def classifier(text):
        calls.append(text)
        label = "joy" if "happy" in text else "anger"
        return [[{"label": label, "score": 0.9}, {"label": "neutral", "score": 0.1}]]

    svc.classifier = classifier
    return svc


class TestTwoTextsDoNotShareACacheEntry:

    @pytest.fixture(autouse=True)
    def in_process_cache(self, monkeypatch):
        """把全局缓存门面接到进程内 KV 上 —— 与 EMBEDDED_MODE 下的运行形态一致。"""
        from app.core import cache as cache_module

        reset_for_tests()
        monkeypatch.setattr(cache_module.redis_client, "redis", LocalKVAsync())
        monkeypatch.setattr(cache_module.redis_client, "enabled", True)
        yield
        reset_for_tests()

    def test_second_text_is_analyzed_not_served_from_first(self):
        calls = []
        svc = _fake_service(calls)

        async def go():
            first = await svc.analyze_async("I am so happy today")
            second = await svc.analyze_async("I am furious right now")
            first_again = await svc.analyze_async("I am so happy today")
            return first, second, first_again

        first, second, first_again = asyncio.run(go())

        assert first["joy"] == pytest.approx(0.9)
        assert second["anger"] == pytest.approx(0.9), \
            "第二段文本拿到了第一段的结果 —— 两段文本命中了同一个缓存项"
        # 第 1 段重复出现时才命中缓存:分类器总共只应被真实调用 2 次
        assert calls == ["I am so happy today", "I am furious right now"]
        assert first_again == first
