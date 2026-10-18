import pytest
from cryptography.fernet import Fernet

from common.errors import redact_secrets
from security.credentials import (
    ENCRYPTED_PREFIX,
    CredentialCipher,
    CredentialConfigurationError,
    CredentialDecryptionError,
)


def make_cipher(*keys: bytes) -> CredentialCipher:
    return CredentialCipher.from_key_string(
        ",".join(key.decode("ascii") for key in keys)
    )


def test_encrypt_round_trip_never_contains_plaintext():
    cipher = make_cipher(Fernet.generate_key())

    stored = cipher.encrypt("provider-secret-value")

    assert stored.startswith(ENCRYPTED_PREFIX)
    assert "provider-secret-value" not in stored
    assert cipher.decrypt(stored) == "provider-secret-value"


def test_legacy_plaintext_is_readable_and_requires_migration():
    cipher = make_cipher(Fernet.generate_key())

    assert cipher.decrypt("legacy-secret") == "legacy-secret"
    assert cipher.needs_migration("legacy-secret") is True
    assert cipher.migrate("legacy-secret").startswith(ENCRYPTED_PREFIX)


def test_old_key_ciphertext_is_rotated_to_primary_key():
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    old_stored = make_cipher(old_key).encrypt("rotated-secret")
    rotating = make_cipher(new_key, old_key)

    assert rotating.needs_migration(old_stored) is True
    migrated = rotating.migrate(old_stored)

    assert migrated != old_stored
    assert make_cipher(new_key).decrypt(migrated) == "rotated-secret"
    assert rotating.needs_migration(migrated) is False


@pytest.mark.parametrize("raw", ["", "not-a-fernet-key", "key-a,key-b"])
def test_missing_or_invalid_key_has_fixed_error(raw):
    with pytest.raises(
        CredentialConfigurationError,
        match="Credential encryption key is missing or invalid",
    ):
        CredentialCipher.from_key_string(raw)


def test_corrupt_ciphertext_has_fixed_error():
    cipher = make_cipher(Fernet.generate_key())

    with pytest.raises(
        CredentialDecryptionError,
        match="Stored credential cannot be decrypted",
    ):
        cipher.decrypt(f"{ENCRYPTED_PREFIX}corrupt")


def test_encrypt_registers_plaintext_for_log_redaction():
    secret = "encrypt-boundary-secret-147"

    make_cipher(Fernet.generate_key()).encrypt(secret)

    assert redact_secrets(f"rejected {secret}") == "rejected ***"


def test_decrypt_registers_ciphertext_plaintext_for_log_redaction():
    key = Fernet.generate_key()
    secret = "decrypt-boundary-secret-258"
    stored = f"{ENCRYPTED_PREFIX}{Fernet(key).encrypt(secret.encode()).decode()}"

    assert make_cipher(key).decrypt(stored) == secret
    assert redact_secrets(f"rejected {secret}") == "rejected ***"


def test_decrypt_registers_legacy_plaintext_for_log_redaction():
    secret = "legacy-boundary-secret-369"

    assert make_cipher(Fernet.generate_key()).decrypt(secret) == secret
    assert redact_secrets(f"rejected {secret}") == "rejected ***"
