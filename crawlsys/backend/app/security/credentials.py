"""LLM 等运行时凭据的加密边界。"""

from __future__ import annotations

import os
from functools import cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from common.errors import register_secret


ENV_NAME = "CRAWLER_CREDENTIAL_FERNET_KEYS"
ENCRYPTED_PREFIX = "fernet:v1:"


class CredentialConfigurationError(RuntimeError):
    """凭据加密配置缺失或无效。"""


class CredentialDecryptionError(RuntimeError):
    """已存储凭据无法用当前密钥解密。"""


class CredentialCipher:
    """使用首选 Fernet key 写入，并使用完整 key ring 读取。"""

    def __init__(self, fernets: list[Fernet]) -> None:
        self._primary = fernets[0]
        self._multi = MultiFernet(fernets)

    @classmethod
    def from_key_string(cls, raw: str) -> CredentialCipher:
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        try:
            if not parts:
                raise ValueError
            return cls([Fernet(part.encode("ascii")) for part in parts])
        except (TypeError, ValueError, UnicodeError) as error:
            raise CredentialConfigurationError(
                "Credential encryption key is missing or invalid"
            ) from error

    def encrypt(self, value: str) -> str:
        register_secret(value)
        if not value:
            return value
        token = self._primary.encrypt(value.encode("utf-8")).decode("ascii")
        return f"{ENCRYPTED_PREFIX}{token}"

    def decrypt(self, value: str) -> str:
        if not value:
            return value
        if not value.startswith(ENCRYPTED_PREFIX):
            register_secret(value)
            return value
        token = self._encoded_token(value)
        try:
            plaintext = self._multi.decrypt(token).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError) as error:
            raise CredentialDecryptionError(
                "Stored credential cannot be decrypted"
            ) from error
        register_secret(plaintext)
        return plaintext

    def needs_migration(self, value: str) -> bool:
        if not value:
            return False
        if not value.startswith(ENCRYPTED_PREFIX):
            return True
        token = self._encoded_token(value)
        try:
            self._primary.decrypt(token)
            return False
        except InvalidToken:
            self.decrypt(value)
            return True

    def migrate(self, value: str) -> str:
        if not self.needs_migration(value):
            return value
        if not value.startswith(ENCRYPTED_PREFIX):
            return self.encrypt(value)
        token = self._encoded_token(value)
        try:
            rotated = self._multi.rotate(token).decode("ascii")
            return f"{ENCRYPTED_PREFIX}{rotated}"
        except (InvalidToken, UnicodeError, ValueError) as error:
            raise CredentialDecryptionError(
                "Stored credential cannot be decrypted"
            ) from error

    @staticmethod
    def _encoded_token(value: str) -> bytes:
        try:
            return value.removeprefix(ENCRYPTED_PREFIX).encode("ascii")
        except UnicodeError as error:
            raise CredentialDecryptionError(
                "Stored credential cannot be decrypted"
            ) from error


@cache
def get_credential_cipher() -> CredentialCipher:
    return CredentialCipher.from_key_string(os.environ.get(ENV_NAME, ""))


def clear_credential_cipher_cache() -> None:
    get_credential_cipher.cache_clear()
