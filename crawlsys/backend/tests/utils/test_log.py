from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import StringIO

from common.errors import redact_secrets, redact_value, register_secret
from utils.log import LogConfig, LoggerManager, get_logger, log


def test_log_config_disables_local_variable_diagnostics():
    assert LogConfig().diagnose is False


def test_logger_masks_registered_secret_in_message():
    secret = "logger-provider-secret-456"
    register_secret(secret)
    output = StringIO()
    handler_id = log.add(output, format="{message}", enqueue=False)

    try:
        get_logger("security-test").error("provider rejected %s", secret)
    finally:
        log.remove(handler_id)

    assert output.getvalue().strip() == "provider rejected ***"


def test_logger_masks_registered_secret_in_nested_extra():
    secret = "logger-extra-secret-789"
    register_secret(secret)
    output = StringIO()
    handler_id = log.add(output, format="{extra}", enqueue=False)

    try:
        get_logger("security-test").bind(
            context={"provider_key": [secret]},
        ).error("failed")
    finally:
        log.remove(handler_id)

    rendered = output.getvalue()
    assert secret not in rendered
    assert "***" in rendered


def test_json_logger_masks_registered_secret_in_exception_value():
    secret = "logger-exception-secret-321"
    register_secret(secret)
    output = StringIO()
    handler_id = log.add(
        output,
        format=LoggerManager._json_formatter,
        enqueue=False,
        backtrace=False,
        diagnose=False,
    )

    try:
        try:
            raise RuntimeError(secret)
        except RuntimeError:
            get_logger("security-test").exception("failed")
    finally:
        log.remove(handler_id)

    rendered = output.getvalue()
    assert secret not in rendered
    assert "***" in rendered


def test_text_logger_masks_registered_secret_in_exception_value():
    secret = "text-exception-secret-741"
    register_secret(secret)
    output = StringIO()
    handler_id = log.add(
        output,
        format="{message}",
        enqueue=False,
        backtrace=False,
        diagnose=False,
    )

    try:
        try:
            raise ValueError(secret)
        except ValueError:
            get_logger("security-test").exception("failed")
    finally:
        log.remove(handler_id)

    rendered = output.getvalue()
    assert secret not in rendered
    assert "ValueError: ***" in rendered


def test_redact_value_preserves_unrelated_and_short_values():
    secret = "nested-provider-secret-654"
    short_value = "q7x!"
    register_secret(secret)
    register_secret(short_value)

    redacted = redact_value(
        {"items": ["unchanged", secret], "pair": (short_value, 7)}
    )

    assert redacted == {
        "items": ["unchanged", "***"],
        "pair": (short_value, 7),
    }


def test_register_secret_is_thread_safe():
    secrets = [f"thread-provider-secret-{index}" for index in range(16)]

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(register_secret, secrets))

    rendered = redact_secrets(" ".join(secrets))
    assert all(secret not in rendered for secret in secrets)
