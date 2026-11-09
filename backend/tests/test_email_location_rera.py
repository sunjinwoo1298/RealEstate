"""Pure unit tests (no database): visit emails carry the RERA number and a map link (client brief)."""
from backend.core.location import map_url_for
from backend.services.customer_email_templates import render_email

PAYLOAD = {
    "first_name": "Asha",
    "project_name": "Project 1",
    "project_location": "SG Highway, Ahmedabad",
    "project_rera_number": "PR/GJ/AHMEDABAD/TEST/0001",
    "start_time": "2026-11-12T09:30:00+00:00",
    "visit_id": "abc",
}


def test_map_url_is_built_from_stored_location_only():
    assert map_url_for("Project 1", "SG Highway, Ahmedabad") == (
        "https://www.google.com/maps/search/?api=1&query=Project+1+SG+Highway%2C+Ahmedabad"
    )
    assert map_url_for("Project 1", None) is None  # never a made-up pin
    assert map_url_for("Project 1", "   ") is None


def test_booked_and_reminder_emails_show_rera_and_map_link():
    for key in ("site_visit_booked", "site_visit_rescheduled", "site_visit_reminder_24h", "site_visit_reminder_2h"):
        email = render_email(key, PAYLOAD)
        assert "RERA registration: PR/GJ/AHMEDABAD/TEST/0001" in email.text_body
        assert "google.com/maps/search" in email.text_body
        assert "Open the location in maps" in email.html_body


def test_cancelled_email_has_no_map_but_still_works_without_rera():
    cancelled = render_email("site_visit_cancelled", PAYLOAD)
    assert "google.com/maps" not in cancelled.text_body
    no_rera = render_email("site_visit_booked", {**PAYLOAD, "project_rera_number": None})
    assert "RERA" not in no_rera.text_body
