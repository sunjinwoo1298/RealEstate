from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin


class HandoffStatus(str, enum.Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


class HandoffReason(str, enum.Enum):
    BUYER_REQUEST = "BUYER_REQUEST"
    UNSUPPORTED_QUERY = "UNSUPPORTED_QUERY"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    COMPLAINT = "COMPLAINT"
    OTHER = "OTHER"


class Handoff(Base, TimestampMixin):
    """
    One escalation workflow for a conversation. At most one Handoff with a
    non-terminal status (PENDING/ASSIGNED/ACCEPTED) may exist per
    conversation at a time -- enforced by a partial unique index -- so
    retrying an escalation never creates a duplicate; HandoffService.create_handoff
    returns the existing active row instead.
    """

    __tablename__ = "handoffs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_executive_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[HandoffStatus] = mapped_column(
        Enum(HandoffStatus, name="handoff_status", native_enum=True), nullable=False, default=HandoffStatus.PENDING
    )
    reason: Mapped[HandoffReason] = mapped_column(
        Enum(HandoffReason, name="handoff_reason", native_enum=True), nullable=False
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped["Conversation"] = relationship("Conversation")
    lead: Mapped["Lead"] = relationship("Lead")
    assignments: Mapped[list["ConversationAssignment"]] = relationship(
        "ConversationAssignment", back_populates="handoff", order_by="ConversationAssignment.assigned_at.desc()"
    )
