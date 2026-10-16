import json
import logging

from app.core.logging import (
    JsonLogFormatter,
    reset_correlation_id,
    set_correlation_id,
)


def test_json_log_formatter_adds_safe_structured_context() -> None:
    token = set_correlation_id("request-123")
    try:
        record = logging.LogRecord(
            name="myticket.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request complete",
            args=(),
            exc_info=None,
        )
        record.event = "http_request_completed"
        record.status_code = 200
        payload = json.loads(JsonLogFormatter().format(record))
    finally:
        reset_correlation_id(token)

    assert payload["message"] == "request complete"
    assert payload["correlation_id"] == "request-123"
    assert payload["event"] == "http_request_completed"
    assert payload["status_code"] == 200
