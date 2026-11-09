"""Deterministic (non-LLM) pieces of the assistant's site-visit and qualification flow."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional, Sequence
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")
_MAX_SLOTS_SHOWN = 6

_TEMPLATES = {
    "EN": {
        "free": "These times are free for {project} on {day}: {times}. {link} — your visit is booked only once you confirm it there.",
        "none": "There are no free times for {project} on {day}. Please pick another day: {link}",
    },
    "HI": {
        "free": "{project} के लिए {day} को ये समय खाली हैं: {times}। {link} — विज़िट तभी बुक मानी जाएगी जब आप वहाँ पुष्टि करेंगे।",
        "none": "{project} के लिए {day} को कोई समय खाली नहीं है। कृपया दूसरा दिन चुनें: {link}",
    },
    "GU": {
        "free": "{project} માટે {day}ના રોજ આ સમય ખાલી છે: {times}. {link} — તમે ત્યાં પુષ્ટિ કરશો ત્યારે જ મુલાકાત બુક ગણાશે.",
        "none": "{project} માટે {day}ના રોજ કોઈ સમય ખાલી નથી. કૃપા કરીને બીજો દિવસ પસંદ કરો: {link}",
    },
}


def build_visit_slots_reply(
    *,
    language: str,
    project_name: str,
    project_id: uuid.UUID,
    target_date: date,
    slots: Sequence,
    portal_base_url: str,
) -> str:
    """
    Lists the real free start times (IST) for the date, plus a link into the
    transactional booking flow pre-filled with project and date. The assistant
    never books or promises a time itself; the booking is only made once the
    buyer confirms it in that flow.
    """
    templates = _TEMPLATES.get(language, _TEMPLATES["EN"])
    link = f"{portal_base_url.rstrip('/')}/customer/visits/book?project={project_id}&date={target_date.isoformat()}"
    day = f"{target_date.day} {target_date.strftime('%b %Y')}"
    starts: List[datetime] = sorted(slot.start_time for slot in slots)
    if not starts:
        return templates["none"].format(project=project_name, day=day, link=link)
    shown = starts[:_MAX_SLOTS_SHOWN]
    times = ", ".join(s.astimezone(_IST).strftime("%I:%M %p").lstrip("0").lower() for s in shown)
    if len(starts) > len(shown):
        times += ", ..."
    return templates["free"].format(project=project_name, day=day, times=times, link=link)


def missing_qualification_details(qualification: Optional[object]) -> List[str]:
    """What we still need to learn about the buyer (project excluded: asked via the chat itself)."""
    missing: List[str] = []
    if qualification is None or getattr(qualification, "configuration", None) is None:
        missing.append("preferred configuration (2 BHK or 3 BHK)")
    if qualification is None or (
        getattr(qualification, "budget_min", None) is None and getattr(qualification, "budget_max", None) is None
    ):
        missing.append("budget range")
    if qualification is None or getattr(qualification, "purchase_purpose", None) is None:
        missing.append("purpose (own use or investment)")
    return missing
