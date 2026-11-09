import asyncio
import secrets
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select, update

from backend.main import app
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.models.availability_rule import AvailabilityRule
from backend.models.blocked_period import BlockedPeriod
from backend.models.lead import ConsentStatus, Lead, LeadStatus
from backend.models.lead_source import LeadSource
from backend.models.project import Project
from backend.models.project_visit_capacity import ProjectVisitCapacity
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.models.user import User, UserRole
from backend.models.visit_event import VisitEvent, VisitEventType
from backend.models.visit_reminder import ReminderStatus, ReminderType, VisitReminder
from backend.services.booking_service import BookingService
from backend.services.reminder_delivery import ReminderDeliveryResult
from backend.services.reminder_worker_service import ReminderWorkerService

IST = ZoneInfo("Asia/Kolkata")

ADMIN_EMAIL = "test-reminder-admin@estateflow.ai"
EXEC1_EMAIL = "test-reminder-exec1@estateflow.ai"
EXEC2_EMAIL = "test-reminder-exec2@estateflow.ai"
PASSWORD = "SuperSecret123!"


def _unique_phone() -> str:
    return "9" + "".join(secrets.choice("0123456789") for _ in range(9))


@pytest_asyncio.fixture
async def db_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def seeded_users(db_session):
    emails = [ADMIN_EMAIL, EXEC1_EMAIL, EXEC2_EMAIL]
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()

    admin = User(email=ADMIN_EMAIL, full_name="Reminder Admin", password_hash=hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True)
    exec1 = User(email=EXEC1_EMAIL, full_name="Reminder Exec One", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    exec2 = User(email=EXEC2_EMAIL, full_name="Reminder Exec Two", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    db_session.add_all([admin, exec1, exec2])
    await db_session.commit()

    yield {"admin": admin, "exec1": exec1, "exec2": exec2}

    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()


@pytest_asyncio.fixture
async def project_with_capacity(db_session):
    project = Project(name=f"ReminderTest Project {uuid.uuid4().hex[:8]}", description="Test", location="Test City", is_active=True)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    capacity = ProjectVisitCapacity(project_id=project.id, capacity=5, visit_duration_minutes=30, buffer_minutes=0)
    db_session.add(capacity)
    await db_session.commit()

    yield project, capacity


@pytest_asyncio.fixture
async def test_lead(db_session):
    lead = Lead(full_name="ReminderTest Buyer", normalized_phone=_unique_phone(), lead_status=LeadStatus.QUALIFIED)
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    yield lead


@pytest_asyncio.fixture(autouse=True)
async def cleanup(db_session):
    yield
    test_lead_ids_result = await db_session.execute(select(Lead.id).where(Lead.full_name.like("ReminderTest%")))
    test_lead_ids = [row[0] for row in test_lead_ids_result.all()]

    await db_session.execute(delete(VisitReminder))
    await db_session.execute(delete(VisitEvent))
    await db_session.execute(delete(SiteVisit))
    await db_session.execute(delete(BlockedPeriod))
    await db_session.execute(delete(AvailabilityRule))
    await db_session.execute(delete(ProjectVisitCapacity))
    if test_lead_ids:
        await db_session.execute(delete(LeadSource).where(LeadSource.lead_id.in_(test_lead_ids)))
        await db_session.execute(delete(Lead).where(Lead.id.in_(test_lead_ids)))
    await db_session.execute(delete(Project).where(Project.name.like("ReminderTest%")))
    await db_session.commit()


async def _login(client, email):
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _add_full_day_rule(db_session, *, executive_id, project_id, day_of_week):
    rule = AvailabilityRule(
        executive_id=executive_id,
        project_id=project_id,
        day_of_week=day_of_week,
        start_time=time(0, 0),
        end_time=time(23, 55),
        is_active=True,
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


async def _book(db_session, *, lead, project, start_time, actor_id=None):
    return await BookingService.book_site_visit(
        db_session, lead_id=lead.id, project_id=project.id, start_time=start_time, actor_id=actor_id
    )


async def _reminders_for(db_session, site_visit_id):
    result = await db_session.execute(
        select(VisitReminder).where(VisitReminder.site_visit_id == site_visit_id).order_by(VisitReminder.scheduled_at)
    )
    return list(result.scalars().all())


class _AlwaysFailProvider:
    async def send(self, *, reminder, visit, lead, project):
        raise RuntimeError("simulated transient provider failure")


class _AlwaysSucceedProvider:
    async def send(self, *, reminder, visit, lead, project):
        return ReminderDeliveryResult(simulated=True, rendered_message="ok")


# --- Scheduling ---------------------------------------------------------


@pytest.mark.asyncio
async def test_booking_creates_24h_and_2h_reminders(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )

    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    reminders = await _reminders_for(db_session, visit.id)

    assert len(reminders) == 2
    types = {r.reminder_type for r in reminders}
    assert types == {ReminderType.H24, ReminderType.H2}
    for r in reminders:
        assert r.status == ReminderStatus.SCHEDULED
        assert r.booking_version == 1
    h24 = next(r for r in reminders if r.reminder_type == ReminderType.H24)
    h2 = next(r for r in reminders if r.reminder_type == ReminderType.H2)
    assert h24.scheduled_at == start_time - timedelta(hours=24)
    assert h2.scheduled_at == start_time - timedelta(hours=2)


@pytest.mark.asyncio
async def test_past_reminder_times_are_skipped(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    # Only 90 minutes away: both the 24h and 2h reminder times have already passed.
    start_time = datetime.now(timezone.utc) + timedelta(minutes=90)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )

    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    reminders = await _reminders_for(db_session, visit.id)
    assert reminders == []


@pytest.mark.asyncio
async def test_reschedule_cancels_old_and_creates_new(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    weekday = start_time.astimezone(IST).weekday()
    await _add_full_day_rule(db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=weekday)

    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    original_reminders = await _reminders_for(db_session, visit.id)
    assert len(original_reminders) == 2

    new_start_time = start_time + timedelta(hours=5)
    updated = await BookingService.reschedule_site_visit(db_session, visit.id, new_start_time=new_start_time)
    assert updated.booking_version == 2

    all_reminders = await _reminders_for(db_session, visit.id)
    old_rows = [r for r in all_reminders if r.booking_version == 1]
    new_rows = [r for r in all_reminders if r.booking_version == 2]
    assert len(old_rows) == 2
    assert all(r.status == ReminderStatus.CANCELLED for r in old_rows)
    assert len(new_rows) == 2
    assert all(r.status == ReminderStatus.SCHEDULED for r in new_rows)
    assert {r.scheduled_at for r in new_rows} == {
        new_start_time - timedelta(hours=24), new_start_time - timedelta(hours=2)
    }


@pytest.mark.asyncio
async def test_cancellation_cancels_pending_reminders(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )

    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    await BookingService.cancel_site_visit(db_session, visit.id)

    reminders = await _reminders_for(db_session, visit.id)
    assert len(reminders) == 2
    assert all(r.status == ReminderStatus.CANCELLED for r in reminders)


@pytest.mark.asyncio
async def test_completed_visit_cancels_remaining_reminders(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )

    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    await BookingService.record_attendance(db_session, visit.id, status=SiteVisitStatus.COMPLETED)

    reminders = await _reminders_for(db_session, visit.id)
    assert len(reminders) == 2
    assert all(r.status == ReminderStatus.CANCELLED for r in reminders)


@pytest.mark.asyncio
async def test_booking_detail_shows_current_generation_reminders_after_reschedule(
    client, db_session, seeded_users, project_with_capacity, test_lead
):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    headers = await _login(client, ADMIN_EMAIL)
    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    booking_id = booked.json()["id"]

    new_start_time = start_time + timedelta(hours=3)
    reschedule = await client.post(
        f"/api/v1/bookings/{booking_id}/reschedule", json={"start_time": new_start_time.isoformat()}, headers=headers
    )
    assert reschedule.status_code == 200

    detail = await client.get(f"/api/v1/bookings/{booking_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["project_name"] == project.name
    assert body["lead_full_name"] == test_lead.full_name
    assert body["reminder_24h"]["status"] == "SCHEDULED"
    assert body["reminder_24h"]["booking_version"] == 2
    assert body["reminder_2h"]["status"] == "SCHEDULED"
    assert body["reminder_2h"]["booking_version"] == 2


# --- Execution -----------------------------------------------------------


@pytest.mark.asyncio
async def test_due_reminder_is_picked_up_and_simulated(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)

    # Force the 2h reminder's scheduled_at into the past so it's due now.
    reminders = await _reminders_for(db_session, visit.id)
    h2 = next(r for r in reminders if r.reminder_type == ReminderType.H2)
    await db_session.execute(
        update(VisitReminder).where(VisitReminder.id == h2.id).values(scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_session.commit()

    claimed = await ReminderWorkerService.claim_due_reminders(db_session)
    claimed_ids = {r.id for r in claimed}
    assert h2.id in claimed_ids

    await ReminderWorkerService.process_reminder(db_session, h2.id, _AlwaysSucceedProvider())
    await db_session.refresh(h2)
    assert h2.status == ReminderStatus.SIMULATED
    assert h2.sent_at is not None


@pytest.mark.asyncio
async def test_multiple_workers_cannot_claim_same_reminder(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)

    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.execute(update(VisitReminder).where(VisitReminder.site_visit_id == visit.id).values(scheduled_at=past))
    await db_session.commit()

    factory = get_session_factory()
    async with factory() as session_a, factory() as session_b:
        results = await asyncio.gather(
            ReminderWorkerService.claim_due_reminders(session_a),
            ReminderWorkerService.claim_due_reminders(session_b),
        )

    ids_a = {r.id for r in results[0]}
    ids_b = {r.id for r in results[1]}
    assert ids_a.isdisjoint(ids_b)
    assert len(ids_a) + len(ids_b) == 2


@pytest.mark.asyncio
async def test_transient_failure_retries_with_backoff(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    reminders = await _reminders_for(db_session, visit.id)
    h2 = next(r for r in reminders if r.reminder_type == ReminderType.H2)

    await db_session.execute(
        update(VisitReminder).where(VisitReminder.id == h2.id).values(scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_session.commit()

    await ReminderWorkerService.claim_due_reminders(db_session)
    await ReminderWorkerService.process_reminder(db_session, h2.id, _AlwaysFailProvider())

    await db_session.refresh(h2)
    assert h2.status == ReminderStatus.SCHEDULED
    assert h2.attempt_count == 1
    assert h2.failure_reason is not None
    assert h2.scheduled_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_permanent_failure_marked_failed_after_max_attempts(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    reminders = await _reminders_for(db_session, visit.id)
    h2 = next(r for r in reminders if r.reminder_type == ReminderType.H2)

    from backend.core.config import settings

    await db_session.execute(
        update(VisitReminder)
        .where(VisitReminder.id == h2.id)
        .values(scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1), attempt_count=settings.REMINDER_MAX_ATTEMPTS - 1)
    )
    await db_session.commit()

    await ReminderWorkerService.claim_due_reminders(db_session)
    await ReminderWorkerService.process_reminder(db_session, h2.id, _AlwaysFailProvider())

    await db_session.refresh(h2)
    assert h2.status == ReminderStatus.FAILED
    assert h2.attempt_count == settings.REMINDER_MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_stale_booking_version_is_skipped(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    reminders = await _reminders_for(db_session, visit.id)
    h2 = next(r for r in reminders if r.reminder_type == ReminderType.H2)

    # Simulate the original (now-stale) reminder still being due after a
    # reschedule bumped the visit's booking_version.
    await db_session.execute(
        update(VisitReminder).where(VisitReminder.id == h2.id).values(scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_session.execute(update(SiteVisit).where(SiteVisit.id == visit.id).values(booking_version=2))
    await db_session.commit()

    await ReminderWorkerService.claim_due_reminders(db_session)
    await ReminderWorkerService.process_reminder(db_session, h2.id, _AlwaysSucceedProvider())

    await db_session.refresh(h2)
    assert h2.status == ReminderStatus.SKIPPED


class _MustNotSendProvider:
    async def send(self, *args, **kwargs):
        raise AssertionError("no reminder may be delivered to an opted-out lead")


@pytest.mark.asyncio
@pytest.mark.parametrize("opt_out", ["status", "consent"])
async def test_opted_out_lead_is_never_reminded(db_session, seeded_users, project_with_capacity, test_lead, opt_out):
    # DPDP / brief: honour opt-outs. The opt-out happens AFTER booking, so the
    # check must run when the reminder is processed, not only when booking.
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    reminders = await _reminders_for(db_session, visit.id)
    h2 = next(r for r in reminders if r.reminder_type == ReminderType.H2)

    values = {"lead_status": LeadStatus.OPTED_OUT} if opt_out == "status" else {"consent_status": ConsentStatus.DECLINED}
    await db_session.execute(update(Lead).where(Lead.id == test_lead.id).values(**values))
    await db_session.execute(
        update(VisitReminder).where(VisitReminder.id == h2.id).values(scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_session.commit()

    await ReminderWorkerService.claim_due_reminders(db_session)
    await ReminderWorkerService.process_reminder(db_session, h2.id, _MustNotSendProvider())

    await db_session.refresh(h2)
    assert h2.status == ReminderStatus.SKIPPED
    assert h2.failure_reason == "lead_opted_out"
    await db_session.refresh(visit)
    assert visit.status == SiteVisitStatus.CONFIRMED  # the booking itself is untouched


@pytest.mark.asyncio
async def test_cancelled_booking_is_never_reminded(db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    reminders = await _reminders_for(db_session, visit.id)
    h2 = next(r for r in reminders if r.reminder_type == ReminderType.H2)

    # Force the reminder back to SCHEDULED+due after cancellation already
    # cancelled it, to prove process_reminder's own re-check also protects
    # against a reminder that somehow became due for a cancelled visit.
    await db_session.execute(
        update(VisitReminder)
        .where(VisitReminder.id == h2.id)
        .values(scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1), status=ReminderStatus.SCHEDULED)
    )
    await db_session.commit()
    await BookingService.cancel_site_visit(db_session, visit.id)
    await db_session.execute(
        update(VisitReminder).where(VisitReminder.id == h2.id).values(status=ReminderStatus.SCHEDULED)
    )
    await db_session.commit()

    await ReminderWorkerService.claim_due_reminders(db_session)
    await ReminderWorkerService.process_reminder(db_session, h2.id, _AlwaysSucceedProvider())

    await db_session.refresh(h2)
    assert h2.status == ReminderStatus.SKIPPED


@pytest.mark.asyncio
async def test_logging_provider_marks_simulated_not_sent(db_session, seeded_users, project_with_capacity, test_lead):
    from backend.services.reminder_delivery import LoggingReminderDeliveryProvider

    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    visit = await _book(db_session, lead=test_lead, project=project, start_time=start_time)
    reminders = await _reminders_for(db_session, visit.id)
    h2 = next(r for r in reminders if r.reminder_type == ReminderType.H2)

    await db_session.execute(
        update(VisitReminder).where(VisitReminder.id == h2.id).values(scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_session.commit()

    await ReminderWorkerService.claim_due_reminders(db_session)
    await ReminderWorkerService.process_reminder(db_session, h2.id, LoggingReminderDeliveryProvider())

    await db_session.refresh(h2)
    assert h2.status == ReminderStatus.SIMULATED
    assert h2.status != ReminderStatus.SENT


# --- Attendance -----------------------------------------------------------


async def _mark_visit_started(db_session, booking_id: str) -> None:
    """
    Bookings can only be created in the future, but attendance may only be
    recorded once a visit has started. Simulate the passage of time by moving
    the booked visit into the past (reminder rows are left untouched).
    """
    now = datetime.now(timezone.utc)
    await db_session.execute(
        update(SiteVisit)
        .where(SiteVisit.id == uuid.UUID(booking_id))
        .values(start_time=now - timedelta(hours=2), end_time=now - timedelta(hours=1))
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_authorized_staff_can_mark_attended_and_no_show(client, db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    headers = await _login(client, ADMIN_EMAIL)
    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    booking_id = booked.json()["id"]
    await _mark_visit_started(db_session, booking_id)

    resp = await client.post(f"/api/v1/bookings/{booking_id}/attendance", json={"status": "NO_SHOW"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "NO_SHOW"


@pytest.mark.asyncio
async def test_unauthorized_executive_cannot_mark_attendance(client, db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    weekday = start_time.astimezone(IST).weekday()
    await _add_full_day_rule(db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=weekday)

    admin_headers = await _login(client, ADMIN_EMAIL)
    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=admin_headers,
    )
    booking_id = booked.json()["id"]
    assert booked.json()["executive_id"] == str(seeded_users["exec1"].id)

    exec2_headers = await _login(client, EXEC2_EMAIL)
    resp = await client.post(
        f"/api/v1/bookings/{booking_id}/attendance", json={"status": "COMPLETED"}, headers=exec2_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invalid_attendance_transition_rejected(client, db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    headers = await _login(client, ADMIN_EMAIL)
    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    booking_id = booked.json()["id"]
    await _mark_visit_started(db_session, booking_id)

    first = await client.post(f"/api/v1/bookings/{booking_id}/attendance", json={"status": "COMPLETED"}, headers=headers)
    assert first.status_code == 200

    second = await client.post(f"/api/v1/bookings/{booking_id}/attendance", json={"status": "NO_SHOW"}, headers=headers)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_attendance_update_creates_visit_event(client, db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    headers = await _login(client, ADMIN_EMAIL)
    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    booking_id = booked.json()["id"]
    await _mark_visit_started(db_session, booking_id)

    await client.post(f"/api/v1/bookings/{booking_id}/attendance", json={"status": "COMPLETED"}, headers=headers)

    events_result = await db_session.execute(
        select(VisitEvent).where(
            VisitEvent.site_visit_id == uuid.UUID(booking_id), VisitEvent.event_type == VisitEventType.ATTENDANCE_MARKED
        )
    )
    events = list(events_result.scalars().all())
    assert len(events) == 1
    assert events[0].extra_metadata["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_finalized_attendance_cancels_pending_reminders_via_api(
    client, db_session, seeded_users, project_with_capacity, test_lead
):
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    headers = await _login(client, ADMIN_EMAIL)
    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    booking_id = booked.json()["id"]
    await _mark_visit_started(db_session, booking_id)

    reminders_before = await db_session.execute(
        select(VisitReminder).where(VisitReminder.site_visit_id == uuid.UUID(booking_id))
    )
    assert len(list(reminders_before.scalars().all())) == 2

    await client.post(f"/api/v1/bookings/{booking_id}/attendance", json={"status": "NO_SHOW"}, headers=headers)

    reminders_after = await db_session.execute(
        select(VisitReminder)
        .where(VisitReminder.site_visit_id == uuid.UUID(booking_id))
        .execution_options(populate_existing=True)
    )
    rows = list(reminders_after.scalars().all())
    assert len(rows) == 2
    assert all(r.status == ReminderStatus.CANCELLED for r in rows)


@pytest.mark.asyncio
async def test_attendance_rejected_before_visit_starts(client, db_session, seeded_users, project_with_capacity, test_lead):
    """E2E BUG-8: a future visit can be neither attended nor a no-show."""
    project, _ = project_with_capacity
    start_time = datetime.now(timezone.utc) + timedelta(days=3)
    await _add_full_day_rule(
        db_session, executive_id=seeded_users["exec1"].id, project_id=project.id, day_of_week=start_time.astimezone(IST).weekday()
    )
    headers = await _login(client, ADMIN_EMAIL)
    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    booking_id = booked.json()["id"]

    for status in ("COMPLETED", "NO_SHOW"):
        resp = await client.post(f"/api/v1/bookings/{booking_id}/attendance", json={"status": status}, headers=headers)
        assert resp.status_code == 409

    detail = await client.get(f"/api/v1/bookings/{booking_id}", headers=headers)
    assert detail.json()["status"] == "CONFIRMED"
    reminders = await db_session.execute(
        select(VisitReminder).where(VisitReminder.site_visit_id == uuid.UUID(booking_id)).execution_options(populate_existing=True)
    )
    assert all(r.status != ReminderStatus.CANCELLED for r in reminders.scalars().all())

    await _mark_visit_started(db_session, booking_id)
    resp = await client.post(f"/api/v1/bookings/{booking_id}/attendance", json={"status": "COMPLETED"}, headers=headers)
    assert resp.status_code == 200
