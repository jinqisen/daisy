"""
情绪分析"不可用"路径的回归:不编造结果、不缓存坏结果、不切掉当前输入。

用本地 GoEmotions 模型实测过的四种输入(旧实现的输出):

    中文原文直接喂英文模型                                  neutral 0.99999
    LLM 失败返回的 "Error generating response: ..." 文案     neutral 0.99999
    2048 字符但 685 token 的文本                            RuntimeError → {"error": 0.0}
    2639 字符的长上下文 + "我只想哭"                         neutral 0.99(单独那句是 sadness 0.999)
    欢快的 AI 回复做上下文 + 用户一句 "ok"                   joy 0.51(AI 的情绪记在了用户头上)

前两种交出一个看起来很确定的 neutral;第三种的 {"error": 0.0} 经节点对全 0 的 Ekman
排序后首位恒为 anger,被写进用户状态并注入回复提示词;第四种是当前输入被截掉了。
而且前三种都被缓存 24 小时。它们与缓存键塌缩叠加,就是"多轮永远 neutral 0.99998"的另一半。
"""

import asyncio
import inspect

import pytest

from app.core.llm import LLM_ERROR_PREFIX
from app.core.local_kv import LocalKVAsync, reset_for_tests
from app.services.persona.emotion import EmotionService
from app.workflow.nodes.emotion import (
    build_analysis_text,
    select_context_messages,
    summarize_emotion,
)

REAL_SCORES = {"sadness": 0.93, "disappointment": 0.04, "neutral": 0.02, "curiosity": 0.01}


def _service(calls, failures=0):
    """
    不加载模型的 EmotionService。classifier 记录每次调用(文本 + 关键字参数),
    前 `failures` 次抛出真实遇到过的 RuntimeError,之后返回固定分数。
    """
    svc = EmotionService.__new__(EmotionService)
    svc.model_name = "fake"
    state = {"failures": failures}

    def classifier(text, **kw):
        calls.append((text, kw))
        if state["failures"] > 0:
            state["failures"] -= 1
            raise RuntimeError("The size of tensor a (685) must match the size of tensor b (512)")
        return [[{"label": k, "score": v} for k, v in REAL_SCORES.items()]]

    svc.classifier = classifier
    return svc


@pytest.fixture
def llm(monkeypatch):
    """翻译用的 LLM 换成桩;提示词模板也换掉,免得依赖 Daisy_prompts 目录。"""
    from app.prompts import templates
    from app.services.persona import emotion as module

    monkeypatch.setattr(templates, "get_translation_prompt", lambda text: text)
    monkeypatch.setattr(templates, "get_translation_system_prompt", lambda: "translate")

    class _LLM:
        reply = "I just want to cry."

        def generate_response(self, **kwargs):
            if isinstance(self.reply, Exception):
                raise self.reply
            return self.reply

    stub = _LLM()
    monkeypatch.setattr(module, "get_llm_service", lambda: stub)
    return stub


class TestTranslationFailureIsNotMistakenForATranslation:

    def test_llm_error_string_is_a_failure(self, llm):
        """generate_response 失败不抛异常,返回错误文案;旧实现把它当译文送进了模型。"""
        llm.reply = f"{LLM_ERROR_PREFIX} Connection error."
        calls = []
        assert _service(calls).analyze("今天好累,只想哭") == {}
        assert calls == [], "错误文案被当成译文送进了模型"

    def test_llm_exception_is_a_failure(self, llm):
        llm.reply = RuntimeError("timeout")
        calls = []
        assert _service(calls).analyze("今天好累,只想哭") == {}
        assert calls == [], "翻译失败后把中文原文喂给了英文模型 —— 结果只会是无意义的 neutral"

    def test_empty_translation_is_a_failure(self, llm):
        llm.reply = '""'
        calls = []
        assert _service(calls).analyze("今天好累,只想哭") == {}
        assert calls == []

    def test_good_translation_reaches_the_model(self, llm):
        calls = []
        assert _service(calls).analyze("今天好累,只想哭") == REAL_SCORES
        assert calls[0][0] == "I just want to cry."

    def test_prefix_matches_what_llm_service_returns(self):
        """两处失败返回必须用同一个常量,否则识别会随文案改动静默失效。"""
        from app.core.llm import LLMService

        for fn in (LLMService.generate_response, LLMService.generate_response_async):
            assert "LLM_ERROR_PREFIX" in inspect.getsource(fn), fn.__name__


class TestClassifierFailure:

    def test_failure_returns_empty_not_an_error_dict(self):
        calls = []
        scores = _service(calls, failures=1).analyze("I just want to cry.")
        assert scores == {}, "旧的 {'error': 0.0} 会让节点算出假的 anger"

    def test_tokenizer_truncation_is_on(self):
        """按字符截断防不住 token 数:2048 字符的短词文本实测 685 token,不开 truncation 整轮报错。"""
        calls = []
        _service(calls).analyze("I just want to cry.")
        assert calls[0][1].get("truncation") is True


class TestUnavailableResultIsNotCached:

    @pytest.fixture(autouse=True)
    def in_process_cache(self, monkeypatch):
        from app.core import cache as cache_module

        reset_for_tests()
        monkeypatch.setattr(cache_module.redis_client, "redis", LocalKVAsync())
        monkeypatch.setattr(cache_module.redis_client, "enabled", True)
        yield
        reset_for_tests()

    def test_failure_is_retried_next_turn_and_success_is_cached(self):
        calls = []
        svc = _service(calls, failures=1)

        async def go():
            first = await svc.analyze_async("I just want to cry.")    # 模型报错 → {}
            second = await svc.analyze_async("I just want to cry.")   # 不能命中坏结果,必须重算
            third = await svc.analyze_async("I just want to cry.")    # 成功结果才进缓存
            return first, second, third

        first, second, third = asyncio.run(go())
        assert first == {}
        assert second == REAL_SCORES, "失败结果被缓存了 —— 一次抖动把这段文本钉死 24 小时"
        assert third == REAL_SCORES
        assert len(calls) == 2


class TestNodeDoesNotFabricateEmotion:

    def test_empty_scores_mean_no_emotion(self):
        summary = summarize_emotion({}, EmotionService.__new__(EmotionService))
        assert summary["top"] == []
        assert summary["ekman_scores"] == {}
        assert summary["intensity"] == 0.0
        assert summary["max_arousal"] == 0.0

    def test_why_the_old_path_said_anger(self):
        """记录旧行为错在哪:对全 0 的 Ekman 分布排序,首位恒为映射表的第一个键 anger。"""
        ekman = EmotionService.__new__(EmotionService)._map_to_ekman({})
        assert sorted(ekman.items(), key=lambda x: x[1], reverse=True)[0] == ("anger", 0.0)

    def test_real_scores_are_summarised_as_before(self):
        summary = summarize_emotion(REAL_SCORES, EmotionService.__new__(EmotionService))
        assert summary["top"][0][0] == "sadness"
        assert len(summary["top"]) == 3
        assert summary["neutral_score"] == pytest.approx(0.02)
        assert summary["intensity"] == pytest.approx(0.98)
        assert summary["max_arousal"] == pytest.approx(0.01)


class TestCurrentInputSurvivesTheContext:

    def test_long_context_is_capped_from_the_tail(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "EMOTION_CONTEXT_MAX_CHARS", 300)
        long_reply = "这是一段很长的解释。" * 200
        merged = build_analysis_text(["上一句", long_reply], "我只想哭")
        assert merged.endswith("我只想哭"), "当前输入被上下文挤掉了"
        assert len(merged) <= 300 + 1 + len("我只想哭")
        assert merged.startswith(long_reply[-300:]), "封顶应保留最近的部分"

    def test_current_message_is_not_duplicated(self):
        assert build_analysis_text(["早", "我只想哭"], "我只想哭") == "早 我只想哭"

    def test_no_context(self):
        assert build_analysis_text([], "我只想哭") == "我只想哭"

    def test_zero_disables_the_cap(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "EMOTION_CONTEXT_MAX_CHARS", 0)
        merged = build_analysis_text(["x" * 1000], "y")
        assert merged == "x" * 1000 + " y"


class TestContextIsTheUsersOwnWords:
    """
    上下文只能是用户自己的消息。原实现把 AI 回复也拼了进去,与它上方的注释
    "获取最近的用户消息"相反;后果见模块说明里的实测数字。
    """

    class _Msg:
        def __init__(self, role, content):
            self.role, self.content = role, content

    def test_ai_replies_are_excluded(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "EMOTION_CONTEXT_TURNS", 2)
        history = [
            self._Msg("user", "第一句"),
            self._Msg("ai", "That's wonderful news, congratulations!"),
            self._Msg("user", "第二句"),
            self._Msg("ai", "Here is a very long explanation..."),
            self._Msg("user", "第三句"),
        ]
        assert select_context_messages(history) == ["第二句", "第三句"]

    def test_only_ai_history_means_no_context(self):
        assert select_context_messages([self._Msg("ai", "hi"), self._Msg("ai", "there")]) == []

    def test_empty_user_messages_are_skipped(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "EMOTION_CONTEXT_TURNS", 2)
        history = [self._Msg("user", "有内容"), self._Msg("user", ""), self._Msg("user", None)]
        assert select_context_messages(history) == ["有内容"]
