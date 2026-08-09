"""
情感状态的接线回归。

review 时发现**两条情绪链路都是断的**,而且都完全静默 —— 日志正常、无异常、
测试全绿,只有产品体验在悄悄劣化。这类缺陷最贵,所以单独立一个文件守住。

    键                        谁读              断在哪                后果
    user:{u}:emotional_state  回复生成          从来没人写            每次都注入「Neutral (强度: 0)」
    user:{u}:last_emotion     主动关心 Track A  从来没人写            情感急救永不触发

第一条尤其糟:它不是"少了个功能",而是**持续给模型一个与事实相反的信号** ——
用户刚说完宠物去世,提示词里却写着"当前情感状态: Neutral (强度: 0)"。
对一个以情绪陪伴为核心的产品,这是直接反作用。

根因是同一个:真实情绪由 analyze 节点算出来放在图状态里,
却有人另建了一套缓存键去读,而写入端从未实现。
"""

import inspect
import os
import re

import pytest

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestGenerationUsesRealEmotion:
    """
    回复生成必须用**本轮真实分析出的**情绪,不能读那个没人写的缓存键。
    """

    def test_no_longer_reads_dead_cache_key(self):
        from app.workflow.nodes import generation

        src = inspect.getsource(generation.generate_response)
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        assert "get_emotional_state" not in code, \
            "仍在读 user:{uid}:emotional_state —— 那个键全库没有任何写入方"

    def test_reads_top_emotions_from_state(self):
        from app.workflow.nodes import generation

        src = inspect.getsource(generation.generate_response)
        assert "top_emotions" in src, \
            "没有使用 analyze 节点算出的真实情绪"

    def test_dead_api_removed_from_core(self):
        """
        留着这两个方法,下一个人还会去调它 —— 而它永远返回默认值。
        """
        src = open(os.path.join(SERVER, "app", "core", "cache.py"),
                   encoding="utf-8").read()
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        assert "def get_emotional_state" not in code
        assert "class EmotionalState" not in code

    def test_neutral_default_no_longer_injected(self):
        """
        核心回归:没有情绪数据时**不能**编一个 Neutral 出来。
        原实现靠 `if emotional_obj:` 判断,而 pydantic 模型恒为真,拦不住。
        """
        from app.workflow.nodes import generation

        src = inspect.getsource(generation.generate_response)
        # 现在的判据是列表是否为空 —— 空列表为假,能正确拦住
        assert re.search(r"top\s*=\s*state\.get\(\"top_emotions\"\)", src), \
            "情绪来源不是图状态,可能又引入了恒真的默认对象"
        assert "if top:" in src, "没有对空情绪做判断,会再次注入编造的默认值"


class TestProactiveTrackAIsWired:
    """
    主动关心的「双轨门控」里,Track A(情感急救)依赖 last_emotion。
    而 StateService.update_emotional_state **全库零调用者** ——
    双轨实际上一直是单轨,负面情绪下最该关心的场景反而从不触发。
    """

    def test_emotion_is_written_after_analysis(self):
        from app.workflow.nodes import emotion

        src = inspect.getsource(emotion.analyze_emotion)
        assert "update_emotional_state" in src, \
            "分析完情绪后没有写入用户状态 —— 情感急救轨道永远拿不到数据"

    def test_writer_and_reader_agree_on_shape(self):
        """
        写入方给的字段必须是读取方要的那几个,否则又是一次静默失效。
        Track A 读 label / score / timestamp。
        """
        from app.services.proactive import service, state

        writer = inspect.getsource(state.StateService.update_emotional_state)
        reader = inspect.getsource(service.ProactiveService.check_and_trigger)

        for field in ("label", "score", "timestamp"):
            assert f'"{field}"' in writer, f"写入方缺少字段 {field}"
        for field in ("label", "score", "timestamp"):
            assert f'"{field}"' in reader or f"'{field}'" in reader, \
                f"读取方不再使用 {field},契约已漂移"

    def test_write_failure_does_not_break_conversation(self):
        """
        情绪留痕是增强项,失败绝不能影响本轮对话 ——
        analyze 是 essential 节点,抛异常会中断整条链路。
        """
        import ast
        import textwrap

        from app.workflow.nodes import emotion

        # 用 AST 判断"这行调用是否处在某个 try 的 body 里",
        # 比按文本位置猜 try/except 的距离可靠得多(第一版就是那么写错的)。
        tree = ast.parse(textwrap.dedent(inspect.getsource(emotion.analyze_emotion)))

        def calls_writer(node) -> bool:
            return any(
                isinstance(n, ast.Attribute) and n.attr == "update_emotional_state"
                for n in ast.walk(node)
            )

        guarded = any(
            calls_writer(node) and node.handlers
            for node in ast.walk(tree)
            if isinstance(node, ast.Try)
        )
        assert guarded, "情绪写入不在 try/except 内 —— 缓存抖动会中断整轮对话"


class TestNoDuplicateEmotionConcepts:
    """
    曾经有**两套同名不同义**的"情感状态":
      - RedisClient.get_emotional_state → EmotionalState(current_mood/intensity)
      - StateService.get_emotional_state → dict(label/score/summary)
    同名、不同键、不同结构、各自的读者。这种重复本身就是缺陷温床。
    """

    def test_only_one_emotional_state_accessor(self):
        import subprocess

        out = subprocess.run(
            ["grep", "-rn", "def get_emotional_state", os.path.join(SERVER, "app")],
            capture_output=True, text=True).stdout.strip()
        assert len(out.splitlines()) == 1, \
            f"存在多个 get_emotional_state 实现,会再次分叉:\n{out}"
