from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from app.core.time_utils import utc_now_iso

SSE_PROTOCOL_VERSION = "1.0"


def build_protocol_event(
    *,
    event: str,
    data: Optional[Mapping[str, Any]] = None,
    sequence: Optional[int] = None,
    event_id: Optional[str] = None,
    legacy_type: Optional[str] = None,
    **legacy_fields: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": SSE_PROTOCOL_VERSION,
        "event": event,
        "timestamp": utc_now_iso(),
        "data": dict(data or {}),
    }
    if sequence is not None:
        payload["sequence"] = sequence
    if event_id is not None:
        payload["event_id"] = event_id
    if legacy_type is not None:
        payload["type"] = legacy_type
    payload.update(legacy_fields)
    return payload


def encode_sse_message(
    payload: Mapping[str, Any],
    *,
    event_name: str = "message",
    retry_ms: Optional[int] = None,
) -> str:
    lines: list[str] = []
    if event_name:
        lines.append(f"event: {event_name}")
    event_id = payload.get("event_id")
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if retry_ms is not None:
        lines.append(f"retry: {retry_ms}")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for line in body.splitlines() or ["{}"]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def decode_pubsub_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        parsed = json.loads(raw)
    elif isinstance(raw, Mapping):
        parsed = dict(raw)
    else:
        raise TypeError(f"Unsupported SSE payload type: {type(raw)!r}")
    if not isinstance(parsed, dict):
        raise TypeError("SSE payload must be a JSON object")
    return parsed
