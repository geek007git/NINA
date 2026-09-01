"""Logging configuration.

Voice agents run unattended, so logs are the only forensics available.  Text
format is used for local development; JSON is used in containers where a log
shipper is parsing stdout.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_LOGGER_NAME = "nina"

# Third-party loggers that are chatty at DEBUG and rarely useful.
_NOISY_LOGGERS = ("httpx", "httpcore", "websockets", "urllib3", "asyncio")

# Attributes present on every LogRecord; anything else was added by the caller
# via `extra=` and is worth emitting as a structured field.
_STANDARD_RECORD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Render records as single-line JSON, including any ``extra=`` fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO", fmt: str = "text") -> logging.Logger:
    """Install a single stderr handler on the ``nina`` logger and return it.

    Idempotent: calling it twice will not double up handlers, which matters
    because LiveKit's CLI may re-enter the process setup path.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level.upper())
    # Let the root logger keep its own handlers for library output, but do not
    # duplicate our records into them.
    logger.propagate = False

    for existing in list(logger.handlers):
        logger.removeHandler(existing)

    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    logger.addHandler(handler)

    if level.upper() == "DEBUG":
        for name in _NOISY_LOGGERS:
            logging.getLogger(name).setLevel(logging.INFO)

    return logger


def get_logger(suffix: str | None = None) -> logging.Logger:
    """Return the ``nina`` logger, or a named child of it."""
    return logging.getLogger(_LOGGER_NAME if not suffix else f"{_LOGGER_NAME}.{suffix}")
