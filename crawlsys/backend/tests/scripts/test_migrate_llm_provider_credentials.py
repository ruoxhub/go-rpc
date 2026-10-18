from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
from cryptography.fernet import Fernet

from scripts.migrate_llm_provider_credentials import (
    build_parser,
    emit_report,
    migrate_values,
    scan_provider_credentials,
)
from security.credentials import (
    ENCRYPTED_PREFIX,
    CredentialCipher,
    CredentialDecryptionError,
)


@dataclass
class Row:
    id: int
    _api_key: str


def cipher(*keys: bytes) -> CredentialCipher:
    return CredentialCipher.from_key_string(
        ",".join(key.decode("ascii") for key in keys)
    )


def test_verify_classifies_plaintext_current_and_old_key_values():
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    current_value = cipher(new_key).encrypt("current-secret")
    rows = [
        Row(1, "legacy-secret"),
        Row(2, current_value),
        Row(3, cipher(old_key).encrypt("old-secret")),
    ]

    report = migrate_values(rows, cipher(new_key, old_key), apply=False)

    assert report.total == 3
    assert report.plaintext_ids == (1,)
    assert report.rotation_ids == (3,)
    assert report.changed == 0
    assert report.pending == 2
    assert rows[0]._api_key == "legacy-secret"
    assert rows[1]._api_key == current_value


def test_apply_encrypts_plaintext_and_rotates_only_old_key_values():
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    target = cipher(new_key, old_key)
    current_value = cipher(new_key).encrypt("current")
    rows = [
        Row(1, "plain"),
        Row(2, cipher(old_key).encrypt("old")),
        Row(3, current_value),
    ]

    report = migrate_values(rows, target, apply=True)

    assert report.changed == 2
    assert all(row._api_key.startswith(ENCRYPTED_PREFIX) for row in rows)
    assert [target.decrypt(row._api_key) for row in rows] == [
        "plain",
        "old",
        "current",
    ]
    assert rows[2]._api_key == current_value
    assert migrate_values(rows, target, apply=False).pending == 0


def test_corrupt_value_leaves_the_whole_batch_unchanged():
    key = Fernet.generate_key()
    rows = [Row(1, "legacy-secret"), Row(2, f"{ENCRYPTED_PREFIX}corrupt")]
    original_values = [row._api_key for row in rows]

    with pytest.raises(CredentialDecryptionError) as raised:
        migrate_values(rows, cipher(key), apply=True)

    assert [row._api_key for row in rows] == original_values
    assert str(raised.value) == (
        "Stored credential cannot be decrypted (provider_id=2)"
    )
    assert "legacy-secret" not in str(raised.value)
    assert ENCRYPTED_PREFIX not in str(raised.value)


class ScalarResult:
    def __init__(self, rows: list[Row]) -> None:
        self._rows = rows

    def scalars(self) -> ScalarResult:
        return self

    def all(self) -> list[Row]:
        return self._rows


class Session:
    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return ScalarResult(self.rows)


class Database:
    def __init__(self, rows: list[Row]) -> None:
        self.session = Session(rows)

    @asynccontextmanager
    async def asession_scope(self):
        yield self.session


@pytest.mark.asyncio
@pytest.mark.parametrize("apply", [False, True])
async def test_scan_locks_rows_only_when_applying(apply):
    db = Database([Row(1, "legacy-secret")])

    report = await scan_provider_credentials(db, cipher(Fernet.generate_key()), apply)

    assert report.changed == int(apply)
    assert (db.session.statement._for_update_arg is not None) is apply


def test_report_output_contains_only_counts_and_ids(capsys):
    rows = [Row(1, "legacy-secret")]
    report = migrate_values(rows, cipher(Fernet.generate_key()), apply=False)

    emit_report(report)

    captured = capsys.readouterr()
    assert "total=1" in captured.out
    assert "pending=1" in captured.out
    assert "plaintext_ids=[1]" in captured.out
    assert "legacy-secret" not in captured.out
    assert ENCRYPTED_PREFIX not in captured.out


def test_cli_requires_exactly_one_execution_mode():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--verify-only", "--apply"])

    assert parser.parse_args(["--verify-only"]).verify_only is True
    assert parser.parse_args(["--apply"]).apply is True
