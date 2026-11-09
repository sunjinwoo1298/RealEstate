from __future__ import annotations
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.location import map_url_for
from backend.models.project import Project
from backend.models.site_visit import SiteVisit
from backend.models.user import User
from backend.models.visit_reminder import ReminderStatus, ReminderType, VisitReminder
from backend.schemas.customer_visit import CustomerReminderPublic, CustomerSiteVisitPublic

# Collapses the internal ReminderStatus state machine into the coarse,
# customer-safe vocabulary the spec allows (section 8: "pending, simulated,
# or sent"). FAILED is deliberately shown as PENDING -- a transient delivery
# failure that the worker will retry is never surfaced as an error to the
# customer, and SKIPPED (a stale reminder for a since-changed booking) reads
# the same as CANCELLED from the customer's point of view.
_CUSTOMER_REMINDER_STATUS: Dict[ReminderStatus, str] = {
    ReminderStatus.SCHEDULED: "PENDING",
    ReminderStatus.PROCESSING: "PENDING",
    ReminderStatus.SENT: "SENT",
    ReminderStatus.SIMULATED: "SIMULATED",
    ReminderStatus.FAILED: "PENDING",
    ReminderStatus.CANCELLED: "CANCELLED",
    ReminderStatus.SKIPPED: "CANCELLED",
}


class CustomerVisitDisplayService:
    """
    Assembles the customer-safe booking representation (project name,
    salesperson name, current-generation reminder status) from existing
    Project/User/VisitReminder data -- mirrors VisitDisplayService's join
    pattern (Feature 07) but never returns a staff-facing schema or an
    internal id (executive_id, reminder id) to a customer.
    """

    @staticmethod
    async def to_details(db: AsyncSession, visits: List[SiteVisit]) -> List[CustomerSiteVisitPublic]:
        if not visits:
            return []

        project_ids = {v.project_id for v in visits}
        executive_ids = {v.executive_id for v in visits if v.executive_id is not None}
        visit_ids = {v.id for v in visits}

        projects: Dict = {
            row.id: row
            for row in (await db.execute(select(Project).where(Project.id.in_(project_ids)))).scalars().all()
        }
        executives: Dict = {}
        if executive_ids:
            executives = {
                row.id: row
                for row in (await db.execute(select(User).where(User.id.in_(executive_ids)))).scalars().all()
            }

        reminders_by_visit: Dict = {}
        if visit_ids:
            reminder_rows = (
                (await db.execute(select(VisitReminder).where(VisitReminder.site_visit_id.in_(visit_ids))))
                .scalars()
                .all()
            )
            for reminder in reminder_rows:
                by_type = reminders_by_visit.setdefault(reminder.site_visit_id, {})
                existing = by_type.get(reminder.reminder_type)
                if existing is None or reminder.booking_version >= existing.booking_version:
                    by_type[reminder.reminder_type] = reminder

        details: List[CustomerSiteVisitPublic] = []
        for visit in visits:
            project = projects.get(visit.project_id)
            executive = executives.get(visit.executive_id) if visit.executive_id else None
            visit_reminders = reminders_by_visit.get(visit.id, {})

            def _current(reminder_type: ReminderType):
                reminder = visit_reminders.get(reminder_type)
                if reminder is None or reminder.booking_version != visit.booking_version:
                    return None
                return CustomerReminderPublic(
                    reminder_type=reminder.reminder_type,
                    status=_CUSTOMER_REMINDER_STATUS[reminder.status],
                )

            details.append(
                CustomerSiteVisitPublic(
                    id=visit.id,
                    project_id=visit.project_id,
                    project_name=project.name if project else "",
                    project_location=project.location if project else None,
                    project_rera_number=project.rera_number if project else None,
                    map_url=map_url_for(project.name, project.location) if project else None,
                    scheduled_start=visit.start_time,
                    scheduled_end=visit.end_time,
                    status=visit.status,
                    booking_reference=visit.booking_reference,
                    executive_full_name=executive.full_name if executive else None,
                    reminder_24h=_current(ReminderType.H24),
                    reminder_2h=_current(ReminderType.H2),
                    created_at=visit.created_at,
                    updated_at=visit.updated_at,
                )
            )
        return details
