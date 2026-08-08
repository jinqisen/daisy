"""
规格设计 vs 实际实现的差距清单(可执行版)。

来源:Daisy_server/docs/AI伴侣统一系统技术规格书 (v3.1 - Final).md

这里把"设计了但没落盘"的功能写成测试:
  - 已修复的 → 正常断言,防止回退
  - 仍未实现的 → xfail(strict=False),使差距在测试报告里持续可见,
    而不是散落在文档里被遗忘。某项实现后测试会变 XPASS,提示可以移除标记。
"""

import json
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parent.parent
CARD_PATH = SERVER / "assets" / "character_cards" / "default_character_card.json"


def _card():
    from app.agents.daisy.character_card import CharacterCard
    return CharacterCard(**json.loads(CARD_PATH.read_text(encoding="utf-8")))


def _addendum(route: str, stage: str = "trust", user_input: str = "你好"):
    from app.services.persona.character_card import build_channel_prompt_addendum
    return build_channel_prompt_addendum(_card(), route, user_input, stage)


# ---------------------------------------------------------------------------
# 规格 §4.2 角色卡分层加载
# ---------------------------------------------------------------------------

class TestSpecLayeredCardLoading:
    """规格明确规定了每条通道该加载角色卡的哪些模块。"""

    def test_fast_channel_loads_quirks_and_phrases(self):
        """规格:快速通道加载 language_style.quirks + common_phrases。"""
        card = _card()
        text = _addendum("FAST")
        quirks = card.language_style.quirks or []
        assert quirks, "测试前提:默认角色卡应含 quirks"
        assert any(q in text for q in quirks), "FAST 通道未加载 quirks(规格 §4.2)"

    def test_standard_channel_loads_dialogue_examples(self):
        """规格:标准通道加载 1-2 个 dialogue_examples。"""
        card = _card()
        text = _addendum("STANDARD")
        examples = card.dialogue_examples or []
        assert examples, "测试前提:默认角色卡应含 dialogue_examples"
        hit = any(
            (getattr(ex, "user", None) or "") in text or (getattr(ex, "assistant", None) or "") in text
            for ex in examples
        )
        assert hit, "STANDARD 通道未加载 dialogue_examples(规格 §4.2)"

    def test_standard_channel_uses_relationship_stage(self):
        """
        规格:标准通道加载"当前关系等级"的 relationship_dynamics。
        infer_relationship_stage 已算出阶段,但此前未被用于选取对应等级。
        """
        low = _addendum("STANDARD", stage="acquaintance")
        high = _addendum("STANDARD", stage="bond")
        assert low != high, "不同关系阶段应加载不同的 relationship_dynamics(规格 §4.2)"

    def test_deep_channel_loads_inner_monologue_patterns(self):
        """规格 §5.1:深度通道需含 inner_monologue_patterns 引导 ReAct 思考。"""
        card = _card()
        text = _addendum("DEEP")
        patterns = card.inner_monologue_patterns or []
        assert patterns, "测试前提:默认角色卡应含 inner_monologue_patterns"
        # 比对独白内容本身(而非 Pydantic 对象的 repr)
        assert any(p.pattern[:12] in text for p in patterns), \
            "DEEP 通道未加载 inner_monologue_patterns(规格 §5.1)"

    def test_deep_channel_loads_constraints(self):
        """规格 §5.1:constraints(如绝对异地)必须作为硬规则进入深度通道。"""
        text = _addendum("DEEP")
        assert "异地" in text or "constraint" in text.lower() or "约束" in text, \
            "DEEP 通道未加载 constraints(规格 §5.1)"


# ---------------------------------------------------------------------------
# 规格 §5.2 Reflexion 反哺闭环 —— 设计要求但未实现
# ---------------------------------------------------------------------------

class TestSpecReflexionFeedback:

    @pytest.mark.xfail(reason="规格 §5.2 设计但未实现:Reflexion 不回写路由规则", strict=False)
    def test_reflexion_optimizes_router_rules(self):
        """规格:系统应能自动发现并修正路由错误。"""
        import app.services.learning.reflexion.service as svc
        src = Path(svc.__file__).read_text(encoding="utf-8")
        assert "router" in src.lower(), "Reflexion 未涉及路由规则优化"

    @pytest.mark.xfail(reason="规格 §5.2 设计但未实现:不会向角色卡补充对话示例", strict=False)
    def test_reflexion_enriches_dialogue_examples(self):
        """规格:角色卡的对话示例库应随时间推移而丰富。"""
        import app.services.learning.reflexion.service as svc
        src = Path(svc.__file__).read_text(encoding="utf-8")
        assert "dialogue_examples" in src, "Reflexion 未回写 dialogue_examples"


# ---------------------------------------------------------------------------
# C 类:功能存在但实际不工作
# ---------------------------------------------------------------------------

class TestKnownBrokenFeatures:

    @pytest.mark.xfail(reason="RL 策略网络未有效训练:不同输入产出相同权重", strict=False)
    def test_rl_strategy_differentiates_inputs(self):
        """RL 策略对不同情绪状态应给出不同权重,否则等同于常量。"""
        import asyncio
        from app.services.persona.strategy import RLStrategy

        happy = {"user_id": 1, "user_input": "今天真开心",
                 "ekman_scores": {"joy": 0.9, "sadness": 0.0}, "emotion_scores": {}, "top_emotions": []}
        sad = {"user_id": 1, "user_input": "我很难过",
               "ekman_scores": {"joy": 0.0, "sadness": 0.9}, "emotion_scores": {}, "top_emotions": []}

        s = RLStrategy()
        a = asyncio.run(s.select_personality(happy)).personality_weights
        b = asyncio.run(s.select_personality(sad)).personality_weights
        assert a != b, "RL 对截然不同的情绪给出了相同权重(未有效训练)"

    def test_multi_agent_service_is_wired_as_fallback(self):
        """
        更正记录:此项曾被误标为"未接入的死代码"—— 当时只在 app/workflow/ 下 grep,
        而实际调用点在 services/generation.py。它是人格融合引擎(fusion_engine)
        抛异常时的降级路径,属有意的容错设计,不是遗留代码。
        """
        src = (SERVER / "app" / "services" / "dialogue" / "generation.py").read_text(encoding="utf-8")
        assert "multi_agent_service.consult_personalities_async" in src, \
            "MultiAgentService 降级路径丢失 —— fusion 引擎故障时内心独白将完全不可用"
        assert "falling back to MultiAgentService" in src, "降级路径缺少可观测日志"

    def test_fusion_engine_imports_core_settings(self):
        """
        回归:融合引擎曾误写 `from .config import settings`。
        services/ 下并不存在 config.py，打包运行时会直接报
        `No module named 'app.services.config'`，整条融合路径被迫降级。

        断言只看**导入目标**,不锁定相对/绝对写法 —— 原先写死
        `from ..core.config import settings`,services 拆分到域子包后
        相对层级必然变化,那样的断言测的是文件位置而非缺陷本身。
        """
        src = (SERVER / "app" / "services" / "persona" / "fusion.py").read_text(encoding="utf-8")
        assert "core.config import settings" in src, \
            "Fusion 引擎未从 core.config 读取 settings —— 打包版会报错降级"
        assert "services.config import" not in src, \
            "又出现了不存在的 services.config —— 正是当初那个缺陷"


# ---------------------------------------------------------------------------
# 规格 §4.0 性能目标(记录现状,不阻塞)
# ---------------------------------------------------------------------------

class TestSpecPerformanceTargets:

    @pytest.mark.xfail(reason="规格目标 80% 对话 3 秒内;实测 FAST 5-6s / DEEP 30-40s", strict=False)
    def test_documented_latency_target_met(self):
        """
        性能目标属实测范畴,此处仅作为差距提醒占位。
        注:流式输出方案已被产品否决(与真人分条回复习惯不符),
        改善方向应为模型/链路优化,而非逐字流式。
        """
        pytest.fail("性能目标未达成:需模型或链路层面优化")
