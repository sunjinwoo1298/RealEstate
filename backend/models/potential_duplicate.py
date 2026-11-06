from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin


class DuplicateReviewStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED_DUPLICATE = "CONFIRMED_DUPLICATE"
    REJECTED = "REJECTED"


class PotentialDuplicateMatch(Base, TimestampMixin):
    """
    Records an ambiguous fuzzy (name-similarity) match between a newly
    created Lead and an existing candidate Lead. Ambiguous matches are
    never merged automatically; this table exists purely for manual review.
    """

    __tablename__ = "potential_duplicate_matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    new_lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    existing_lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_reason: Mapped[str] = mapped_column(String(100), nullable=False)
    similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[DuplicateReviewStatus] = mapped_column(
        Enum(DuplicateReviewStatus, name="duplicate_review_status", native_enum=True),
        nullable=False,
        default=DuplicateReviewStatus.PENDING_REVIEW,
    )
    reviewed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    new_lead: Mapped["Lead"] = relationship("Lead", foreign_keys=[new_lead_id])
    existing_lead: Mapped["Lead"] = relationship("Lead", foreign_keys=[existing_lead_id])
