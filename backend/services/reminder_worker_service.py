from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.logging import logger
from backend.models.lead import Lead
from backend.models.project import Project
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.models.visit_reminder import ReminderStatus, VisitReminder
from backend.services.reminder_delivery import LoggingReminderDeliveryProvider, ReminderDeliveryProvider


class ReminderWorkerService:
    """
    Persistent, database-backed reminder execution. The VisitReminder table
    is the sole source of truth for what is due; there is no in-memory
    scheduling state, so execution survives a restart of the worker process
    (and the API process, which never runs this itself).

    Claiming is done with `SELECT ... FOR UPDATE SKIP LOCKED`: two workers
    racing the same due-reminder query will never both receive the same
    row, so a reminder is only ever processed by one worker at a time.
    """

    @staticmethod
    async def claim_due_reminders(db: AsyncSession, *, limit: Optional[int] = None) -> List[VisitReminder]:
        now = datetime.now(timezone.utc)
        batch_size = limit or settings.REMINDER_WORKER_BATCH_SIZE

        result = await db.execute(
            select(VisitReminder)
            .where(VisitReminder.status == ReminderStatus.SCHEDULED, VisitReminder.scheduled_at <= now)
            .order_by(VisitReminder.scheduled_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        claimed = list(result.scalars().all())
        for reminder in claimed:
            reminder.status = ReminderStatus.PROCESSING
            reminder.attempt_count += 1
            reminder.last_attempt_at = now
        await db.commit()
        for reminder in claimed:
            await db.refresh(reminder)
        return claimed

    @staticmethod
    async def process_reminder(
        db: AsyncSession, reminder_id, delivery_provider: ReminderDeliveryProvider
    ) -> None:
        """
        Re-validates the reminder's own booking before sending, so a visit
        cancelled/completed/rescheduled after this reminder was claimed (but
        before it was sent) is never reminded against a stale schedule.
        """
        result = await db.execute(select(VisitReminder).where(VisitReminder.id == reminder_id))
        reminder = result.scalar_one_or_none()
        if reminder is None:
            return

        visit_result = await db.execute(select(SiteVisit).where(SiteVisit.id == reminder.site_visit_id))
        visit = visit_result.scalar_one_or_none()

        if (
            visit is None
            or visit.status != SiteVisitStatus.CONFIRMED
            or visit.booking_version != reminder.booking_version
        ):
            reminder.status = ReminderStatus.SKIPPED
            await db.commit()
            return

        lead_result = await db.execute(select(Lead).where(Lead.id == visit.lead_id))
        lead = lead_result.scalar_one_or_none()
        project_result = await db.execute(select(Project).where(Project.id == visit.project_id))
        project = project_result.scalar_one_or_none()
        if lead is None or project is None:
            reminder.status = ReminderStatus.SKIPPED
            await db.commit()
            return

        try:
            delivery_result = await delivery_provider.send(reminder=reminder, visit=visit, lead=lead, project=project)
        except Exception as exc:  # noqa: BLE001 -- any provider failure is a transient delivery failure to retry/fail, never a crash
            ReminderWorkerService._handle_failure(reminder, exc)
            await db.commit()
            return

        reminder.status = ReminderStatus.SIMULATED if delivery_result.simulated else ReminderStatus.SENT
        reminder.sent_at = datetime.now(timezone.utc)
        reminder.failure_reason = None
        await db.commit()

    @staticmethod
    def _handle_failure(reminder: VisitReminder, exc: Exception) -> None:
        logger.warning(f"Reminder delivery failed for visit {reminder.site_visit_id}: {type(exc).__name__}")
        reminder.failure_reason = f"{type(exc).__name__}: {exc}"
        if reminder.attempt_count >= settings.REMINDER_MAX_ATTEMPTS:
            reminder.status = ReminderStatus.FAILED
            return

        backoff_seconds = min(
            settings.REMINDER_RETRY_BASE_SECONDS * (2 ** (reminder.attempt_count - 1)),
            settings.REMINDER_RETRY_MAX_SECONDS,
        )
        reminder.status = ReminderStatus.SCHEDULED
        reminder.scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)

    @staticmethod
    async def run_due_reminders(
        db: AsyncSession, *, delivery_provider: Optional[ReminderDeliveryProvider] = None, limit: Optional[int] = None
    ) -> int:
        """
        Claims and processes one batch of due reminders. Returns the number
        claimed. Intended to be called repeatedly by the worker entry point
        (backend/workers/reminder_worker.py) on a poll interval.
        """
        provider = delivery_provider or LoggingReminderDeliveryProvider()
        claimed = await ReminderWorkerService.claim_due_reminders(db, limit=limit)
        for reminder in claimed:
            await ReminderWorkerService.process_reminder(db, reminder.id, provider)
        return len(claimed)
