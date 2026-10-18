from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import re
from typing import Any
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from parser.definition import JsonValue


_SENSITIVE_SEGMENTS = {
    "token": "token",
    "accesstoken": "token",
    "refreshtoken": "token",
    "authorization": "authorization",
    "cookie": "cookie",
    "setcookie": "cookie",
    "session": "session",
    "apikey": "api_key",
    "secret": "secret",
    "password": "password",
    "credential": "credential",
    "phone": "phone",
    "mobile": "phone",
    "email": "email",
}
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\."
    r"[A-Za-z0-9_-]+(?![A-Za-z0-9_-])"
)
_EMAIL = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+"
    r"(?:\.[A-Za-z0-9-]+)+(?![\w.-])"
)
_PHONE = re.compile(
    r"(?<!\d)(?:\+?86[ -]?)?1[3-9]\d(?:[ -]?\d){8}(?!\d)"
    r"|(?<!\d)\+[1-9]\d(?:[ -]?\d){6,13}(?!\d)"
)
_URL = re.compile(r"https?://[^\s\"'<>]+")
_MAX_SAFE_DEPTH = 128


class JsonResourceLimitError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SanitizationHit:
    pointer: str
    category: str
    count: int


@dataclass(frozen=True, slots=True)
class SanitizationReport:
    hits: tuple[SanitizationHit, ...]


@dataclass(frozen=True, slots=True)
class SanitizedJson:
    value: JsonValue
    report: SanitizationReport


@dataclass(frozen=True, slots=True)
class AiSampleSummary:
    omitted_array_items: int
    truncated_nodes: int
    original_bytes: int


@dataclass(frozen=True, slots=True)
class PreparedAiSample:
    value: dict[str, JsonValue]
    summary: AiSampleSummary


def canonical_json_bytes(value: JsonValue) -> bytes:
    _validate_json(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def json_sha256(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def json_hmac_sha256(value: JsonValue, key: bytes) -> str:
    if not key:
        raise ValueError("hmac_key_required")
    return hmac.new(key, canonical_json_bytes(value), hashlib.sha256).hexdigest()


def sanitize_json(
    value: Any, *, max_depth: int = 64, max_nodes: int = 100_000
) -> SanitizedJson:
    if max_depth < 0 or max_depth > _MAX_SAFE_DEPTH:
        raise JsonResourceLimitError("max_depth")
    if max_nodes < 1:
        raise JsonResourceLimitError("max_nodes")

    _validate_sanitizable(value, max_depth=max_depth, max_nodes=max_nodes)

    def visit(
        current: Any,
    ) -> tuple[JsonValue, list[tuple[tuple[str, ...], str, int]]]:
        if type(current) is dict:
            copied: dict[str, JsonValue] = {}
            hits: list[tuple[tuple[str, ...], str, int]] = []
            for key, child in current.items():
                category = _sensitive_category(key)
                if category is not None:
                    copied[key] = _placeholder(category)
                    hits.append(((key,), category, 1))
                else:
                    copied[key], child_hits = visit(child)
                    hits.extend(
                        ((key, *path), hit_category, count)
                        for path, hit_category, count in child_hits
                    )
            return copied, hits
        if type(current) in (list, tuple):
            copied_list: list[JsonValue] = []
            hits = []
            for index, child in enumerate(current):
                copied_child, child_hits = visit(child)
                copied_list.append(copied_child)
                hits.extend(
                    ((str(index), *path), category, count)
                    for path, category, count in child_hits
                )
            return copied_list, hits
        if type(current) is set:
            sanitized_items = [visit(child) for child in current]
            sanitized_items.sort(key=lambda item: canonical_json_bytes(item[0]))
            copied_list = []
            hits = []
            for index, (copied_child, child_hits) in enumerate(sanitized_items):
                copied_list.append(copied_child)
                hits.extend(
                    ((str(index), *path), category, count)
                    for path, category, count in child_hits
                )
            return copied_list, hits
        if isinstance(current, str):
            redacted, counts = _sanitize_string(current)
            return redacted, [
                ((), category, count) for category, count in counts.items()
            ]
        if current is None or type(current) in (bool, int):
            return current, []
        if type(current) is float:
            if not math.isfinite(current):
                raise ValueError("non_finite_float")
            return current, []
        raise TypeError("unsupported_json_type")

    sanitized, raw_hits = visit(value)
    hit_counts: dict[tuple[str, str], int] = {}
    for path, category, count in raw_hits:
        key = (_pointer_string(path), category)
        hit_counts[key] = hit_counts.get(key, 0) + count
    hits = tuple(
        SanitizationHit(pointer, category, count)
        for (pointer, category), count in hit_counts.items()
    )
    return SanitizedJson(sanitized, SanitizationReport(hits))


def prepare_ai_sample(
    value: Any,
    *,
    max_bytes: int,
    max_array_items: int,
    max_depth: int = 64,
    max_nodes: int = 100_000,
) -> PreparedAiSample:
    if max_bytes < 1:
        raise JsonResourceLimitError("ai_max_bytes")
    if max_array_items < 0:
        raise JsonResourceLimitError("max_array_items")

    sanitized = sanitize_json(
        value, max_depth=max_depth, max_nodes=max_nodes
    ).value
    original_bytes = len(canonical_json_bytes(sanitized))
    original_sample, omitted = _crop_arrays(sanitized, max_array_items)
    sample = _copy_json(original_sample)
    truncated_nodes = 0

    while True:
        summary = AiSampleSummary(omitted, truncated_nodes, original_bytes)
        envelope: dict[str, JsonValue] = {
            "sample": sample,
            "_parser_sample_summary": {
                "omitted_array_items": summary.omitted_array_items,
                "truncated_nodes": summary.truncated_nodes,
                "original_bytes": summary.original_bytes,
            },
        }
        if len(canonical_json_bytes(envelope)) <= max_bytes:
            return PreparedAiSample(envelope, summary)

        candidates = _truncation_candidates(sample, original_sample)
        if not candidates:
            root_replacement = _truncated_value(original_sample)
            if len(canonical_json_bytes(root_replacement)) >= len(
                canonical_json_bytes(sample)
            ):
                raise JsonResourceLimitError("ai_max_bytes")
            root_summary = AiSampleSummary(
                omitted, truncated_nodes + 1, original_bytes
            )
            root_envelope: dict[str, JsonValue] = {
                "sample": root_replacement,
                "_parser_sample_summary": {
                    "omitted_array_items": root_summary.omitted_array_items,
                    "truncated_nodes": root_summary.truncated_nodes,
                    "original_bytes": root_summary.original_bytes,
                },
            }
            if len(canonical_json_bytes(root_envelope)) <= max_bytes:
                return PreparedAiSample(root_envelope, root_summary)
            raise JsonResourceLimitError("ai_max_bytes")
        else:
            _, pointer, replacement = candidates[0]
            sample = _replace_pointer(sample, pointer, replacement)
        truncated_nodes += 1


def _placeholder(category: str) -> str:
    return f"<redacted:{category}>"


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _sensitive_category(key: str) -> str | None:
    words = (
        _CAMEL_BOUNDARY.sub(" ", key)
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )
    collapsed = "".join(words).lower()
    if collapsed in _SENSITIVE_SEGMENTS:
        return _SENSITIVE_SEGMENTS[collapsed]
    lowered = [word.lower() for word in words]
    for size in range(min(3, len(lowered)), 0, -1):
        for start in range(len(lowered) - size + 1):
            category = _SENSITIVE_SEGMENTS.get(
                "".join(lowered[start : start + size])
            )
            if category is not None:
                return category
    return None


def _sanitize_string(value: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}

    def replace(pattern: re.Pattern[str], category: str, text: str) -> str:
        def replacement(_: re.Match[str]) -> str:
            counts[category] = counts.get(category, 0) + 1
            return _placeholder(category)

        return pattern.sub(replacement, text)

    result = replace(_BEARER, "authorization", value)
    result = replace(_JWT, "token", result)
    result = replace(_EMAIL, "email", result)
    result = replace(_PHONE, "phone", result)

    def redact_url(match: re.Match[str]) -> str:
        redacted, url_counts = _sanitize_url(match.group(0))
        for category, count in url_counts.items():
            counts[category] = counts.get(category, 0) + count
        return redacted

    return _URL.sub(redact_url, result), counts


def _sanitize_url(value: str) -> tuple[str, dict[str, int]]:
    parts = urlsplit(value)
    if not parts.query:
        return value, {}

    counts: dict[str, int] = {}
    parameters = []
    for parameter in parts.query.split("&"):
        key, separator, parameter_value = parameter.partition("=")
        category = _sensitive_category(unquote_plus(key))
        if category is not None and separator:
            parameter_value = _placeholder(category)
            counts[category] = counts.get(category, 0) + 1
        parameters.append(f"{key}{separator}{parameter_value}")
    query = "&".join(parameters)
    return (
        urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment)),
        counts,
    )


def _crop_arrays(value: JsonValue, limit: int) -> tuple[JsonValue, int]:
    if isinstance(value, dict):
        copied: dict[str, JsonValue] = {}
        omitted = 0
        for key, child in value.items():
            copied[key], child_omitted = _crop_arrays(child, limit)
            omitted += child_omitted
        return copied, omitted
    if isinstance(value, list):
        copied_list: list[JsonValue] = []
        omitted = max(0, len(value) - limit)
        for child in value[:limit]:
            copied_child, child_omitted = _crop_arrays(child, limit)
            copied_list.append(copied_child)
            omitted += child_omitted
        return copied_list, omitted
    return value, 0


def _truncated_value(value: JsonValue) -> dict[str, JsonValue]:
    encoded = canonical_json_bytes(value)
    return {
        "$truncated": {
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "original_bytes": len(encoded),
        }
    }


def _truncation_candidates(
    value: JsonValue, original: JsonValue
) -> list[tuple[int, tuple[str, ...], dict[str, JsonValue]]]:
    candidates: list[tuple[int, tuple[str, ...], dict[str, JsonValue]]] = []

    def visit(current: JsonValue, pointer: tuple[str, ...]) -> None:
        if pointer and isinstance(current, (str, dict, list)):
            if isinstance(current, dict) and set(current) == {"$truncated"}:
                return
            original_node = _resolve_pointer(original, pointer)
            original_encoded = canonical_json_bytes(original_node)
            replacement = _truncated_value(original_node)
            if len(canonical_json_bytes(replacement)) < len(
                canonical_json_bytes(current)
            ):
                candidates.append(
                    (len(original_encoded), pointer, replacement)
                )
        if isinstance(current, dict):
            for key, child in current.items():
                visit(child, (*pointer, key))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                visit(child, (*pointer, str(index)))

    visit(value, ())
    candidates.sort(key=lambda item: (-item[0], _pointer_string(item[1])))
    return candidates


def _validate_json(value: Any) -> None:
    stack = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > _MAX_SAFE_DEPTH:
            raise JsonResourceLimitError("max_depth")
        if current is None or type(current) in (bool, str, int):
            continue
        if type(current) is float:
            if not math.isfinite(current):
                raise ValueError("non_finite_float")
            continue
        if type(current) is list:
            stack.extend((child, depth + 1) for child in current)
            continue
        if type(current) is dict:
            if any(type(key) is not str for key in current):
                raise TypeError("json_object_key_must_be_string")
            stack.extend((child, depth + 1) for child in current.values())
            continue
        raise TypeError("unsupported_json_type")


def _validate_sanitizable(
    value: Any, *, max_depth: int, max_nodes: int
) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            raise JsonResourceLimitError("max_depth")
        nodes += 1
        if nodes > max_nodes:
            raise JsonResourceLimitError("max_nodes")
        if current is None or type(current) in (bool, str, int):
            continue
        if type(current) is float:
            if not math.isfinite(current):
                raise ValueError("non_finite_float")
            continue
        if type(current) is dict:
            if any(type(key) is not str for key in current):
                raise TypeError("json_object_key_must_be_string")
            stack.extend((child, depth + 1) for child in current.values())
            continue
        if type(current) in (list, tuple, set):
            stack.extend((child, depth + 1) for child in current)
            continue
        raise TypeError("unsupported_json_type")


def _copy_json(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {key: _copy_json(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_copy_json(child) for child in value]
    return value


def _resolve_pointer(value: JsonValue, pointer: tuple[str, ...]) -> JsonValue:
    current = value
    for token in pointer:
        if isinstance(current, list):
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise JsonResourceLimitError("ai_max_bytes")
    return current


def _pointer_string(pointer: tuple[str, ...]) -> str:
    return "".join(f"/{_escape_pointer(token)}" for token in pointer)


def _replace_pointer(
    value: JsonValue,
    pointer: tuple[str, ...],
    replacement: JsonValue,
) -> JsonValue:
    if not pointer:
        return replacement
    current: Any = value
    for token in pointer[:-1]:
        current = current[int(token)] if isinstance(current, list) else current[token]
    final = pointer[-1]
    if isinstance(current, list):
        current[int(final)] = replacement
    else:
        current[final] = replacement
    return value


__all__ = [
    "AiSampleSummary",
    "JsonResourceLimitError",
    "PreparedAiSample",
    "SanitizationHit",
    "SanitizationReport",
    "SanitizedJson",
    "canonical_json_bytes",
    "json_hmac_sha256",
    "json_sha256",
    "prepare_ai_sample",
    "sanitize_json",
]
