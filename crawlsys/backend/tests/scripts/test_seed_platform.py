"""Seed platform script entrypoint tests."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.seed_platform import build_parser


BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_seed_platform_help_runs_from_backend_directory():
    result = subprocess.run(
        [sys.executable, "scripts/seed_platform.py", "--help"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--code" in result.stdout
    assert "--name" in result.stdout


def test_seed_platform_parser_defaults_without_database_access():
    args = build_parser().parse_args([])

    assert args.code == "bilibili"
    assert args.name == "B站"
    assert args.concurrency == 1
    assert args.rps == 1.0
    assert args.burst == 3
    assert args.cooldown == 300
