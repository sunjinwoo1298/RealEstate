from __future__ import annotations
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ConflictException, NotFoundException, ValidationException
from backend.models.availability_rule import AvailabilityRule
from backend.models.lead import Lead, LeadStatus
from backend.models.project import Project
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.models.visit_event import VisitEvent, VisitEventType
from backend.models.customer_notification_delivery import CustomerNotificationEvent
from backend.services.availability_service import AvailabilityService, IST
from backend.services.customer_notification_service import CustomerNotificationService
from backend.services.reminder_service import ReminderService


def _generate_booking_reference() -> str:
    return "SV-" + secrets.token_hex(4).upper()


async def _advisory_lock_project(db: AsyncSession, project_id: uuid.UUID) -> None:
    """
    Serializes all booking writes for a single project within the current
    transaction (released automatically on commit/rollback), so concurrent
    requests for the same project never both believe capacity is free.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(project_id)})


async def _advisory_lock_executive(db: AsyncSession, executive_id: uuid.UUID) -> None:
    """
    Serializes all booking writes for a single executive within the current
    transaction, so the same executive can never be double-booked by two
    concurrent requests targeting different projects.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(executive_id)})


class BookingService:
    """
    Transactional, concurrency-safe site-visit booking. Every write path
    (book / reschedule / cancel / attendance) locks the relevant project and
    executive via Postgres advisory transaction locks before re-validating
    availability and capacity, then commits atomically. Never reports a
    booking as successful before the transaction commits.
    """

    @staticmethod
    async def get_site_visit(db: AsyncSession, site_visit_id: uuid.UUID) -> SiteVisit:
        result = await db.execute(select(SiteVisit).where(SiteVisit.id == site_visit_id))
        visit = result.scalar_one_or_none()
        if visit is None:
            raise NotFoundException("Site visit not found")
        return visit

    @staticmethod
    async def get_by_idempotency_key(db: AsyncSession, idempotency_key: str) -> Optional[SiteVisit]:
        result = await db.execute(select(SiteVisit).where(SiteVisit.idempotency_key == idempotency_key))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_site_visits(
        db: AsyncSession,
        *,
        lead_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        executive_id: Optional[uuid.UUID] = None,
        status: Optional[SiteVisitStatus] = None,
        upcoming: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[SiteVisit], int]:
        query = select(SiteVisit)
        count_query = select(func.count()).select_from(SiteVisit)

        filters = []
        if lead_id is not None:
            filters.append(SiteVisit.lead_id == lead_id)
        if project_id is not None:
            filters.append(SiteVisit.project_id == project_id)
        if executive_id is not None:
            filters.append(SiteVisit.executive_id == executive_id)
        if status is not None:
            filters.append(SiteVisit.status == status)
        if upcoming is not None:
            now = datetime.now(timezone.utc)
            filters.append(SiteVisit.start_time >= now if upcoming else SiteVisit.start_time < now)

        for f in filters:
            query = query.where(f)
            count_query = count_query.where(f)

        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(SiteVisit.start_time.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all()), total

    @staticmethod
    def _replay_idempotent_booking(
        existing: SiteVisit, *, lead_id: uuid.UUID, project_id: uuid.UUID, start_time: datetime
    ) -> SiteVisit:
        """
        An idempotency key may only replay the *same* request. Reusing it for a
        different buyer/project/time is a client error, not a silent replay.
        """
        same_request = existing.lead_id == lead_id and existing.project_id == project_id
        if same_request and existing.booking_version == 1:
            # Once rescheduled, the stored time legitimately differs from the original request.
            same_request = start_time.tzinfo is not None and existing.start_time == start_time
        if not same_request:
            raise ConflictException("This Idempotency-Key was already used for a different booking request")
        return existing

    @staticmethod
    async def book_site_visit(
        db: AsyncSession,
        *,
        lead_id: uuid.UUID,
        project_id: uuid.UUID,
        start_time: datetime,
        idempotency_key: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> SiteVisit:
        if idempotency_key:
            existing = await BookingService.get_by_idempotency_key(db, idempotency_key)
            if existing is not None:
                return BookingService._replay_idempotent_booking(
                    existing, lead_id=lead_id, project_id=project_id, start_time=start_time
                )

        if start_time.tzinfo is None:
            raise ValidationException("start_time must include timezone information")
        if start_time < datetime.now(timezone.utc):
            raise ValidationException("Cannot book a site visit in the past")

        lead_result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = lead_result.scalar_one_or_none()
        if lead is None:
            raise NotFoundException("Lead not found")

        project_result = await db.execute(select(Project).where(Project.id == project_id))
        if project_result.scalar_one_or_none() is None:
            raise NotFoundException("Project not found")

        await _advisory_lock_project(db, project_id)

        capacity_config = await AvailabilityService.get_visit_capacity(db, project_id)
        end_time = start_time + timedelta(minutes=capacity_config.visit_duration_minutes)

        booked_count = await AvailabilityService._confirmed_visit_count_for_project(
            db, project_id, start_time, end_time
        )
        if booked_count >= capacity_config.capacity:
            raise ConflictException("This slot is no longer available for this project")

        executive_id = await BookingService._lock_and_find_executive(db, project_id, start_time, end_time)
        if executive_id is None:
            raise ConflictException("No executive is available for this slot")

        visit = SiteVisit(
            lead_id=lead_id,
            project_id=project_id,
            executive_id=executive_id,
            start_time=start_time,
            end_time=end_time,
            status=SiteVisitStatus.CONFIRMED,
            booking_reference=_generate_booking_reference(),
            idempotency_key=idempotency_key,
        )
        db.add(visit)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            if idempotency_key:
                existing = await BookingService.get_by_idempotency_key(db, idempotency_key)
                if existing is not None:
                    return BookingService._replay_idempotent_booking(
                        existing, lead_id=lead_id, project_id=project_id, start_time=start_time
                    )
            raise ConflictException("This slot is no longer available")

        db.add(
            VisitEvent(
                site_visit_id=visit.id,
                event_type=VisitEventType.BOOKED,
                actor_id=actor_id,
                extra_metadata={
                    "project_id": str(project_id),
                    "executive_id": str(executive_id),
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                },
            )
        )
        lead.lead_status = LeadStatus.VISIT_BOOKED

        ReminderService.schedule_reminders_for_visit(db, visit)
        # Outbox row is part of this same transaction: it only becomes
        # deliverable if (and when) the booking commits.
        await CustomerNotificationService.enqueue_visit_event(db, visit, CustomerNotificationEvent.SITE_VISIT_BOOKED)

        await db.commit()
        await db.refresh(visit)
        return visit

    @staticmethod
    async def _lock_and_find_executive(
        db: AsyncSession,
        project_id: uuid.UUID,
        start_time: datetime,
        end_time: datetime,
        *,
        exclude_site_visit_id: Optional[uuid.UUID] = None,
    ) -> Optional[uuid.UUID]:
        candidates = await BookingService._candidate_executives(db, project_id, start_time, end_time)
        for executive_id in candidates:
            await _advisory_lock_executive(db, executive_id)
            if await AvailabilityService.is_executive_free(
                db, executive_id, start_time, end_time, exclude_site_visit_id=exclude_site_visit_id
            ):
                return executive_id
        return None

    @staticmethod
    async def _candidate_executives(
        db: AsyncSession, project_id: uuid.UUID, start_time: datetime, end_time: datetime
    ) -> List[uuid.UUID]:
        local_start = start_time.astimezone(IST)
        day_of_week = local_start.weekday()
        local_time_of_day = local_start.time()
        local_end_time_of_day = end_time.astimezone(IST).time()

        result = await db.execute(
            select(AvailabilityRule.executive_id)
            .where(
                AvailabilityRule.is_active.is_(True),
                AvailabilityRule.day_of_week == day_of_week,
                AvailabilityRule.start_time <= local_time_of_day,
                AvailabilityRule.end_time >= local_end_time_of_day,
                or_(AvailabilityRule.project_id.is_(None), AvailabilityRule.project_id == project_id),
            )
            .distinct()
            .order_by(AvailabilityRule.executive_id)
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def cancel_site_visit(
        db: AsyncSession, site_visit_id: uuid.UUID, *, actor_id: Optional[uuid.UUID] = None
    ) -> SiteVisit:
        result = await db.execute(
            select(SiteVisit).where(SiteVisit.id == site_visit_id).with_for_update()
        )
        visit = result.scalar_one_or_none()
        if visit is None:
            raise NotFoundException("Site visit not found")

        if visit.status != SiteVisitStatus.CONFIRMED:
            raise ConflictException(f"Cannot cancel a visit with status {visit.status.value}")

        visit.status = SiteVisitStatus.CANCELLED
        db.add(
            VisitEvent(
                site_visit_id=visit.id,
                event_type=VisitEventType.CANCELLED,
                actor_id=actor_id,
                extra_metadata={},
            )
        )
        await ReminderService.cancel_pending_reminders(db, visit.id)
        await CustomerNotificationService.enqueue_visit_event(db, visit, CustomerNotificationEvent.SITE_VISIT_CANCELLED)
        await db.commit()
        await db.refresh(visit)
        return visit

    @staticmethod
    async def reschedule_site_visit(
        db: AsyncSession,
        site_visit_id: uuid.UUID,
        *,
        new_start_time: datetime,
        actor_id: Optional[uuid.UUID] = None,
    ) -> SiteVisit:
        if new_start_time.tzinfo is None:
            raise ValidationException("start_time must include timezone information")
        if new_start_time < datetime.now(timezone.utc):
            raise ValidationException("Cannot reschedule a site visit to a time in the past")

        result = await db.execute(
            select(SiteVisit).where(SiteVisit.id == site_visit_id).with_for_update()
        )
        visit = result.scalar_one_or_none()
        if visit is None:
            raise NotFoundException("Site visit not found")
        if visit.status != SiteVisitStatus.CONFIRMED:
            raise ConflictException(f"Cannot reschedule a visit with status {visit.status.value}")

        old_start_time, old_end_time = visit.start_time, visit.end_time

        await _advisory_lock_project(db, visit.project_id)
        capacity_config = await AvailabilityService.get_visit_capacity(db, visit.project_id)
        new_end_time = new_start_time + timedelta(minutes=capacity_config.visit_duration_minutes)

        booked_count = await AvailabilityService._confirmed_visit_count_for_project(
            db, visit.project_id, new_start_time, new_end_time
        )
        # Exclude this visit's own current slot from the capacity count it is vacating.
        if AvailabilityService._overlaps(new_start_time, new_end_time, old_start_time, old_end_time):
            booked_count -= 1
        if booked_count >= capacity_config.capacity:
            raise ConflictException("This slot is no longer available for this project")

        executive_id = await BookingService._lock_and_find_executive(
            db, visit.project_id, new_start_time, new_end_time, exclude_site_visit_id=visit.id
        )
        if executive_id is None:
            raise ConflictException("No executive is available for this slot")

        await ReminderService.cancel_pending_reminders(db, visit.id)

        visit.start_time = new_start_time
        visit.end_time = new_end_time
        visit.executive_id = executive_id
        visit.booking_version += 1

        db.add(
            VisitEvent(
                site_visit_id=visit.id,
                event_type=VisitEventType.RESCHEDULED,
                actor_id=actor_id,
                extra_metadata={
                    "old_start_time": old_start_time.isoformat(),
                    "old_end_time": old_end_time.isoformat(),
                    "new_start_time": new_start_time.isoformat(),
                    "new_end_time": new_end_time.isoformat(),
                    "executive_id": str(executive_id),
                },
            )
        )
        ReminderService.schedule_reminders_for_visit(db, visit)
        await CustomerNotificationService.enqueue_visit_event(
            db, visit, CustomerNotificationEvent.SITE_VISIT_RESCHEDULED, previous_start_time=old_start_time
        )
        await db.commit()
        await db.refresh(visit)
        return visit

    @staticmethod
    async def record_attendance(
        db: AsyncSession,
        site_visit_id: uuid.UUID,
        *,
        status: SiteVisitStatus,
        actor_id: Optional[uuid.UUID] = None,
    ) -> SiteVisit:
        result = await db.execute(
            select(SiteVisit).where(SiteVisit.id == site_visit_id).with_for_update()
        )
        visit = result.scalar_one_or_none()
        if visit is None:
            raise NotFoundException("Site visit not found")

        if visit.status != SiteVisitStatus.CONFIRMED:
            raise ConflictException("Attendance has already been recorded for this visit, or it is not confirmed")

        if status not in (SiteVisitStatus.COMPLETED, SiteVisitStatus.NO_SHOW):
            raise ValidationException("Attendance status must be COMPLETED or NO_SHOW")

        # A visit that has not started yet can be neither attended nor missed
        # (CLAUDE.md: future appointments must never count as no-shows).
        if visit.start_time > datetime.now(timezone.utc):
            raise ConflictException("Attendance can only be recorded once the visit has started")

        visit.status = status
        db.add(
            VisitEvent(
                site_visit_id=visit.id,
                event_type=VisitEventType.ATTENDANCE_MARKED,
                actor_id=actor_id,
                extra_metadata={"status": status.value},
            )
        )

        lead_result = await db.execute(select(Lead).where(Lead.id == visit.lead_id))
        lead = lead_result.scalar_one_or_none()
        if lead is not None and status == SiteVisitStatus.COMPLETED:
            lead.lead_status = LeadStatus.VISIT_COMPLETED

        await ReminderService.cancel_pending_reminders(db, visit.id)

        await db.commit()
        await db.refresh(visit)
        return visit
