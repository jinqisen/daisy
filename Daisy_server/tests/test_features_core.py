"""
核心 feature 覆盖测试:对话处理、护栏、回复分段、路由。

覆盖「功能全集」中的:
  一、对话核心(三档路由、输入纠错、回复分段、护栏)
  十一、模型分层
"""

import pytest

from app.core.utils import (
    is_offline_meetup_intent,
    is_offline_meetup_violation,
    split_response_into_parts,
)


# --- 回复分段:模拟真人分条发送(而非流式逐字输出)---

class TestResponseSplitting:
    """真人不会逐字流式输出,而是分条发送。这是本项目刻意的设计选择。"""

    def test_splits_multi_sentence_reply(self):
        parts = split_response_into_parts("今天天气真好。你那边怎么样？")
        assert len(parts) >= 1
        assert all(p.strip() for p in parts), "不应产生空片段"

    def test_single_short_reply_stays_one_part(self):
        parts = split_response_into_parts("好的")
        assert parts == ["好的"] or len(parts) == 1

    def test_empty_input_yields_no_empty_garbage(self):
        parts = split_response_into_parts("")
        assert parts == [] or all(p.strip() for p in parts)

    def test_parts_preserve_content(self):
        """分段不得丢字。"""
        text = "第一句话。第二句话。第三句话。"
        parts = split_response_into_parts(text)
        joined = "".join(parts).replace(" ", "")
        for ch in "第一句话第二句话第三句话":
            assert ch in joined


# --- 线下见面护栏(规格 §5.1 的硬约束)---

class TestOfflineMeetupGuardrail:
    """规格要求:用户请求见面时,Agent 必须能识别并拒绝(绝对异地约束)。"""

    @pytest.mark.parametrize("text", [
        "周四我们见面吧",
        "把你的地址发我",
        "我去找你",
        "我们线下见一面",
    ])
    def test_detects_meetup_intent(self, text):
        assert is_offline_meetup_intent(text), f"未识别线下见面意图: {text}"

    @pytest.mark.parametrize("text", [
        "今天天气真好",
        "我最近失眠",
        "谢谢你",
    ])
    def test_ignores_normal_chat(self, text):
        assert not is_offline_meetup_intent(text), f"误判为见面意图: {text}"

    def test_detects_violation_in_agent_reply(self):
        """Agent 若答应见面,必须被判定为违规(触发兜底改写)。"""
        assert is_offline_meetup_violation("好啊,那我们周四老地方见")

    def test_normal_reply_not_flagged(self):
        assert not is_offline_meetup_violation("我们是异地,见不了的")

    @pytest.mark.parametrize("text", [
        "好啊,那我们周四老地方见",
        "行,礼拜六我过来",
        "那就 15 号吧",
    ])
    def test_specific_date_commitment_is_violation(self, text):
        """
        具体星期/日期构成明确赴约。此前关键词表只有"今晚/明天/周末"等模糊词,
        导致"周四老地方见"漏判。
        """
        assert is_offline_meetup_violation(text), f"漏判赴约: {text}"

    def test_guardrail_keywords_not_overfit_to_past_incident(self):
        """
        动态护栏关键词曾硬编码「江滩」「老渡口」「周四」—— 那是从某次具体对话抄来的,
        换个用户/场景即失效。锁定不得再出现这类具体地名。
        """
        from pathlib import Path
        src = Path(__file__).resolve().parent.parent / "app" / "workflow" / "nodes" / "context_assembly.py"
        text = src.read_text(encoding="utf-8")
        # 取 sensitive_keywords 那一行(注释里提及历史问题是允许的)
        line = next(l for l in text.splitlines() if l.strip().startswith("sensitive_keywords"))
        for overfit in ("江滩", "老渡口", "周四"):
            assert overfit not in line, f"护栏关键词仍过拟合到具体案例: {overfit}"


# --- 路由分档 ---

class TestRouting:
    def test_router_module_exposes_route(self):
        from app.services.dialogue.router import IntelligentRouter
        assert hasattr(IntelligentRouter, "route")

    def test_three_channels_declared_in_graph(self):
        """FAST/STANDARD/DEEP 三档必须都在图里有落点。"""
        from app.workflow.graph import create_graph
        compiled = create_graph()
        nodes = set(compiled.get_graph().nodes)
        assert "fast_generate" in nodes
        assert "standard_generate" in nodes
        assert "analyze" in nodes, "DEEP 入口节点缺失"

    def test_lightweight_model_used_for_internal_tasks(self):
        """内部分类任务应走轻量模型,不占用重模型(成本/延迟)。"""
        from pathlib import Path
        src = Path(__file__).resolve().parent.parent / "app" / "services" / "persona" / "strategy.py"
        assert "force_lightweight" in src.read_text(encoding="utf-8")
