"""
LLM 调用轨迹的落库出口(可插拔)。

为什么要这层间接:LLM 客户端是基础设施(core),而"轨迹存到哪张表"是业务/持久化
关注点。core 直接 import LLMTraceDB 会让最底层反过来依赖 models,形成循环 ——
这类反向依赖正是"改一处从别处回弹"的来源。

做法与 job_registry 一致:core 只声明"有一个 sink 可以收轨迹",由上层在启动时注入
真正的实现。未注入时静默丢弃 —— 记录轨迹是可观测性,绝不该因它失败而影响对话。
"""

from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger()

_sink: Optional[Callable[..., Any]] = None


def set_trace_sink(fn: Callable[..., Any]) -> None:
    """注入轨迹落库实现(见 services/trace_store.py)。"""
    global _sink
    _sink = fn


def write_llm_trace(**fields: Any) -> None:
    """记录一次 LLM 调用。任何失败都吞掉 —— 可观测性不能反过来拖垮主链路。"""
    if _sink is None:
        return
    try:
        _sink(**fields)
    except Exception as e:
        logger.error(f"Failed to log LLM trace: {e}")
