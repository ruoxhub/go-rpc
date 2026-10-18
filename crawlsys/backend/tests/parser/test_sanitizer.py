from copy import deepcopy
import dataclasses

import pytest

from parser.sanitizer import (
    JsonResourceLimitError,
    canonical_json_bytes,
    json_hmac_sha256,
    json_sha256,
    prepare_ai_sample,
    sanitize_json,
)


def test_recursive_sanitizer_covers_keys_and_free_text_values():
    original = {
        "accessToken": "abc",
        "nested": [
            {
                "Set-Cookie": "sid=secret",
                "note": "mail alice@example.com, call +86 13800138000, JWT eyJhbGciOiJIUzI1NiJ9.abc.signature",
                "authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.abc.signature",
            }
        ],
        "url": "https://example.test/a?token=secret&cursor=2",
    }
    snapshot = deepcopy(original)

    result = sanitize_json(original, max_depth=64, max_nodes=100_000)

    assert original == snapshot
    assert result.value["accessToken"] == "<redacted:token>"
    assert result.value["nested"][0]["Set-Cookie"] == "<redacted:cookie>"
    serialized = canonical_json_bytes(result.value)
    for secret in (
        b"abc",
        b"alice@example.com",
        b"13800138000",
        b"secret",
        b"eyJhbGciOiJIUzI1NiJ9",
    ):
        assert secret not in serialized
    assert all(not hasattr(hit, "original_value") for hit in result.report.hits)


def test_sanitizer_normalizes_nested_tuples_and_sets_without_leaks():
    original = {
        "nested": [
            (
                {"accessToken": "tuple-secret"},
                {"plain", "alice@example.com"},
            )
        ]
    }

    result = sanitize_json(original)

    assert result.value == {
        "nested": [
            [
                {"accessToken": "<redacted:token>"},
                ["<redacted:email>", "plain"],
            ]
        ]
    }
    assert b"tuple-secret" not in canonical_json_bytes(result.value)
    assert b"alice@example.com" not in canonical_json_bytes(result.value)

    prepared = prepare_ai_sample(
        original, max_bytes=1_024, max_array_items=20
    )
    ai_bytes = canonical_json_bytes(prepared.value)
    assert b"tuple-secret" not in ai_bytes
    assert b"alice@example.com" not in ai_bytes


@pytest.mark.parametrize(
    "value", [b"secret", object(), {"accessToken": object()}]
)
def test_sanitizer_fails_closed_for_unsupported_types(value):
    with pytest.raises(TypeError, match="unsupported_json_type"):
        sanitize_json({"value": value})


def test_sanitizer_rejects_non_string_object_keys():
    with pytest.raises(TypeError, match="json_object_key_must_be_string"):
        sanitize_json({1: "value"})


def test_sanitizer_reports_stable_categories_counts_and_rfc6901_pointers():
    result = sanitize_json(
        {"a/b~c": "alice@example.com and bob@example.com"},
        max_depth=64,
        max_nodes=100,
    )

    assert [dataclasses.asdict(hit) for hit in result.report.hits] == [
        {"pointer": "/a~1b~0c", "category": "email", "count": 2}
    ]
    assert "alice" not in repr(result.report)


def test_sensitive_key_matching_covers_adjacent_words_and_common_prefixes():
    result = sanitize_json(
        {
            "X-Api-Key": "api-secret",
            "serviceAccessToken": "access-secret",
        }
    )

    assert result.value == {
        "X-Api-Key": "<redacted:api_key>",
        "serviceAccessToken": "<redacted:token>",
    }


def test_url_query_key_is_decoded_for_matching_but_preserved_in_output():
    result = sanitize_json(
        {"url": "https://example.test/path?%74oken=secret&cursor=2"}
    )

    assert result.value["url"] == (
        "https://example.test/path?%74oken=<redacted:token>&cursor=2"
    )


def test_canonical_json_hash_and_hmac_are_order_independent():
    left = {"b": 2, "a": "你好"}
    right = {"a": "你好", "b": 2}

    assert canonical_json_bytes(left) == b'{"a":"\xe4\xbd\xa0\xe5\xa5\xbd","b":2}'
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert json_sha256(left) == json_sha256(right)
    assert json_hmac_sha256(left, b"dedicated-key") == json_hmac_sha256(
        right, b"dedicated-key"
    )


def test_hmac_matches_known_sha256_vector_and_changes_with_key():
    value = {"a": 1}

    assert json_hmac_sha256(value, b"key") == (
        "88a67f24bbcdaed0e6c997404bb79a743baf44c6bab2f4c27328e3009d22e342"
    )
    assert json_hmac_sha256(value, b"other-key") != json_hmac_sha256(
        value, b"key"
    )


@pytest.mark.parametrize("key", [b"", None])
def test_hmac_rejects_missing_key(key):
    with pytest.raises(ValueError, match="hmac_key_required"):
        json_hmac_sha256({"safe": True}, key)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_non_finite_numbers(value):
    with pytest.raises(ValueError):
        canonical_json_bytes({"value": value})


@pytest.mark.parametrize(
    "value",
    [
        (1, 2),
        {1, 2},
        b"bytes",
        {1: "value"},
    ],
)
def test_canonical_json_rejects_non_json_types(value):
    with pytest.raises(TypeError):
        canonical_json_bytes(value)


def test_depth_and_node_limits_fail_before_recursion_exhaustion():
    with pytest.raises(JsonResourceLimitError, match="max_depth"):
        sanitize_json(
            {"a": {"b": {"c": 1}}}, max_depth=2, max_nodes=100
        )
    with pytest.raises(JsonResourceLimitError, match="max_nodes"):
        sanitize_json([1, 2, 3], max_depth=64, max_nodes=2)


def test_unsafe_requested_depth_is_rejected_before_python_recursion():
    deeply_nested = None
    for _ in range(2_000):
        deeply_nested = [deeply_nested]

    with pytest.raises(JsonResourceLimitError, match="max_depth"):
        sanitize_json(deeply_nested, max_depth=10_000)


def test_ai_sample_is_sanitized_bounded_and_reports_cropping():
    sample = {
        "accessToken": "never-send-this",
        "items": [{"text": "x" * 40_000} for _ in range(30)],
    }

    prepared = prepare_ai_sample(
        sample, max_bytes=16_384, max_array_items=20
    )

    serialized = canonical_json_bytes(prepared.value)
    assert len(serialized) <= 16_384
    assert b"never-send-this" not in serialized
    assert prepared.value["_parser_sample_summary"] == dataclasses.asdict(
        prepared.summary
    )
    assert prepared.summary.omitted_array_items == 10
    assert prepared.summary.truncated_nodes > 0
    assert prepared.summary.original_bytes == len(
        canonical_json_bytes(sanitize_json(sample).value)
    )


def test_ai_sample_cropping_is_deterministic_for_equal_sized_nodes():
    sample = {"b": "x" * 200, "a": "y" * 200}

    left = prepare_ai_sample(sample, max_bytes=450, max_array_items=20)
    right = prepare_ai_sample(sample, max_bytes=450, max_array_items=20)

    assert left == right
    assert "$truncated" in left.value["sample"]["a"]
    assert left.value["sample"]["b"] == "x" * 200


def test_root_truncation_hashes_the_original_cropped_tree():
    sample = {"a": ["x" * 200, "omitted"], "b": "y" * 200}
    cropped = {"a": ["x" * 200], "b": "y" * 200}

    prepared = prepare_ai_sample(sample, max_bytes=260, max_array_items=1)
    marker = prepared.value["sample"]["$truncated"]

    assert marker == {
        "sha256": json_sha256(cropped),
        "original_bytes": len(canonical_json_bytes(cropped)),
    }
    assert prepared.summary.omitted_array_items == 1


@pytest.mark.parametrize("max_bytes", [1, 128, 192])
def test_shrinkable_root_that_still_exceeds_budget_fails_closed(max_bytes):
    with pytest.raises(JsonResourceLimitError, match="ai_max_bytes"):
        prepare_ai_sample(
            "x" * 200, max_bytes=max_bytes, max_array_items=20
        )


def test_ai_sample_rejects_limit_smaller_than_minimal_envelope():
    with pytest.raises(JsonResourceLimitError, match="ai_max_bytes"):
        prepare_ai_sample({}, max_bytes=1, max_array_items=20)
