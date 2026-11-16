"""LangSmith tracing bootstrap for LangChain / LangGraph runs."""

from __future__ import annotations

import logging
import os
from typing import Any

from safar_api.config import settings

logger = logging.getLogger(__name__)

_CONFIGURED = False


def configure_langsmith() -> bool:
    """Enable LangSmith from settings. Safe to call multiple times. Returns True if on."""
    global _CONFIGURED
    if _CONFIGURED:
        return bool(os.environ.get("LANGSMITH_TRACING", "").lower() in ("1", "true", "yes"))

    _CONFIGURED = True
    api_key = (settings.langsmith_api_key or "").strip()
    project = (settings.langsmith_project or "trip planner").strip().strip('"').strip("'")
    endpoint = (settings.langsmith_endpoint or "https://api.smith.langchain.com").strip()
    enabled = settings.langsmith_tracing and bool(api_key)

    if not enabled:
        # Ensure we do not accidentally inherit a half-set shell env.
        os.environ.pop("LANGSMITH_TRACING", None)
        os.environ.pop("LANGCHAIN_TRACING_V2", None)
        if not api_key and settings.langsmith_tracing:
            logger.warning("LangSmith tracing requested but LANGSMITH_API_KEY is empty")
        else:
            logger.info("LangSmith tracing disabled")
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = api_key
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ["LANGSMITH_PROJECT"] = project
    os.environ["LANGCHAIN_PROJECT"] = project
    os.environ["LANGSMITH_ENDPOINT"] = endpoint

    logger.info("LangSmith tracing enabled | project=%s endpoint=%s", project, endpoint)
    return True


def langsmith_run_config(
    thread_id: str,
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Graph invoke/stream config with LangSmith tags + session metadata."""
    metadata: dict[str, Any] = {"thread_id": thread_id}
    if extra_metadata:
        metadata.update(extra_metadata)

    return {
        "configurable": {"thread_id": thread_id},
        "run_name": "safar",
        "tags": ["safar"],
        "metadata": metadata,
    }
