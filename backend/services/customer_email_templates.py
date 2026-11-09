from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from backend.core.config import settings
from backend.core.location import map_url_for
from backend.models.customer_notification_delivery import CustomerNotificationEvent

IST = ZoneInfo("Asia/Kolkata")
TEMPLATE_VERSION = 1

TEMPLATE_KEYS: Dict[CustomerNotificationEvent, str] = {
    CustomerNotificationEvent.SITE_VISIT_BOOKED: "site_visit_booked",
    CustomerNotificationEvent.SITE_VISIT_RESCHEDULED: "site_visit_rescheduled",
    CustomerNotificationEvent.SITE_VISIT_CANCELLED: "site_visit_cancelled",
    CustomerNotificationEvent.SITE_VISIT_REMINDER_24H: "site_visit_reminder_24h",
    CustomerNotificationEvent.SITE_VISIT_REMINDER_2H: "site_visit_reminder_2h",
}

_BRAND = "#173B35"

# key -> (subject template, headline, lead sentence, show_visit_link)
_COPY: Dict[str, Dict[str, Any]] = {
    "site_visit_booked": {
        "subject": "Your site visit to {project} is confirmed",
        "headline": "Your site visit is confirmed",
        "lead": "Your visit to {project} has been booked.",
    },
    "site_visit_rescheduled": {
        "subject": "Your site visit to {project} has been rescheduled",
        "headline": "Your site visit was rescheduled",
        "lead": "Your visit to {project} has a new date and time.",
    },
    "site_visit_cancelled": {
        "subject": "Your site visit to {project} has been cancelled",
        "headline": "Your site visit was cancelled",
        "lead": "Your visit to {project} has been cancelled.",
    },
    "site_visit_reminder_24h": {
        "subject": "Reminder: your site visit to {project} is tomorrow",
        "headline": "Your site visit is tomorrow",
        "lead": "This is a reminder about your visit to {project}.",
    },
    "site_visit_reminder_2h": {
        "subject": "Reminder: your site visit to {project} is in about 2 hours",
        "headline": "Your site visit is coming up",
        "lead": "This is a reminder about your visit to {project} in about 2 hours.",
    },
}


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text_body: str
    html_body: str


def format_ist(iso_value: str) -> str:
    return datetime.fromisoformat(iso_value).astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


def visit_link(visit_id: Optional[str]) -> Optional[str]:
    """Authenticated portal link; carries only the visit id, no personal data."""
    if not visit_id:
        return None
    return f"{settings.customer_portal_base_url}/customer/visits/{visit_id}"


def _clean(value: Any) -> str:
    return " ".join(str(value).split()) if value else ""


def render_email(template_key: str, payload: Dict[str, Any]) -> RenderedEmail:
    """
    Renders from the minimal stored payload only. Every interpolated value is
    HTML-escaped in the HTML body and control-character-normalised for the
    subject/text parts. Raises KeyError for an unknown template.
    """
    copy = _COPY[template_key]
    project = _clean(payload.get("project_name")) or "your project"
    first_name = _clean(payload.get("first_name"))
    location = _clean(payload.get("project_location"))
    rera = _clean(payload.get("project_rera_number"))
    map_link = map_url_for(project, location) if location else None
    executive = _clean(payload.get("executive_name"))
    start = payload.get("start_time")
    previous = payload.get("previous_start_time")
    link = visit_link(payload.get("visit_id"))
    support = _clean(settings.EMAIL_SUPPORT_CONTACT)

    subject = copy["subject"].format(project=project)
    lead = copy["lead"].format(project=project)
    greeting = f"Hi {first_name}," if first_name else "Hello,"

    details = []
    if start:
        details.append(("Date and time", format_ist(start)))
    if template_key == "site_visit_rescheduled" and previous:
        details.append(("Previously scheduled", format_ist(previous)))
    if location:
        details.append(("Location", location))
    if rera:
        details.append(("RERA registration", rera))
    if executive and template_key != "site_visit_cancelled":
        details.append(("Your contact at the site", executive))

    text_lines = [greeting, "", lead, ""]
    text_lines += [f"{k}: {v}" for k, v in details]
    if map_link and template_key != "site_visit_cancelled":
        text_lines += ["", f"Open in maps: {map_link}"]
    if link and template_key != "site_visit_cancelled":
        text_lines += ["", f"View your visit: {link}"]
    elif template_key == "site_visit_cancelled" and link:
        text_lines += ["", f"Visit details: {link}"]
    if support:
        text_lines += ["", f"Need help? {support}"]
    text_lines += ["", "You are receiving this because you booked a site visit with EstateFlow."]
    text_body = "\n".join(text_lines)

    rows = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#737C76;font-size:14px">{escape(k)}</td>'
        f'<td style="padding:4px 0;color:#202B28;font-size:14px;font-weight:600">{escape(v)}</td></tr>'
        for k, v in details
    )
    map_html = (
        f'<p style="margin:16px 0 0"><a href="{escape(map_link, quote=True)}" '
        f'style="color:{_BRAND};font-size:14px;font-weight:600">Open the location in maps</a></p>'
        if map_link and template_key != "site_visit_cancelled"
        else ""
    )
    button = (
        f'<p style="margin:24px 0"><a href="{escape(link, quote=True)}" '
        f'style="background:{_BRAND};color:#ffffff;text-decoration:none;padding:12px 20px;'
        f'border-radius:8px;font-weight:600;font-size:14px;display:inline-block">View your visit</a></p>'
        if link
        else ""
    )
    support_html = (
        f'<p style="font-size:13px;color:#737C76">Need help? {escape(support)}</p>' if support else ""
    )
    html_body = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(subject)}</title></head>"
        '<body style="margin:0;background:#F7F6F2;font-family:Arial,Helvetica,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:560px;background:#ffffff;border:1px solid #E5E5DE;border-radius:12px">'
        f'<tr><td style="background:{_BRAND};color:#ffffff;padding:16px 24px;border-radius:12px 12px 0 0;'
        'font-weight:700;font-size:16px">EstateFlow</td></tr>'
        '<tr><td style="padding:24px">'
        f'<h1 style="margin:0 0 12px;font-size:20px;color:#202B28">{escape(copy["headline"])}</h1>'
        f'<p style="margin:0 0 8px;font-size:14px;color:#202B28">{escape(greeting)}</p>'
        f'<p style="margin:0 0 16px;font-size:14px;color:#202B28">{escape(lead)}</p>'
        f'<table role="presentation" cellpadding="0" cellspacing="0">{rows}</table>'
        f"{map_html}{button}{support_html}"
        '<p style="margin:16px 0 0;font-size:12px;color:#9EA69F">You are receiving this service message '
        "because you booked a site visit with EstateFlow.</p>"
        "</td></tr></table></td></tr></table></body></html>"
    )
    return RenderedEmail(subject=subject, text_body=text_body, html_body=html_body)
