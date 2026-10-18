"""调度器入口在脚本与包模式下的导入兼容测试。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_DIR.parent


@pytest.mark.parametrize(
    ("working_directory", "statement"),
    [
        (BACKEND_DIR, "import main; assert callable(main._app_factory)"),
        (
            REPOSITORY_ROOT,
            "import backend.main; assert callable(backend.main._app_factory)",
        ),
        (
            REPOSITORY_ROOT,
            "import asyncio, runpy; "
            "asyncio.run = lambda coroutine: coroutine.close(); "
            "runpy.run_module('backend.main', run_name='__main__')",
        ),
    ],
)
def test_scheduler_entrypoint_imports_in_supported_modes(
    working_directory: Path,
    statement: str,
):
    result = subprocess.run(
        [sys.executable, "-c", statement],
        cwd=working_directory,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
