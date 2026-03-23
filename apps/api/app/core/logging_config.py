"""
Centralized logging configuration for Hunter888 API.

- Development: human-readable text format with colors
- Production: JSON format for log aggregation (ELK, Loki, CloudWatch)

Usage: call `setup_logging()` once at app startup (in main.py).
All existing `logging.getLogger(...)` calls continue to work.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for production.

    Outputs one JSON object per line, compatible with ELK, Loki, CloudWatch.
    Includes extra fields (request_id, user_id, etc.) when attached to log records.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "pid": record.process,
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include extra context fields (e.g., user_id, request_id from middleware)
        for key in ("user_id", "request_id", "client_ip", "duration_ms", "session_id"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(log_level: str = "info", log_format: str = "text") -> None:
    """Configure root logger with appropriate format.

    Args:
        log_level: "debug", "info", "warning", "error"
        log_format: "text" (human-readable) or "json" (structured)
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers to avoid duplicates on reload
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s │ %(levelname)-8s │ %(name)-30s │ %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root.addHandler(handler)

    # Reduce noise from verbose libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)
