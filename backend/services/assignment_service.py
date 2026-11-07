from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ConflictException, ForbiddenException, NotFoundException, ValidationException
from backend.models.conversation import Conversation, OwnershipStatus
from backend.models.conversation_assignment import AssignmentStatus, ConversationAssignment
from backend.models.handoff import Handoff, HandoffStatus
from backend.models.user import User, UserRole
from backend.services.conversation_service import ConversationService
from backend.services.notification_service import NotificationService


class AssignmentService:
    """
    Who gets assigned to a handoff -- kept deliberately separate from
    HandoffService's escalation lifecycle (spec section 5). The initial
    strategy is "first eligible, active SALES_EXECUTIVE by id order"
    (matching BookingService's existing executive-assignment convention).
    Every (re)assignment creates a new ConversationAssignment row rather
    than mutating a prior one, preserving assignment history.
    """

    @staticmethod
    async def pick_eligible_executive(db: AsyncSession, *, exclude_executive_ids: Optional[List[uuid.UUID]] = None) -> Optional[User]:
        exclude = exclude_executive_ids or []
        query = select(User).where(User.role == UserRole.SALES_EXECUTIVE, User.is_active.is_(True))
        if exclude:
            query = query.where(User.id.notin_(exclude))
        query = query.order_by(User.id)
        result = await db.execute(query)
        return result.scalars().first()

    @staticmethod
    async def _end_active_assignment(db: AsyncSession, handoff_id: uuid.UUID, *, new_status: AssignmentStatus) -> None:
        result = await db.execute(
            select(ConversationAssignment)
            .where(
                ConversationAssignment.handoff_id == handoff_id,
                ConversationAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED]),
            )
            .with_for_update()
        )
        active = result.scalar_one_or_none()
        if active is not None:
            active.status = new_status
            active.ended_at = datetime.now(timezone.utc)

    @staticmethod
    async def _assign(
        db: AsyncSession,
        handoff: Handoff,
        conversation: Conversation,
        executive: User,
        *,
        assigned_by: Optional[uuid.UUID],
    ) -> ConversationAssignment:
        await AssignmentService._end_active_assignment(db, handoff.id, new_status=AssignmentStatus.ENDED)

        now = datetime.now(timezone.utc)
        assignment = ConversationAssignment(
            conversation_id=conversation.id,
            handoff_id=handoff.id,
            executive_id=executive.id,
            assigned_by=assigned_by,
            status=AssignmentStatus.ASSIGNED,
            assigned_at=now,
        )
        db.add(assignment)
        handoff.assigned_executive_id = executive.id
        handoff.status = HandoffStatus.ASSIGNED

        if conversation.ownership_status == OwnershipStatus.AI_ACTIVE:
            ConversationService.transition_ownership(conversation, OwnershipStatus.PENDING_ASSIGNMENT)

        await db.flush()
        await NotificationService.notify_handoff_assigned(db, executive.id, handoff)

        await db.commit()
        await db.refresh(assignment)
        return assignment

    @staticmethod
    async def auto_assign_if_unassigned(db: AsyncSession, handoff: Handoff) -> Optional[ConversationAssignment]:
        """
        Idempotent: a handoff that is already assigned/accepted/resolved is
        left untouched. Used by the AI tool and the buyer-request endpoint
        right after HandoffService.create_handoff, so a retried escalation
        never creates a second assignment or notification.
        """
        if handoff.status != HandoffStatus.PENDING or handoff.assigned_executive_id is not None:
            return None

        conversation_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conversation = conversation_result.scalar_one_or_none()
        if conversation is None:
            raise NotFoundException("Conversation not found")

        executive = await AssignmentService.pick_eligible_executive(db)
        if executive is None:
            return None
        return await AssignmentService._assign(db, handoff, conversation, executive, assigned_by=None)

    @staticmethod
    async def reassign(
        db: AsyncSession, handoff_id: uuid.UUID, *, new_executive_id: uuid.UUID, assigned_by: uuid.UUID
    ) -> ConversationAssignment:
        result = await db.execute(select(Handoff).where(Handoff.id == handoff_id).with_for_update())
        handoff = result.scalar_one_or_none()
        if handoff is None:
            raise NotFoundException("Handoff not found")
        if handoff.status in (HandoffStatus.RESOLVED, HandoffStatus.CANCELLED):
            raise ConflictException(f"Cannot reassign a handoff that is already {handoff.status.value}")

        executive_result = await db.execute(
            select(User).where(User.id == new_executive_id, User.role == UserRole.SALES_EXECUTIVE, User.is_active.is_(True))
        )
        executive = executive_result.scalar_one_or_none()
        if executive is None:
            raise ValidationException("Target executive must be an active sales executive")

        conversation_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conversation = conversation_result.scalar_one_or_none()
        if conversation is None:
            raise NotFoundException("Conversation not found")

        return await AssignmentService._assign(db, handoff, conversation, executive, assigned_by=assigned_by)

    @staticmethod
    async def accept(db: AsyncSession, handoff_id: uuid.UUID, *, executive: User) -> Handoff:
        result = await db.execute(select(Handoff).where(Handoff.id == handoff_id).with_for_update())
        handoff = result.scalar_one_or_none()
        if handoff is None:
            raise NotFoundException("Handoff not found")
        if handoff.assigned_executive_id != executive.id:
            raise ForbiddenException("This handoff is not assigned to you")
        if handoff.status != HandoffStatus.ASSIGNED:
            raise ConflictException(f"Cannot accept a handoff with status {handoff.status.value}")

        assignment_result = await db.execute(
            select(ConversationAssignment)
            .where(ConversationAssignment.handoff_id == handoff.id, ConversationAssignment.status == AssignmentStatus.ASSIGNED)
            .with_for_update()
        )
        assignment = assignment_result.scalar_one_or_none()
        if assignment is None:
            raise ConflictException("No active assignment to accept")

        conversation_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conversation = conversation_result.scalar_one_or_none()
        if conversation is None:
            raise NotFoundException("Conversation not found")

        now = datetime.now(timezone.utc)
        assignment.status = AssignmentStatus.ACCEPTED
        assignment.accepted_at = now
        handoff.status = HandoffStatus.ACCEPTED
        ConversationService.transition_ownership(conversation, OwnershipStatus.HUMAN_ACTIVE)

        await db.commit()
        await db.refresh(handoff)
        return handoff

    @staticmethod
    async def reject(db: AsyncSession, handoff_id: uuid.UUID, *, executive: User, reason: Optional[str] = None) -> Handoff:
        result = await db.execute(select(Handoff).where(Handoff.id == handoff_id).with_for_update())
        handoff = result.scalar_one_or_none()
        if handoff is None:
            raise NotFoundException("Handoff not found")
        if handoff.assigned_executive_id != executive.id:
            raise ForbiddenException("This handoff is not assigned to you")
        if handoff.status != HandoffStatus.ASSIGNED:
            raise ConflictException(f"Cannot reject a handoff with status {handoff.status.value}")

        await AssignmentService._end_active_assignment(db, handoff.id, new_status=AssignmentStatus.REJECTED)
        handoff.assigned_executive_id = None
        handoff.status = HandoffStatus.PENDING
        if reason:
            note = f"{executive.full_name} declined: {reason.strip()}"
            handoff.summary = f"{handoff.summary}\n{note}" if handoff.summary else note
        await db.flush()

        previously_assigned_result = await db.execute(
            select(ConversationAssignment.executive_id).where(ConversationAssignment.handoff_id == handoff.id)
        )
        previously_assigned = [row[0] for row in previously_assigned_result.all() if row[0] is not None]

        conversation_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conversation = conversation_result.scalar_one_or_none()
        if conversation is None:
            raise NotFoundException("Conversation not found")

        next_executive = await AssignmentService.pick_eligible_executive(db, exclude_executive_ids=previously_assigned)
        if next_executive is not None:
            await AssignmentService._assign(db, handoff, conversation, next_executive, assigned_by=None)
        else:
            await db.commit()
            await db.refresh(handoff)
        return handoff
