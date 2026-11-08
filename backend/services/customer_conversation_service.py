from __future__ import annotations
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.core.exceptions import ConflictException, NotFoundException, ValidationException
from backend.models.conversation import (
    ChannelType,
    Conversation,
    ConversationLanguage,
    ConversationState,
    ConversationStatus,
    OwnershipStatus,
)
from backend.models.customer_account import CustomerAccount
from backend.models.handoff import Handoff, HandoffReason
from backend.models.message import Message, MessageType, SenderType
from backend.services.ai_orchestrator_service import AIOrchestratorService
from backend.services.assignment_service import AssignmentService
from backend.services.conversation_service import ConversationService
from backend.services.handoff_service import HandoffService
from backend.services.lead_service import LeadService

_VALID_LANGUAGES = {lang.value for lang in ConversationLanguage}


class CustomerConversationService:
    """
    Narrowly scoped customer-facing orchestration over the existing
    Conversation/Message/AI-orchestrator/handoff infrastructure (Features
    03/04/06) -- never a second AI pipeline, a second message store, or a
    duplicate handoff workflow. Every method here authorizes solely by
    `Conversation.customer_account_id == customer.id`; a caller-supplied
    Lead id or conversation id alone is never sufficient.
    """

    @staticmethod
    async def create_conversation(db: AsyncSession, customer: CustomerAccount) -> Conversation:
        """
        Per spec section 2: if the customer has no linked Lead, this must
        not silently create or claim one -- it returns a clear, safe error
        and leaves the account unchanged.
        """
        if customer.lead_id is None:
            raise ValidationException(
                "Your account is not yet linked to an enquiry. Please contact our support team before starting a chat."
            )

        lead = await LeadService.get_lead_by_id(db, customer.lead_id)
        language = (
            ConversationLanguage(lead.preferred_language)
            if lead.preferred_language in _VALID_LANGUAGES
            else ConversationLanguage.EN
        )

        conversation = Conversation(
            lead_id=customer.lead_id,
            customer_account_id=customer.id,
            channel=ChannelType.WEB_CHAT,
            status=ConversationStatus.ACTIVE,
            language=language,
            conversation_state=ConversationState.DISCOVERY,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return conversation

    @staticmethod
    async def get_owned_conversation(
        db: AsyncSession, customer: CustomerAccount, conversation_id: uuid.UUID
    ) -> Conversation:
        """
        Returns a 404 (never 403) for a conversation that doesn't exist,
        belongs to another customer, or is an anonymous buyer conversation
        (customer_account_id is NULL) -- so a caller can never distinguish
        "not yours" from "doesn't exist", per spec section 11.
        """
        result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conversation = result.scalar_one_or_none()
        if conversation is None or conversation.customer_account_id != customer.id:
            raise NotFoundException("Conversation not found")
        return conversation

    @staticmethod
    async def list_conversations(
        db: AsyncSession,
        customer: CustomerAccount,
        *,
        conversation_state: Optional[ConversationState] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Tuple[Conversation, Optional[Message]]], int]:
        base_query = select(Conversation).where(Conversation.customer_account_id == customer.id)
        count_query = (
            select(func.count()).select_from(Conversation).where(Conversation.customer_account_id == customer.id)
        )
        if conversation_state is not None:
            base_query = base_query.where(Conversation.conversation_state == conversation_state)
            count_query = count_query.where(Conversation.conversation_state == conversation_state)

        total = (await db.execute(count_query)).scalar_one()

        base_query = base_query.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)
        conversations = list((await db.execute(base_query)).scalars().all())
        if not conversations:
            return [], total

        # Batched latest-message lookup (one extra query, not N) -- same
        # technique VisitDisplayService uses to avoid N+1 when annotating a
        # list of parent rows with a derived child-row value.
        conversation_ids = [c.id for c in conversations]
        row_number = (
            func.row_number()
            .over(partition_by=Message.conversation_id, order_by=Message.created_at.desc())
            .label("rn")
        )
        subquery = (
            select(Message, row_number).where(Message.conversation_id.in_(conversation_ids)).subquery()
        )
        latest_message_alias = aliased(Message, subquery)
        latest_result = await db.execute(select(latest_message_alias).where(subquery.c.rn == 1))
        latest_by_conversation = {m.conversation_id: m for m in latest_result.scalars().all()}

        return [(c, latest_by_conversation.get(c.id)) for c in conversations], total

    @staticmethod
    async def list_messages(
        db: AsyncSession, conversation: Conversation, *, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Message], int]:
        return await ConversationService.list_messages(db, conversation.id, limit=limit, offset=offset)

    @staticmethod
    async def send_message(
        db: AsyncSession, customer: CustomerAccount, conversation: Conversation, content: str
    ) -> Message:
        """
        Persists the customer's message, then invokes the existing AI
        orchestrator only while the conversation is AI_ACTIVE -- the AI must
        never compete with a human during PENDING_ASSIGNMENT/HUMAN_ACTIVE,
        and a RESOLVED conversation must never silently reopen.
        """
        if conversation.ownership_status == OwnershipStatus.RESOLVED:
            raise ConflictException(
                "This conversation has been resolved. Please start a new conversation if you need further help."
            )

        message = await ConversationService.post_message(
            db,
            conversation,
            sender_type=SenderType.BUYER,
            sender_id=customer.id,
            content=content,
            message_type=MessageType.TEXT,
        )

        if conversation.ownership_status == OwnershipStatus.AI_ACTIVE:
            lead = await LeadService.get_lead_by_id(db, conversation.lead_id)
            await AIOrchestratorService.handle_buyer_message(db, conversation, lead, content)

        return message

    @staticmethod
    async def request_handoff(db: AsyncSession, customer: CustomerAccount, conversation: Conversation) -> Handoff:
        """
        Idempotent via the existing HandoffService -- a repeated request
        returns the existing active handoff rather than creating a duplicate.
        """
        lead = await LeadService.get_lead_by_id(db, conversation.lead_id)
        handoff = await HandoffService.create_handoff(
            db, conversation, lead, reason=HandoffReason.BUYER_REQUEST, summary=None
        )
        await AssignmentService.auto_assign_if_unassigned(db, handoff)
        return handoff
