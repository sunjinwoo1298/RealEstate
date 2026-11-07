from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class ReminderType(str, enum.Enum):
    H24 = "24H"
    H2 = "2H"


class ReminderStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    SIMULATED = "SIMULATED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class VisitReminder(Base, TimestampMixin):
    """
    A single scheduled 24-hour or 2-hour reminder for a confirmed SiteVisit.

    booking_version is a snapshot of SiteVisit.booking_version at the time
    this reminder was created. A reschedule bumps SiteVisit.booking_version
    and creates new reminder rows rather than mutating these -- the unique
    constraint on (site_visit_id, reminder_type, booking_version) prevents
    a duplicate reminder for the same schedule, and the worker re-checks the
    visit's *current* booking_version before sending so a stale reminder for
    a since-rescheduled or cancelled visit is never delivered.
    """

    __tablename__ = "visit_reminders"
    __table_args__ = (
        UniqueConstraint(
            "site_visit_id", "reminder_type", "booking_version", name="uq_visit_reminders_booking_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site_visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reminder_type: Mapped[ReminderType] = mapped_column(
        Enum(
            ReminderType,
            name="reminder_type",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(
            ReminderStatus,
            name="reminder_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ReminderStatus.SCHEDULED,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    booking_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
