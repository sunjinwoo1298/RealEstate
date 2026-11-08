from __future__ import annotations
import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


class TokenPurpose(str, enum.Enum):
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
    PASSWORD_RESET = "PASSWORD_RESET"


class CustomerVerificationToken(Base):
    """
    Single-use, hashed, expiring token backing both email verification and
    password recovery (a reusable token-purpose design, per spec, rather than
    two near-identical models). Raw tokens are never persisted -- only the
    SHA-256 hash of the token delivered to the customer.
    """

    __tablename__ = "customer_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[TokenPurpose] = mapped_column(
        Enum(TokenPurpose, name="token_purpose", native_enum=True), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    customer_account: Mapped["CustomerAccount"] = relationship("CustomerAccount", back_populates="verification_tokens")

    @property
    def is_usable(self) -> bool:
        if self.used_at is not None:
            return False
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at >= datetime.now(timezone.utc)
