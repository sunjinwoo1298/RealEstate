from __future__ import annotations
import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


class SourceType(str, enum.Enum):
    WEBSITE = "WEBSITE"
    PROPERTY_PORTAL = "PROPERTY_PORTAL"
    SOCIAL_AD = "SOCIAL_AD"
    HOARDING = "HOARDING"
    MANUAL = "MANUAL"
    CSV_IMPORT = "CSV_IMPORT"


class LeadSource(Base):
    """
    One individual enquiry submitted through a particular source/channel.
    Original enquiry records are never discarded when leads are deduplicated.
    """

    __tablename__ = "lead_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", native_enum=True), nullable=False, index=True
    )
    external_lead_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    campaign_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    lead: Mapped["Lead"] = relationship("Lead", back_populates="sources")
