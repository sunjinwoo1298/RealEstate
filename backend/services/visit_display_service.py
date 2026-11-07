from __future__ import annotations
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.lead import Lead
from backend.models.project import Project
from backend.models.site_visit import SiteVisit
from backend.models.user import User
from backend.models.visit_reminder import ReminderType, VisitReminder
from backend.schemas.booking import SiteVisitDetail, SiteVisitPublic
from backend.schemas.reminder import VisitReminderPublic


class VisitDisplayService:
    """
    Assembles the joined display context (buyer name/contact, project name,
    executive name, current-generation reminder status) the staff
    workspace needs, from already-existing Lead/Project/User/VisitReminder
    data -- no new storage, batched to avoid N+1 queries per visit.
    """

    @staticmethod
    async def to_details(db: AsyncSession, visits: List[SiteVisit]) -> List[SiteVisitDetail]:
        if not visits:
            return []

        lead_ids = {v.lead_id for v in visits}
        project_ids = {v.project_id for v in visits}
        executive_ids = {v.executive_id for v in visits if v.executive_id is not None}
        visit_ids = {v.id for v in visits}

        leads: Dict = {
            row.id: row for row in (await db.execute(select(Lead).where(Lead.id.in_(lead_ids)))).scalars().all()
        }
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
                # Keep the highest booking_version seen per type -- a
                # reschedule leaves the prior CANCELLED row in place
                # alongside the new one, and only the current generation
                # should ever be shown (query has no defined row order).
                if existing is None or reminder.booking_version >= existing.booking_version:
                    by_type[reminder.reminder_type] = reminder

        details: List[SiteVisitDetail] = []
        for visit in visits:
            lead = leads.get(visit.lead_id)
            project = projects.get(visit.project_id)
            executive = executives.get(visit.executive_id) if visit.executive_id else None
            visit_reminders = reminders_by_visit.get(visit.id, {})

            # Only the reminder for the visit's *current* booking_version is
            # shown -- a cancelled reminder from a prior reschedule would
            # otherwise confusingly outrank the active one.
            def _current(reminder_type: ReminderType):
                reminder = visit_reminders.get(reminder_type)
                if reminder is None or reminder.booking_version != visit.booking_version:
                    return None
                return VisitReminderPublic.model_validate(reminder)

            base = SiteVisitPublic.model_validate(visit).model_dump()
            details.append(
                SiteVisitDetail(
                    **base,
                    lead_full_name=lead.full_name if lead else "",
                    lead_normalized_phone=lead.normalized_phone if lead else None,
                    project_name=project.name if project else "",
                    executive_full_name=executive.full_name if executive else None,
                    reminder_24h=_current(ReminderType.H24),
                    reminder_2h=_current(ReminderType.H2),
                )
            )
        return details
