from __future__ import annotations
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash

from backend.core.config import settings
from backend.core.exceptions import ValidationException

_password_hasher = PasswordHasher()

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
CUSTOMER_ACCESS_TOKEN_TYPE = "customer_access"


def hash_password(plain_password: str) -> str:
    """Hashes a plaintext password using Argon2."""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verifies a plaintext password against an Argon2 hash. Never raises on mismatch."""
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False


def generate_refresh_token() -> str:
    """Generates a cryptographically random opaque refresh token."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    """Hashes a refresh token for storage; raw tokens are never persisted."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(user_id: str, role: str) -> str:
    """Creates a short-lived signed JWT access token for a staff user."""
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a JWT access token's signature, expiry, issuer and audience. Raises jwt.PyJWTError on failure."""
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
    )
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Not an access token")
    return payload


def create_customer_access_token(customer_account_id: str) -> str:
    """
    Creates a short-lived signed JWT access token for a customer account.
    Uses a distinct "type" claim from staff access tokens so a customer token
    can never be decoded as a staff token (or vice versa) even if a caller
    presents it to the wrong dependency.
    """
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": customer_account_id,
        "type": CUSTOMER_ACCESS_TOKEN_TYPE,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.CUSTOMER_ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_customer_access_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a customer JWT access token. Raises jwt.PyJWTError on failure."""
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
    )
    if payload.get("type") != CUSTOMER_ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Not a customer access token")
    return payload


def validate_password_strength(password: str) -> None:
    """
    Enforces minimum password strength for customer-facing account creation
    and password resets. Raises ValidationException on failure.
    """
    if len(password) < 8:
        raise ValidationException("Password must be at least 8 characters long")
    if not re.search(r"[A-Za-z]", password):
        raise ValidationException("Password must contain at least one letter")
    if not re.search(r"[0-9]", password):
        raise ValidationException("Password must contain at least one number")


def generate_secure_token() -> str:
    """Generates a cryptographically secure random token for email verification / password reset links."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Hashes a one-time token (verification/reset) for storage; raw tokens are never persisted."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
