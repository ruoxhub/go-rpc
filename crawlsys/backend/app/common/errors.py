"""Safe exception rendering for logs and persistence."""
from __future__ import annotations

import re
from threading import RLock


_SECRET_VALUE = re.compile(
    r"(?ix)((?:[a-z0-9]+[_-])*(?:api[_-]?key|token|password|secret[_-]?key|secret|access[_-]?key))"
    r"(?![a-z0-9_-])(\s*[:=]\s*)"
    r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|'
    r'"(?:\\.|[^"\\])*\\?\Z|\'(?:\\.|[^\'\\])*\\?\Z|[^\s,;]+)'
)
_SECRET_LABEL = re.compile(
    r"(?ix)((?:[a-z0-9]+[_-])*(?:api[_-]?key|token|password|secret[_-]?key|secret|access[_-]?key))"
    r"(?=\s*[:=])"
)
_BEARER_TOKEN = re.compile(r"(?i)\b(Bearer)(\s+)(\S+)")
_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s]+")
# ponytail: The process-local set and linear scan assume a small Provider
# credential count; replace with a bounded trie if redaction becomes a hot path.
_DYNAMIC_SECRETS: set[str] = set()
_DYNAMIC_SECRETS_LOCK = RLock()
MIN_DYNAMIC_SECRET_LENGTH = 5


def register_secret(value: str) -> None:
    # ponytail: Very short values would erase ordinary log text; structured
    # api_key/token/password/Bearer masking remains responsible for those.
    if len(value) < MIN_DYNAMIC_SECRET_LENGTH:
        return
    with _DYNAMIC_SECRETS_LOCK:
        _DYNAMIC_SECRETS.add(value)


def _replace_secret(match: re.Match[str]) -> str:
    value = match.group(3)
    quote = value[0] if value[:1] in {'"', "'"} else ""
    return f"{match.group(1)}{match.group(2)}{quote}***{quote}"


def _redact_dynamic_secrets(message: str, secrets: tuple[str, ...]) -> str:
    parts = _SECRET_LABEL.split(message)
    for index in range(0, len(parts), 2):
        for secret in secrets:
            parts[index] = parts[index].replace(secret, "***")
    return "".join(parts)


def redact_secrets(message: str) -> str:
    message = _URL.sub("[REDACTED_URL]", message)
    message = _BEARER_TOKEN.sub(r"\1\2***", message)
    message = _SECRET_VALUE.sub(_replace_secret, message)
    with _DYNAMIC_SECRETS_LOCK:
        secrets = tuple(sorted(_DYNAMIC_SECRETS, key=len, reverse=True))
    return _redact_dynamic_secrets(message, secrets)


def redact_value(value: object) -> object:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {
            redact_value(key): redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    return value


def format_error(exc: BaseException, max_length: int = 2000) -> str:
    """Return a bounded exception type/message with credentials redacted."""
    return f"{type(exc).__name__}: {redact_secrets(str(exc))}"[:max_length]
