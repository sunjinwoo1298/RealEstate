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


def test_pick_slot_matches_only_exact_free_start_in_ist():
    from backend.ai.visit_slots import build_booked_reply, build_confirm_time_reply, build_time_taken_reply, pick_slot

    slots = [_slot(5, 30), _slot(6, 30)]  # 11:00 and 12:00 IST
    assert pick_slot(slots, DAY, "11:00") is slots[0]
    assert pick_slot(slots, DAY, "11:30") is None  # not a free start
    assert pick_slot(slots, DAY, "nonsense") is None and pick_slot(slots, DAY, None) is None
    assert "11:00 am is free" in build_confirm_time_reply(language="EN", project_name="P", target_date=DAY, slot=slots[0])
    done = build_booked_reply(
        language="EN", project_name="P", target_date=DAY, start_time=slots[0].start_time, booking_reference="SV-1",
        location="SG Highway", map_url="https://maps", rera_number="RERA-1",
    )
    assert "SV-1" in done and "RERA: RERA-1" in done and "reminders 1 day and 2 hours" in done
    taken = build_time_taken_reply(language="EN", project_name="P", target_date=DAY, hhmm="15:00", slots_reply="Other times: ...")
    assert "3:00 pm is no longer free" in taken and "Other times" in taken


def test_flagged_reasons_cover_guardrails_and_escalations():
    from backend.services.flagged_chat_service import FlaggedChatService as F

    assert F.reasons_from_metadata(None) == [] and F.reasons_from_metadata({"guardrail_flags": {"complaint_detected": False}}) == []
    got = F.reasons_from_metadata({"guardrail_flags": {"prompt_injection_detected": True}, "handoff_reason": "UNSUPPORTED_QUERY"})
    assert got == ["Suspicious instruction", "Escalated to a salesperson"]
