from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin


class ChannelType(str, enum.Enum):
    WEB_CHAT = "WEB_CHAT"


class ConversationStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class OwnershipStatus(str, enum.Enum):
    AI_ACTIVE = "AI_ACTIVE"
    PENDING_ASSIGNMENT = "PENDING_ASSIGNMENT"
    HUMAN_ACTIVE = "HUMAN_ACTIVE"
    RESOLVED = "RESOLVED"


class ConversationLanguage(str, enum.Enum):
    EN = "EN"
    HI = "HI"
    GU = "GU"


class ConversationState(str, enum.Enum):
    DISCOVERY = "DISCOVERY"
    QUALIFIED = "QUALIFIED"
    VISIT_REQUESTED = "VISIT_REQUESTED"
    VISIT_BOOKED = "VISIT_BOOKED"


class Conversation(Base, TimestampMixin):
    """
    One buyer conversation thread against a single channel. A Lead may have
    multiple conversations over time; conversation_state and ownership_status
    are tracked independently of Lead.lead_status.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, name="channel_type", native_enum=True), nullable=False, default=ChannelType.WEB_CHAT
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status", native_enum=True),
        nullable=False,
        default=ConversationStatus.ACTIVE,
    )
    ownership_status: Mapped[OwnershipStatus] = mapped_column(
        Enum(OwnershipStatus, name="ownership_status", native_enum=True),
        nullable=False,
        default=OwnershipStatus.AI_ACTIVE,
    )
    language: Mapped[ConversationLanguage] = mapped_column(
        Enum(ConversationLanguage, name="conversation_language", native_enum=True),
        nullable=False,
        default=ConversationLanguage.EN,
    )
    conversation_state: Mapped[ConversationState] = mapped_column(
        Enum(ConversationState, name="conversation_state", native_enum=True),
        nullable=False,
        default=ConversationState.DISCOVERY,
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Nullable: NULL means an anonymous buyer-chat conversation (Feature 03),
    # unchanged by this feature. A non-null value means the conversation was
    # created by an authenticated customer (Feature 12) and access to it must
    # be authorized solely by this column, never by lead_id or a caller
    # supplied id.
    customer_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    lead: Mapped["Lead"] = relationship("Lead")
    messages: Mapped[List["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at.asc()"
    )
    buyer_sessions: Mapped[List["BuyerSession"]] = relationship(
        "BuyerSession", back_populates="conversation", cascade="all, delete-orphan"
    )
