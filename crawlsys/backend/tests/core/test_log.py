from common.logging import get_logger


def test_logger_exposes_debugger_method():
    logger = get_logger("test")

    assert callable(logger.debugger)
    logger.debugger("debugger log %s", "ok")
