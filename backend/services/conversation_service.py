from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import ConflictException, NotFoundException, ValidationException
from backend.models.conversation import ChannelType, Conversation, ConversationLanguage, ConversationState, ConversationStatus
from backend.models.lead import ConsentStatus, Lead
from backend.models.lead_source import SourceType
from backend.models.message import Message, MessageType, SenderType
from backend.services.lead_ingestion_service import LeadIngestionService

# Validated forward-only state transitions. Not yet exposed via an API in this
# feature; future features (qualification, booking) will drive transitions
# through this map rather than setting conversation_state directly.
ALLOWED_STATE_TRANSITIONS: Dict[ConversationState, set] = {
    ConversationState.DISCOVERY: {ConversationState.QUALIFIED},
    ConversationState.QUALIFIED: {ConversationState.VISIT_REQUESTED},
    ConversationState.VISIT_REQUESTED: {ConversationState.VISIT_BOOKED},
    ConversationState.VISIT_BOOKED: set(),
}


@dataclass
class ChatSessionResult:
    conversation: Conversation
    lead: Lead
    created_new_lead: bool


class ConversationService:
    """Persistence and lifecycle operations for conversations and messages."""

    @staticmethod
    async def create_chat_session(
        db: AsyncSession,
        *,
        full_name: str,
        raw_phone: str,
        raw_email: Optional[str],
        preferred_language: ConversationLanguage,
        consent_given: bool,
    ) -> ChatSessionResult:
        """
        Resolves or creates the buyer's canonical Lead via the existing
        identity-resolution service, then opens a new conversation thread
        for this chat widget session, initialized to DISCOVERY/AI_ACTIVE.
        """
        if not consent_given:
            raise ValidationException("Consent is required to start a chat session")

        ingestion = await LeadIngestionService.ingest(
            db,
            full_name=full_name,
            raw_phone=raw_phone,
            raw_email=raw_email,
            preferred_language=preferred_language.value,
            source_type=SourceType.WEBSITE,
            external_lead_id=None,
            campaign_name="Web Chat Widget",
            raw_payload={"channel": "WEB_CHAT", "consent_given": consent_given},
            consent_status=ConsentStatus.GRANTED,
        )

        conversation = Conversation(
            lead_id=ingestion.lead.id,
            channel=ChannelType.WEB_CHAT,
            status=ConversationStatus.ACTIVE,
            language=preferred_language,
            conversation_state=ConversationState.DISCOVERY,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

        return ChatSessionResult(
            conversation=conversation, lead=ingestion.lead, created_new_lead=ingestion.created_new_lead
        )

    @staticmethod
    async def get_conversation_by_id(db: AsyncSession, conversation_id: uuid.UUID) -> Conversation:
        result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise NotFoundException("Conversation not found")
        return conversation

    @staticmethod
    def assert_active(conversation: Conversation) -> None:
        if conversation.status != ConversationStatus.ACTIVE:
            raise ConflictException("This conversation is closed")

    @staticmethod
    async def list_messages(
        db: AsyncSession, conversation_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Message], int]:
        count_result = await db.execute(
            select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)
        )
        total = count_result.scalar_one()

        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def post_message(
        db: AsyncSession,
        conversation: Conversation,
        *,
        sender_type: SenderType,
        sender_id: Optional[uuid.UUID],
        content: str,
        message_type: MessageType = MessageType.TEXT,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        ConversationService.assert_active(conversation)

        stripped = content.strip()
        if not stripped:
            raise ValidationException("Message content cannot be empty")
        if len(stripped) > settings.CHAT_MESSAGE_MAX_LENGTH:
            raise ValidationException(
                f"Message exceeds the maximum length of {settings.CHAT_MESSAGE_MAX_LENGTH} characters"
            )

        message = Message(
            conversation_id=conversation.id,
            sender_type=sender_type,
            sender_id=sender_id,
            content=stripped,
            message_type=message_type,
            extra_metadata=extra_metadata,
        )
        db.add(message)

        now = datetime.now(timezone.utc)
        conversation.last_message_at = now

        await db.commit()
        await db.refresh(message)
        return message

    @staticmethod
    def transition_state(conversation: Conversation, new_state: ConversationState) -> None:
        """
        Validates and applies a conversation_state transition. Raises
        ValidationException for any transition not explicitly allowed.
        Not called by any endpoint in this feature; reserved for future
        qualification/booking features to drive state changes safely.
        """
        allowed = ALLOWED_STATE_TRANSITIONS.get(conversation.conversation_state, set())
        if new_state not in allowed:
            raise ValidationException(
                f"Cannot transition conversation from {conversation.conversation_state.value} to {new_state.value}"
            )
        conversation.conversation_state = new_state

    @staticmethod
    async def list_conversations_staff(
        db: AsyncSession,
        *,
        status: Optional[ConversationStatus] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Tuple[Conversation, Lead]], int]:
        base_query = select(Conversation, Lead).join(Lead, Lead.id == Conversation.lead_id)
        count_query = select(func.count()).select_from(Conversation)

        if status is not None:
            base_query = base_query.where(Conversation.status == status)
            count_query = count_query.where(Conversation.status == status)

        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        base_query = base_query.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)
        result = await db.execute(base_query)
        return [(row[0], row[1]) for row in result.all()], total
