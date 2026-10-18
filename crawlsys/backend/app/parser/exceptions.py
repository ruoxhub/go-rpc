"""Parser-specific exceptions."""

from typing import Any


class ConfiguredParserError(ValueError):
    def __init__(self, code: str, *, report: Any | None = None) -> None:
        self.code = code
        self.report = report
        super().__init__(code)


class ParserCallConfigurationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ParserNotFoundError(ValueError):
    def __init__(self, platform: str, parsetype: str, available: dict[str, list[str]] | None = None) -> None:
        msg = f"No parser registered for platform='{platform}', parsetype='{parsetype}'"
        if available:
            msg += f". Available: {available}"
        super().__init__(msg)


class ParserExecutionError(RuntimeError):
    def __init__(self, platform: str, parsetype: str, cause: Exception) -> None:
        self.platform = platform
        self.parsetype = parsetype
        self.cause = cause
        super().__init__(f"Parser for {platform}/{parsetype} failed: {cause}")
        self.__cause__ = cause
