from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_buyer_conversation, get_db_session, verify_same_origin
from backend.core.config import settings
from backend.core.exceptions import ForbiddenException
from backend.core.rate_limit import enforce_chat_message_rate_limit, enforce_chat_session_rate_limit
from backend.models.conversation import Conversation
from backend.models.message import MessageType, SenderType
from backend.schemas.conversation import (
    BuyerSessionCreateRequest,
    ConversationPublic,
    MessageListResponse,
    MessagePublic,
    SendMessageRequest,
)
from backend.services.ai_orchestrator_service import AIOrchestratorService
from backend.services.buyer_session_service import BuyerSessionService
from backend.services.conversation_service import ConversationService
from backend.services.lead_service import LeadService

router = APIRouter(prefix="/chat", tags=["Buyer Chat"])


# Scoped to /api/v1 (not just /api/v1/chat) since Feature 05 added buyer-session
# authorized booking endpoints at /api/v1/bookings and /api/v1/availability.
_BUYER_SESSION_COOKIE_PATH = "/api/v1"


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.BUYER_SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=settings.BUYER_SESSION_EXPIRE_HOURS * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path=_BUYER_SESSION_COOKIE_PATH,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.BUYER_SESSION_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path=_BUYER_SESSION_COOKIE_PATH,
    )


def _require_matching_conversation(conversation: Conversation, conversation_id: uuid.UUID) -> None:
    if conversation.id != conversation_id:
        raise ForbiddenException("This session does not authorize access to that conversation")


@router.post(
    "/sessions",
    response_model=ConversationPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a buyer chat session and conversation",
)
async def create_chat_session(
    payload: BuyerSessionCreateRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> ConversationPublic:
    client_ip = request.client.host if request.client else "unknown"
    await enforce_chat_session_rate_limit(client_ip)

    result = await ConversationService.create_chat_session(
        db,
        full_name=payload.full_name,
        raw_phone=payload.phone,
        raw_email=payload.email,
        preferred_language=payload.preferred_language,
        consent_given=payload.consent_given,
    )

    _, raw_token = await BuyerSessionService.create_session(db, result.conversation.id)
    _set_session_cookie(response, raw_token)

    return ConversationPublic.model_validate(result.conversation)


@router.get("/session", response_model=ConversationPublic, summary="Retrieve the current buyer session's conversation")
async def get_current_session(
    conversation: Conversation = Depends(get_buyer_conversation),
) -> ConversationPublic:
    return ConversationPublic.model_validate(conversation)


@router.post(
    "/session/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current buyer chat session",
)
async def logout_chat_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    _origin_ok: None = Depends(verify_same_origin),
) -> None:
    raw_token = request.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)
    if raw_token:
        await BuyerSessionService.revoke_session(db, raw_token)
    _clear_session_cookie(response)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationPublic,
    summary="Retrieve the buyer's authorized conversation",
)
async def get_buyer_conversation_detail(
    conversation_id: uuid.UUID,
    conversation: Conversation = Depends(get_buyer_conversation),
) -> ConversationPublic:
    _require_matching_conversation(conversation, conversation_id)
    return ConversationPublic.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="Retrieve message history for the buyer's conversation",
)
async def get_buyer_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    conversation: Conversation = Depends(get_buyer_conversation),
) -> MessageListResponse:
    _require_matching_conversation(conversation, conversation_id)
    messages, total = await ConversationService.list_messages(db, conversation_id, limit=limit, offset=offset)
    return MessageListResponse(items=[MessagePublic.model_validate(m) for m in messages], total=total)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessagePublic,
    status_code=status.HTTP_201_CREATED,
    summary="Send a buyer message",
)
async def send_buyer_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    db: AsyncSession = Depends(get_db_session),
    conversation: Conversation = Depends(get_buyer_conversation),
    _origin_ok: None = Depends(verify_same_origin),
) -> MessagePublic:
    _require_matching_conversation(conversation, conversation_id)
    await enforce_chat_message_rate_limit(str(conversation_id))

    message = await ConversationService.post_message(
        db,
        conversation,
        sender_type=SenderType.BUYER,
        sender_id=conversation.lead_id,
        content=payload.content,
        message_type=MessageType.TEXT,
    )

    lead = await LeadService.get_lead_by_id(db, conversation.lead_id)
    await AIOrchestratorService.handle_buyer_message(db, conversation, lead, payload.content)

    return MessagePublic.model_validate(message)
