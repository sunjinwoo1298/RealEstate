from __future__ import annotations
import base64
import binascii
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.core.config import settings
from backend.core.logging import logger

_NONCE_BYTES = 12


def _load_key() -> Optional[bytes]:
    raw = settings.REFRESH_RECOVERY_KEY.strip()
    if not raw:
        return None
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (binascii.Error, ValueError):
        logger.error("REFRESH_RECOVERY_KEY is not valid base64url; refresh recovery is disabled")
        return None
    if len(key) != 32:
        logger.error("REFRESH_RECOVERY_KEY must decode to exactly 32 bytes; refresh recovery is disabled")
        return None
    return key


def is_enabled() -> bool:
    return settings.REFRESH_RECOVERY_GRACE_SECONDS > 0 and _load_key() is not None


def recovery_deadline(now: datetime) -> datetime:
    return now + timedelta(seconds=settings.REFRESH_RECOVERY_GRACE_SECONDS)


def _aad(previous_session_id: uuid.UUID, successor_session_id: uuid.UUID) -> bytes:
    # Binds the ciphertext to exactly this previous->successor pair, so a blob
    # can never be replayed to recover a different session's token.
    return f"{previous_session_id}:{successor_session_id}".encode()


def encrypt_successor(
    raw_successor_token: str, previous_session_id: uuid.UUID, successor_session_id: uuid.UUID
) -> Optional[str]:
    key = _load_key()
    if key is None:
        return None
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(
        nonce, raw_successor_token.encode(), _aad(previous_session_id, successor_session_id)
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_successor(
    blob: str, previous_session_id: uuid.UUID, successor_session_id: uuid.UUID
) -> Optional[str]:
    key = _load_key()
    if key is None:
        return None
    try:
        data = base64.urlsafe_b64decode(blob.encode())
        plaintext = AESGCM(key).decrypt(
            data[:_NONCE_BYTES], data[_NONCE_BYTES:], _aad(previous_session_id, successor_session_id)
        )
        return plaintext.decode()
    except (InvalidTag, binascii.Error, ValueError):
        logger.warning("Refresh recovery blob failed authentication; ignoring")
        return None


def within_window(recoverable_until: Optional[datetime], now: datetime) -> bool:
    if recoverable_until is None:
        return False
    if recoverable_until.tzinfo is None:
        recoverable_until = recoverable_until.replace(tzinfo=timezone.utc)
    return now <= recoverable_until
