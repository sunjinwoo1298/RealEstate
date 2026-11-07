from __future__ import annotations
import asyncio
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import List, Optional

from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.groq_client import GroqClient, LLMProviderError
from backend.ai.guardrails import (
    GuardrailFlags,
    detect_handoff_request,
    detect_pricing_or_discount_request,
    detect_prompt_injection,
    enforce_reply_guardrails,
)
from backend.ai.prompts import build_history_messages, build_response_system_prompt, format_knowledge_context, EXTRACTION_SYSTEM_PROMPT
from backend.ai.schemas import ExtractionResult, OrchestratorReply
from backend.ai.tools import AITools, ToolCallLog
from backend.core.config import settings
from backend.core.database import get_session_factory
from backend.core.logging import logger
from backend.core.redis import get_redis_client
from backend.models.conversation import Conversation, ConversationState, ConversationStatus, OwnershipStatus
from backend.models.lead import Lead
from backend.models.lead_qualification import ConfigurationType, PurchasePurpose
from backend.models.message import Message, MessageType, SenderType
from backend.services.conversation_service import ALLOWED_STATE_TRANSITIONS, ConversationService
from backend.services.project_service import ProjectService
from backend.services.qualification_service import QualificationService

_FALLBACK_REPLY = {
    "EN": "Sorry, I'm having trouble responding right now. A member of our team will follow up with you shortly.",
    "HI": "Maaf kijiye, abhi jawab dene mein dikkat aa rahi hai. Hamari team aapse jaldi contact karegi.",
    "GU": "Maaf karjo, atyare javab aapva ma takalif thai rahi chhe. Amari team tamne thodi vaar ma contact karshe.",
}

_SENDER_ROLE_MAP = {
    SenderType.BUYER: "user",
    SenderType.AI: "assistant",
}

_MAX_HISTORY_MESSAGES = 16


@dataclass
class OrchestratorResult:
    ai_message: Optional[Message]
    skipped_reason: Optional[str] = None


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class AIOrchestratorService:
    """
    Provider-independent AI orchestration for buyer chat. Invoked
    synchronously, in-request, right after a buyer message is persisted.
    Never generates a reply when the conversation isn't AI-owned/active,
    and never lets the LLM touch the database directly — every side effect
    goes through AITools -> an existing domain service.
    """

    @staticmethod
    async def handle_buyer_message(
        db: AsyncSession, conversation: Conversation, lead: Lead, buyer_message_text: str
    ) -> OrchestratorResult:
        if conversation.status != ConversationStatus.ACTIVE:
            return OrchestratorResult(ai_message=None, skipped_reason="CONVERSATION_CLOSED")
        if conversation.ownership_status != OwnershipStatus.AI_ACTIVE:
            return OrchestratorResult(ai_message=None, skipped_reason="NOT_AI_OWNED")

        lock_key = f"ai_processing_lock:{conversation.id}"
        lock_acquired = True
        try:
            redis_client = get_redis_client()
            lock_acquired = bool(
                await redis_client.set(lock_key, "1", nx=True, ex=settings.AI_PROCESSING_LOCK_TTL_SECONDS)
            )
        except RedisError as e:
            logger.warning(f"AI processing lock unavailable, failing open: {e}")
            lock_acquired = True

        if not lock_acquired:
            logger.info(f"Skipping AI generation for conversation {conversation.id}: already processing")
            return OrchestratorResult(ai_message=None, skipped_reason="ALREADY_PROCESSING")

        try:
            return await asyncio.wait_for(
                AIOrchestratorService._run_pipeline(db, conversation, lead, buyer_message_text),
                timeout=settings.AI_RESPONSE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(f"AI pipeline timed out for conversation {conversation.id}")
            return await AIOrchestratorService._persist_fallback(db, conversation, "TIMEOUT")
        except LLMProviderError as e:
            logger.warning(f"AI pipeline LLM failure for conversation {conversation.id}: {e}")
            return await AIOrchestratorService._persist_fallback(db, conversation, "LLM_FAILURE")
        except Exception as e:  # noqa: BLE001 - never let an AI failure lose the buyer's message or crash the request
            logger.exception(f"Unexpected AI pipeline failure for conversation {conversation.id}: {e}")
            return await AIOrchestratorService._persist_fallback(db, conversation, "UNEXPECTED_ERROR")
        finally:
            try:
                redis_client = get_redis_client()
                await redis_client.delete(lock_key)
            except RedisError:
                pass

    @staticmethod
    async def _run_pipeline(
        db: AsyncSession, conversation: Conversation, lead: Lead, buyer_message_text: str
    ) -> OrchestratorResult:
        guardrail_flags = GuardrailFlags(
            prompt_injection_detected=detect_prompt_injection(buyer_message_text),
            pricing_or_discount_requested=detect_pricing_or_discount_request(buyer_message_text),
            handoff_requested=detect_handoff_request(buyer_message_text),
        )

        history = await AIOrchestratorService._load_history_messages(
            db, conversation.id, exclude_latest_content=buyer_message_text
        )
        extraction_completion = await GroqClient.generate_structured(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            messages=build_history_messages(history, latest_message=buyer_message_text),
            schema=ExtractionResult,
        )
        extraction: ExtractionResult = extraction_completion.data
        if extraction.wants_human_handoff:
            guardrail_flags.handoff_requested = True

        tool_log = ToolCallLog()
        tools = AITools(db, tool_log)

        qualification = await QualificationService.get_for_lead(db, lead.id)
        resolved_project_id = qualification.project_id if qualification else None
        if extraction.mentioned_project_name:
            project = await ProjectService.find_by_name(db, extraction.mentioned_project_name)
            if project is not None:
                resolved_project_id = project.id

        configuration = ConfigurationType(extraction.configuration) if extraction.configuration else None
        purchase_purpose = PurchasePurpose(extraction.purchase_purpose) if extraction.purchase_purpose else None
        if any(
            [
                resolved_project_id,
                configuration,
                extraction.budget_min,
                extraction.budget_max,
                purchase_purpose,
                extraction.preferred_visit_date,
            ]
        ):
            qualification = await tools.update_buyer_qualification(
                lead.id,
                project_id=resolved_project_id,
                configuration=configuration,
                budget_min=extraction.budget_min,
                budget_max=extraction.budget_max,
                purchase_purpose=purchase_purpose,
                preferred_language=conversation.language,
                preferred_visit_date=_parse_date(extraction.preferred_visit_date),
            )

        project_info = None
        retrieved_chunks: List = []
        if resolved_project_id is not None:
            project_info = await tools.get_project_information(resolved_project_id)
            if extraction.intent in ("PROJECT_QUESTION", "OTHER"):
                retrieved_chunks = await tools.search_project_knowledge(resolved_project_id, buyer_message_text)

        escalate_to_human = guardrail_flags.handoff_requested
        knowledge_context = format_knowledge_context(
            project_info=project_info, chunks=[c.content for c in retrieved_chunks]
        )
        reply_language = extraction.detected_language or conversation.language.value
        response_system_prompt = build_response_system_prompt(
            language=reply_language, knowledge_context=knowledge_context
        )

        reply_completion = await GroqClient.generate_structured(
            system_prompt=response_system_prompt,
            messages=build_history_messages(history, latest_message=buyer_message_text),
            schema=OrchestratorReply,
            temperature=0.4,
        )
        reply: OrchestratorReply = reply_completion.data
        final_reply_text = enforce_reply_guardrails(reply.reply_text, language=reply_language, flags=guardrail_flags)

        if escalate_to_human:
            final_reply_text = (
                final_reply_text
                + ("\n\n" if final_reply_text else "")
                + {
                    "EN": "I'm connecting you with a member of our sales team now — they'll join this chat shortly.",
                    "HI": "Main aapko hamari sales team se jod rahi hoon — woh thodi hi der mein is chat mein judenge.",
                    "GU": "Hun tamne amari sales team sathe jodu chhu — te thodi vaar ma aa chat ma jodaashe.",
                }.get(reply_language, "Connecting you with a member of our sales team now.")
            )
            conversation.ownership_status = OwnershipStatus.PENDING_ASSIGNMENT

        if (
            conversation.conversation_state == ConversationState.DISCOVERY
            and QualificationService.is_fully_qualified(qualification)
        ):
            if ConversationState.QUALIFIED in ALLOWED_STATE_TRANSITIONS.get(conversation.conversation_state, set()):
                ConversationService.transition_state(conversation, ConversationState.QUALIFIED)

        total_latency_ms = extraction_completion.latency_ms + reply_completion.latency_ms
        ai_message = Message(
            conversation_id=conversation.id,
            sender_type=SenderType.AI,
            sender_id=None,
            content=final_reply_text,
            message_type=MessageType.TEXT,
            extra_metadata={
                "model": settings.GROQ_MODEL,
                "latency_ms": round(total_latency_ms, 2),
                "prompt_tokens": extraction_completion.prompt_tokens + reply_completion.prompt_tokens,
                "completion_tokens": extraction_completion.completion_tokens + reply_completion.completion_tokens,
                "intent": extraction.intent,
                "retrieval_references": [
                    {
                        "chunk_id": str(c.chunk_id),
                        "document_id": str(c.document_id),
                        "document_title": c.document_title,
                        "document_version": c.document_version,
                        "similarity": round(c.similarity, 4),
                    }
                    for c in retrieved_chunks
                ],
                "tool_calls": tool_log.as_metadata(),
                "guardrail_flags": {
                    "prompt_injection_detected": guardrail_flags.prompt_injection_detected,
                    "pricing_or_discount_requested": guardrail_flags.pricing_or_discount_requested,
                    "handoff_requested": guardrail_flags.handoff_requested,
                    "reply_price_violation_blocked": guardrail_flags.reply_price_violation_blocked,
                    "notes": guardrail_flags.notes,
                },
            },
        )
        db.add(ai_message)
        conversation.last_message_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(ai_message)
        return OrchestratorResult(ai_message=ai_message)

    @staticmethod
    async def _persist_fallback(db: AsyncSession, conversation: Conversation, reason: str) -> OrchestratorResult:
        language = conversation.language.value
        try:
            ai_message = Message(
                conversation_id=conversation.id,
                sender_type=SenderType.AI,
                sender_id=None,
                content=_FALLBACK_REPLY.get(language, _FALLBACK_REPLY["EN"]),
                message_type=MessageType.TEXT,
                extra_metadata={"guardrail_flags": {"notes": [f"AI pipeline failed: {reason}"]}, "failure_reason": reason},
            )
            db.add(ai_message)
            conversation.last_message_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(ai_message)
            return OrchestratorResult(ai_message=ai_message, skipped_reason=reason)
        except Exception as e:  # noqa: BLE001 - the buyer's own message is already committed; never raise from here
            logger.exception(f"Failed to persist AI fallback message: {e}")
            await db.rollback()
            return OrchestratorResult(ai_message=None, skipped_reason=reason)

    @staticmethod
    async def _load_history_messages(
        db: AsyncSession, conversation_id: uuid.UUID, *, exclude_latest_content: Optional[str] = None
    ) -> List[dict]:
        total_count = (
            await db.execute(select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id))
        ).scalar_one()

        fetch_limit = _MAX_HISTORY_MESSAGES + 1
        offset = max(total_count - fetch_limit, 0)
        messages, _ = await ConversationService.list_messages(db, conversation_id, limit=fetch_limit, offset=offset)

        if (
            exclude_latest_content is not None
            and messages
            and messages[-1].sender_type == SenderType.BUYER
            and messages[-1].content == exclude_latest_content
        ):
            messages = messages[:-1]
        messages = messages[-_MAX_HISTORY_MESSAGES:]

        history: List[dict] = []
        for message in messages:
            role = _SENDER_ROLE_MAP.get(message.sender_type)
            if role is None:
                continue
            history.append({"role": role, "content": message.content})
        return history
