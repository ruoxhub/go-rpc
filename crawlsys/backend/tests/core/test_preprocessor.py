import pytest
from app.pipeline.preprocessor import clean_nul_bytes

def test_clean_nul_bytes_string():
    assert clean_nul_bytes("hello\x00world") == "helloworld"
    assert clean_nul_bytes("clean") == "clean"

def test_clean_nul_bytes_nested():
    data = {
        "title": "abc\x00def",
        "tags": ["python\x00", "safe"],
        "meta": {"desc": "more\x00nul"},
        "count": 42,
    }
    cleaned = clean_nul_bytes(data)
    assert cleaned["title"] == "abcdef"
    assert cleaned["tags"] == ["python", "safe"]
    assert cleaned["meta"]["desc"] == "morenul"
    assert cleaned["count"] == 42
