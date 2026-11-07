from __future__ import annotations
import uuid
from datetime import time
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class AvailabilityRule(Base, TimestampMixin):
    """
    A recurring weekly working-hours window for a sales executive, in
    Asia/Kolkata local wall-clock time. day_of_week follows Python's
    date.weekday() convention: Monday=0 .. Sunday=6.

    project_id is nullable: a null project_id means the rule applies to the
    executive across all projects; a set project_id scopes the rule to a
    single project (an executive can have different hours per project).
    """

    __tablename__ = "availability_rules"
    __table_args__ = (
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_availability_rules_day_of_week"),
        CheckConstraint("end_time > start_time", name="ck_availability_rules_end_after_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    executive_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    end_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
