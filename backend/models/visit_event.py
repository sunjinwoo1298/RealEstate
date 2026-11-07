from __future__ import annotations
import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class VisitEventType(str, enum.Enum):
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"
    ATTENDANCE_MARKED = "ATTENDANCE_MARKED"


class VisitEvent(Base):
    """
    Append-only audit history for a SiteVisit: booking, cancellation,
    rescheduling and attendance changes. Never updated or deleted.
    """

    __tablename__ = "visit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site_visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[VisitEventType] = mapped_column(
        Enum(VisitEventType, name="visit_event_type", native_enum=True), nullable=False
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
