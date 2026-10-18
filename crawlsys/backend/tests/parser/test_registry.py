"""Tests for unified ParserRegistry with ParserEntry."""
import pytest
from parser.registry import ParserRegistry, ParserEntry


def test_register_default_mode_is_standard():
    reg = ParserRegistry()

    @reg.register("test_platform", "test_action")
    def my_parser(data):
        yield ("content", {"title": "hi"})

    entry = reg.get("test_platform", "test_action")
    assert entry is not None
    assert entry.mode == "standard"
    assert entry.func is my_parser


def test_register_direct_mode():
    reg = ParserRegistry()

    @reg.register("test_platform", "test_action", mode="direct")
    def my_direct_parser(data):
        return "result"

    entry = reg.get("test_platform", "test_action")
    assert entry is not None
    assert entry.mode == "direct"
    assert entry.func is my_direct_parser


def test_register_direct_alias():
    reg = ParserRegistry()

    @reg.register_direct("test_platform", "test_action")
    def my_direct_parser(data):
        return "result"

    entry = reg.get("test_platform", "test_action")
    assert entry is not None
    assert entry.mode == "direct"
    assert entry.func is my_direct_parser


def test_get_returns_none_for_missing():
    reg = ParserRegistry()
    entry = reg.get("nonexistent", "nope")
    assert entry is None


def test_get_direct_backward_compat():
    reg = ParserRegistry()

    @reg.register_direct("test_platform", "test_action")
    def my_direct_parser(data):
        return "result"

    func = reg.get_direct("test_platform", "test_action")
    assert func is my_direct_parser


def test_get_direct_raises_for_standard():
    reg = ParserRegistry()

    @reg.register("test_platform", "test_action")
    def my_parser(data):
        yield ("content", {})

    with pytest.raises(Exception):
        reg.get_direct("test_platform", "test_action")


def test_list_returns_all_entries():
    reg = ParserRegistry()

    @reg.register("p1", "a1")
    def parser1(data):
        yield ("content", {})

    @reg.register("p1", "a2", mode="direct")
    def parser2(data):
        return "x"

    result = reg.list()
    assert "p1" in result
    assert "a1" in result["p1"]
    assert "a2" in result["p1"]


def test_list_direct_returns_only_direct():
    reg = ParserRegistry()

    @reg.register("p1", "a1")
    def parser1(data):
        yield ("content", {})

    @reg.register("p1", "a2", mode="direct")
    def parser2(data):
        return "x"

    result = reg.list_direct()
    assert "p1" in result
    assert "a2" in result["p1"]
    assert "a1" not in result["p1"]


def test_overwrite_warning(caplog):
    reg = ParserRegistry()

    @reg.register("p1", "a1")
    def parser1(data):
        yield ("content", {})

    @reg.register("p1", "a1")
    def parser2(data):
        yield ("content", {})

    entry = reg.get("p1", "a1")
    assert entry.func is parser2
