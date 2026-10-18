import logging

import pytest

from worker.media_logging import MEDIA_LOG_FIELDS, log_media_event


def test_log_media_event_emits_only_approved_structured_fields(caplog):
    logger = logging.getLogger("test.media_logging.fields")

    with caplog.at_level(logging.INFO, logger=logger.name):
        log_media_event(
            logger,
            logging.INFO,
            task_id=41,
            consumer_key="task:41",
            platform="tiktok",
            outcome="success",
        )

    record = caplog.records[-1]
    assert MEDIA_LOG_FIELDS == (
        "task_id",
        "consumer_key",
        "platform",
        "content_id",
        "batch_id",
        "claim_token_prefix",
        "attempt_count",
        "outcome",
        "latency_ms",
        "exception_type",
    )
    assert {field: getattr(record, field) for field in MEDIA_LOG_FIELDS} == {
        "task_id": 41,
        "consumer_key": "task:41",
        "platform": "tiktok",
        "content_id": None,
        "batch_id": None,
        "claim_token_prefix": None,
        "attempt_count": None,
        "outcome": "success",
        "latency_ms": None,
        "exception_type": None,
    }
    assert record.getMessage() == "media event succeeded"


def test_log_media_event_formats_and_redacts_failed_error(caplog):
    logger = logging.getLogger("test.media_logging.failed")
    error = RuntimeError(
        "url=https://private.invalid/video token=full-secret " + "x" * 600
    )

    with caplog.at_level(logging.ERROR, logger=logger.name):
        log_media_event(
            logger,
            logging.ERROR,
            task_id=41,
            consumer_key="task:41",
            platform="tiktok",
            batch_id="batch-1",
            outcome="failed",
            latency_ms=12,
            exception_type="RuntimeError",
            error=error,
        )

    record = caplog.records[-1]
    assert record.getMessage().startswith("RuntimeError: ")
    assert len(record.getMessage()) <= 500
    assert "https://" not in record.getMessage()
    assert "full-secret" not in record.getMessage()
    assert record.exception_type == "RuntimeError"


def test_log_media_event_rejects_unknown_structured_fields():
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        log_media_event(
            logging.getLogger("test.media_logging.unknown"),
            logging.INFO,
            outcome="success",
            media_url="https://private.invalid/video",
        )
