"""Credential encryption for connector secrets (Fernet, key derived from SECRET_KEY).

Credentials are stored encrypted at rest in the database and never returned
by the API (only masked). The encryption key is derived from the application
SECRET_KEY with HKDF-SHA256 using a distinct info label so a leaked connector
key does not imply the signing key and vice versa.
"""
from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

_HKDF_INFO = b"nexus-connector-credentials-v1"


class CredentialError(RuntimeError):
    pass


def _fernet() -> Fernet:
    secret = (settings.secret_key or "").encode("utf-8")
    if not secret:
        raise CredentialError("SECRET_KEY must be configured to encrypt connector credentials")
    kdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO)
    key = base64.urlsafe_b64encode(kdf.derive(secret))
    return Fernet(key)


def encrypt_credentials(credentials: dict[str, Any]) -> str:
    """Encrypt a credentials dict into a Fernet token string."""
    f = _fernet()
    return f.encrypt(json.dumps(credentials, ensure_ascii=False).encode("utf-8")).decode("ascii")


def decrypt_credentials(token: str | None) -> dict[str, Any]:
    """Decrypt a Fernet token back into a credentials dict."""
    if not token:
        return {}
    try:
        raw = _fernet().decrypt(token.encode("utf-8"))
    except (InvalidToken, binascii.Error) as e:
        raise CredentialError(f"Stored credentials cannot be decrypted (wrong SECRET_KEY or corrupted): {e}") from e
    except Exception as e:  # noqa: BLE001
        raise CredentialError(f"Credential decryption failed: {e}") from e
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise CredentialError(f"Decrypted credentials are not valid JSON: {e}") from e


def mask_credentials(credentials: dict[str, Any]) -> dict[str, Any]:
    """Mask secret values for API responses, preserving shape."""
    masked: dict[str, Any] = {}
    for key, value in credentials.items():
        if not isinstance(value, str) or not value:
            masked[key] = value
            continue
        if len(value) <= 4:
            masked[key] = "••••"
        else:
            masked[key] = f"{value[:2]}••••{value[-2:]}"
    return masked
