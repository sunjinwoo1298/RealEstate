from __future__ import annotations
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db_session
from backend.models.conversation import ConversationStatus
from backend.models.user import User
from backend.schemas.conversation import ConversationListItem, ConversationListResponse, MessageListResponse, MessagePublic
from backend.services.conversation_service import ConversationService
from backend.services.lead_service import LeadService

router = APIRouter(prefix="/conversations", tags=["Staff Conversation Workspace"])


@router.get("", response_model=ConversationListResponse, summary="List conversations (staff)")
async def list_conversations(
    conversation_status: Optional[ConversationStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> ConversationListResponse:
    rows, total = await ConversationService.list_conversations_staff(
        db, status=conversation_status, limit=limit, offset=offset
    )
    items = [
        ConversationListItem.model_validate(conversation).model_copy(
            update={"lead_full_name": lead.full_name, "lead_normalized_phone": lead.normalized_phone}
        )
        for conversation, lead in rows
    ]
    return ConversationListResponse(items=items, total=total)


@router.get("/{conversation_id}", response_model=ConversationListItem, summary="Get conversation detail (staff)")
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> ConversationListItem:
    conversation = await ConversationService.get_conversation_by_id(db, conversation_id)
    lead = await LeadService.get_lead_by_id(db, conversation.lead_id)
    return ConversationListItem.model_validate(conversation).model_copy(
        update={"lead_full_name": lead.full_name, "lead_normalized_phone": lead.normalized_phone}
    )


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="Get conversation message history (staff)",
)
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> MessageListResponse:
    await ConversationService.get_conversation_by_id(db, conversation_id)
    messages, total = await ConversationService.list_messages(db, conversation_id, limit=limit, offset=offset)
    return MessageListResponse(items=[MessagePublic.model_validate(m) for m in messages], total=total)
