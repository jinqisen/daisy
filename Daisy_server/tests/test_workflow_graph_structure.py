"""
工作流图结构回归测试(#6-min 安全网的一部分)。

锁定主图的节点集合与关键边,防止 generation.py 拆分等重构无意间改变 DAG 形状。
只做结构断言,不执行任何节点。
"""

from app.workflow.graph import create_graph

EXPECTED_NODES = {
    "analyze",
    "retrieve",
    "analyze_communication_style",
    "summarize_topic",
    "ensure_portrait",
    "analyze_style",
    "agent_thoughts",
    "generate",
    "save",
    "fast_generate",
    "standard_generate",
    "tool_check",
}

# analyze 之后的五路并行 fan-out
EXPECTED_FANOUT_FROM_ANALYZE = {
    "retrieve",
    "analyze_communication_style",
    "summarize_topic",
    "ensure_portrait",
    "tool_check",
}

# 汇聚进 generate 的入边来源
EXPECTED_INBOUND_TO_GENERATE = {
    "analyze_style",
    "agent_thoughts",
    "retrieve",
    "tool_check",
}


def _edges(compiled):
    return {(e.source, e.target) for e in compiled.get_graph().edges}


def test_graph_compiles_and_has_expected_nodes():
    compiled = create_graph()
    nodes = set(compiled.get_graph().nodes)
    # get_graph() 会包含 __start__/__end__ 虚拟节点,只断言业务节点是超集关系
    missing = EXPECTED_NODES - nodes
    assert not missing, f"缺少节点: {missing}"


def test_parallel_fanout_from_analyze():
    edges = _edges(create_graph())
    fanout = {t for (s, t) in edges if s == "analyze"}
    assert EXPECTED_FANOUT_FROM_ANALYZE <= fanout, (
        f"analyze 的并行分支缺失: {EXPECTED_FANOUT_FROM_ANALYZE - fanout}"
    )


def test_convergence_into_generate():
    edges = _edges(create_graph())
    inbound = {s for (s, t) in edges if t == "generate"}
    assert EXPECTED_INBOUND_TO_GENERATE <= inbound, (
        f"generate 的汇聚入边缺失: {EXPECTED_INBOUND_TO_GENERATE - inbound}"
    )


def test_fast_and_standard_paths_reach_save():
    edges = _edges(create_graph())
    assert ("fast_generate", "save") in edges
    assert ("standard_generate", "save") in edges
