from __future__ import annotations
import uuid
from typing import FrozenSet

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.lead import Lead, LeadStatus
from backend.models.site_visit import SiteVisitStatus

# Statuses from which a booking may advance a lead to VISIT_BOOKED. Everything
# after it in the buyer lifecycle (VISIT_COMPLETED) and every terminal sales
# outcome (CONVERTED, LOST, OPTED_OUT) is deliberately absent: booking another
# visit must never move a lead backwards or overwrite an outcome.
_BOOKING_FROM: FrozenSet[LeadStatus] = frozenset(
    {
        LeadStatus.NEW,
        LeadStatus.AI_CONTACTED,
        LeadStatus.QUALIFIED,
        LeadStatus.VISIT_REQUESTED,
        LeadStatus.VISIT_BOOKED,
    }
)

# Completing a visit advances the lead from any pre-visit stage, but never
# overwrites a terminal outcome.
_COMPLETION_FROM: FrozenSet[LeadStatus] = _BOOKING_FROM | {LeadStatus.VISIT_COMPLETED}


def status_after_booking(current: LeadStatus) -> LeadStatus:
    return LeadStatus.VISIT_BOOKED if current in _BOOKING_FROM else current


def status_after_attendance(current: LeadStatus, visit_status: SiteVisitStatus) -> LeadStatus:
    """A NO_SHOW is a visit outcome, not a lead-lifecycle change."""
    if visit_status == SiteVisitStatus.COMPLETED and current in _COMPLETION_FROM:
        return LeadStatus.VISIT_COMPLETED
    return current


class LeadLifecycleService:
    """
    Single place that decides how visit events move Lead.lead_status, so
    customer and staff flows behave identically. SiteVisit.status remains the
    authority for appointment state; LeadStatus is the broader buyer lifecycle.

    Each transition is one conditional UPDATE (`WHERE lead_status IN (allowed)`),
    so concurrent booking/attendance transactions serialise on the lead row and
    the loser re-evaluates the guard instead of regressing the lifecycle.
    """

    @staticmethod
    async def apply_booking(db: AsyncSession, lead_id: uuid.UUID) -> None:
        await LeadLifecycleService._advance(db, lead_id, LeadStatus.VISIT_BOOKED, _BOOKING_FROM)

    @staticmethod
    async def apply_attendance(db: AsyncSession, lead_id: uuid.UUID, visit_status: SiteVisitStatus) -> None:
        if visit_status != SiteVisitStatus.COMPLETED:
            return
        await LeadLifecycleService._advance(db, lead_id, LeadStatus.VISIT_COMPLETED, _COMPLETION_FROM)

    @staticmethod
    async def _advance(
        db: AsyncSession, lead_id: uuid.UUID, target: LeadStatus, allowed_from: FrozenSet[LeadStatus]
    ) -> None:
        await db.execute(
            update(Lead)
            .where(Lead.id == lead_id, Lead.lead_status.in_(allowed_from))
            .values(lead_status=target)
            .execution_options(synchronize_session="fetch")
        )
