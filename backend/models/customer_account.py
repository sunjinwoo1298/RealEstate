from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin


class CustomerAccountStatus(str, enum.Enum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"


class CustomerAccount(Base, TimestampMixin):
    """
    Customer (buyer-facing) identity. Entirely separate from staff `User`
    records -- a CustomerAccount is never granted staff roles or access.
    At most one CustomerAccount may be linked to a given canonical Lead
    (enforced by the unique constraint on lead_id).
    """

    __tablename__ = "customer_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    phone_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CustomerAccountStatus] = mapped_column(
        Enum(CustomerAccountStatus, name="customer_account_status", native_enum=True),
        nullable=False,
        default=CustomerAccountStatus.PENDING_VERIFICATION,
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), unique=True, nullable=True, index=True
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Consent, recorded separately per spec section 13 ("Record privacy/terms
    # acceptance and optional marketing consent separately"). Not in the
    # spec's own "suggested fields" list for CustomerAccount, but required by
    # its security/privacy section -- added here rather than inventing a
    # separate consent table, mirroring how `Lead.consent_status` is a plain
    # column rather than its own table.
    privacy_policy_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    marketing_consent_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Feature 14: customer control over essential visit emails (booking,
    # reschedule, cancellation, reminders). Distinct from marketing_consent
    # above -- marketing email does not exist yet and is never inferred from
    # or substituted for this flag.
    transactional_email_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    notification_preferences_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[List["CustomerSession"]] = relationship(
        "CustomerSession", back_populates="customer_account", cascade="all, delete-orphan"
    )
    verification_tokens: Mapped[List["CustomerVerificationToken"]] = relationship(
        "CustomerVerificationToken", back_populates="customer_account", cascade="all, delete-orphan"
    )
