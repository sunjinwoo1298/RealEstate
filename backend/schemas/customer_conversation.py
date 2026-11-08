from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.models.conversation import ConversationLanguage, ConversationState, ConversationStatus, OwnershipStatus
from backend.models.handoff import HandoffStatus
from backend.models.message import MessageType, SenderType


class CustomerConversationPublic(BaseModel):
    """
    The customer-facing conversation representation. Deliberately excludes
    lead_id (customers never see or supply a Lead id -- access is authorized
    solely by customer_account_id, never by a caller-visible Lead reference).
    """

    id: uuid.UUID
    status: ConversationStatus
    ownership_status: OwnershipStatus
    language: ConversationLanguage
    conversation_state: ConversationState
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime]

    model_config = {"from_attributes": True}


class CustomerConversationListItem(CustomerConversationPublic):
    last_message_preview: Optional[str] = None
    last_message_sender_type: Optional[SenderType] = None


class CustomerConversationListResponse(BaseModel):
    items: List[CustomerConversationListItem]
    total: int


class CustomerMessagePublic(BaseModel):
    """
    Customer-facing message representation. Deliberately excludes the
    internal `extra_metadata` (model name, latency, retrieval references,
    tool-call log, guardrail flags) -- never reveal internal AI/CRM
    diagnostics to a customer.
    """

    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: SenderType
    content: str
    message_type: MessageType
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerMessageListResponse(BaseModel):
    items: List[CustomerMessagePublic]
    total: int


class CustomerSendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=settings.CHAT_MESSAGE_MAX_LENGTH)


class CustomerHandoffStatus(BaseModel):
    """
    Minimal, customer-safe handoff status -- deliberately omits
    assigned_executive_id and the internal escalation reason/summary, which
    are staff-only context (HandoffDetail), not something a customer needs.
    """

    status: HandoffStatus
    created_at: datetime

    model_config = {"from_attributes": True}
