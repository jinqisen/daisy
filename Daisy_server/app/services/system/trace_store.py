"""
LLM 轨迹落库实现。

持久化知道"有哪些表",所以它住在 services;core 只通过 trace_sink 的接口调用它
(见 core/trace_sink.py 的说明)。启动时由 main.py 完成注入。
"""

from app.core.database import SessionLocal
from app.core.trace_sink import set_trace_sink
from app.models.trace import LLMTraceDB


def _store_llm_trace(**fields) -> None:
    with SessionLocal() as db:
        db.add(LLMTraceDB(**fields))
        db.commit()


def install() -> None:
    """把落库实现注入 core。应在应用启动早期调用一次。"""
    set_trace_sink(_store_llm_trace)
