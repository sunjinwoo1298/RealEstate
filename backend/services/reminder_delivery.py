from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from zoneinfo import ZoneInfo

from backend.core.logging import logger
from backend.models.lead import Lead
from backend.models.project import Project
from backend.models.site_visit import SiteVisit
from backend.models.visit_reminder import VisitReminder

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class ReminderDeliveryResult:
    """
    What actually happened on this delivery attempt. `simulated=True` means
    no real channel was used -- the reminder worker must record SIMULATED,
    never SENT, so the system never claims a buyer was actually reached.
    """

    simulated: bool
    rendered_message: str


def render_reminder_message(visit: SiteVisit, lead: Lead, project: Project, reminder: VisitReminder) -> str:
    """
    Builds reminder content strictly from already-approved data (project
    name/location, the visit's own scheduled time) -- never invents a
    detail the system doesn't actually have.
    """
    local_time = visit.start_time.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
    lines = [
        f"Hi {lead.full_name}, this is a reminder for your site visit to {project.name}.",
        f"Scheduled for: {local_time}.",
    ]
    if project.location:
        lines.append(f"Location: {project.location}.")
    lines.append("If you need to change this visit, please contact our sales team.")
    return " ".join(lines)


class ReminderDeliveryProvider(Protocol):
    """
    Delivery-channel abstraction. Swapping in a real WhatsApp/SMS provider
    later only means implementing this interface -- scheduling, retry and
    staleness logic in ReminderService/ReminderWorkerService never change.
    """

    async def send(
        self, *, reminder: VisitReminder, visit: SiteVisit, lead: Lead, project: Project
    ) -> ReminderDeliveryResult: ...


class LoggingReminderDeliveryProvider:
    """
    Development/logging provider: the only implementation for this feature,
    per spec section 6 ("do not introduce WhatsApp API credentials or an
    external messaging dependency"). Logs the rendered message (never buyer
    phone/email, per spec section 10) and always reports `simulated=True`.
    """

    async def send(
        self, *, reminder: VisitReminder, visit: SiteVisit, lead: Lead, project: Project
    ) -> ReminderDeliveryResult:
        message = render_reminder_message(visit, lead, project, reminder)
        logger.info(
            f"[SIMULATED REMINDER] visit={visit.id} type={reminder.reminder_type.value} "
            f"booking_ref={visit.booking_reference} message=\"{message}\""
        )
        return ReminderDeliveryResult(simulated=True, rendered_message=message)
