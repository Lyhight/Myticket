import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone

from app.core.config import settings


_correlation_id: ContextVar[str | None] = ContextVar(
    "correlation_id",
    default=None,
)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(value: str) -> Token:
    return _correlation_id.set(value)


def reset_correlation_id(token: Token) -> None:
    _correlation_id.reset(token)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id
        for name in (
            "event",
            "method",
            "route",
            "status_code",
            "duration_ms",
            "task_id",
            "attempt",
            "worker_id",
        ):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    if any(getattr(item, "_myticket_handler", False) for item in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler._myticket_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(
        JsonLogFormatter()
        if settings.log_format == "json"
        else logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    )
    root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
