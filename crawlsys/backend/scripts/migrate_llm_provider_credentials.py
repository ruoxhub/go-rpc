"""验证或迁移 LLM Provider 的遗留凭据与旧 Fernet key 密文。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from sqlalchemy import select

from core.config import SchedulerConfig
from models.llm_provider import LlmProvider
from security.credentials import (
    ENCRYPTED_PREFIX,
    CredentialCipher,
    CredentialConfigurationError,
    CredentialDecryptionError,
    get_credential_cipher,
)
from storage import SQLAlchemyDB


@dataclass(frozen=True)
class MigrationReport:
    total: int
    plaintext_ids: tuple[int, ...]
    rotation_ids: tuple[int, ...]
    changed: int

    @property
    def pending(self) -> int:
        return len(self.plaintext_ids) + len(self.rotation_ids)


def migrate_values(
    rows: list[LlmProvider],
    cipher: CredentialCipher,
    *,
    apply: bool,
) -> MigrationReport:
    rows = list(rows)
    plaintext_ids: list[int] = []
    rotation_ids: list[int] = []
    replacements: list[tuple[LlmProvider, str]] = []

    for row in rows:
        stored = row._api_key
        try:
            migrated = cipher.migrate(stored)
        except CredentialDecryptionError as error:
            raise CredentialDecryptionError(
                f"Stored credential cannot be decrypted (provider_id={row.id})"
            ) from error
        if migrated == stored:
            continue
        if stored.startswith(ENCRYPTED_PREFIX):
            rotation_ids.append(row.id)
        else:
            plaintext_ids.append(row.id)
        replacements.append((row, migrated))

    if apply:
        for row, migrated in replacements:
            row._api_key = migrated

    return MigrationReport(
        total=len(rows),
        plaintext_ids=tuple(plaintext_ids),
        rotation_ids=tuple(rotation_ids),
        changed=len(replacements) if apply else 0,
    )


async def scan_provider_credentials(
    db,
    cipher: CredentialCipher,
    apply: bool,
) -> MigrationReport:
    statement = select(LlmProvider).order_by(LlmProvider.id)
    if apply:
        statement = statement.with_for_update()
    async with db.asession_scope() as session:
        result = await session.execute(statement)
        return migrate_values(result.scalars().all(), cipher, apply=apply)


def emit_report(report: MigrationReport, *, label: str = "scan") -> None:
    print(
        f"{label} total={report.total} pending={report.pending} "
        f"changed={report.changed} "
        f"plaintext_ids={list(report.plaintext_ids)} "
        f"rotation_ids={list(report.rotation_ids)}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify, encrypt, or rotate stored LLM Provider credentials."
    )
    parser.add_argument("--config", default="config.toml")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify-only", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser


async def run(args: argparse.Namespace) -> int:
    config = SchedulerConfig.from_toml(args.config)
    pg = config.postgresql
    db = SQLAlchemyDB(
        username=pg.username,
        password=pg.password,
        host=pg.host,
        port=pg.port,
        database=pg.database,
        amode=True,
        driver="postgresql",
    )
    cipher = get_credential_cipher()

    try:
        await db.aconnect()
        report = await scan_provider_credentials(db, cipher, args.apply)
        emit_report(report)
        if args.verify_only:
            return 2 if report.pending else 0

        verification = await scan_provider_credentials(db, cipher, False)
        emit_report(verification, label="verification")
        return 1 if verification.pending else 0
    finally:
        await db.aclose()


def _find_credential_error(error: BaseException) -> BaseException | None:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(
            current,
            (CredentialConfigurationError, CredentialDecryptionError),
        ):
            return current
        current = (
            current.__cause__
            or getattr(current, "cause", None)
            or getattr(current, "original_error", None)
        )
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run(args))
    except Exception as error:
        credential_error = _find_credential_error(error)
        if credential_error is not None:
            print(str(credential_error), file=sys.stderr)
        else:
            print(
                f"Credential migration failed ({type(error).__name__})",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
