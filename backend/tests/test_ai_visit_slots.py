"""Pure unit tests (no database) for the assistant's deterministic visit-slot reply."""
import datetime as dt
import uuid
from types import SimpleNamespace as NS

from backend.ai.prompts import build_extraction_system_prompt, build_response_system_prompt
from backend.ai.visit_slots import build_visit_slots_reply, missing_qualification_details

PID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DAY = dt.date(2026, 11, 10)


def _slot(utc_hour, utc_minute=0):
    return NS(start_time=dt.datetime(2026, 11, 10, utc_hour, utc_minute, tzinfo=dt.timezone.utc))


def test_reply_lists_real_slots_in_ist_with_prefilled_link():
    reply = build_visit_slots_reply(
        language="EN", project_name="Project 1", project_id=PID, target_date=DAY,
        slots=[_slot(6), _slot(5)], portal_base_url="https://app.example/",
    )
    assert "10:30 am, 11:30 am" in reply  # UTC 05:00/06:00 -> IST, sorted
    assert f"https://app.example/customer/visits/book?project={PID}&date=2026-11-10" in reply
    assert "booked only once you confirm" in reply


def test_reply_never_claims_a_booking_and_handles_no_free_slots():
    reply = build_visit_slots_reply(
        language="EN", project_name="Project 1", project_id=PID, target_date=DAY, slots=[], portal_base_url="https://app.example",
    )
    assert "no free times" in reply.lower()
    assert "booked" not in reply.lower()


def test_reply_is_localised_and_caps_the_list():
    slots = [_slot(h) for h in range(3, 12)]
    hi = build_visit_slots_reply(language="HI", project_name="P", project_id=PID, target_date=DAY, slots=slots, portal_base_url="https://a")
    gu = build_visit_slots_reply(language="GU", project_name="P", project_id=PID, target_date=DAY, slots=slots, portal_base_url="https://a")
    assert "खाली" in hi and "ખાલી" in gu
    assert hi.count(" am") + hi.count(" pm") == 6 and "..." in hi


def test_missing_details_only_lists_what_is_unknown():
    assert len(missing_qualification_details(None)) == 3
    known = NS(configuration="BHK_3", budget_min=None, budget_max=5000000, purchase_purpose=None)
    assert missing_qualification_details(known) == ["purpose (own use or investment)"]
    full = NS(configuration="BHK_2", budget_min=1, budget_max=2, purchase_purpose="SELF_USE")
    assert missing_qualification_details(full) == []


def test_prompts_forbid_promising_visits_and_ask_for_one_missing_detail():
    prompt = build_response_system_prompt(language="EN", knowledge_context="x", missing_details=["budget range"])
    assert "Never say or imply that a site visit is booked" in prompt
    assert "budget range" in prompt and "exactly ONE" in prompt
    assert "exactly ONE" not in build_response_system_prompt(language="EN", knowledge_context="x")
    assert "TODAY (India, IST) is 2026-11-09" in build_extraction_system_prompt("2026-11-09")
