from __future__ import annotations
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class ProjectVisitCapacity(Base, TimestampMixin):
    """
    Configurable site-visit scheduling constraints for a project: how many
    concurrent visits the site can host, how long a visit occupies an
    executive, and the buffer kept between consecutive visits.
    """

    __tablename__ = "project_visit_capacities"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_project_visit_capacities_capacity_positive"),
        CheckConstraint("visit_duration_minutes > 0", name="ck_project_visit_capacities_duration_positive"),
        CheckConstraint("buffer_minutes >= 0", name="ck_project_visit_capacities_buffer_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    visit_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
