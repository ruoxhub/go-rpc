"""Test import paths for the repository's flat backend module layout."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
for path in (
    BACKEND_DIR / "app",
    BACKEND_DIR.parent,
    BACKEND_DIR.parent / "sdk" / "python" / "src",
):
    path_string = str(path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)


_TEST_CREDENTIAL_KEY = Fernet.generate_key().decode("ascii")
os.environ["CRAWLER_CREDENTIAL_FERNET_KEYS"] = _TEST_CREDENTIAL_KEY


@pytest.fixture(autouse=True)
def isolated_credential_cipher(monkeypatch):
    from security.credentials import (  # pyright: ignore[reportMissingImports]
        ENV_NAME,
        clear_credential_cipher_cache,
    )

    monkeypatch.setenv(ENV_NAME, _TEST_CREDENTIAL_KEY)
    clear_credential_cipher_cache()
    yield
    clear_credential_cipher_cache()
