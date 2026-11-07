from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class NotificationType(str, enum.Enum):
    HANDOFF_ASSIGNED = "HANDOFF_ASSIGNED"


class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class Notification(Base, TimestampMixin):
    """
    Internal notification mechanism for staff (e.g. an executive being
    assigned a handoff). Delivery is in-app only -- external channels
    (WhatsApp/email) are explicitly out of scope. The unique constraint on
    (recipient_id, reference_id, notification_type) makes retried delivery
    attempts idempotent: a repeat never creates a second row for the same
    event.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("recipient_id", "reference_id", "notification_type", name="uq_notifications_dedupe"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type", native_enum=True), nullable=False
    )
    reference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status", native_enum=True),
        nullable=False,
        default=NotificationStatus.PENDING,
    )
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
