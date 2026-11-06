from __future__ import annotations
import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


class SenderType(str, enum.Enum):
    BUYER = "BUYER"
    AI = "AI"
    STAFF = "STAFF"
    SYSTEM = "SYSTEM"


class MessageType(str, enum.Enum):
    TEXT = "TEXT"
    SYSTEM_EVENT = "SYSTEM_EVENT"


class Message(Base):
    """
    One persisted conversation message. sender_id is nullable and intentionally
    has no foreign key, since it may reference a buyer (no staff account) or a
    staff user depending on sender_type.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_type: Mapped[SenderType] = mapped_column(
        Enum(SenderType, name="sender_type", native_enum=True), nullable=False
    )
    sender_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[MessageType] = mapped_column(
        Enum(MessageType, name="message_type", native_enum=True), nullable=False, default=MessageType.TEXT
    )
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
