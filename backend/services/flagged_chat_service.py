from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.conversation import Conversation
from backend.models.lead import Lead
from backend.models.message import Message, SenderType

IST = ZoneInfo("Asia/Kolkata")

# Guardrail flags the orchestrator stores on every AI message -> label shown to the sales head.
FLAG_LABELS = {
    "complaint_detected": "Complaint",
    "pricing_or_discount_requested": "Price or discount ask",
    "reply_price_violation_blocked": "Price quote blocked",
    "handoff_requested": "Asked for a person",
    "prompt_injection_detected": "Suspicious instruction",
}


class FlaggedChatService:
    """Chats the sales head reviews each day: any AI reply that tripped a guardrail or escalated."""

    @staticmethod
    def day_window(day: date) -> Tuple[datetime, datetime]:
        start = datetime(day.year, day.month, day.day, tzinfo=IST)
        return start, start + timedelta(days=1)

    @staticmethod
    def reasons_from_metadata(metadata: dict | None) -> List[str]:
        if not metadata:
            return []
        reasons: List[str] = []
        flags = metadata.get("guardrail_flags") or {}
        for key, label in FLAG_LABELS.items():
            if flags.get(key) is True:
                reasons.append(label)
        if metadata.get("handoff_reason") and "Asked for a person" not in reasons:
            reasons.append("Escalated to a salesperson")
        return reasons

    @staticmethod
    async def list_for_day(
        db: AsyncSession, *, day: date, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Tuple[Conversation, Lead, List[str]]], int]:
        start, end = FlaggedChatService.day_window(day)
        rows = (
            await db.execute(
                select(Message.conversation_id, Message.extra_metadata).where(
                    Message.sender_type == SenderType.AI,
                    Message.created_at >= start,
                    Message.created_at < end,
                    Message.extra_metadata.isnot(None),
                )
            )
        ).all()
        reasons_by_conversation: Dict = {}
        for conversation_id, metadata in rows:
            found = FlaggedChatService.reasons_from_metadata(metadata)
            if found:
                bucket = reasons_by_conversation.setdefault(conversation_id, [])
                bucket.extend(r for r in found if r not in bucket)
        if not reasons_by_conversation:
            return [], 0
        pairs = (
            await db.execute(
                select(Conversation, Lead)
                .join(Lead, Lead.id == Conversation.lead_id)
                .where(Conversation.id.in_(list(reasons_by_conversation)))
                .order_by(Conversation.last_message_at.desc().nullslast())
            )
        ).all()
        items = [(c, lead, reasons_by_conversation[c.id]) for c, lead in pairs]
        return items[offset : offset + limit], len(items)
