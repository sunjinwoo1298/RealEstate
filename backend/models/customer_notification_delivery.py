from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class CustomerNotificationEvent(str, enum.Enum):
    SITE_VISIT_BOOKED = "SITE_VISIT_BOOKED"
    SITE_VISIT_RESCHEDULED = "SITE_VISIT_RESCHEDULED"
    SITE_VISIT_CANCELLED = "SITE_VISIT_CANCELLED"
    SITE_VISIT_REMINDER_24H = "SITE_VISIT_REMINDER_24H"
    SITE_VISIT_REMINDER_2H = "SITE_VISIT_REMINDER_2H"


class CustomerNotificationChannel(str, enum.Enum):
    EMAIL = "EMAIL"


class CustomerDeliveryStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    # Delivered only to the development logging provider -- never a real send.
    SIMULATED = "SIMULATED"
    FAILED = "FAILED"
    # Superseded/stale (e.g. its booking version was rescheduled/cancelled).
    CANCELLED = "CANCELLED"
    # Deliberately not attempted (no verified email, customer opted out).
    SKIPPED = "SKIPPED"


def _enum(enum_cls: type, name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class CustomerNotificationDelivery(Base, TimestampMixin):
    """
    Durable outbox of customer-facing transactional messages (Feature 14).

    Rows for booking/reschedule/cancellation are inserted in the *same*
    transaction as the booking change, so a rolled-back booking leaves no
    deliverable row and a committed one can never lose its notification.
    Reminder rows (visit_reminder_id set) are owned and dispatched by the
    Feature 07 reminder worker; all other rows are claimed by the customer
    email worker. This table is deliberately separate from the staff-only
    `notifications` table.
    """

    __tablename__ = "customer_notification_deliveries"
    __table_args__ = (
        Index("ix_cnd_claim", "status", "next_attempt_at"),
        Index("ix_cnd_customer_history", "customer_account_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_accounts.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    site_visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site_visits.id", ondelete="CASCADE"), nullable=True, index=True
    )
    visit_reminder_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visit_reminders.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    booking_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    event_type: Mapped[CustomerNotificationEvent] = mapped_column(
        _enum(CustomerNotificationEvent, "customer_notification_event"), nullable=False
    )
    channel: Mapped[CustomerNotificationChannel] = mapped_column(
        _enum(CustomerNotificationChannel, "customer_notification_channel"),
        nullable=False,
        default=CustomerNotificationChannel.EMAIL,
    )
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    template_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    status: Mapped[CustomerDeliveryStatus] = mapped_column(
        _enum(CustomerDeliveryStatus, "customer_delivery_status"),
        nullable=False,
        default=CustomerDeliveryStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
