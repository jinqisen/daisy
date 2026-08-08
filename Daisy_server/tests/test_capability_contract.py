"""
工作流能力分级契约的回归。

真实事故:用户没配**可选**的搜索密钥 → `tool_check` 抛异常 → 异常打死整个
chat_task → 消息永久卡在 pending → 之后每次发送都重放它。
一个锦上添花的功能,让用户完全说不了话。

根因不是某处 try/except 写漏,而是**没有契约** —— 没人规定哪些节点是对话的必要
条件、哪些只是增强。缺了契约,错误处理靠每个作者当时的判断,迟早会漏。

这里强制两件事:每个进图的节点都必须声明等级;增强节点失败必须降级不中断。
"""

import asyncio

import pytest

from app.workflow.capability import (
    Capability,
    capability_of,
    declared_capabilities,
    enhancement,
    essential,
)


class TestEveryGraphNodeDeclaresLevel:
    """新加节点忘了声明等级,直接失败 —— 这正是上次漏掉的那一步。"""

    GRAPH_NODES = [
        "analyze_emotion", "retrieve_memory", "analyze_communication_style",
        "summarize_topic", "ensure_portrait", "analyze_style", "agent_thoughts",
        "generate_response", "save_memory_and_log",
        "fast_generate", "standard_generate", "tool_check",
    ]

    def test_all_nodes_declared(self):
        import app.workflow.graph  # noqa: F401  触发节点模块导入与声明

        declared = declared_capabilities()
        missing = [n for n in self.GRAPH_NODES if n not in declared]
        assert not missing, (
            f"这些节点未声明能力等级:{missing}。"
            f"未声明意味着没人想过它失败时该中断还是降级 —— 上次就是这么出的事故。"
        )

    def test_conversation_critical_nodes_are_essential(self):
        import app.workflow.graph  # noqa: F401

        for name in ("analyze_emotion", "generate_response", "save_memory_and_log",
                     "fast_generate", "standard_generate"):
            assert capability_of(name) == Capability.ESSENTIAL, \
                f"{name} 是对话的必要环节,不该标为增强"

    def test_optional_enrichments_are_enhancement(self):
        import app.workflow.graph  # noqa: F401

        for name in ("tool_check", "retrieve_memory", "summarize_topic",
                     "ensure_portrait", "analyze_style", "agent_thoughts",
                     "analyze_communication_style"):
            assert capability_of(name) == Capability.ENHANCEMENT, \
                f"{name} 只是增强,失败不该中断对话"


class TestEnhancementActuallyDegrades:

    def test_exception_becomes_fallback(self):
        @enhancement(fallback={"tool_results": {}})
        async def boom(state):
            raise RuntimeError("搜索密钥没配")

        out = asyncio.run(boom({}))
        assert out == {"tool_results": {}}, "增强节点异常没有被降级为兜底值"

    def test_fallback_writes_expected_keys(self):
        """
        兜底必须写出下游在等的键。悄悄返回空 dict 会让汇聚节点一直等 ——
        那是另一种形式的中断。
        """
        @enhancement(fallback={"topic_summary": ""})
        async def boom(state):
            raise RuntimeError("x")

        assert "topic_summary" in asyncio.run(boom({}))

    def test_success_path_untouched(self):
        @enhancement(fallback={"a": 0})
        async def ok(state):
            return {"a": 42}

        assert asyncio.run(ok({})) == {"a": 42}

    def test_essential_still_propagates(self):
        """必需节点失败必须向上传播,由任务层统一处理并如实告知用户。"""
        @essential
        async def boom(state):
            raise RuntimeError("LLM 挂了")

        with pytest.raises(RuntimeError):
            asyncio.run(boom({}))


class TestSearchKeyRegressionSpecifically:
    """把那次真实事故钉死:缺搜索密钥不得中断对话。"""

    def test_tool_check_is_enhancement(self):
        import app.workflow.graph  # noqa: F401

        assert capability_of("tool_check") == Capability.ENHANCEMENT

    def test_tool_check_declares_tool_results_fallback(self):
        from app.workflow.nodes.react import tool_check

        fb = getattr(tool_check, "_fallback", None)
        assert fb and "tool_results" in fb, \
            "tool_check 降级时不写 tool_results,下游汇聚会缺键"
