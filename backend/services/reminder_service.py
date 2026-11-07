from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ConflictException, NotFoundException
from backend.models.site_visit import SiteVisit
from backend.models.visit_reminder import ReminderStatus, ReminderType, VisitReminder

REMINDER_OFFSETS: dict = {
    ReminderType.H24: timedelta(hours=24),
    ReminderType.H2: timedelta(hours=2),
}

# Reminders that haven't fired yet; a reschedule/cancellation/attendance
# finalization only ever needs to cancel work still in one of these states.
_PENDING_STATUSES = (ReminderStatus.SCHEDULED, ReminderStatus.PROCESSING)


class ReminderService:
    """
    Creates and cancels VisitReminder rows for a SiteVisit. Every method here
    only adds/updates rows on the given AsyncSession without committing --
    callers (BookingService) are responsible for committing in the same
    transaction as the booking change itself, so a booking can never succeed
    with its reminders missing.
    """

    @staticmethod
    def schedule_reminders_for_visit(db: AsyncSession, visit: SiteVisit) -> List[VisitReminder]:
        """
        Creates a 24h and/or 2h reminder for this visit's *current*
        start_time/booking_version. A reminder whose scheduled_at has
        already passed is never created (per spec section 4.5).
        """
        now = datetime.now(timezone.utc)
        created: List[VisitReminder] = []
        for reminder_type, offset in REMINDER_OFFSETS.items():
            scheduled_at = visit.start_time - offset
            if scheduled_at <= now:
                continue
            reminder = VisitReminder(
                site_visit_id=visit.id,
                reminder_type=reminder_type,
                scheduled_at=scheduled_at,
                status=ReminderStatus.SCHEDULED,
                booking_version=visit.booking_version,
            )
            db.add(reminder)
            created.append(reminder)
        return created

    @staticmethod
    async def cancel_pending_reminders(db: AsyncSession, site_visit_id: uuid.UUID) -> None:
        """
        Cancels (never deletes) every SCHEDULED/PROCESSING reminder for this
        visit, regardless of booking_version -- used on reschedule,
        cancellation, and attendance finalization. History is preserved as
        CANCELLED rows rather than removed.
        """
        result = await db.execute(
            select(VisitReminder).where(
                VisitReminder.site_visit_id == site_visit_id,
                VisitReminder.status.in_(_PENDING_STATUSES),
            )
        )
        for reminder in result.scalars().all():
            reminder.status = ReminderStatus.CANCELLED

    @staticmethod
    async def get_reminder(db: AsyncSession, reminder_id: uuid.UUID) -> VisitReminder:
        result = await db.execute(select(VisitReminder).where(VisitReminder.id == reminder_id))
        reminder = result.scalar_one_or_none()
        if reminder is None:
            raise NotFoundException("Reminder not found")
        return reminder

    @staticmethod
    async def list_reminders_for_visit(db: AsyncSession, site_visit_id: uuid.UUID) -> List[VisitReminder]:
        result = await db.execute(
            select(VisitReminder)
            .where(VisitReminder.site_visit_id == site_visit_id)
            .order_by(VisitReminder.scheduled_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_reminders(
        db: AsyncSession,
        *,
        executive_id: Optional[uuid.UUID] = None,
        status: Optional[ReminderStatus] = None,
        reminder_type: Optional[ReminderType] = None,
        site_visit_id: Optional[uuid.UUID] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[VisitReminder], int]:
        query = select(VisitReminder)
        count_query = select(func.count()).select_from(VisitReminder)

        if executive_id is not None:
            query = query.join(SiteVisit, SiteVisit.id == VisitReminder.site_visit_id).where(
                SiteVisit.executive_id == executive_id
            )
            count_query = count_query.join(SiteVisit, SiteVisit.id == VisitReminder.site_visit_id).where(
                SiteVisit.executive_id == executive_id
            )
        if status is not None:
            query = query.where(VisitReminder.status == status)
            count_query = count_query.where(VisitReminder.status == status)
        if reminder_type is not None:
            query = query.where(VisitReminder.reminder_type == reminder_type)
            count_query = count_query.where(VisitReminder.reminder_type == reminder_type)
        if site_visit_id is not None:
            query = query.where(VisitReminder.site_visit_id == site_visit_id)
            count_query = count_query.where(VisitReminder.site_visit_id == site_visit_id)

        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(VisitReminder.scheduled_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all()), total

    @staticmethod
    async def retry_reminder(db: AsyncSession, reminder_id: uuid.UUID) -> VisitReminder:
        """
        Idempotent admin-triggered retry: only a FAILED reminder is actually
        reset (to SCHEDULED, immediately due); calling this again once it is
        no longer FAILED is a no-op that just returns its current state,
        rather than erroring on a repeated click.
        """
        reminder = await ReminderService.get_reminder(db, reminder_id)
        if reminder.status != ReminderStatus.FAILED:
            return reminder

        result = await db.execute(select(SiteVisit).where(SiteVisit.id == reminder.site_visit_id))
        visit = result.scalar_one_or_none()
        if visit is None or visit.booking_version != reminder.booking_version:
            raise ConflictException("This reminder's booking has since changed and can no longer be retried")

        reminder.status = ReminderStatus.SCHEDULED
        reminder.failure_reason = None
        reminder.scheduled_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(reminder)
        return reminder
