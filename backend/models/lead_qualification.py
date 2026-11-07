from __future__ import annotations
import enum
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import Date, Enum, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin
from backend.models.conversation import ConversationLanguage


class ConfigurationType(str, enum.Enum):
    BHK_2 = "BHK_2"
    BHK_3 = "BHK_3"


class PurchasePurpose(str, enum.Enum):
    SELF_USE = "SELF_USE"
    INVESTMENT = "INVESTMENT"


class LeadQualification(Base, TimestampMixin):
    """
    The single current qualification snapshot for a buyer, extracted
    incrementally by the AI orchestrator. One row per lead; fields are
    merged (never blindly overwritten with null) as new information is
    extracted across messages.
    """

    __tablename__ = "lead_qualifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    configuration: Mapped[Optional[ConfigurationType]] = mapped_column(
        Enum(ConfigurationType, name="qualification_configuration", native_enum=True), nullable=True
    )
    budget_min: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    budget_max: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    purchase_purpose: Mapped[Optional[PurchasePurpose]] = mapped_column(
        Enum(PurchasePurpose, name="purchase_purpose", native_enum=True), nullable=True
    )
    preferred_language: Mapped[Optional[ConversationLanguage]] = mapped_column(
        Enum(ConversationLanguage, name="conversation_language", native_enum=True, create_type=False), nullable=True
    )
    preferred_visit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    lead: Mapped["Lead"] = relationship("Lead")
    project: Mapped[Optional["Project"]] = relationship("Project")
