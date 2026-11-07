from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class BlockedPeriod(Base, TimestampMixin):
    """
    An absolute-time window (leave, break, or other unavailability) during
    which an executive cannot be offered or booked for a site visit,
    regardless of their recurring AvailabilityRule.
    """

    __tablename__ = "blocked_periods"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_blocked_periods_end_after_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    executive_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
