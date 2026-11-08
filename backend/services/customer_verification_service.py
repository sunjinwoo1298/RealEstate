from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.security import generate_secure_token, hash_token
from backend.models.customer_verification_token import CustomerVerificationToken, TokenPurpose

_EXPIRY_BY_PURPOSE = {
    TokenPurpose.EMAIL_VERIFICATION: lambda: timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
    TokenPurpose.PASSWORD_RESET: lambda: timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
}


class CustomerVerificationService:
    """
    Issues and validates single-use, hashed, expiring tokens for both email
    verification and password recovery (one reusable token-purpose model).
    """

    @staticmethod
    async def invalidate_active_tokens(
        db: AsyncSession, customer_account_id: uuid.UUID, purpose: TokenPurpose
    ) -> None:
        """Marks every still-usable token of this purpose for this account as used, superseding them."""
        now = datetime.now(timezone.utc)
        await db.execute(
            update(CustomerVerificationToken)
            .where(
                CustomerVerificationToken.customer_account_id == customer_account_id,
                CustomerVerificationToken.purpose == purpose,
                CustomerVerificationToken.used_at.is_(None),
            )
            .values(used_at=now)
        )

    @staticmethod
    async def issue_token(
        db: AsyncSession, customer_account_id: uuid.UUID, purpose: TokenPurpose
    ) -> Tuple[CustomerVerificationToken, str]:
        """
        Supersedes any previously issued, still-active token of the same
        purpose for this account, then issues and persists a new one.
        Does not commit -- the caller controls the transaction boundary.
        """
        await CustomerVerificationService.invalidate_active_tokens(db, customer_account_id, purpose)

        raw_token = generate_secure_token()
        expires_at = datetime.now(timezone.utc) + _EXPIRY_BY_PURPOSE[purpose]()
        token = CustomerVerificationToken(
            customer_account_id=customer_account_id,
            purpose=purpose,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
        db.add(token)
        await db.flush()
        return token, raw_token

    @staticmethod
    async def consume_token(
        db: AsyncSession, raw_token: str, purpose: TokenPurpose
    ) -> Optional[CustomerVerificationToken]:
        """
        Validates and atomically marks a token used via a single UPDATE ...
        WHERE used_at IS NULL, so two concurrent requests presenting the same
        raw token can never both succeed -- the second blocks on the row lock
        until the first transaction commits/rolls back, then its WHERE clause
        no longer matches. Returns None for any invalid/expired/already-used
        token (single generic failure case -- callers must not distinguish
        these to avoid leaking which failure occurred). Does not commit.
        """
        token_hash = hash_token(raw_token)
        now = datetime.now(timezone.utc)
        result = await db.execute(
            update(CustomerVerificationToken)
            .where(
                CustomerVerificationToken.token_hash == token_hash,
                CustomerVerificationToken.purpose == purpose,
                CustomerVerificationToken.used_at.is_(None),
                CustomerVerificationToken.expires_at >= now,
            )
            .values(used_at=now)
            .returning(CustomerVerificationToken.id)
        )
        row = result.first()
        if row is None:
            return None

        await db.flush()
        reloaded = await db.execute(select(CustomerVerificationToken).where(CustomerVerificationToken.id == row[0]))
        return reloaded.scalar_one()
