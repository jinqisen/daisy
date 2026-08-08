"""
指标事件落库与聚合。

持久化知道"有哪些表",所以它住在 services;埋点方(core/llm.py、workflow)
只通过 core/metrics_sink 的接口调用它。启动时由 main.py 完成注入。

写入在**热路径**上,所以只做单行插入;聚合放在读取侧(SLO 接口),
那里一天调用不了几次,一次 SQL 聚合远比维护一堆计数器可靠 ——
计数器与事实不一致是没法自愈的,而聚合永远等于事实。
"""

import datetime
from typing import Any, Dict, Optional

import structlog

from app.core.database import SessionLocal
from app.core.metrics_sink import KIND_E2E, KIND_LLM, KIND_ROUTER, set_metrics_sink
from app.models.trace import MetricEventDB

logger = structlog.get_logger()

# 指标只保留这么多天。不设上限的话,一行一次调用会让这张表无限增长,
# 而 SLO 面板关心的本来就是近期表现。
RETENTION_DAYS = 90


def _store_metric(**fields: Any) -> None:
    with SessionLocal() as db:
        db.add(MetricEventDB(**fields))
        db.commit()


def install() -> None:
    """把落库实现注入 core。应在应用启动早期调用一次。"""
    set_metrics_sink(_store_metric)


def purge_old(days: int = RETENTION_DAYS) -> int:
    """删除过期指标。返回删除行数。"""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    with SessionLocal() as db:
        n = (db.query(MetricEventDB)
               .filter(MetricEventDB.timestamp < cutoff)
               .delete(synchronize_session=False))
        db.commit()
        return n


# ---------------------------------------------------------------------------
# 聚合(读取侧)
# ---------------------------------------------------------------------------

def _bucket(ms: Optional[int], thresholds) -> str:
    """把时延归入直方图桶。与 core/metrics.bucket_label 保持同一套阈值。"""
    from app.core.metrics import bucket_label

    return bucket_label(int(ms or 0), thresholds)


def summarize(since_days: Optional[int] = None) -> Dict[str, Any]:
    """
    聚合出 SLO 面板需要的全部数字。

    返回结构与原先基于 Redis 计数器的版本**完全一致** —— 换存储不该让前端改代码。
    """
    from app.core.metrics import E2E_HIST_THRESHOLDS_MS, ROUTER_HIST_THRESHOLDS_MS

    out: Dict[str, Any] = {
        "router": {"count": 0, "sum_ms": 0, "by_route": {}, "hist": {}},
        "e2e": {"count": 0, "sum_ms": 0, "by_route": {}, "hist": {}},
        "llm": {"count": 0, "sum_in": 0, "sum_out": 0, "sum_cost": 0.0,
                "by_route": {}, "by_model": {}},
    }

    with SessionLocal() as db:
        q = db.query(MetricEventDB)
        if since_days:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=since_days)
            q = q.filter(MetricEventDB.timestamp >= cutoff)

        for ev in q.yield_per(1000):
            if ev.kind == KIND_LLM:
                b = out["llm"]
                b["count"] += 1
                b["sum_in"] += ev.in_tokens or 0
                b["sum_out"] += ev.out_tokens or 0
                b["sum_cost"] += ev.cost_usd or 0.0
                r = ev.route or "UNKNOWN"
                b["by_route"][r] = b["by_route"].get(r, 0) + 1
                if ev.model_name:
                    b["by_model"][ev.model_name] = b["by_model"].get(ev.model_name, 0) + 1
                continue

            if ev.kind == KIND_ROUTER:
                b, thresholds = out["router"], ROUTER_HIST_THRESHOLDS_MS
            elif ev.kind == KIND_E2E:
                b, thresholds = out["e2e"], E2E_HIST_THRESHOLDS_MS
            else:
                continue

            b["count"] += 1
            b["sum_ms"] += ev.duration_ms or 0
            r = ev.route or "UNKNOWN"
            b["by_route"][r] = b["by_route"].get(r, 0) + 1
            label = _bucket(ev.duration_ms, thresholds)
            b["hist"][label] = b["hist"].get(label, 0) + 1

    return out
