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
        "free": "These times are free for {project} on {day}: {times}. Tell me the time you would like and I will book it here in the chat, or choose it yourself: {link} — your visit is booked only once you confirm it.",
        "none": "There are no free times for {project} on {day}. Please pick another day: {link}",
    },
    "HI": {
        "free": "{project} के लिए {day} को ये समय खाली हैं: {times}। मुझे अपना पसंदीदा समय बताएँ, मैं यहीं बुक कर दूँगा, या खुद चुनें: {link} — विज़िट तभी बुक मानी जाएगी जब आप पुष्टि करेंगे।",
        "none": "{project} के लिए {day} को कोई समय खाली नहीं है। कृपया दूसरा दिन चुनें: {link}",
    },
    "GU": {
        "free": "{project} માટે {day}ના રોજ આ સમય ખાલી છે: {times}. તમારો પસંદગીનો સમય કહો, હું અહીં જ બુક કરી દઈશ, અથવા જાતે પસંદ કરો: {link} — તમે પુષ્ટિ કરશો ત્યારે જ મુલાકાત બુક ગણાશે.",
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


# --- booking inside the chat ----------------------------------------------------

_BOOK_TEMPLATES = {
    "EN": {
        "ask": "{time} is free for {project} on {day}. Reply \"yes\" and I will book it for you.",
        "done": "Done! Your visit to {project} is booked for {day} at {time} (IST). Booking reference: {ref}.{place} You will get reminders 1 day and 2 hours before.",
        "taken": "Sorry, {time} is no longer free for {project} on {day}.",
    },
    "HI": {
        "ask": "{project} के लिए {day} को {time} खाली है। बुक करने के लिए \"हाँ\" लिखें।",
        "done": "हो गया! {project} की आपकी विज़िट {day} को {time} (IST) पर बुक हो गई है। बुकिंग संदर्भ: {ref}।{place} आपको 1 दिन और 2 घंटे पहले रिमाइंडर मिलेंगे।",
        "taken": "क्षमा करें, {project} के लिए {day} को {time} अब खाली नहीं है।",
    },
    "GU": {
        "ask": "{project} માટે {day}ના રોજ {time} ખાલી છે. બુક કરવા માટે \"હા\" લખો.",
        "done": "થઈ ગયું! {project} ની તમારી મુલાકાત {day}ના રોજ {time} (IST) માટે બુક થઈ ગઈ છે. બુકિંગ સંદર્ભ: {ref}.{place} તમને 1 દિવસ અને 2 કલાક પહેલાં રિમાઇન્ડર મળશે.",
        "taken": "માફ કરશો, {project} માટે {day}ના રોજ {time} હવે ખાલી નથી.",
    },
}


def _day(target_date: date) -> str:
    return f"{target_date.day} {target_date.strftime('%b %Y')}"


def format_ist_time(moment: datetime) -> str:
    return moment.astimezone(_IST).strftime("%I:%M %p").lstrip("0").lower()


def pick_slot(slots: Sequence, target_date: date, hhmm: Optional[str]):
    """The real free slot starting exactly at HH:MM India time on target_date, else None."""
    if not hhmm:
        return None
    try:
        hour, minute = (int(part) for part in hhmm.split(":"))
        wanted = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=_IST)
    except (ValueError, TypeError):
        return None
    for slot in slots:
        if slot.start_time == wanted:
            return slot
    return None


def build_confirm_time_reply(*, language: str, project_name: str, target_date: date, slot) -> str:
    t = _BOOK_TEMPLATES.get(language, _BOOK_TEMPLATES["EN"])
    return t["ask"].format(time=format_ist_time(slot.start_time), project=project_name, day=_day(target_date))


def build_booked_reply(
    *, language: str, project_name: str, target_date: date, start_time: datetime, booking_reference: str,
    location: Optional[str] = None, map_url: Optional[str] = None, rera_number: Optional[str] = None,
) -> str:
    t = _BOOK_TEMPLATES.get(language, _BOOK_TEMPLATES["EN"])
    place = ""
    if location:
        place += f" Location: {location}" + (f" ({map_url})" if map_url else "") + "."
    if rera_number:
        place += f" RERA: {rera_number}."
    return t["done"].format(
        project=project_name, day=_day(target_date), time=format_ist_time(start_time), ref=booking_reference, place=place
    )


def build_time_taken_reply(*, language: str, project_name: str, target_date: date, hhmm: str, slots_reply: str) -> str:
    t = _BOOK_TEMPLATES.get(language, _BOOK_TEMPLATES["EN"])
    try:
        shown = datetime(2000, 1, 1, int(hhmm[:2]), int(hhmm[3:5])).strftime("%I:%M %p").lstrip("0").lower()
    except ValueError:
        shown = hhmm
    return t["taken"].format(time=shown, project=project_name, day=_day(target_date)) + " " + slots_reply
