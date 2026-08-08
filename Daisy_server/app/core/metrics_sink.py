"""
指标事件的落库出口(可插拔)。

与 trace_sink 同样的理由:埋点发生在 core(LLM 客户端)和 workflow(路由/端到端),
而"指标存到哪张表"是持久化关注点。core 直接 import 模型会让最底层反过来依赖
models,形成循环。

为什么要落库,而不是继续只累加在 Redis 里:
嵌入模式的缓存是**进程内的,重启即空**,而这些是**累计量**
(总调用数、总 token、总成本)。原先每次重启归零,SLO 面板永远只反映
"本次运行",成本统计基本没有意义。累计量是长期事实,属于 SQLite。

失败一律吞掉 —— 可观测性绝不能反过来拖垮主链路。
"""

from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger()

_sink: Optional[Callable[..., Any]] = None

# 指标事件的三种来源
KIND_LLM = "llm"        # 一次 LLM 调用
KIND_ROUTER = "router"  # 一次路由决策
KIND_E2E = "e2e"        # 一轮端到端对话


def set_metrics_sink(fn: Callable[..., Any]) -> None:
    """注入指标落库实现(见 services/system/metrics_store.py)。"""
    global _sink
    _sink = fn


def record_metric(**fields: Any) -> None:
    """
    记录一个指标事件。未注入 sink 时静默丢弃。

    调用方在**热路径**上,所以这里只做入队/写入,不做聚合 ——
    聚合放在读取侧(SLO 接口),那里一天也调用不了几次。
    """
    if _sink is None:
        return
    try:
        _sink(**fields)
    except Exception as e:
        logger.error(f"Failed to record metric: {e}")
