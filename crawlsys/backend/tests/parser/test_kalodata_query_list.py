"""Kalodata queryList parser tests."""
from __future__ import annotations

import pytest

from parser import general_parser
from parser.exceptions import ParserExecutionError


def test_query_list_parser_emits_unique_content_ids():
    response = {"data": ["video-1", 2, "video-1", "", None]}

    items = list(
        general_parser.parse("kalodata", response, "queryList", as_dto=False)
    )

    assert items == [
        {"content_id": "video-1"},
        {"content_id": "2"},
    ]


def test_query_list_parser_accepts_empty_id_list():
    assert list(
        general_parser.parse("kalodata", {"data": []}, "queryList", as_dto=False)
    ) == []


@pytest.mark.parametrize("response", [None, {}, {"data": None}, {"data": "video-1"}])
def test_query_list_parser_rejects_invalid_response_shape(response):
    with pytest.raises(ParserExecutionError, match="queryList response.data"):
        list(general_parser.parse("kalodata", response, "queryList", as_dto=False))
