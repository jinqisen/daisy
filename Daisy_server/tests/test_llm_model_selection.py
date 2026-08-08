"""
LLM 模型选择测试(F3 修复的根因守卫)。

根因:user_settings.llm_model_name 一旦有值,model 即非空,
`if not model:` 会把整个 route→模型映射短路 —— 内部系统任务因此被迫使用
用户的重模型(实测 analyze_communication_style p50≈22-28s)。

force_lightweight 必须优先于 user_settings,且不得影响 by_route 统计。
"""

import ast
import inspect
from pathlib import Path

from app.core.llm import LLMService

LLM_PATH = Path(__file__).resolve().parent.parent / "app" / "core" / "llm.py"


def _model_selection_order(func_name: str) -> tuple[int, int]:
    """返回 (force_lightweight 分支行号, `if not model` 分支行号)。"""
    source = LLM_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    force_line = not_model_line = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) or node.name != func_name:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.If):
                snippet = ast.unparse(sub.test)
                if "force_lightweight" in snippet and force_line is None:
                    force_line = sub.lineno
                if snippet.strip() == "not model" and not_model_line is None:
                    not_model_line = sub.lineno
    return force_line, not_model_line


def test_force_lightweight_precedes_model_shortcircuit_in_both_paths():
    """同步与异步两条路径都必须先判 force_lightweight,再走 `if not model`。"""
    for func in ("generate_response", "generate_response_async"):
        force_line, not_model_line = _model_selection_order(func)
        assert force_line is not None, f"{func} 缺少 force_lightweight 分支"
        assert not_model_line is not None, f"{func} 缺少 `if not model` 分支"
        assert force_line < not_model_line, (
            f"{func}: force_lightweight(行{force_line}) 必须在 `if not model`(行{not_model_line}) 之前,"
            f"否则用户设置了 llm_model_name 时会被短路"
        )


def test_internal_json_tasks_declare_force_lightweight():
    """内部分类任务必须声明 force_lightweight,否则会退回用户重模型。"""
    strategy_src = (Path(__file__).resolve().parent.parent / "app" / "services" / "persona" / "strategy.py").read_text(encoding="utf-8")
    assert strategy_src.count("force_lightweight") >= 2, (
        "strategy_service 的同步与异步两条调用路径都应声明 force_lightweight"
    )


def test_force_lightweight_does_not_pollute_route_metric():
    """
    force_lightweight 不应写成 route="FAST" —— 那会让 metrics:llm:by_route
    把 DEEP 路径的子任务统计成 FAST,污染路由分布。
    """
    strategy_src = (Path(__file__).resolve().parent.parent / "app" / "services" / "persona" / "strategy.py").read_text(encoding="utf-8")
    assert '"route": "FAST"' not in strategy_src, (
        "内部任务不得用 route 伪装成 FAST,应使用 force_lightweight"
    )
