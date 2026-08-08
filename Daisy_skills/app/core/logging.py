import contextvars
import uuid
import structlog

_trace_id_var = contextvars.ContextVar("trace_id", default=None)
_user_id_var = contextvars.ContextVar("user_id", default=None)
_session_id_var = contextvars.ContextVar("session_id", default=None)
_admin_var = contextvars.ContextVar("admin", default=False)


def init_logging(log_level: str = "INFO"):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
    )


def set_trace_context(trace_id: str | None = None, user_id: str | None = None, session_id: str | None = None, admin: bool | None = None) -> str:
    if not trace_id:
        trace_id = uuid.uuid4().hex
    _trace_id_var.set(trace_id)
    if user_id is not None:
        _user_id_var.set(user_id)
    if session_id is not None:
        _session_id_var.set(session_id)
    if admin is not None:
        _admin_var.set(admin)
    structlog.contextvars.bind_contextvars(
        trace_id=trace_id,
        user_id=user_id,
        session_id=session_id,
        admin=admin if admin is not None else _admin_var.get(),
    )
    return trace_id


def get_trace_id() -> str | None:
    return _trace_id_var.get()


def get_logger():
    return structlog.get_logger()


def clear_context():
    structlog.contextvars.clear_contextvars()
