import asyncio
import re
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

from backend.main import app
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.models.availability_rule import AvailabilityRule
from backend.models.customer_account import CustomerAccount
from backend.models.customer_session import CustomerSession
from backend.models.customer_verification_token import CustomerVerificationToken
from backend.models.lead import Lead
from backend.models.project import Project, ProjectVisibility
from backend.models.project_visit_capacity import ProjectVisitCapacity
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.models.user import User, UserRole
from backend.models.visit_event import VisitEvent, VisitEventType
from backend.models.visit_reminder import VisitReminder
import backend.api.v1.endpoints.customer_auth as customer_auth_endpoints

IST = ZoneInfo("Asia/Kolkata")
PASSWORD = "SuperSecret123!"
TEST_EMAIL_DOMAIN = "test-customer-visits.estateflow.ai"
EXEC_EMAIL = "test-customer-visits-exec@estateflow.ai"
STAFF_EMAIL = "test-customer-visits-staff@estateflow.ai"


def unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@{TEST_EMAIL_DOMAIN}"


def _next_weekday(target_weekday: int):
    today = datetime.now(IST).date()
    days_ahead = (target_weekday - today.weekday()) % 7
    days_ahead = days_ahead if days_ahead > 0 else 7
    return today + timedelta(days=days_ahead)


def _slot_start_utc(target_date, local_time: time) -> datetime:
    return datetime.combine(target_date, local_time, tzinfo=IST).astimezone(timezone.utc)


class FakeEmailProvider:
    def __init__(self):
        self.sent = []

    async def send(self, *, to_email: str, subject: str, body: str) -> bool:
        self.sent.append({"to": to_email, "subject": subject, "body": body})
        return True

    def last_token(self) -> str:
        match = re.search(r"token=([A-Za-z0-9_-]+)", self.sent[-1]["body"])
        assert match, "no token found in simulated email body"
        return match.group(1)


@pytest.fixture
def fake_email(monkeypatch):
    provider = FakeEmailProvider()
    monkeypatch.setattr(customer_auth_endpoints, "get_email_provider", lambda: provider)
    return provider


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
async def seeded_exec(db_session):
    emails = [EXEC_EMAIL, STAFF_EMAIL]
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()

    executive = User(
        email=EXEC_EMAIL, full_name="Visit Exec", password_hash=hash_password(PASSWORD),
        role=UserRole.SALES_EXECUTIVE, is_active=True,
    )
    staff = User(
        email=STAFF_EMAIL, full_name="Visit Staff", password_hash=hash_password(PASSWORD),
        role=UserRole.ADMIN, is_active=True,
    )
    db_session.add_all([executive, staff])
    await db_session.commit()
    await db_session.refresh(executive)
    await db_session.refresh(staff)
    yield executive, staff

    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()


@pytest_asyncio.fixture
async def published_project(db_session, seeded_exec):
    executive, _ = seeded_exec
    project = Project(
        name=f"CustomerVisitTest Project {uuid.uuid4().hex[:8]}",
        description="Test",
        location="Test City",
        is_active=True,
        visibility_status=ProjectVisibility.PUBLISHED,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    capacity = ProjectVisitCapacity(project_id=project.id, capacity=1, visit_duration_minutes=30, buffer_minutes=0)
    db_session.add(capacity)

    target_date = _next_weekday(2)
    rule = AvailabilityRule(
        executive_id=executive.id,
        project_id=None,
        day_of_week=target_date.weekday(),
        start_time=time(9, 0),
        end_time=time(18, 0),
        is_active=True,
    )
    db_session.add(rule)
    await db_session.commit()

    yield project, capacity, target_date


@pytest_asyncio.fixture
async def draft_project(db_session):
    project = Project(
        name=f"CustomerVisitTest Draft {uuid.uuid4().hex[:8]}",
        is_active=True,
        visibility_status=ProjectVisibility.DRAFT,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    yield project


@pytest_asyncio.fixture(autouse=True)
async def cleanup(db_session):
    yield
    test_lead_ids_result = await db_session.execute(
        select(Lead.id).where(Lead.full_name.like("Chat Customer%") | Lead.full_name.like("CustomerVisitTest%"))
    )
    test_lead_ids = [row[0] for row in test_lead_ids_result.all()]

    await db_session.execute(delete(VisitEvent))
    await db_session.execute(delete(VisitReminder))
    await db_session.execute(delete(SiteVisit))
    await db_session.execute(delete(AvailabilityRule))
    await db_session.execute(delete(ProjectVisitCapacity))
    await db_session.execute(delete(Project).where(Project.name.like("CustomerVisitTest%")))

    customers_result = await db_session.execute(
        select(CustomerAccount.id).where(CustomerAccount.normalized_email.like(f"%@{TEST_EMAIL_DOMAIN}"))
    )
    customer_ids = [row[0] for row in customers_result.all()]
    if customer_ids:
        await db_session.execute(delete(CustomerSession).where(CustomerSession.customer_account_id.in_(customer_ids)))
        await db_session.execute(
            delete(CustomerVerificationToken).where(CustomerVerificationToken.customer_account_id.in_(customer_ids))
        )
        await db_session.execute(delete(CustomerAccount).where(CustomerAccount.id.in_(customer_ids)))

    if test_lead_ids:
        await db_session.execute(delete(Lead).where(Lead.id.in_(test_lead_ids)))
    await db_session.commit()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register_login_verify(client, fake_email, *, email=None):
    email = email or unique_email("visit")
    resp = await client.post(
        "/api/v1/customer-auth/register",
        json={
            "full_name": "Chat Customer",
            "email": email,
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
            "accepted_privacy_policy": True,
        },
    )
    assert resp.status_code == 201, resp.text
    token = fake_email.last_token()
    verify_resp = await client.post("/api/v1/customer-auth/verify-email", json={"token": token})
    assert verify_resp.status_code == 200, verify_resp.text

    login_resp = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD})
    assert login_resp.status_code == 200, login_resp.text
    access_token = login_resp.json()["access_token"]
    return email, access_token


async def _get_customer(db_session, email):
    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    return result.scalar_one()


async def _book_slot(client, token, project, target_date, local_time=time(10, 0), idempotency_key=None):
    start = _slot_start_utc(target_date, local_time)
    headers = auth_headers(token)
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    resp = await client.post(
        "/api/v1/customer/visits",
        json={"project_id": str(project.id), "scheduled_start": start.isoformat()},
        headers=headers,
    )
    return resp


# --- GET /customer/visits/availability ---


@pytest.mark.asyncio
async def test_customer_can_get_available_slots(client, fake_email, published_project):
    project, _, target_date = published_project
    _, token = await _register_login_verify(client, fake_email)

    resp = await client.get(
        "/api/v1/customer/visits/availability",
        params={"project_id": str(project.id), "date": target_date.isoformat()},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["slots"]) > 0
    assert body["display_timezone"] == "Asia/Kolkata"
    # Customer-safe slot shape only -- no internal capacity/executive data.
    assert set(body["slots"][0].keys()) == {"start_time", "end_time"}


@pytest.mark.asyncio
async def test_draft_project_availability_returns_404(client, fake_email, draft_project):
    _, token = await _register_login_verify(client, fake_email)
    resp = await client.get(
        "/api/v1/customer/visits/availability",
        params={"project_id": str(draft_project.id), "date": _next_weekday(2).isoformat()},
        headers=auth_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_past_date_returns_no_slots(client, fake_email, published_project):
    project, _, _ = published_project
    _, token = await _register_login_verify(client, fake_email)
    yesterday = (datetime.now(IST).date() - timedelta(days=1)).isoformat()

    resp = await client.get(
        "/api/v1/customer/visits/availability",
        params={"project_id": str(project.id), "date": yesterday},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["slots"] == []


# --- POST /customer/visits ---


@pytest.mark.asyncio
async def test_customer_can_book_available_slot(client, fake_email, db_session, published_project):
    project, _, target_date = published_project
    email, token = await _register_login_verify(client, fake_email)
    customer = await _get_customer(db_session, email)

    resp = await _book_slot(client, token, project, target_date)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "CONFIRMED"
    assert body["project_id"] == str(project.id)
    assert body["display_timezone"] == "Asia/Kolkata"
    assert "executive_id" not in body

    visit_result = await db_session.execute(select(SiteVisit).where(SiteVisit.id == uuid.UUID(body["id"])))
    visit = visit_result.scalar_one()
    assert visit.lead_id == customer.lead_id


@pytest.mark.asyncio
async def test_booking_ignores_caller_supplied_lead_and_executive_id(client, fake_email, db_session, published_project):
    project, _, target_date = published_project
    email, token = await _register_login_verify(client, fake_email)
    customer = await _get_customer(db_session, email)
    other_lead_id = str(uuid.uuid4())
    other_exec_id = str(uuid.uuid4())

    start = _slot_start_utc(target_date, time(10, 30))
    resp = await client.post(
        "/api/v1/customer/visits",
        json={
            "project_id": str(project.id),
            "scheduled_start": start.isoformat(),
            "lead_id": other_lead_id,
            "executive_id": other_exec_id,
            "attendance_status": "COMPLETED",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text

    visit_result = await db_session.execute(select(SiteVisit).where(SiteVisit.id == uuid.UUID(resp.json()["id"])))
    visit = visit_result.scalar_one()
    assert visit.lead_id == customer.lead_id
    assert str(visit.lead_id) != other_lead_id
    assert str(visit.executive_id) != other_exec_id
    assert visit.status == SiteVisitStatus.CONFIRMED


@pytest.mark.asyncio
async def test_unlinked_customer_cannot_book(client, fake_email, db_session, published_project):
    project, _, target_date = published_project
    email, token = await _register_login_verify(client, fake_email)
    customer = await _get_customer(db_session, email)
    customer.lead_id = None
    await db_session.commit()

    resp = await _book_slot(client, token, project, target_date)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_draft_project_cannot_be_booked(client, fake_email, draft_project):
    _, token = await _register_login_verify(client, fake_email)
    start = _slot_start_utc(_next_weekday(2), time(10, 0))
    resp = await client.post(
        "/api/v1/customer/visits",
        json={"project_id": str(draft_project.id), "scheduled_start": start.isoformat()},
        headers=auth_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_slot_with_no_availability_rejected(client, fake_email, db_session, seeded_exec):
    # Published project with capacity but no AvailabilityRule at all -- no
    # executive can ever be found for it.
    project = Project(
        name=f"CustomerVisitTest NoRule {uuid.uuid4().hex[:8]}", is_active=True,
        visibility_status=ProjectVisibility.PUBLISHED,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    db_session.add(ProjectVisitCapacity(project_id=project.id, capacity=1, visit_duration_minutes=30, buffer_minutes=0))
    await db_session.commit()

    _, token = await _register_login_verify(client, fake_email)
    start = _slot_start_utc(_next_weekday(2), time(10, 0))
    resp = await client.post(
        "/api/v1/customer/visits",
        json={"project_id": str(project.id), "scheduled_start": start.isoformat()},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_booking_idempotency_prevents_duplicate_visits(client, fake_email, published_project):
    project, _, target_date = published_project
    _, token = await _register_login_verify(client, fake_email)
    key = f"idem-{uuid.uuid4().hex}"

    first = await _book_slot(client, token, project, target_date, idempotency_key=key)
    second = await _book_slot(client, token, project, target_date, idempotency_key=key)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_concurrent_bookings_respect_capacity(client, fake_email, published_project):
    project, capacity, target_date = published_project
    assert capacity.capacity == 1
    start = _slot_start_utc(target_date, time(14, 0))

    tokens = []
    for _ in range(3):
        _, token = await _register_login_verify(client, fake_email)
        tokens.append(token)

    async def attempt(token):
        return await client.post(
            "/api/v1/customer/visits",
            json={"project_id": str(project.id), "scheduled_start": start.isoformat()},
            headers=auth_headers(token),
        )

    results = await asyncio.gather(*[attempt(t) for t in tokens])
    statuses = sorted(r.status_code for r in results)
    assert statuses.count(201) == 1
    assert statuses.count(409) == 2


@pytest.mark.asyncio
async def test_visit_event_and_reminders_created_on_booking(client, fake_email, db_session, published_project):
    project, _, target_date = published_project
    _, token = await _register_login_verify(client, fake_email)

    resp = await _book_slot(client, token, project, target_date, local_time=time(11, 0))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    visit_id = uuid.UUID(body["id"])

    event_result = await db_session.execute(select(VisitEvent).where(VisitEvent.site_visit_id == visit_id))
    events = event_result.scalars().all()
    assert any(e.event_type == VisitEventType.BOOKED for e in events)

    reminder_result = await db_session.execute(select(VisitReminder).where(VisitReminder.site_visit_id == visit_id))
    reminders = reminder_result.scalars().all()
    assert len(reminders) == 2
    assert body["reminder_24h"]["status"] == "PENDING"
    assert body["reminder_2h"]["status"] == "PENDING"


# --- Booking access ---


@pytest.mark.asyncio
async def test_customer_lists_only_own_visits(client, fake_email, published_project):
    project, _, target_date = published_project
    _, token_a = await _register_login_verify(client, fake_email)
    _, token_b = await _register_login_verify(client, fake_email)

    booked = await _book_slot(client, token_a, project, target_date, local_time=time(9, 30))
    assert booked.status_code == 201

    resp_a = await client.get("/api/v1/customer/visits", headers=auth_headers(token_a))
    assert resp_a.status_code == 200
    assert resp_a.json()["total"] == 1

    resp_b = await client.get("/api/v1/customer/visits", headers=auth_headers(token_b))
    assert resp_b.status_code == 200
    assert resp_b.json()["total"] == 0


@pytest.mark.asyncio
async def test_customer_can_retrieve_own_booking(client, fake_email, published_project):
    project, _, target_date = published_project
    _, token = await _register_login_verify(client, fake_email)
    booked = await _book_slot(client, token, project, target_date, local_time=time(9, 30))
    visit_id = booked.json()["id"]

    resp = await client.get(f"/api/v1/customer/visits/{visit_id}", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["id"] == visit_id


@pytest.mark.asyncio
async def test_customer_cannot_retrieve_another_customers_booking(client, fake_email, published_project):
    project, _, target_date = published_project
    _, token_a = await _register_login_verify(client, fake_email)
    _, token_b = await _register_login_verify(client, fake_email)

    booked = await _book_slot(client, token_a, project, target_date, local_time=time(9, 30))
    visit_id = booked.json()["id"]

    resp = await client.get(f"/api/v1/customer/visits/{visit_id}", headers=auth_headers(token_b))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_customer_cannot_cancel_another_customers_booking(client, fake_email, published_project):
    project, _, target_date = published_project
    _, token_a = await _register_login_verify(client, fake_email)
    _, token_b = await _register_login_verify(client, fake_email)

    booked = await _book_slot(client, token_a, project, target_date, local_time=time(9, 30))
    visit_id = booked.json()["id"]

    resp = await client.post(f"/api/v1/customer/visits/{visit_id}/cancel", headers=auth_headers(token_b))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_customer_visit_endpoints_reject_staff_token(client, seeded_exec):
    _, staff = seeded_exec
    login_resp = await client.post("/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": PASSWORD})
    staff_token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/customer/visits", headers=auth_headers(staff_token))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_customer_visit_endpoints_reject_anonymous_buyer_session_cookie(client):
    client.cookies.set("estateflow_buyer_session", "some-opaque-buyer-session-token")
    resp = await client.get("/api/v1/customer/visits")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_customer_visit_endpoints_reject_missing_authentication(client):
    resp = await client.get("/api/v1/customer/visits")
    assert resp.status_code == 401


# --- Reschedule ---


@pytest.mark.asyncio
async def test_customer_can_reschedule_eligible_booking(client, fake_email, db_session, published_project):
    project, _, target_date = published_project
    _, token = await _register_login_verify(client, fake_email)
    booked = await _book_slot(client, token, project, target_date, local_time=time(9, 30))
    visit_id = booked.json()["id"]

    new_start = _slot_start_utc(target_date, time(15, 0))
    resp = await client.patch(
        f"/api/v1/customer/visits/{visit_id}/reschedule",
        json={"scheduled_start": new_start.isoformat()},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert datetime.fromisoformat(body["scheduled_start"].replace("Z", "+00:00")) == new_start

    visit_result = await db_session.execute(select(SiteVisit).where(SiteVisit.id == uuid.UUID(visit_id)))
    visit = visit_result.scalar_one()
    assert visit.booking_version == 2


@pytest.mark.asyncio
async def test_cancelled_visit_cannot_be_rescheduled(client, fake_email, published_project):
    project, _, target_date = published_project
    _, token = await _register_login_verify(client, fake_email)
    booked = await _book_slot(client, token, project, target_date, local_time=time(9, 30))
    visit_id = booked.json()["id"]

    cancel_resp = await client.post(f"/api/v1/customer/visits/{visit_id}/cancel", headers=auth_headers(token))
    assert cancel_resp.status_code == 200

    new_start = _slot_start_utc(target_date, time(15, 0))
    resp = await client.patch(
        f"/api/v1/customer/visits/{visit_id}/reschedule",
        json={"scheduled_start": new_start.isoformat()},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


# --- Cancellation ---


@pytest.mark.asyncio
async def test_customer_can_cancel_eligible_booking(client, fake_email, published_project):
    project, _, target_date = published_project
    _, token = await _register_login_verify(client, fake_email)
    booked = await _book_slot(client, token, project, target_date, local_time=time(9, 30))
    visit_id = booked.json()["id"]

    resp = await client.post(f"/api/v1/customer/visits/{visit_id}/cancel", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancelling_already_cancelled_visit_conflicts(client, fake_email, published_project):
    project, _, target_date = published_project
    _, token = await _register_login_verify(client, fake_email)
    booked = await _book_slot(client, token, project, target_date, local_time=time(9, 30))
    visit_id = booked.json()["id"]

    first = await client.post(f"/api/v1/customer/visits/{visit_id}/cancel", headers=auth_headers(token))
    assert first.status_code == 200
    second = await client.post(f"/api/v1/customer/visits/{visit_id}/cancel", headers=auth_headers(token))
    assert second.status_code == 409
