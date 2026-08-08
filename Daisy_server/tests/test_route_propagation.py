"""
route 传递契约测试(F5)。

根因:route_logic 是 conditional entry point,其返回值只用于选分支、就地赋值不进通道,
导致 route 键从未进入 state —— tool_check 永远早退(工具能力完全失效)、
DEEP 的角色卡 addendum / 超时保护 / 专用模型选择全部静默失效。

这里锁定两件事:
1. LangGraph 语义本身(条件入口的就地赋值不持久化)——契约存在的依据;
2. 三个入口节点必须在返回 dict 中显式写入自己的 route。
"""

import ast
import asyncio
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, END

NODES_DIR = Path(__file__).resolve().parent.parent / "app" / "workflow" / "nodes"


def test_conditional_entry_inplace_assignment_does_not_persist():
    """条件入口里的就地赋值不会进入 state(F5 的根因)。"""

    class S(TypedDict):
        route: str
        x: str

    async def entry(state):
        state["route"] = "DEEP"  # 就地赋值:不进通道
        return "DEEP"            # 返回值仅用于选分支

    seen = {}

    async def deep(state):
        seen["route"] = state.get("route")
        return {"x": "done"}

    g = StateGraph(S)
    g.add_node("deep", deep)
    g.set_conditional_entry_point(entry, {"DEEP": "deep"})
    g.add_edge("deep", END)
    result = asyncio.run(g.compile().ainvoke({"x": ""}))

    assert seen["route"] is None, "若此断言失败说明 LangGraph 语义已变,契约可放宽"
    assert result.get("route") is None


def _returns_route_literal(source: str, func_name: str) -> set[str]:
    """静态解析:提取函数返回 dict 中 "route" 键的字面量值。"""
    tree = ast.parse(source)
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) or node.name != func_name:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                for k, v in zip(sub.value.keys, sub.value.values):
                    if isinstance(k, ast.Constant) and k.value == "route" and isinstance(v, ast.Constant):
                        found.add(v.value)
    return found


def test_entry_nodes_declare_their_route():
    """三个入口节点必须在返回 dict 里显式写入自己的 route。"""
    cases = [
        ("emotion.py", "analyze_emotion", "DEEP"),
        ("fast_path.py", "fast_generate", "FAST"),
        ("fast_path.py", "standard_generate", "STANDARD"),
    ]
    for filename, func, expected in cases:
        source = (NODES_DIR / filename).read_text(encoding="utf-8")
        routes = _returns_route_literal(source, func)
        assert expected in routes, (
            f"{filename}::{func} 的返回 dict 缺少 route={expected!r};"
            f" 实际找到 {routes or '无'}。缺失会导致 tool_check 早退与 DEEP 特性静默失效。"
        )
