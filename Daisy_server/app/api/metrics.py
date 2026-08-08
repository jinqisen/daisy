from fastapi import APIRouter, HTTPException
from typing import Any, Dict

from ..core.redis import redis_client
from ..core.metrics import hist_percentiles, ROUTER_HIST_THRESHOLDS_MS, E2E_HIST_THRESHOLDS_MS
from ..core.config import settings


router = APIRouter()


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


@router.get("/slo")
async def get_slo_metrics() -> Dict[str, Any]:
    if not redis_client.enabled:
        await redis_client.connect()

    if not redis_client.enabled or not redis_client.redis:
        raise HTTPException(status_code=503, detail="Redis not available")

    r = redis_client.redis

    router_count = _to_int(await r.get("metrics:router:count"))
    router_sum_ms = _to_int(await r.get("metrics:router:sum_ms"))
    router_by_route = await r.hgetall("metrics:router:by_route")
    router_hist = await r.hgetall("metrics:router:hist")

    e2e_count = _to_int(await r.get("metrics:e2e:count"))
    e2e_sum_ms = _to_int(await r.get("metrics:e2e:sum_ms"))
    e2e_by_route = await r.hgetall("metrics:e2e:by_route")
    e2e_hist = await r.hgetall("metrics:e2e:hist")

    router_by_route_int = {k: _to_int(v) for k, v in (router_by_route or {}).items()}
    e2e_by_route_int = {k: _to_int(v) for k, v in (e2e_by_route or {}).items()}
    router_hist_int = {k: _to_int(v) for k, v in (router_hist or {}).items()}
    e2e_hist_int = {k: _to_int(v) for k, v in (e2e_hist or {}).items()}

    fast_hits = router_by_route_int.get("FAST", 0)
    fast_hit_rate = (fast_hits / router_count) if router_count > 0 else 0.0

    router_percentiles = hist_percentiles(router_hist_int, ROUTER_HIST_THRESHOLDS_MS, [0.5, 0.9, 0.95])
    e2e_percentiles = hist_percentiles(e2e_hist_int, E2E_HIST_THRESHOLDS_MS, [0.5, 0.9, 0.95])

    llm_count = _to_int(await r.get("metrics:llm:count"))
    llm_sum_in = _to_int(await r.get("metrics:llm:sum_in_tokens"))
    llm_sum_out = _to_int(await r.get("metrics:llm:sum_out_tokens"))
    llm_sum_cost = _to_float(await r.get("metrics:llm:sum_cost_usd"))
    llm_by_route = await r.hgetall("metrics:llm:by_route")
    llm_by_model = await r.hgetall("metrics:llm:by_model")
    llm_by_route_int = {k: _to_int(v) for k, v in (llm_by_route or {}).items()}
    llm_by_model_int = {k: _to_int(v) for k, v in (llm_by_model or {}).items()}

    return {
        "router": {
            "count": router_count,
            "avg_ms": (router_sum_ms / router_count) if router_count > 0 else 0.0,
            "by_route": router_by_route_int,
            "hist": router_hist_int,
            **router_percentiles,
        },
        "e2e": {
            "count": e2e_count,
            "avg_ms": (e2e_sum_ms / e2e_count) if e2e_count > 0 else 0.0,
            "by_route": e2e_by_route_int,
            "hist": e2e_hist_int,
            **e2e_percentiles,
        },
        "llm": {
            "count": llm_count,
            "avg_in_tokens": (llm_sum_in / llm_count) if llm_count > 0 else 0.0,
            "avg_out_tokens": (llm_sum_out / llm_count) if llm_count > 0 else 0.0,
            "sum_in_tokens": llm_sum_in,
            "sum_out_tokens": llm_sum_out,
            "sum_cost_usd": llm_sum_cost,
            "by_route": llm_by_route_int,
            "by_model": llm_by_model_int,
            "est_chars_per_token": settings.TOKEN_EST_CHARS_PER_TOKEN,
            "est_cost_per_1k_input_usd": settings.EST_COST_PER_1K_INPUT_USD,
            "est_cost_per_1k_output_usd": settings.EST_COST_PER_1K_OUTPUT_USD,
        },
        "fast_hit_rate": fast_hit_rate,
    }
