import pytest
from app.core.rpc_base import validate_json_depth, validate_json_nodes, validate_response_size

def test_validate_json_depth_boundaries():
    shallow = {"a": {"b": 1}}
    assert validate_json_depth(shallow, max_depth=2) is True
    assert validate_json_depth(shallow, max_depth=1) is False

    nested_list = [[[1]]]
    assert validate_json_depth(nested_list, max_depth=3) is True
    assert validate_json_depth(nested_list, max_depth=2) is False

def test_validate_json_nodes_count():
    obj = {"k1": "v1", "k2": [1, 2, 3], "k3": {"nested": "value"}}
    # 节点计数: dict(1) + "v1"(1) + list(1) + 3 items(3) + dict(1) + "value"(1) = 8
    assert validate_json_nodes(obj, max_nodes=10) is True
    assert validate_json_nodes(obj, max_nodes=5) is False

def test_validate_response_size():
    assert validate_response_size(1024, max_bytes=2048) is True
    assert validate_response_size(2048, max_bytes=1024) is False
    assert validate_response_size(None, max_bytes=1024) is True
