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
from backend.models.lead import Lead, LeadStatus
from backend.models.lead_source import LeadSource
from backend.models.project import Project
from backend.models.project_visit_capacity import ProjectVisitCapacity
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.models.user import User, UserRole
from backend.models.visit_event import VisitEvent

IST = ZoneInfo("Asia/Kolkata")

ADMIN_EMAIL = "test-booking-admin@estateflow.ai"
EXEC1_EMAIL = "test-booking-exec1@estateflow.ai"
EXEC2_EMAIL = "test-booking-exec2@estateflow.ai"
PASSWORD = "SuperSecret123!"


def _unique_phone() -> str:
    return "9" + "".join(secrets.choice("0123456789") for _ in range(9))


def _next_weekday(target_weekday: int) -> "datetime.date":
    today = datetime.now(IST).date()
    days_ahead = (target_weekday - today.weekday()) % 7
    days_ahead = days_ahead if days_ahead > 0 else 7
    return today + timedelta(days=days_ahead)


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

    admin = User(email=ADMIN_EMAIL, full_name="Booking Admin", password_hash=hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True)
    exec1 = User(email=EXEC1_EMAIL, full_name="Booking Exec One", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    exec2 = User(email=EXEC2_EMAIL, full_name="Booking Exec Two", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    db_session.add_all([admin, exec1, exec2])
    await db_session.commit()

    yield {"admin": admin, "exec1": exec1, "exec2": exec2}

    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()


@pytest_asyncio.fixture
async def project_with_capacity(db_session):
    project = Project(name=f"BookingTest Project {uuid.uuid4().hex[:8]}", description="Test", location="Test City", is_active=True)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    capacity = ProjectVisitCapacity(project_id=project.id, capacity=1, visit_duration_minutes=30, buffer_minutes=0)
    db_session.add(capacity)
    await db_session.commit()

    yield project, capacity


@pytest_asyncio.fixture
async def test_lead(db_session):
    lead = Lead(full_name="BookingTest Buyer", normalized_phone=_unique_phone(), lead_status=LeadStatus.QUALIFIED)
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    yield lead


@pytest_asyncio.fixture(autouse=True)
async def cleanup(db_session):
    yield
    # Scoped to this file's own test data: Lead/LeadSource are shared tables
    # that also hold real seeded demo leads, so they must never be
    # blanket-deleted here (unlike the booking-specific tables below, which
    # have no other production usage yet).
    test_lead_ids_result = await db_session.execute(select(Lead.id).where(Lead.full_name.like("BookingTest%")))
    test_lead_ids = [row[0] for row in test_lead_ids_result.all()]

    await db_session.execute(delete(VisitEvent))
    await db_session.execute(delete(SiteVisit))
    await db_session.execute(delete(BlockedPeriod))
    await db_session.execute(delete(AvailabilityRule))
    await db_session.execute(delete(ProjectVisitCapacity))
    if test_lead_ids:
        await db_session.execute(delete(LeadSource).where(LeadSource.lead_id.in_(test_lead_ids)))
        await db_session.execute(delete(Lead).where(Lead.id.in_(test_lead_ids)))
    await db_session.execute(delete(Project).where(Project.name.like("BookingTest%")))
    await db_session.commit()


async def _login(client, email):
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _add_rule(db_session, *, executive_id, project_id=None, day_of_week, start="09:00", end="18:00"):
    rule = AvailabilityRule(
        executive_id=executive_id,
        project_id=project_id,
        day_of_week=day_of_week,
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
        is_active=True,
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


def _slot_start_utc(target_date, local_time: time) -> datetime:
    return datetime.combine(target_date, local_time, tzinfo=IST).astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_executive_availability_calculation(client, db_session, seeded_users, project_with_capacity):
    project, _ = project_with_capacity
    target_date = _next_weekday(2)  # a Wednesday, well clear of "today" edge cases
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())

    headers = await _login(client, ADMIN_EMAIL)
    resp = await client.get(
        "/api/v1/availability", params={"project_id": str(project.id), "date": target_date.isoformat()}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["slots"]) > 0
    assert all(s["available_executive_count"] >= 1 for s in body["slots"])


@pytest.mark.asyncio
async def test_working_hours_and_blocked_period_restrictions(client, db_session, seeded_users, project_with_capacity):
    project, _ = project_with_capacity
    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday(), start="09:00", end="10:00")

    # Block the executive's entire working window for this day.
    db_session.add(
        BlockedPeriod(
            executive_id=seeded_users["exec1"].id,
            start_time=_slot_start_utc(target_date, time(0, 0)),
            end_time=_slot_start_utc(target_date, time(23, 59)),
            reason="On leave",
        )
    )
    await db_session.commit()

    headers = await _login(client, ADMIN_EMAIL)
    resp = await client.get(
        "/api/v1/availability", params={"project_id": str(project.id), "date": target_date.isoformat()}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["slots"] == []


@pytest.mark.asyncio
async def test_successful_booking_and_executive_assignment(client, db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    start_time = _slot_start_utc(target_date, time(10, 0))

    headers = await _login(client, ADMIN_EMAIL)
    resp = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "CONFIRMED"
    assert body["executive_id"] == str(seeded_users["exec1"].id)
    assert body["booking_reference"].startswith("SV-")

    lead_result = await db_session.execute(
        select(Lead).where(Lead.id == test_lead.id).execution_options(populate_existing=True)
    )
    lead = lead_result.scalar_one()
    assert lead.lead_status == LeadStatus.VISIT_BOOKED


@pytest.mark.asyncio
async def test_overlap_detection_rejects_second_booking_for_same_executive(
    client, db_session, seeded_users, project_with_capacity, test_lead
):
    # capacity=2 so the project-capacity gate doesn't mask the executive-overlap gate
    project, capacity = project_with_capacity
    capacity.capacity = 2
    await db_session.commit()

    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    start_time = _slot_start_utc(target_date, time(11, 0))

    headers = await _login(client, ADMIN_EMAIL)
    lead2 = Lead(full_name="BookingTest Second Buyer", normalized_phone=_unique_phone())
    db_session.add(lead2)
    await db_session.commit()

    first = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    assert first.status_code == 201

    # Only one executive is configured for this project/day, so a second,
    # overlapping booking must fail even though project capacity allows 2.
    second = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(lead2.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_project_capacity_enforcement(client, db_session, seeded_users, project_with_capacity, test_lead):
    project, capacity = project_with_capacity
    capacity.capacity = 1
    await db_session.commit()

    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    await _add_rule(db_session, executive_id=seeded_users["exec2"].id, day_of_week=target_date.weekday())
    start_time = _slot_start_utc(target_date, time(12, 0))

    headers = await _login(client, ADMIN_EMAIL)
    lead2 = Lead(full_name="BookingTest Second Buyer Cap", normalized_phone=_unique_phone())
    db_session.add(lead2)
    await db_session.commit()

    first = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    assert first.status_code == 201

    # Two executives are free, but site capacity is 1 -- the second request
    # must be rejected even though an executive would otherwise be free.
    second = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(lead2.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_concurrent_requests_for_same_executive_slot(client, db_session, seeded_users, project_with_capacity):
    project, capacity = project_with_capacity
    capacity.capacity = 8  # capacity isn't the constraint under test; the single executive is
    await db_session.commit()

    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    start_time = _slot_start_utc(target_date, time(13, 0))

    headers = await _login(client, ADMIN_EMAIL)
    leads = []
    for i in range(5):
        lead = Lead(full_name=f"BookingTest Concurrent Buyer {i}", normalized_phone=_unique_phone())
        db_session.add(lead)
        leads.append(lead)
    await db_session.commit()

    async def _book(lead_id):
        return await client.post(
            "/api/v1/bookings",
            json={"lead_id": str(lead_id), "project_id": str(project.id), "start_time": start_time.isoformat()},
            headers=headers,
        )

    results = await asyncio.gather(*[_book(l.id) for l in leads])
    statuses = [r.status_code for r in results]
    assert statuses.count(201) == 1
    assert statuses.count(409) == 4


@pytest.mark.asyncio
async def test_concurrent_requests_exceeding_site_capacity(client, db_session, seeded_users, project_with_capacity):
    project, capacity = project_with_capacity
    capacity.capacity = 2
    await db_session.commit()

    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    await _add_rule(db_session, executive_id=seeded_users["exec2"].id, day_of_week=target_date.weekday())
    start_time = _slot_start_utc(target_date, time(14, 0))

    headers = await _login(client, ADMIN_EMAIL)
    leads = []
    for i in range(5):
        lead = Lead(full_name=f"BookingTest Capacity Buyer {i}", normalized_phone=_unique_phone())
        db_session.add(lead)
        leads.append(lead)
    await db_session.commit()

    async def _book(lead_id):
        return await client.post(
            "/api/v1/bookings",
            json={"lead_id": str(lead_id), "project_id": str(project.id), "start_time": start_time.isoformat()},
            headers=headers,
        )

    results = await asyncio.gather(*[_book(l.id) for l in leads])
    statuses = [r.status_code for r in results]
    assert statuses.count(201) == 2
    assert statuses.count(409) == 3


@pytest.mark.asyncio
async def test_booking_idempotency(client, db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    start_time = _slot_start_utc(target_date, time(15, 0))

    headers = await _login(client, ADMIN_EMAIL)
    headers_with_key = {**headers, "Idempotency-Key": "booking-test-key-1"}

    first = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers_with_key,
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers_with_key,
    )
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    count_result = await db_session.execute(select(SiteVisit).where(SiteVisit.lead_id == test_lead.id))
    assert len(count_result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_cancellation_releases_capacity(client, db_session, seeded_users, project_with_capacity, test_lead):
    project, capacity = project_with_capacity
    capacity.capacity = 1
    await db_session.commit()

    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    start_time = _slot_start_utc(target_date, time(16, 0))

    headers = await _login(client, ADMIN_EMAIL)
    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    assert booked.status_code == 201
    booking_id = booked.json()["id"]

    cancel = await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"

    lead2 = Lead(full_name="BookingTest Rebooking Buyer", normalized_phone=_unique_phone())
    db_session.add(lead2)
    await db_session.commit()

    rebooked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(lead2.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    assert rebooked.status_code == 201

    cancel_again = await client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=headers)
    assert cancel_again.status_code == 409


@pytest.mark.asyncio
async def test_reschedule_conflict_leaves_original_untouched(
    client, db_session, seeded_users, project_with_capacity, test_lead
):
    project, capacity = project_with_capacity
    capacity.capacity = 1
    await db_session.commit()

    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    slot_a = _slot_start_utc(target_date, time(9, 0))
    slot_b = _slot_start_utc(target_date, time(9, 30))

    headers = await _login(client, ADMIN_EMAIL)
    first = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": slot_a.isoformat()},
        headers=headers,
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    lead2 = Lead(full_name="BookingTest Blocking Buyer", normalized_phone=_unique_phone())
    db_session.add(lead2)
    await db_session.commit()
    second = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(lead2.id), "project_id": str(project.id), "start_time": slot_b.isoformat()},
        headers=headers,
    )
    assert second.status_code == 201

    # Capacity is 1 and slot_b is already fully booked -- rescheduling the
    # first visit into it must fail and leave the first visit untouched.
    reschedule = await client.post(
        f"/api/v1/bookings/{first_id}/reschedule", json={"start_time": slot_b.isoformat()}, headers=headers
    )
    assert reschedule.status_code == 409

    unchanged = await client.get(f"/api/v1/bookings/{first_id}", headers=headers)
    assert unchanged.json()["start_time"] == slot_a.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.mark.asyncio
async def test_attendance_marking_and_duplicate_rejection(
    client, db_session, seeded_users, project_with_capacity, test_lead
):
    project, _ = project_with_capacity
    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    start_time = _slot_start_utc(target_date, time(10, 30))

    headers = await _login(client, ADMIN_EMAIL)
    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    booking_id = booked.json()["id"]

    # Attendance may only be recorded once the visit has started; simulate
    # the visit time passing by moving the booked visit into the past.
    now = datetime.now(timezone.utc)
    await db_session.execute(
        update(SiteVisit)
        .where(SiteVisit.id == uuid.UUID(booking_id))
        .values(start_time=now - timedelta(hours=2), end_time=now - timedelta(hours=1))
    )
    await db_session.commit()

    attendance = await client.post(
        f"/api/v1/bookings/{booking_id}/attendance", json={"status": "COMPLETED"}, headers=headers
    )
    assert attendance.status_code == 200
    assert attendance.json()["status"] == "COMPLETED"

    duplicate = await client.post(
        f"/api/v1/bookings/{booking_id}/attendance", json={"status": "NO_SHOW"}, headers=headers
    )
    assert duplicate.status_code == 409

    lead_result = await db_session.execute(
        select(Lead).where(Lead.id == test_lead.id).execution_options(populate_existing=True)
    )
    lead = lead_result.scalar_one()
    assert lead.lead_status == LeadStatus.VISIT_COMPLETED


@pytest.mark.asyncio
async def test_unauthorized_booking_access(client, db_session, seeded_users, project_with_capacity, test_lead):
    project, _ = project_with_capacity
    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    start_time = _slot_start_utc(target_date, time(11, 30))

    headers = await _login(client, ADMIN_EMAIL)
    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": str(test_lead.id), "project_id": str(project.id), "start_time": start_time.isoformat()},
        headers=headers,
    )
    booking_id = booked.json()["id"]

    no_auth = await client.get(f"/api/v1/bookings/{booking_id}")
    assert no_auth.status_code == 401

    # A buyer session for a *different* lead must not be able to view this booking.
    other_session = await client.post(
        "/api/v1/chat/sessions",
        json={"full_name": "BookingTest Other Buyer", "phone": _unique_phone(), "preferred_language": "EN", "consent_given": True},
    )
    assert other_session.status_code == 201
    cookie = other_session.cookies.get("estateflow_buyer_session")
    client.cookies.set("estateflow_buyer_session", cookie)

    forbidden = await client.get(f"/api/v1/bookings/{booking_id}")
    assert forbidden.status_code == 403
    client.cookies.clear()


@pytest.mark.asyncio
async def test_buyer_can_book_and_view_own_visit(client, db_session, project_with_capacity, seeded_users):
    project, _ = project_with_capacity
    target_date = _next_weekday(2)
    await _add_rule(db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday())
    start_time = _slot_start_utc(target_date, time(12, 30))

    session_resp = await client.post(
        "/api/v1/chat/sessions",
        json={"full_name": "BookingTest Buyer Self Booker", "phone": _unique_phone(), "preferred_language": "EN", "consent_given": True},
    )
    assert session_resp.status_code == 201
    lead_id = session_resp.json()["lead_id"]
    cookie = session_resp.cookies.get("estateflow_buyer_session")
    client.cookies.set("estateflow_buyer_session", cookie)

    booked = await client.post(
        "/api/v1/bookings",
        json={"lead_id": lead_id, "project_id": str(project.id), "start_time": start_time.isoformat()},
    )
    assert booked.status_code == 201

    booking_id = booked.json()["id"]
    detail = await client.get(f"/api/v1/bookings/{booking_id}")
    assert detail.status_code == 200
    client.cookies.clear()


@pytest.mark.asyncio
async def test_timezone_boundary_slot_generation(client, db_session, seeded_users, project_with_capacity):
    """
    A rule of 22:00-23:30 IST sits close to the UTC date boundary (IST is
    UTC+5:30), so the resulting slot's UTC date differs from its IST date --
    verifying slots are generated/returned correctly across that boundary.
    """
    project, _ = project_with_capacity
    target_date = _next_weekday(2)
    await _add_rule(
        db_session, executive_id=seeded_users["exec1"].id, day_of_week=target_date.weekday(), start="22:00", end="23:30"
    )

    headers = await _login(client, ADMIN_EMAIL)
    resp = await client.get(
        "/api/v1/availability", params={"project_id": str(project.id), "date": target_date.isoformat()}, headers=headers
    )
    assert resp.status_code == 200
    slots = resp.json()["slots"]
    assert len(slots) > 0
    for slot in slots:
        start_utc = datetime.fromisoformat(slot["start_time"].replace("Z", "+00:00"))
        start_ist = start_utc.astimezone(IST)
        assert start_ist.date() == target_date
        assert time(22, 0) <= start_ist.time() < time(23, 30)
