"""Explicit parser registry — unified single-table design with ParserEntry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator
from common.logging import get_logger

logger = get_logger(__file__)


@dataclass(frozen=True)
class ParserEntry:
    func: Callable
    mode: str  # "standard" | "direct" | "none"


class ParserRegistry:
    def __init__(self) -> None:
        self._table: dict[str, dict[str, ParserEntry]] = {}

    def register(self, platform: str, parsetype: str, *, mode: str = "standard") -> Callable:
        def deco(func):
            self._table.setdefault(platform, {})
            if parsetype in self._table[platform]:
                logger.warning(
                    "Overwriting parser %s/%s with %s",
                    platform, parsetype, func.__qualname__,
                )
            self._table[platform][parsetype] = ParserEntry(func=func, mode=mode)
            return func
        return deco

    def register_direct(self, platform: str, parsetype: str) -> Callable:
        return self.register(platform, parsetype, mode="direct")

    def get(self, platform: str, parsetype: str) -> ParserEntry | None:
        self._ensure_platform(platform)
        return self._table.get(platform, {}).get(parsetype)

    def get_direct(self, platform: str, parsetype: str) -> Callable:
        self._ensure_platform(platform)
        entry = self._table.get(platform, {}).get(parsetype)
        if entry is None or entry.mode != "direct":
            from .exceptions import ParserNotFoundError
            raise ParserNotFoundError(platform, parsetype, available=self.list_direct())
        return entry.func

    def load_platform_strict(self, platform: str) -> None:
        """显式加载指定平台的所有解析器模块，若模块不存在或导入失败直接抛出异常（Fail-Fast）。"""
        import importlib
        import pkgutil

        parent_pkg = __name__.rsplit(".", 1)[0]
        pkg_name = f"{parent_pkg}.{platform}"
        pkg = importlib.import_module(pkg_name)

        if hasattr(pkg, "__path__"):
            for _, mod_name, _ in pkgutil.walk_packages(pkg.__path__, prefix=pkg_name + "."):
                importlib.import_module(mod_name)

    def _ensure_platform(self, platform: str) -> None:
        if platform not in self._table:
            self._lazy_load_platform(platform)

    def _lazy_load_platform(self, platform: str) -> None:
        import importlib
        import pkgutil

        parent_pkg = __name__.rsplit(".", 1)[0]
        try:
            pkg_name = f"{parent_pkg}.{platform}"
            pkg = importlib.import_module(pkg_name)
        except ImportError:
            return

        if hasattr(pkg, "__path__"):
            for _, mod_name, _ in pkgutil.walk_packages(pkg.__path__, prefix=pkg_name + "."):
                try:
                    importlib.import_module(mod_name)
                except Exception as e:
                    logger.warning(
                        "Failed to import platform submodule %s: %s",
                        mod_name, e, exc_info=True,
                    )

    def list(self) -> dict[str, list[str]]:
        return {p: list(t.keys()) for p, t in self._table.items()}

    def list_direct(self) -> dict[str, list[str]]:
        return {
            p: [k for k, v in t.items() if v.mode == "direct"]
            for p, t in self._table.items()
        }
