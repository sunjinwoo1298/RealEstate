from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field

from backend.core.config import settings
from backend.models.conversation import ChannelType, ConversationLanguage, ConversationState, ConversationStatus, OwnershipStatus
from backend.models.message import MessageType, SenderType


class BuyerSessionCreateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=6, max_length=20)
    email: Optional[EmailStr] = None
    preferred_language: ConversationLanguage = ConversationLanguage.EN
    consent_given: bool = Field(description="Buyer must explicitly consent to be contacted")


class ConversationPublic(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    channel: ChannelType
    status: ConversationStatus
    ownership_status: OwnershipStatus
    language: ConversationLanguage
    conversation_state: ConversationState
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime]

    model_config = {"from_attributes": True}


class MessagePublic(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: SenderType
    sender_id: Optional[uuid.UUID]
    content: str
    message_type: MessageType
    metadata: Optional[Dict[str, Any]] = Field(default=None, validation_alias="extra_metadata")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class MessageListResponse(BaseModel):
    items: List[MessagePublic]
    total: int


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=settings.CHAT_MESSAGE_MAX_LENGTH)


class ConversationListItem(ConversationPublic):
    lead_full_name: str = ""
    lead_normalized_phone: Optional[str] = None


class ConversationListResponse(BaseModel):
    items: List[ConversationListItem]
    total: int
