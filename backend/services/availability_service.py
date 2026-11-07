from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundException, ValidationException
from backend.models.availability_rule import AvailabilityRule
from backend.models.blocked_period import BlockedPeriod
from backend.models.project import Project
from backend.models.project_visit_capacity import ProjectVisitCapacity
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.models.user import User, UserRole

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class Slot:
    start_time: datetime  # UTC
    end_time: datetime  # UTC
    available_executive_count: int


class AvailabilityService:
    """
    Computes dynamically available site-visit slots for a project/date from
    executive working hours, blocked periods, existing confirmed
    appointments and project capacity. Read-only and best-effort for
    display purposes only -- the booking transaction in BookingService
    re-validates everything from scratch and is the sole source of truth.
    """

    @staticmethod
    async def get_visit_capacity(db: AsyncSession, project_id: uuid.UUID) -> ProjectVisitCapacity:
        result = await db.execute(
            select(ProjectVisitCapacity).where(ProjectVisitCapacity.project_id == project_id)
        )
        capacity = result.scalar_one_or_none()
        if capacity is None:
            raise NotFoundException("Visit capacity has not been configured for this project")
        return capacity

    @staticmethod
    async def upsert_visit_capacity(
        db: AsyncSession,
        project_id: uuid.UUID,
        *,
        capacity: int,
        visit_duration_minutes: int,
        buffer_minutes: int,
    ) -> ProjectVisitCapacity:
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        if project_result.scalar_one_or_none() is None:
            raise NotFoundException("Project not found")

        result = await db.execute(
            select(ProjectVisitCapacity).where(ProjectVisitCapacity.project_id == project_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = ProjectVisitCapacity(project_id=project_id)
            db.add(record)

        record.capacity = capacity
        record.visit_duration_minutes = visit_duration_minutes
        record.buffer_minutes = buffer_minutes
        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def _eligible_executives(db: AsyncSession, project_id: uuid.UUID) -> List[uuid.UUID]:
        result = await db.execute(
            select(AvailabilityRule.executive_id)
            .where(
                AvailabilityRule.is_active.is_(True),
                or_(AvailabilityRule.project_id.is_(None), AvailabilityRule.project_id == project_id),
            )
            .distinct()
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def _rules_for_executive_on_day(
        db: AsyncSession, executive_id: uuid.UUID, project_id: uuid.UUID, day_of_week: int
    ) -> List[AvailabilityRule]:
        result = await db.execute(
            select(AvailabilityRule).where(
                AvailabilityRule.executive_id == executive_id,
                AvailabilityRule.is_active.is_(True),
                AvailabilityRule.day_of_week == day_of_week,
                or_(AvailabilityRule.project_id.is_(None), AvailabilityRule.project_id == project_id),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def _blocked_periods_for_executive(
        db: AsyncSession, executive_id: uuid.UUID, window_start: datetime, window_end: datetime
    ) -> List[BlockedPeriod]:
        result = await db.execute(
            select(BlockedPeriod).where(
                BlockedPeriod.executive_id == executive_id,
                BlockedPeriod.start_time < window_end,
                BlockedPeriod.end_time > window_start,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def _confirmed_visits_for_executive(
        db: AsyncSession, executive_id: uuid.UUID, window_start: datetime, window_end: datetime
    ) -> List[SiteVisit]:
        result = await db.execute(
            select(SiteVisit).where(
                SiteVisit.executive_id == executive_id,
                SiteVisit.status == SiteVisitStatus.CONFIRMED,
                SiteVisit.start_time < window_end,
                SiteVisit.end_time > window_start,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def _confirmed_visit_count_for_project(
        db: AsyncSession, project_id: uuid.UUID, start_time: datetime, end_time: datetime
    ) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(SiteVisit)
            .where(
                SiteVisit.project_id == project_id,
                SiteVisit.status == SiteVisitStatus.CONFIRMED,
                SiteVisit.start_time < end_time,
                SiteVisit.end_time > start_time,
            )
        )
        return result.scalar_one()

    @staticmethod
    def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
        return a_start < b_end and a_end > b_start

    @staticmethod
    async def is_executive_free(
        db: AsyncSession,
        executive_id: uuid.UUID,
        start_time: datetime,
        end_time: datetime,
        *,
        exclude_site_visit_id: Optional[uuid.UUID] = None,
    ) -> bool:
        blocked = await AvailabilityService._blocked_periods_for_executive(db, executive_id, start_time, end_time)
        if blocked:
            return False

        visits = await AvailabilityService._confirmed_visits_for_executive(db, executive_id, start_time, end_time)
        for visit in visits:
            if exclude_site_visit_id is not None and visit.id == exclude_site_visit_id:
                continue
            return False
        return True

    @staticmethod
    async def get_available_slots(
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        target_date: date,
        preferred_start_time: Optional[time] = None,
        preferred_end_time: Optional[time] = None,
    ) -> List[Slot]:
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        if project_result.scalar_one_or_none() is None:
            raise NotFoundException("Project not found")

        capacity_config = await AvailabilityService.get_visit_capacity(db, project_id)
        day_of_week = target_date.weekday()

        day_start_utc = datetime.combine(target_date, time.min, tzinfo=IST).astimezone(timezone.utc)
        day_end_utc = datetime.combine(target_date, time.max, tzinfo=IST).astimezone(timezone.utc)

        executive_ids = await AvailabilityService._eligible_executives(db, project_id)

        # candidate_start_time (UTC) -> set of free executive_ids
        slot_candidates: dict = {}
        step = timedelta(minutes=capacity_config.visit_duration_minutes + capacity_config.buffer_minutes)
        duration = timedelta(minutes=capacity_config.visit_duration_minutes)

        for executive_id in executive_ids:
            rules = await AvailabilityService._rules_for_executive_on_day(db, executive_id, project_id, day_of_week)
            if not rules:
                continue

            blocked_periods = await AvailabilityService._blocked_periods_for_executive(
                db, executive_id, day_start_utc, day_end_utc
            )
            confirmed_visits = await AvailabilityService._confirmed_visits_for_executive(
                db, executive_id, day_start_utc, day_end_utc
            )

            for rule in rules:
                window_start = datetime.combine(target_date, rule.start_time, tzinfo=IST).astimezone(timezone.utc)
                window_end = datetime.combine(target_date, rule.end_time, tzinfo=IST).astimezone(timezone.utc)

                cursor = window_start
                while cursor + duration <= window_end:
                    slot_start = cursor
                    slot_end = cursor + duration
                    cursor += step

                    if preferred_start_time is not None or preferred_end_time is not None:
                        local_slot_start = slot_start.astimezone(IST).time()
                        if preferred_start_time is not None and local_slot_start < preferred_start_time:
                            continue
                        if preferred_end_time is not None and local_slot_start >= preferred_end_time:
                            continue

                    blocked = any(
                        AvailabilityService._overlaps(slot_start, slot_end, bp.start_time, bp.end_time)
                        for bp in blocked_periods
                    )
                    if blocked:
                        continue

                    conflicting = any(
                        AvailabilityService._overlaps(slot_start, slot_end, v.start_time, v.end_time)
                        for v in confirmed_visits
                    )
                    if conflicting:
                        continue

                    slot_candidates.setdefault(slot_start, {"end_time": slot_end, "executives": set()})
                    slot_candidates[slot_start]["executives"].add(executive_id)

        slots: List[Slot] = []
        for slot_start, info in sorted(slot_candidates.items()):
            booked_count = await AvailabilityService._confirmed_visit_count_for_project(
                db, project_id, slot_start, info["end_time"]
            )
            remaining_capacity = capacity_config.capacity - booked_count
            if remaining_capacity <= 0:
                continue
            available_executive_count = min(len(info["executives"]), remaining_capacity)
            if available_executive_count <= 0:
                continue
            slots.append(
                Slot(
                    start_time=slot_start,
                    end_time=info["end_time"],
                    available_executive_count=available_executive_count,
                )
            )
        return slots

    @staticmethod
    async def find_eligible_executive(
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        start_time: datetime,
        end_time: datetime,
        exclude_site_visit_id: Optional[uuid.UUID] = None,
    ) -> Optional[uuid.UUID]:
        """
        Returns the id of one SALES_EXECUTIVE whose AvailabilityRule covers
        this slot and who has no blocking period or overlapping confirmed
        visit. Does not lock anything -- callers inside a booking
        transaction must still re-check under lock before confirming.
        """
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
        candidate_ids = [row[0] for row in result.all()]

        for executive_id in candidate_ids:
            if await AvailabilityService.is_executive_free(
                db, executive_id, start_time, end_time, exclude_site_visit_id=exclude_site_visit_id
            ):
                return executive_id
        return None
