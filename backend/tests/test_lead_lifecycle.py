"""BUG-24: visit events must never move Lead.lead_status backwards."""
import pytest

from backend.models.lead import LeadStatus
from backend.models.site_visit import SiteVisitStatus
from backend.services.lead_lifecycle import status_after_attendance, status_after_booking

BOOKING_TABLE = {
    LeadStatus.NEW: LeadStatus.VISIT_BOOKED,
    LeadStatus.AI_CONTACTED: LeadStatus.VISIT_BOOKED,
    LeadStatus.QUALIFIED: LeadStatus.VISIT_BOOKED,
    LeadStatus.VISIT_REQUESTED: LeadStatus.VISIT_BOOKED,
    LeadStatus.VISIT_BOOKED: LeadStatus.VISIT_BOOKED,
    LeadStatus.VISIT_COMPLETED: LeadStatus.VISIT_COMPLETED,
    LeadStatus.CONVERTED: LeadStatus.CONVERTED,
    LeadStatus.LOST: LeadStatus.LOST,
    LeadStatus.OPTED_OUT: LeadStatus.OPTED_OUT,
}


def test_booking_table_covers_every_status():
    assert set(BOOKING_TABLE) == set(LeadStatus)


@pytest.mark.parametrize("current,expected", list(BOOKING_TABLE.items()))
def test_booking_transition(current, expected):
    assert status_after_booking(current) == expected


@pytest.mark.parametrize("current", [LeadStatus.CONVERTED, LeadStatus.LOST, LeadStatus.OPTED_OUT])
def test_attendance_never_overwrites_terminal_outcomes(current):
    assert status_after_attendance(current, SiteVisitStatus.COMPLETED) == current


@pytest.mark.parametrize("current", list(LeadStatus))
def test_no_show_never_changes_lead_status(current):
    assert status_after_attendance(current, SiteVisitStatus.NO_SHOW) == current


@pytest.mark.parametrize(
    "current",
    [LeadStatus.NEW, LeadStatus.AI_CONTACTED, LeadStatus.QUALIFIED, LeadStatus.VISIT_REQUESTED, LeadStatus.VISIT_BOOKED],
)
def test_completed_visit_advances_pre_visit_leads(current):
    assert status_after_attendance(current, SiteVisitStatus.COMPLETED) == LeadStatus.VISIT_COMPLETED


def test_completed_then_second_booking_stays_completed():
    status = status_after_attendance(LeadStatus.VISIT_BOOKED, SiteVisitStatus.COMPLETED)
    assert status_after_booking(status) == LeadStatus.VISIT_COMPLETED


def test_completed_lead_unchanged_by_later_no_show_or_cancellation():
    # Cancellation never touches lead_status at all; a no-show is a no-op.
    assert status_after_attendance(LeadStatus.VISIT_COMPLETED, SiteVisitStatus.NO_SHOW) == LeadStatus.VISIT_COMPLETED
