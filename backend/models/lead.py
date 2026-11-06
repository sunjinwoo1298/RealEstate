from __future__ import annotations
import enum
import uuid
from typing import List, Optional

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey

from backend.models.base import Base, TimestampMixin


class LeadStatus(str, enum.Enum):
    NEW = "NEW"
    AI_CONTACTED = "AI_CONTACTED"
    QUALIFIED = "QUALIFIED"
    VISIT_REQUESTED = "VISIT_REQUESTED"
    VISIT_BOOKED = "VISIT_BOOKED"
    VISIT_COMPLETED = "VISIT_COMPLETED"
    CONVERTED = "CONVERTED"
    LOST = "LOST"
    OPTED_OUT = "OPTED_OUT"


class ConsentStatus(str, enum.Enum):
    GRANTED = "GRANTED"
    DECLINED = "DECLINED"
    NOT_RECORDED = "NOT_RECORDED"


class Lead(Base, TimestampMixin):
    """
    Canonical buyer profile. One Lead can be associated with multiple
    LeadSource (enquiry) records across different channels.
    """

    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    normalized_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    preferred_language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    lead_status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, name="lead_status", native_enum=True),
        nullable=False,
        default=LeadStatus.NEW,
    )
    assigned_executive_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    consent_status: Mapped[ConsentStatus] = mapped_column(
        Enum(ConsentStatus, name="consent_status", native_enum=True),
        nullable=False,
        default=ConsentStatus.NOT_RECORDED,
    )

    sources: Mapped[List["LeadSource"]] = relationship(
        "LeadSource", back_populates="lead", cascade="all, delete-orphan", order_by="LeadSource.submitted_at.desc()"
    )
