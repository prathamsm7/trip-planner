"""Emit tool progress via LangGraph stream_writer (runtime.stream_writer)."""

from __future__ import annotations

from typing import Any


def emit_progress(
    runtime: Any,
    *,
    tool: str,
    status: str,
    detail: str = "",
    label: str | None = None,
) -> None:
    """Write a custom stream event from inside a tool.

    Consumed by stream_mode including \"custom\". Safe no-op if writer missing.
    status: start | progress | complete
    """
    writer = getattr(runtime, "stream_writer", None) if runtime is not None else None
    if writer is None:
        return
    try:
        writer(
            {
                "tool": tool,
                "status": status,
                "detail": detail,
                "label": label or tool,
                "tool_call_id": getattr(runtime, "tool_call_id", None),
            }
        )
    except Exception:
        # Never fail the tool because progress streaming failed.
        return
