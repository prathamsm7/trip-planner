"""Application logging setup — formatted console logs for every error path."""

from __future__ import annotations

import logging
import sys
from typing import Any


_CONFIGURED = False

LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent root logger setup for the API process."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on reload.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(handler)

    # Keep noisy third-party libs quieter unless debugging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    _CONFIGURED = True


def log_exception(
    logger: logging.Logger,
    message: str,
    exc: BaseException | None = None,
    *,
    context: dict[str, Any] | None = None,
) -> None:
    """Log an error with optional structured context and full traceback when available."""
    extras: list[str] = []
    if context:
        for key, value in context.items():
            extras.append(f"{key}={value!r}")
    suffix = f" | {' '.join(extras)}" if extras else ""
    if exc is not None:
        logger.error("%s%s", message, suffix, exc_info=exc)
    else:
        logger.error("%s%s", message, suffix)
