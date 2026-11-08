from __future__ import annotations
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_customer, get_db_session
from backend.core.rate_limit import (
    enforce_customer_chat_message_rate_limit,
    enforce_customer_conversation_rate_limit,
    enforce_customer_handoff_rate_limit,
)
from backend.models.conversation import ConversationState
from backend.models.customer_account import CustomerAccount
from backend.schemas.customer_conversation import (
    CustomerConversationListItem,
    CustomerConversationListResponse,
    CustomerConversationPublic,
    CustomerHandoffStatus,
    CustomerMessageListResponse,
    CustomerMessagePublic,
    CustomerSendMessageRequest,
)
from backend.services.customer_conversation_service import CustomerConversationService

# Separate from `customer.py`'s `/customer` profile/enquiry router -- this
# one holds the customer chat resources added in this feature, all
# authenticated via the same CustomerPrincipal (`get_current_customer`).
router = APIRouter(prefix="/customer/conversations", tags=["Customer Chat"])


def _message_preview(message) -> Optional[str]:
    if message is None:
        return None
    return message.content[:160]


@router.post(
    "",
    response_model=CustomerConversationPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new customer conversation",
)
async def create_conversation(
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerConversationPublic:
    await enforce_customer_conversation_rate_limit(str(current_customer.id))
    conversation = await CustomerConversationService.create_conversation(db, current_customer)
    return CustomerConversationPublic.model_validate(conversation)


@router.get(
    "",
    response_model=CustomerConversationListResponse,
    summary="List the authenticated customer's own conversations",
)
async def list_conversations(
    conversation_state: Optional[ConversationState] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerConversationListResponse:
    rows, total = await CustomerConversationService.list_conversations(
        db, current_customer, conversation_state=conversation_state, limit=limit, offset=offset
    )
    items = [
        CustomerConversationListItem.model_validate(conversation).model_copy(
            update={
                "last_message_preview": _message_preview(last_message),
                "last_message_sender_type": last_message.sender_type if last_message else None,
            }
        )
        for conversation, last_message in rows
    ]
    return CustomerConversationListResponse(items=items, total=total)


@router.get(
    "/{conversation_id}",
    response_model=CustomerConversationPublic,
    summary="Retrieve the customer's own conversation",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerConversationPublic:
    conversation = await CustomerConversationService.get_owned_conversation(db, current_customer, conversation_id)
    return CustomerConversationPublic.model_validate(conversation)


@router.get(
    "/{conversation_id}/messages",
    response_model=CustomerMessageListResponse,
    summary="Retrieve message history for the customer's own conversation",
)
async def get_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerMessageListResponse:
    conversation = await CustomerConversationService.get_owned_conversation(db, current_customer, conversation_id)
    messages, total = await CustomerConversationService.list_messages(db, conversation, limit=limit, offset=offset)
    return CustomerMessageListResponse(items=[CustomerMessagePublic.model_validate(m) for m in messages], total=total)


@router.post(
    "/{conversation_id}/messages",
    response_model=CustomerMessagePublic,
    status_code=status.HTTP_201_CREATED,
    summary="Send a customer message",
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: CustomerSendMessageRequest,
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerMessagePublic:
    conversation = await CustomerConversationService.get_owned_conversation(db, current_customer, conversation_id)
    await enforce_customer_chat_message_rate_limit(str(conversation.id))

    message = await CustomerConversationService.send_message(db, current_customer, conversation, payload.content)
    return CustomerMessagePublic.model_validate(message)


@router.post(
    "/{conversation_id}/handoff",
    response_model=CustomerHandoffStatus,
    status_code=status.HTTP_201_CREATED,
    summary="Request a human salesperson for the customer's own conversation",
)
async def request_handoff(
    conversation_id: uuid.UUID,
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerHandoffStatus:
    conversation = await CustomerConversationService.get_owned_conversation(db, current_customer, conversation_id)
    await enforce_customer_handoff_rate_limit(str(current_customer.id))

    handoff = await CustomerConversationService.request_handoff(db, current_customer, conversation)
    return CustomerHandoffStatus.model_validate(handoff)
