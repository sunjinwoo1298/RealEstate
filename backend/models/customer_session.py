from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin


class CustomerSession(Base, TimestampMixin):
    """
    Tracks an issued customer refresh token (hashed) for rotation and
    revocation. Kept in its own table, entirely isolated from staff
    `AuthSession` rows, per the customer/staff authentication separation
    required for this feature.
    """

    __tablename__ = "customer_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_sessions.id", ondelete="SET NULL"), nullable=True
    )

    customer_account: Mapped["CustomerAccount"] = relationship("CustomerAccount", back_populates="sessions")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
