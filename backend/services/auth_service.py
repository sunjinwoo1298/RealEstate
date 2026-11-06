from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import UnauthorizedException
from backend.core.logging import logger
from backend.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from backend.models.auth_session import AuthSession
from backend.models.user import User

INVALID_CREDENTIALS_MESSAGE = "Invalid email or password"


class AuthService:
    """Coordinates staff login, refresh-token rotation and session revocation."""

    @staticmethod
    async def authenticate(db: AsyncSession, email: str, password: str) -> User:
        """
        Validates staff credentials. Raises UnauthorizedException for any failure
        case (unknown email, wrong password, inactive account) with an identical
        message, so login failures never reveal whether an email exists.
        """
        normalized_email = email.strip().lower()
        result = await db.execute(select(User).where(User.email == normalized_email))
        user = result.scalar_one_or_none()

        if user is None:
            # Perform a dummy verification to keep response timing similar
            # regardless of whether the account exists.
            verify_password(password, "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$ZHVtbXloYXNo")
            raise UnauthorizedException(INVALID_CREDENTIALS_MESSAGE)

        if not verify_password(password, user.password_hash):
            raise UnauthorizedException(INVALID_CREDENTIALS_MESSAGE)

        if not user.is_active:
            raise UnauthorizedException("This account has been deactivated")

        return user

    @staticmethod
    async def issue_session(db: AsyncSession, user: User) -> Tuple[str, str, int]:
        """
        Creates a new access token and a new rotated refresh-token session.
        Returns (access_token, raw_refresh_token, access_token_expires_in_seconds).
        """
        access_token = create_access_token(user_id=str(user.id), role=user.role.value)
        raw_refresh_token = generate_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        session = AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(raw_refresh_token),
            expires_at=expires_at,
        )
        db.add(session)
        await db.commit()

        return access_token, raw_refresh_token, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @staticmethod
    async def rotate_refresh_token(db: AsyncSession, raw_refresh_token: str) -> Tuple[str, str, int]:
        """
        Validates and rotates a refresh token. On any sign of reuse of an already
        revoked/rotated token, revokes the entire session chain for that user as
        a precaution and rejects the request.
        """
        token_hash = hash_refresh_token(raw_refresh_token)
        result = await db.execute(
            select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
        )
        session = result.scalar_one_or_none()

        if session is None:
            raise UnauthorizedException("Invalid refresh token")

        now = datetime.now(timezone.utc)
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if session.revoked_at is not None:
            # Reuse of a rotated/revoked token: treat as compromised and revoke
            # every active session belonging to this user.
            logger.warning(f"Refresh token reuse detected for user_id={session.user_id}")
            await AuthService._revoke_all_sessions(db, session.user_id)
            raise UnauthorizedException("Refresh token has been revoked")

        if expires_at < now:
            raise UnauthorizedException("Refresh token has expired")

        result = await db.execute(select(User).where(User.id == session.user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise UnauthorizedException("Account is not available")

        access_token = create_access_token(user_id=str(user.id), role=user.role.value)
        new_raw_refresh_token = generate_refresh_token()
        new_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        new_session = AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(new_raw_refresh_token),
            expires_at=new_expires_at,
        )
        db.add(new_session)
        await db.flush()

        session.revoked_at = now
        session.replaced_by_id = new_session.id
        await db.commit()

        return access_token, new_raw_refresh_token, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @staticmethod
    async def revoke_refresh_token(db: AsyncSession, raw_refresh_token: str) -> None:
        """Revokes a single refresh-token session (logout)."""
        token_hash = hash_refresh_token(raw_refresh_token)
        result = await db.execute(
            select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
        )
        session = result.scalar_one_or_none()
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            await db.commit()

    @staticmethod
    async def _revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
        result = await db.execute(
            select(AuthSession).where(
                AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
            )
        )
        now = datetime.now(timezone.utc)
        for s in result.scalars().all():
            s.revoked_at = now
        await db.commit()
