from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ConflictException, NotFoundException, ValidationException
from backend.models.conversation import Conversation, OwnershipStatus
from backend.models.conversation_assignment import AssignmentStatus, ConversationAssignment
from backend.models.handoff import Handoff, HandoffReason, HandoffStatus
from backend.models.lead import Lead
from backend.models.lead_qualification import LeadQualification
from backend.models.lead_source import LeadSource
from backend.models.site_visit import SiteVisit
from backend.services.conversation_service import ConversationService


async def _advisory_lock_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> None:
    """
    Serializes all handoff/assignment/ownership writes for a single
    conversation within the current transaction (released automatically on
    commit/rollback) -- mirrors BookingService's advisory-lock pattern so
    concurrent escalation/accept/reject/resolve calls for the same
    conversation are never both believed to succeed.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(conversation_id)})


class HandoffService:
    """
    Escalation lifecycle only -- who gets assigned is AssignmentService's
    concern (kept separate per spec section 5). Never lets a conversation
    accumulate more than one active (PENDING/ASSIGNED/ACCEPTED) handoff:
    create_handoff is idempotent and returns the existing active row on a
    retry rather than creating a duplicate.
    """

    @staticmethod
    async def get_handoff(db: AsyncSession, handoff_id: uuid.UUID) -> Handoff:
        result = await db.execute(select(Handoff).where(Handoff.id == handoff_id))
        handoff = result.scalar_one_or_none()
        if handoff is None:
            raise NotFoundException("Handoff not found")
        return handoff

    @staticmethod
    async def get_active_handoff_for_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> Optional[Handoff]:
        result = await db.execute(
            select(Handoff).where(
                Handoff.conversation_id == conversation_id,
                Handoff.status.in_([HandoffStatus.PENDING, HandoffStatus.ASSIGNED, HandoffStatus.ACCEPTED]),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_handoff(
        db: AsyncSession,
        conversation: Conversation,
        lead: Lead,
        *,
        reason: HandoffReason,
        summary: Optional[str],
    ) -> Handoff:
        await _advisory_lock_conversation(db, conversation.id)

        existing = await HandoffService.get_active_handoff_for_conversation(db, conversation.id)
        if existing is not None:
            return existing

        if conversation.ownership_status == OwnershipStatus.AI_ACTIVE:
            ConversationService.transition_ownership(conversation, OwnershipStatus.PENDING_ASSIGNMENT)
        elif conversation.ownership_status not in (OwnershipStatus.PENDING_ASSIGNMENT,):
            # Buyer explicitly requesting a human while already HUMAN_ACTIVE/RESOLVED
            # is a no-op for ownership -- there is nothing to escalate into.
            raise ConflictException(
                f"Cannot request a handoff while ownership is {conversation.ownership_status.value}"
            )

        handoff = Handoff(
            conversation_id=conversation.id,
            lead_id=lead.id,
            status=HandoffStatus.PENDING,
            reason=reason,
            summary=summary,
        )
        db.add(handoff)
        await db.commit()
        await db.refresh(handoff)
        return handoff

    @staticmethod
    async def list_handoffs(
        db: AsyncSession,
        *,
        status: Optional[HandoffStatus] = None,
        assigned_executive_id: Optional[uuid.UUID] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Tuple[Handoff, Lead]], int]:
        base_query = select(Handoff, Lead).join(Lead, Lead.id == Handoff.lead_id)
        count_query = select(func.count()).select_from(Handoff)

        filters = []
        if status is not None:
            filters.append(Handoff.status == status)
        if assigned_executive_id is not None:
            filters.append(Handoff.assigned_executive_id == assigned_executive_id)

        for f in filters:
            base_query = base_query.where(f)
            count_query = count_query.where(f)

        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        base_query = base_query.order_by(Handoff.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(base_query)
        return [(row[0], row[1]) for row in result.all()], total

    @staticmethod
    async def get_detail_context(db: AsyncSession, handoff: Handoff) -> dict:
        """
        Assembles the handoff context a sales executive needs (spec section
        6/8): buyer requirements, source, and booking details -- read from
        existing Lead/LeadSource/LeadQualification/SiteVisit records, never
        duplicated into the Handoff row itself.
        """
        lead_result = await db.execute(select(Lead).where(Lead.id == handoff.lead_id))
        lead = lead_result.scalar_one_or_none()
        if lead is None:
            raise NotFoundException("Lead not found")

        qualification_result = await db.execute(
            select(LeadQualification).where(LeadQualification.lead_id == handoff.lead_id)
        )
        qualification = qualification_result.scalar_one_or_none()

        source_types_result = await db.execute(select(LeadSource.source_type).where(LeadSource.lead_id == handoff.lead_id))
        source_types = sorted({row[0].value for row in source_types_result.all()})

        site_visits_result = await db.execute(
            select(SiteVisit).where(SiteVisit.lead_id == handoff.lead_id).order_by(SiteVisit.start_time.desc())
        )
        site_visits = list(site_visits_result.scalars().all())

        assignments_result = await db.execute(
            select(ConversationAssignment)
            .where(ConversationAssignment.handoff_id == handoff.id)
            .order_by(ConversationAssignment.assigned_at.desc())
        )
        assignments = list(assignments_result.scalars().all())

        conversation_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conversation = conversation_result.scalar_one_or_none()
        if conversation is None:
            raise NotFoundException("Conversation not found")

        return {
            "lead": lead,
            "qualification": qualification,
            "source_types": source_types,
            "site_visits": site_visits,
            "assignments": assignments,
            "conversation": conversation,
        }

    @staticmethod
    async def resolve_handoff(db: AsyncSession, handoff_id: uuid.UUID, *, actor_id: Optional[uuid.UUID]) -> Handoff:
        result = await db.execute(select(Handoff).where(Handoff.id == handoff_id).with_for_update())
        handoff = result.scalar_one_or_none()
        if handoff is None:
            raise NotFoundException("Handoff not found")
        if handoff.status in (HandoffStatus.RESOLVED, HandoffStatus.CANCELLED):
            raise ConflictException(f"Handoff is already {handoff.status.value}")

        await _advisory_lock_conversation(db, handoff.conversation_id)

        conversation_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conversation = conversation_result.scalar_one_or_none()
        if conversation is None:
            raise NotFoundException("Conversation not found")

        ConversationService.transition_ownership(conversation, OwnershipStatus.RESOLVED)
        handoff.status = HandoffStatus.RESOLVED
        handoff.resolved_at = datetime.now(timezone.utc)

        assignment_result = await db.execute(
            select(ConversationAssignment)
            .where(
                ConversationAssignment.handoff_id == handoff.id,
                ConversationAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED]),
            )
            .with_for_update()
        )
        active_assignment = assignment_result.scalar_one_or_none()
        if active_assignment is not None:
            active_assignment.status = AssignmentStatus.ENDED
            active_assignment.ended_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(handoff)
        return handoff
