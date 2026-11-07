from __future__ import annotations
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import BookingPrincipal, get_booking_principal, get_current_user, get_db_session, verify_same_origin
from backend.core.exceptions import ForbiddenException
from backend.models.conversation import ConversationStatus, OwnershipStatus
from backend.models.handoff import HandoffReason
from backend.models.message import MessageType, SenderType
from backend.models.user import User, UserRole
from backend.schemas.conversation import ConversationListItem, ConversationListResponse, MessageListResponse, MessagePublic, SendMessageRequest
from backend.schemas.handoff import HandoffPublic, HandoffRequestCreate, OwnershipTransitionRequest
from backend.services.assignment_service import AssignmentService
from backend.services.conversation_service import ConversationService
from backend.services.handoff_service import HandoffService
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


@router.post(
    "/{conversation_id}/messages",
    response_model=MessagePublic,
    status_code=201,
    summary="Send a staff reply into a human-owned conversation",
)
async def send_staff_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    _origin_ok: None = Depends(verify_same_origin),
) -> MessagePublic:
    """
    The buyer's chat widget and the AI orchestrator are the only other
    writers of this conversation's messages; the AI orchestrator already
    refuses to generate while ownership_status != AI_ACTIVE, so gating this
    endpoint to HUMAN_ACTIVE + the assigned executive (or a manager/admin
    override) is what keeps AI and staff from ever replying at once.
    """
    conversation = await ConversationService.get_conversation_by_id(db, conversation_id)
    handoff = await HandoffService.get_active_handoff_for_conversation(db, conversation_id)

    is_manager_or_admin = current_user.role in (UserRole.MANAGER, UserRole.ADMIN)
    is_assigned_executive = handoff is not None and handoff.assigned_executive_id == current_user.id
    if not (is_manager_or_admin or is_assigned_executive):
        raise ForbiddenException("You are not the assigned executive for this conversation")
    if conversation.ownership_status != OwnershipStatus.HUMAN_ACTIVE:
        raise ForbiddenException("This conversation is not currently owned by a sales executive")

    message = await ConversationService.post_message(
        db,
        conversation,
        sender_type=SenderType.STAFF,
        sender_id=current_user.id,
        content=payload.content,
        message_type=MessageType.TEXT,
    )
    return MessagePublic.model_validate(message)


@router.post(
    "/{conversation_id}/handoff",
    response_model=HandoffPublic,
    status_code=201,
    summary="Request a human handoff for a conversation",
)
async def request_handoff(
    conversation_id: uuid.UUID,
    payload: HandoffRequestCreate,
    db: AsyncSession = Depends(get_db_session),
    principal: BookingPrincipal = Depends(get_booking_principal),
    _origin_ok: None = Depends(verify_same_origin),
) -> HandoffPublic:
    conversation = await ConversationService.get_conversation_by_id(db, conversation_id)
    if not principal.is_staff and principal.buyer_lead_id != conversation.lead_id:
        raise ForbiddenException("You may only request a handoff for your own conversation")

    lead = await LeadService.get_lead_by_id(db, conversation.lead_id)
    # A buyer always escalates as BUYER_REQUEST, regardless of what the
    # request body says; only staff manually escalating on the buyer's
    # behalf (e.g. logging a complaint from the transcript) may choose
    # another reason.
    reason = payload.reason if principal.is_staff else HandoffReason.BUYER_REQUEST
    handoff = await HandoffService.create_handoff(db, conversation, lead, reason=reason, summary=payload.summary)
    await AssignmentService.auto_assign_if_unassigned(db, handoff)
    return HandoffPublic.model_validate(handoff)


@router.post(
    "/{conversation_id}/ownership",
    response_model=ConversationListItem,
    summary="Authorized ownership transition",
)
async def transition_ownership(
    conversation_id: uuid.UUID,
    payload: OwnershipTransitionRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    _origin_ok: None = Depends(verify_same_origin),
) -> ConversationListItem:
    """
    A manager/admin may always perform an authorized transition (e.g.
    returning a resolved conversation to the AI). The assigned executive of
    the conversation's active or most recent handoff may also transition
    it -- covers an executive manually handing a conversation back to the
    AI without a manager in the loop.
    """
    conversation = await ConversationService.get_conversation_by_id(db, conversation_id)

    if current_user.role not in (UserRole.MANAGER, UserRole.ADMIN):
        active_handoff = await HandoffService.get_active_handoff_for_conversation(db, conversation_id)
        if active_handoff is None or active_handoff.assigned_executive_id != current_user.id:
            raise ForbiddenException("You are not authorized to change ownership of this conversation")

    ConversationService.transition_ownership(conversation, payload.ownership_status)
    await db.commit()
    await db.refresh(conversation)

    lead = await LeadService.get_lead_by_id(db, conversation.lead_id)
    return ConversationListItem.model_validate(conversation).model_copy(
        update={"lead_full_name": lead.full_name, "lead_normalized_phone": lead.normalized_phone}
    )
