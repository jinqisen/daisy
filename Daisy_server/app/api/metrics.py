"""
SLO 指标接口。

数据来自 `metric_events` 表,**不再是 Redis 计数器**:那些是累计量
(总调用数/总 token/总成本),而嵌入模式的 Redis 是进程内 fakeredis、重启即空 ——
面板原先永远只反映"本次运行",成本统计基本没有意义。

响应结构与改造前**完全一致**,前端无需改动。
"""

import asyncio
from typing import Any, Dict

from fastapi import APIRouter

from ..core.config import settings
from ..core.metrics import (
    E2E_HIST_THRESHOLDS_MS,
    ROUTER_HIST_THRESHOLDS_MS,
    hist_percentiles,
)

router = APIRouter()


@router.get("/slo")
async def get_slo_metrics() -> Dict[str, Any]:
    from ..services.system.metrics_store import summarize

    # 聚合是同步的 SQL 扫描,丢到线程池,别占着事件循环
    loop = asyncio.get_running_loop()
    agg = await loop.run_in_executor(None, summarize)

    r = agg["router"]
    e = agg["e2e"]
    l = agg["llm"]

    router_count = r["count"]
    e2e_count = e["count"]
    llm_count = l["count"]

    fast_hit_rate = (r["by_route"].get("FAST", 0) / router_count) if router_count else 0.0

    return {
        "router": {
            "count": router_count,
            "avg_ms": (r["sum_ms"] / router_count) if router_count else 0.0,
            "by_route": r["by_route"],
            "hist": r["hist"],
            **hist_percentiles(r["hist"], ROUTER_HIST_THRESHOLDS_MS, [0.5, 0.9, 0.95]),
        },
        "e2e": {
            "count": e2e_count,
            "avg_ms": (e["sum_ms"] / e2e_count) if e2e_count else 0.0,
            "by_route": e["by_route"],
            "hist": e["hist"],
            **hist_percentiles(e["hist"], E2E_HIST_THRESHOLDS_MS, [0.5, 0.9, 0.95]),
        },
        "llm": {
            "count": llm_count,
            "avg_in_tokens": (l["sum_in"] / llm_count) if llm_count else 0.0,
            "avg_out_tokens": (l["sum_out"] / llm_count) if llm_count else 0.0,
            "sum_in_tokens": l["sum_in"],
            "sum_out_tokens": l["sum_out"],
            "sum_cost_usd": l["sum_cost"],
            "by_route": l["by_route"],
            "by_model": l["by_model"],
            "est_chars_per_token": settings.TOKEN_EST_CHARS_PER_TOKEN,
            "est_cost_per_1k_input_usd": settings.EST_COST_PER_1K_INPUT_USD,
            "est_cost_per_1k_output_usd": settings.EST_COST_PER_1K_OUTPUT_USD,
        },
        "fast_hit_rate": fast_hit_rate,
    }
