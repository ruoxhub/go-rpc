import pytest
from app.parser.registry import ParserRegistry

def test_registry_load_platform_strict_raises_on_missing_module():
    registry = ParserRegistry()
    with pytest.raises(ImportError):
        registry.load_platform_strict("non_existent_platform_xyz_123")

def test_registry_load_platform_strict_success_on_existing_platform():
    registry = ParserRegistry()
    # tiktok 是存在的平台模块，严格加载时不应抛出异常
    registry.load_platform_strict("tiktok")
