from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import UnauthorizedException
from backend.core.security import generate_refresh_token, hash_refresh_token
from backend.models.buyer_session import BuyerSession


class BuyerSessionService:
    """
    Issues, validates and revokes opaque buyer chat session tokens. Only the
    SHA-256 hash of a session token is ever persisted; the raw token exists
    only in the Secure/HttpOnly cookie delivered to the buyer's browser.
    """

    @staticmethod
    async def create_session(db: AsyncSession, conversation_id: uuid.UUID) -> Tuple[BuyerSession, str]:
        raw_token = generate_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.BUYER_SESSION_EXPIRE_HOURS)

        session = BuyerSession(
            conversation_id=conversation_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=expires_at,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session, raw_token

    @staticmethod
    async def validate_session(db: AsyncSession, raw_token: str) -> BuyerSession:
        token_hash = hash_refresh_token(raw_token)
        result = await db.execute(select(BuyerSession).where(BuyerSession.token_hash == token_hash))
        session = result.scalar_one_or_none()

        if session is None:
            raise UnauthorizedException("Invalid or expired session")

        now = datetime.now(timezone.utc)
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if session.revoked_at is not None:
            raise UnauthorizedException("Session has been revoked")
        if expires_at < now:
            raise UnauthorizedException("Session has expired")

        return session

    @staticmethod
    async def revoke_session(db: AsyncSession, raw_token: str) -> None:
        token_hash = hash_refresh_token(raw_token)
        result = await db.execute(select(BuyerSession).where(BuyerSession.token_hash == token_hash))
        session = result.scalar_one_or_none()
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            await db.commit()
