"""
AgentState 合并契约测试(深改点 #1)。

三层保障:
1. 记录 LangGraph 语义:同一 superstep 并行双写无 reducer 的键会抛 InvalidUpdateError
   (这是契约存在的原因,防止未来有人认为"覆盖一下没关系")。
2. 上游任务节点(analyze_style / agent_thoughts)依赖缺失时返回 {},
   不写单写者键 _skip_generation。
3. generate 的汇聚检查兜底:依赖缺失时正确返回 _skip_generation=True。
"""

import asyncio
from typing import TypedDict

import pytest
from langgraph.graph import StateGraph, END
from langgraph.errors import InvalidUpdateError

from app.workflow.nodes.context_tasks import analyze_style, agent_thoughts
from app.workflow.nodes.generation import generate_response


def test_langgraph_concurrent_same_key_write_raises():
    """并行双写同一个无 reducer 键 → InvalidUpdateError(契约的依据)"""

    class S(TypedDict):
        x: bool
        y: str

    async def a(state): return {"y": "a"}
    async def b(state): return {"x": True}
    async def c(state): return {"x": True}
    async def d(state): return {}

    g = StateGraph(S)
    for name, fn in [("a", a), ("b", b), ("c", c), ("d", d)]:
        g.add_node(name, fn)
    g.set_entry_point("a")
    g.add_edge("a", "b")
    g.add_edge("a", "c")
    g.add_edge("b", "d")
    g.add_edge("c", "d")
    g.add_edge("d", END)
    app = g.compile()

    with pytest.raises(InvalidUpdateError):
        asyncio.run(app.ainvoke({"y": ""}))


def test_analyze_style_missing_deps_returns_empty_update():
    """analyze_style 缺 love_style_weights → 返回 {},不得写 _skip_generation"""
    result = asyncio.run(analyze_style({"user_id": 1, "user_input": "hi"}))
    assert result == {}, f"应返回空更新,实际: {result}"


def test_agent_thoughts_missing_deps_returns_empty_update():
    """agent_thoughts 缺依赖 → 返回 {},不得写 _skip_generation"""
    result = asyncio.run(agent_thoughts({"user_id": 1, "user_input": "hi"}))
    assert result == {}, f"应返回空更新,实际: {result}"


def test_generate_missing_deps_sets_skip_flag():
    """generate 汇聚检查兜底:依赖缺失 → _skip_generation=True(唯一合法写者)"""
    result = asyncio.run(generate_response({"user_id": 1, "user_input": "hi"}))
    assert result == {"_skip_generation": True}
