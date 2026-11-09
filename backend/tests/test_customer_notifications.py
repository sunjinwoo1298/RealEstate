import asyncio
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

import backend.services.customer_email_provider as email_provider_module
from backend.core.config import settings
from backend.core.database import get_session_factory
from backend.core.security import create_access_token, create_customer_access_token, hash_password
from backend.main import app
from backend.models.availability_rule import AvailabilityRule
from backend.models.customer_account import CustomerAccount, CustomerAccountStatus
from backend.models.customer_notification_delivery import (
    CustomerDeliveryStatus as DS,
    CustomerNotificationDelivery,
    CustomerNotificationEvent as EV,
)
from backend.models.lead import Lead, LeadStatus
from backend.models.project import Project, ProjectVisibility
from backend.models.project_visit_capacity import ProjectVisitCapacity
from backend.models.site_visit import SiteVisit
from backend.models.user import User, UserRole
from backend.models.visit_event import VisitEvent
from backend.models.visit_reminder import ReminderStatus, VisitReminder
from backend.services.booking_service import BookingService
from backend.services.customer_email_provider import (
    EmailConfigurationError,
    EmailPermanentError,
    EmailSendResult,
    EmailTransientError,
    LoggingCustomerEmailProvider,
    OutgoingEmail,
    ResendEmailProvider,
    validate_email_configuration,
)
from backend.services.customer_email_templates import render_email
from backend.services.customer_notification_service import (
    CustomerNotificationService,
    compute_backoff_seconds,
    ineligibility_reason,
    sanitize_error,
)
from backend.services.reminder_delivery import ReminderDeliveryResult
from backend.services.reminder_worker_service import ReminderWorkerService

IST = ZoneInfo("Asia/Kolkata")
DOMAIN = "test-cust-notif.estateflow.ai"
ADMIN_EMAIL = "test-cust-notif-admin@estateflow.ai"
MANAGER_EMAIL = "test-cust-notif-mgr@estateflow.ai"
EXEC_EMAIL = "test-cust-notif-exec@estateflow.ai"
PASSWORD = "SuperSecret123!"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeEmailProvider:
    """Behaves like a real provider (simulated=False) unless told to fail."""

    def __init__(self, *, error=None):
        self.error = error
        self.sent = []

    async def send(self, message: OutgoingEmail) -> EmailSendResult:
        if self.error is not None:
            raise self.error
        self.sent.append(message)
        return EmailSendResult(simulated=False, provider_message_id="msg-1")


class NoopReminderProvider:
    async def send(self, *, reminder, visit, lead, project):
        return ReminderDeliveryResult(simulated=True, rendered_message="legacy")


# ---------------------------------------------------------------------------
# Pure unit tests (no database)
# ---------------------------------------------------------------------------


def test_template_escapes_html_and_has_text_alternative():
    payload = {
        "first_name": "<script>alert(1)</script>",
        "project_name": 'Tower "A" & <b>B</b>',
        "project_location": "Ahmedabad <i>West</i>",
        "start_time": "2026-12-01T04:30:00+00:00",
        "visit_id": "11111111-1111-1111-1111-111111111111",
        "executive_name": "Exec <x>",
    }
    for key in (
        "site_visit_booked",
        "site_visit_rescheduled",
        "site_visit_cancelled",
        "site_visit_reminder_24h",
        "site_visit_reminder_2h",
    ):
        mail = render_email(key, {**payload, "previous_start_time": "2026-11-30T04:30:00+00:00"})
        assert "<script>" not in mail.html_body
        assert "<b>B</b>" not in mail.html_body and "&lt;b&gt;B&lt;/b&gt;" in mail.html_body
        assert mail.text_body
        assert "01 Dec 2026, 10:00 AM IST" in mail.text_body  # Asia/Kolkata display
        assert "/customer/visits/11111111-1111-1111-1111-111111111111" in mail.html_body


def test_template_never_leaks_internal_data_or_invents_contact():
    mail = render_email(
        "site_visit_booked",
        {"project_name": "P", "start_time": "2026-12-01T04:30:00+00:00", "visit_id": str(uuid.uuid4())},
    )
    assert "Need help" not in mail.text_body  # no support contact configured
    assert "Location" not in mail.text_body  # no invented address
    assert "price" not in mail.text_body.lower()


def test_backoff_is_bounded_exponential_with_jitter_and_retry_after():
    low = compute_backoff_seconds(3, base=10, max_seconds=1000, rand=lambda: 0.0)
    high = compute_backoff_seconds(3, base=10, max_seconds=1000, rand=lambda: 1.0)
    assert (low, high) == (20.0, 40.0)  # exp = 40 -> [20, 40]
    assert compute_backoff_seconds(20, base=10, max_seconds=100, rand=lambda: 1.0) == 100.0  # capped
    assert compute_backoff_seconds(1, base=10, max_seconds=1000, rand=lambda: 0.0, retry_after=300) == 300.0


def test_sanitize_error_strips_secrets_and_addresses(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_API_KEY", "re_supersecret123")
    cleaned = sanitize_error("auth failed re_supersecret123 for jane@example.com Bearer abc.def")
    assert "re_supersecret123" not in cleaned and "jane@example.com" not in cleaned and "abc.def" not in cleaned


def test_ineligibility_rules():
    now = datetime.now(timezone.utc)

    class A:
        status = CustomerAccountStatus.ACTIVE
        email_verified_at = now
        transactional_email_enabled = True

    assert ineligibility_reason(None) == "NO_CUSTOMER_ACCOUNT"
    assert ineligibility_reason(A()) is None
    a = A()
    a.email_verified_at = None
    assert ineligibility_reason(a) == "EMAIL_NOT_VERIFIED"
    a = A()
    a.transactional_email_enabled = False
    assert ineligibility_reason(a) == "TRANSACTIONAL_EMAIL_DISABLED_BY_CUSTOMER"
    a = A()
    a.status = CustomerAccountStatus.SUSPENDED
    assert ineligibility_reason(a) == "ACCOUNT_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_logging_provider_is_simulated_and_never_logs_body_or_address(caplog):
    caplog.set_level("INFO")
    result = await LoggingCustomerEmailProvider().send(
        OutgoingEmail("secret.person@example.com", "Subject", "BODYTEXT", "<p>BODYHTML</p>", "d1")
    )
    assert result.simulated is True
    assert "secret.person@example.com" not in caplog.text and "BODYTEXT" not in caplog.text


def _resend_with(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        email_provider_module.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    return ResendEmailProvider(api_key="k", from_address="a@b.co", from_name="E", reply_to="", timeout=1)


_MSG = OutgoingEmail("to@example.com", "S", "T", "<p>T</p>", "delivery-1")


@pytest.mark.asyncio
async def test_resend_success_sends_idempotency_key_and_returns_message_id(monkeypatch):
    seen = {}

    def handler(request):
        seen["idem"] = request.headers["Idempotency-Key"]
        return httpx.Response(200, json={"id": "abc123"})

    result = await _resend_with(monkeypatch, handler).send(_MSG)
    assert (result.simulated, result.provider_message_id, seen["idem"]) == (False, "abc123", "delivery-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,expected",
    [
        (httpx.Response(429, headers={"retry-after": "42"}), EmailTransientError),
        (httpx.Response(503), EmailTransientError),
        (httpx.Response(422, json={"message": "invalid to"}), EmailPermanentError),
        (httpx.Response(401), EmailPermanentError),
    ],
)
async def test_resend_error_classification(monkeypatch, response, expected):
    with pytest.raises(expected) as info:
        await _resend_with(monkeypatch, lambda request: response).send(_MSG)
    if response.status_code == 429:
        assert info.value.retry_after_seconds == 42.0


@pytest.mark.asyncio
async def test_resend_timeout_is_transient(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(EmailTransientError):
        await _resend_with(monkeypatch, handler).send(_MSG)


def test_email_configuration_validation(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "log")
    validate_email_configuration()
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "EMAIL_API_KEY", "")
    with pytest.raises(EmailConfigurationError):
        validate_email_configuration()
    monkeypatch.setattr(settings, "EMAIL_API_KEY", "k")
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "not-an-email")
    with pytest.raises(EmailConfigurationError):
        validate_email_configuration()
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "no-reply@estateflow.ai")
    monkeypatch.setattr(settings, "CUSTOMER_PORTAL_BASE_URL", "https://portal.estateflow.ai")
    validate_email_configuration()
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "mailgun")
    with pytest.raises(EmailConfigurationError):
        validate_email_configuration()


# ---------------------------------------------------------------------------
# Integration fixtures (hosted PostgreSQL)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def world(db_session):
    """One executive (full-day rule), one project, staff users."""
    emails = [ADMIN_EMAIL, MANAGER_EMAIL, EXEC_EMAIL]
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    users = {
        "admin": User(email=ADMIN_EMAIL, full_name="Notif Admin", password_hash=hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True),
        "manager": User(email=MANAGER_EMAIL, full_name="Notif Manager", password_hash=hash_password(PASSWORD), role=UserRole.MANAGER, is_active=True),
        "exec": User(email=EXEC_EMAIL, full_name="Notif Exec", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True),
    }
    db_session.add_all(users.values())
    project = Project(
        name=f"CustNotifTest Project {uuid.uuid4().hex[:6]}", location="Test City", is_active=True,
        visibility_status=ProjectVisibility.PUBLISHED,
    )
    db_session.add(project)
    await db_session.commit()
    db_session.add(ProjectVisitCapacity(project_id=project.id, capacity=10, visit_duration_minutes=30, buffer_minutes=0))
    for weekday in range(7):
        db_session.add(
            AvailabilityRule(
                executive_id=users["exec"].id, project_id=None, day_of_week=weekday,
                start_time=time(0, 0), end_time=time(23, 55), is_active=True,
            )
        )
    await db_session.commit()
    project_id, exec_id = project.id, users["exec"].id  # plain ids survive a test-side rollback()
    yield users, project

    # Cleanup is scoped to rows created by this module (its project, test
    # customer domain and test staff) -- never whole tables.
    visit_ids = select(SiteVisit.id).where(SiteVisit.project_id == project_id)
    account_ids = select(CustomerAccount.id).where(CustomerAccount.normalized_email.like(f"%@{DOMAIN}"))
    await db_session.execute(
        delete(CustomerNotificationDelivery).where(CustomerNotificationDelivery.customer_account_id.in_(account_ids))
    )
    await db_session.execute(delete(VisitReminder).where(VisitReminder.site_visit_id.in_(visit_ids)))
    await db_session.execute(delete(VisitEvent).where(VisitEvent.site_visit_id.in_(visit_ids)))
    await db_session.execute(delete(SiteVisit).where(SiteVisit.project_id == project_id))
    await db_session.execute(
        delete(AvailabilityRule).where(AvailabilityRule.executive_id == exec_id)
    )
    await db_session.execute(delete(ProjectVisitCapacity).where(ProjectVisitCapacity.project_id == project_id))
    await db_session.execute(delete(CustomerAccount).where(CustomerAccount.normalized_email.like(f"%@{DOMAIN}")))
    await db_session.execute(delete(Lead).where(Lead.full_name.like("CustNotifTest%")))
    await db_session.execute(delete(Project).where(Project.id == project_id))
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()


async def _make_customer(db, *, verified=True, transactional=True, with_lead=True, label="c"):
    lead = None
    if with_lead:
        lead = Lead(
            full_name=f"CustNotifTest {label}",
            normalized_phone="9" + str(uuid.uuid4().int)[:9],
            lead_status=LeadStatus.QUALIFIED,
        )
        db.add(lead)
        await db.commit()
    email = f"{label}-{uuid.uuid4().hex[:6]}@{DOMAIN}"
    account = CustomerAccount(
        email=email, normalized_email=email, password_hash="x", full_name="Asha Patel",
        email_verified_at=datetime.now(timezone.utc) if verified else None,
        status=CustomerAccountStatus.ACTIVE,
        lead_id=lead.id if lead else None,
        privacy_policy_accepted_at=datetime.now(timezone.utc),
        marketing_consent=False,
        transactional_email_enabled=transactional,
    )
    db.add(account)
    await db.commit()
    return account, lead


def _start(days=4, hour=10):
    day = datetime.now(IST).date() + timedelta(days=days)
    return datetime.combine(day, time(hour, 0), tzinfo=IST).astimezone(timezone.utc)


async def _book(db, lead, project, *, days=4, hour=10):
    return await BookingService.book_site_visit(db, lead_id=lead.id, project_id=project.id, start_time=_start(days, hour))


async def _deliveries(db, visit_id=None, account_id=None):
    query = select(CustomerNotificationDelivery).order_by(CustomerNotificationDelivery.created_at)
    if visit_id:
        query = query.where(CustomerNotificationDelivery.site_visit_id == visit_id)
    if account_id:
        query = query.where(CustomerNotificationDelivery.customer_account_id == account_id)
    return list((await db.execute(query)).scalars().all())


async def _drain(db, provider, visit_id):
    """Runs one worker pass over due deliveries."""
    ids = await CustomerNotificationService.claim_due(db, limit=50, site_visit_ids=[visit_id])
    for delivery_id in ids:
        await CustomerNotificationService.process_delivery(db, delivery_id, provider)
    return ids


def _auth(account):
    return {"Authorization": f"Bearer {create_customer_access_token(str(account.id))}"}


# ---------------------------------------------------------------------------
# Booking lifecycle -> outbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_booking_creates_exactly_one_idempotent_delivery(db_session, world):
    _, project = world
    account, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)

    rows = await _deliveries(db_session, visit.id)
    assert [r.event_type for r in rows] == [EV.SITE_VISIT_BOOKED]
    row = rows[0]
    assert row.idempotency_key == f"visit:{visit.id}:booked:v1"
    assert row.status == DS.PENDING and row.recipient == account.email
    assert "lead_id" not in row.payload and "customer_account_id" not in row.payload

    # Duplicate event -> no second row, and no error inside the transaction.
    assert await CustomerNotificationService.enqueue_visit_event(db_session, visit, EV.SITE_VISIT_BOOKED)
    await db_session.commit()
    assert len(await _deliveries(db_session, visit.id)) == 1


@pytest.mark.asyncio
async def test_lead_without_customer_account_creates_no_delivery(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session, with_lead=True, label="x")
    await db_session.execute(delete(CustomerAccount).where(CustomerAccount.lead_id == lead.id))
    await db_session.commit()
    visit = await _book(db_session, lead, project)
    assert await _deliveries(db_session, visit.id) == []


@pytest.mark.asyncio
async def test_rolled_back_transaction_leaves_no_deliverable_row(db_session, world):
    _, project = world
    account, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)
    # rollback() expires ORM objects, so capture plain ids first.
    visit_id, account_id, lead_id, project_id = visit.id, account.id, lead.id, project.id
    # Enqueue a reschedule event, then roll the transaction back.
    visit.booking_version = 2
    await CustomerNotificationService.enqueue_visit_event(db_session, visit, EV.SITE_VISIT_RESCHEDULED)
    await db_session.rollback()
    assert [r.event_type for r in await _deliveries(db_session, visit_id)] == [EV.SITE_VISIT_BOOKED]

    # A booking rejected by validation also leaves nothing new.
    before = len(await _deliveries(db_session, account_id=account_id))
    with pytest.raises(Exception):
        await BookingService.book_site_visit(
            db_session, lead_id=lead_id, project_id=project_id, start_time=datetime.now(timezone.utc) - timedelta(days=1)
        )
    await db_session.rollback()
    assert len(await _deliveries(db_session, account_id=account_id)) == before


@pytest.mark.asyncio
async def test_worker_marks_real_provider_sent_and_logging_provider_simulated(db_session, world):
    _, project = world
    account, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)

    fake = FakeEmailProvider()
    await _drain(db_session, fake, visit.id)
    row = (await _deliveries(db_session, visit.id))[0]
    assert row.status == DS.SENT and row.provider_message_id == "msg-1" and row.sent_at is not None
    assert len(fake.sent) == 1 and fake.sent[0].to_email == account.email
    assert "10:00 AM IST" in fake.sent[0].text_body

    # SENT is never re-sent.
    await _drain(db_session, fake, visit.id)
    assert len(fake.sent) == 1

    visit2 = await _book(db_session, lead, project, days=5)
    await _drain(db_session, LoggingCustomerEmailProvider(), visit2.id)
    row2 = (await _deliveries(db_session, visit2.id))[0]
    assert row2.status == DS.SIMULATED  # never SENT in development


@pytest.mark.asyncio
async def test_reschedule_supersedes_old_unsent_email_and_reminders(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)
    await BookingService.reschedule_site_visit(db_session, visit.id, new_start_time=_start(5, 11))

    rows = {r.event_type: r for r in await _deliveries(db_session, visit.id)}
    assert rows[EV.SITE_VISIT_BOOKED].status == DS.CANCELLED  # unsent, superseded
    resched = rows[EV.SITE_VISIT_RESCHEDULED]
    assert resched.idempotency_key == f"visit:{visit.id}:rescheduled:v2" and resched.status == DS.PENDING
    assert "previous_start_time" in resched.payload

    fake = FakeEmailProvider()
    await _drain(db_session, fake, visit.id)
    assert [m.subject for m in fake.sent] == [f"Your site visit to {project.name} has been rescheduled"]


@pytest.mark.asyncio
async def test_sent_booking_email_then_cancel_creates_one_cancellation(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)
    fake = FakeEmailProvider()
    await _drain(db_session, fake, visit.id)

    # Make a reminder delivery in flight to prove cancellation supersedes it.
    reminders = (await db_session.execute(select(VisitReminder).where(VisitReminder.site_visit_id == visit.id))).scalars().all()
    assert len(reminders) == 2
    await BookingService.cancel_site_visit(db_session, visit.id)

    rows = await _deliveries(db_session, visit.id)
    cancelled = [r for r in rows if r.event_type == EV.SITE_VISIT_CANCELLED]
    assert len(cancelled) == 1 and cancelled[0].idempotency_key == f"visit:{visit.id}:cancelled:v1"
    assert all(
        r.status == ReminderStatus.CANCELLED
        for r in (await db_session.execute(select(VisitReminder).where(VisitReminder.site_visit_id == visit.id))).scalars()
    )
    await _drain(db_session, fake, visit.id)
    assert fake.sent[-1].subject == f"Your site visit to {project.name} has been cancelled"
    assert "Your contact at the site" not in fake.sent[-1].text_body


# ---------------------------------------------------------------------------
# Recipient eligibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unverified_email_is_skipped_without_breaking_booking(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session, verified=False)
    visit = await _book(db_session, lead, project)  # booking still succeeds
    assert visit.status.value == "CONFIRMED"
    fake = FakeEmailProvider()
    await _drain(db_session, fake, visit.id)
    row = (await _deliveries(db_session, visit.id))[0]
    assert row.status == DS.SKIPPED and row.last_error == "EMAIL_NOT_VERIFIED" and fake.sent == []


@pytest.mark.asyncio
async def test_customer_opt_out_of_transactional_email_is_honoured(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session, transactional=False)
    visit = await _book(db_session, lead, project)
    fake = FakeEmailProvider()
    await _drain(db_session, fake, visit.id)
    row = (await _deliveries(db_session, visit.id))[0]
    assert row.status == DS.SKIPPED and row.last_error == "TRANSACTIONAL_EMAIL_DISABLED_BY_CUSTOMER"
    assert fake.sent == []


# ---------------------------------------------------------------------------
# Retry policy, crash recovery, concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transient_failures_retry_then_fail_at_max_attempts(db_session, world, monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_EMAIL_MAX_ATTEMPTS", 2)
    _, project = world
    _, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)

    failing = FakeEmailProvider(error=EmailTransientError("Provider error 503", retry_after_seconds=120))
    await _drain(db_session, failing, visit.id)
    row = (await _deliveries(db_session, visit.id))[0]
    await db_session.refresh(row)
    assert row.status == DS.PENDING and row.attempt_count == 1
    assert row.next_attempt_at >= datetime.now(timezone.utc) + timedelta(seconds=100)  # Retry-After honoured
    assert row.last_error.startswith("EmailTransientError")

    await db_session.execute(
        update(CustomerNotificationDelivery).where(CustomerNotificationDelivery.id == row.id)
        .values(next_attempt_at=datetime.now(timezone.utc))
    )
    await db_session.commit()
    await _drain(db_session, failing, visit.id)
    await db_session.refresh(row)
    assert row.status == DS.FAILED and row.attempt_count == 2

    # A FAILED delivery is never retried automatically.
    assert await _drain(db_session, FakeEmailProvider(), visit.id) == []


@pytest.mark.asyncio
async def test_permanent_error_fails_immediately_and_unexpected_error_is_sanitized(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)
    await _drain(db_session, FakeEmailProvider(error=EmailPermanentError("Provider rejected the message (422)")), visit.id)
    row = (await _deliveries(db_session, visit.id))[0]
    assert row.status == DS.FAILED and row.attempt_count == 1

    visit2 = await _book(db_session, lead, project, days=5)
    await _drain(db_session, FakeEmailProvider(error=RuntimeError("secret asha@example.com token=xyz")), visit2.id)
    row2 = (await _deliveries(db_session, visit2.id))[0]
    assert "asha@example.com" not in row2.last_error and "xyz" not in row2.last_error


@pytest.mark.asyncio
async def test_orphaned_processing_row_is_reclaimed_after_lease(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)
    row = (await _deliveries(db_session, visit.id))[0]

    # Simulate a worker that claimed the row and crashed mid-send.
    stale = datetime.now(timezone.utc) - timedelta(seconds=settings.CUSTOMER_EMAIL_PROCESSING_LEASE_SECONDS + 60)
    await db_session.execute(
        update(CustomerNotificationDelivery).where(CustomerNotificationDelivery.id == row.id)
        .values(status=DS.PROCESSING, attempt_count=1, last_attempt_at=stale)
    )
    await db_session.commit()

    fake = FakeEmailProvider()
    await _drain(db_session, fake, visit.id)
    await db_session.refresh(row)
    assert row.status == DS.SENT and len(fake.sent) == 1


@pytest.mark.asyncio
async def test_concurrent_workers_never_claim_the_same_row(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session)
    visit_ids = [(await _book(db_session, lead, project, days=day)).id for day in (4, 5, 6, 7)]

    factory = get_session_factory()

    async def claim():
        async with factory() as session:
            return await CustomerNotificationService.claim_due(session, limit=2, site_visit_ids=visit_ids)

    first, second = await asyncio.gather(claim(), claim())
    assert not set(first) & set(second)
    assert len(first) + len(second) == 4


# ---------------------------------------------------------------------------
# Reminder integration (Feature 07 worker is the single owner)
# ---------------------------------------------------------------------------


async def _make_reminders_due(db, visit_id):
    await db.execute(
        update(VisitReminder).where(VisitReminder.site_visit_id == visit_id)
        .values(scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db.commit()


async def _reminder_rows(db, visit_id):
    result = await db.execute(select(VisitReminder).where(VisitReminder.site_visit_id == visit_id).order_by(VisitReminder.scheduled_at))
    rows = list(result.scalars().all())
    for r in rows:
        await db.refresh(r)
    return rows


@pytest.mark.asyncio
async def test_due_reminders_send_one_email_each_and_do_not_duplicate(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)
    await _drain(db_session, FakeEmailProvider(), visit.id)  # clear the booking email
    await _make_reminders_due(db_session, visit.id)

    fake = FakeEmailProvider()
    await ReminderWorkerService.run_due_reminders(db_session, delivery_provider=NoopReminderProvider(), email_provider=fake, site_visit_ids=[visit.id])
    reminders = await _reminder_rows(db_session, visit.id)
    assert [r.status for r in reminders] == [ReminderStatus.SENT, ReminderStatus.SENT]
    assert len(fake.sent) == 2
    assert {m.subject.split(":")[0] for m in fake.sent} == {"Reminder"}

    reminder_rows = [d for d in await _deliveries(db_session, visit.id) if d.visit_reminder_id]
    assert len(reminder_rows) == 2 and all(d.status == DS.SENT for d in reminder_rows)
    assert {d.idempotency_key for d in reminder_rows} == {f"visit-reminder:{r.id}" for r in reminders}

    await ReminderWorkerService.run_due_reminders(db_session, delivery_provider=NoopReminderProvider(), email_provider=fake, site_visit_ids=[visit.id])
    assert len(fake.sent) == 2  # no duplicate

    # The customer email worker never touches reminder-linked rows.
    assert await CustomerNotificationService.claim_due(db_session, limit=50, site_visit_ids=[visit.id]) == []


@pytest.mark.asyncio
async def test_reminder_with_logging_email_provider_is_simulated_not_sent(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)
    await _make_reminders_due(db_session, visit.id)
    await ReminderWorkerService.run_due_reminders(
        db_session, delivery_provider=NoopReminderProvider(), email_provider=LoggingCustomerEmailProvider(),
        site_visit_ids=[visit.id],
    )
    assert {r.status for r in await _reminder_rows(db_session, visit.id)} == {ReminderStatus.SIMULATED}
    assert {d.status for d in await _deliveries(db_session, visit.id) if d.visit_reminder_id} == {DS.SIMULATED}


@pytest.mark.asyncio
async def test_reminder_transient_failure_retries_then_permanent_and_admin_retry(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)
    await _make_reminders_due(db_session, visit.id)

    await ReminderWorkerService.run_due_reminders(
        db_session, delivery_provider=NoopReminderProvider(), email_provider=FakeEmailProvider(error=EmailTransientError("503")),
        site_visit_ids=[visit.id],
    )
    reminders = await _reminder_rows(db_session, visit.id)
    assert {r.status for r in reminders} == {ReminderStatus.SCHEDULED}  # existing Feature 07 backoff
    assert not any(r.status == ReminderStatus.SENT for r in reminders)  # never SENT on failure
    rem_deliveries = [d for d in await _deliveries(db_session, visit.id) if d.visit_reminder_id]
    assert {d.status for d in rem_deliveries} == {DS.PENDING}

    await _make_reminders_due(db_session, visit.id)
    await ReminderWorkerService.run_due_reminders(
        db_session, delivery_provider=NoopReminderProvider(), email_provider=FakeEmailProvider(error=EmailPermanentError("bad")),
        site_visit_ids=[visit.id],
    )
    assert {r.status for r in await _reminder_rows(db_session, visit.id)} == {ReminderStatus.FAILED}
    for d in [d for d in await _deliveries(db_session, visit.id) if d.visit_reminder_id]:
        await db_session.refresh(d)
        assert d.status == DS.FAILED  # visible as a failed delivery

    # Admin retry re-drives the *existing* reminder rows -- no new schedule.
    failed = [d for d in await _deliveries(db_session, visit.id) if d.visit_reminder_id]
    admin_id = uuid.uuid4()
    for d in failed:
        await CustomerNotificationService.retry_failed(db_session, d.id, actor_id=admin_id)
    assert len(await _reminder_rows(db_session, visit.id)) == 2
    fake = FakeEmailProvider()
    await ReminderWorkerService.run_due_reminders(db_session, delivery_provider=NoopReminderProvider(), email_provider=fake, site_visit_ids=[visit.id])
    assert len(fake.sent) == 2
    assert {r.status for r in await _reminder_rows(db_session, visit.id)} == {ReminderStatus.SENT}


@pytest.mark.asyncio
async def test_stale_reminder_after_reschedule_is_never_emailed(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)
    old = await _reminder_rows(db_session, visit.id)
    await BookingService.reschedule_site_visit(db_session, visit.id, new_start_time=_start(6, 12))
    # Force the superseded (CANCELLED) old reminders back to due to prove the
    # version/status guard, not just the cancel, protects the customer.
    await db_session.execute(
        update(VisitReminder).where(VisitReminder.id.in_([r.id for r in old]))
        .values(status=ReminderStatus.SCHEDULED, scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_session.commit()
    fake = FakeEmailProvider()
    await ReminderWorkerService.run_due_reminders(db_session, delivery_provider=NoopReminderProvider(), email_provider=fake, site_visit_ids=[visit.id])
    assert fake.sent == []
    assert {r.status for r in await _reminder_rows(db_session, visit.id) if r.id in {o.id for o in old}} == {ReminderStatus.SKIPPED}


@pytest.mark.asyncio
async def test_reminder_for_unverified_customer_is_skipped_with_reason(db_session, world):
    _, project = world
    _, lead = await _make_customer(db_session, verified=False)
    visit = await _book(db_session, lead, project)
    await _make_reminders_due(db_session, visit.id)
    fake = FakeEmailProvider()
    await ReminderWorkerService.run_due_reminders(db_session, delivery_provider=NoopReminderProvider(), email_provider=fake, site_visit_ids=[visit.id])
    reminders = await _reminder_rows(db_session, visit.id)
    assert {r.status for r in reminders} == {ReminderStatus.SKIPPED}
    assert {r.failure_reason for r in reminders} == {"EMAIL_NOT_VERIFIED"} and fake.sent == []


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_is_paginated_newest_first_and_safe(client, db_session, world):
    _, project = world
    account, lead = await _make_customer(db_session)
    for day in (4, 5, 6):
        await _book(db_session, lead, project, days=day)

    resp = await client.get("/api/v1/customer/notifications", params={"limit": 2}, headers=_auth(account))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3 and len(body["items"]) == 2 and body["limit"] == 2 and body["offset"] == 0
    created = [i["created_at"] for i in body["items"]]
    assert created == sorted(created, reverse=True)
    item = body["items"][0]
    assert set(item) == {
        "id", "event_type", "channel", "status", "project_name", "visit_id", "visit_start_time", "created_at", "sent_at",
    }
    assert item["status"] == "PENDING" and item["project_name"] == project.name
    assert account.email not in resp.text

    page2 = await client.get("/api/v1/customer/notifications", params={"limit": 2, "offset": 2}, headers=_auth(account))
    assert len(page2.json()["items"]) == 1


@pytest.mark.asyncio
async def test_history_and_detail_are_ownership_protected(client, db_session, world):
    _, project = world
    owner, lead = await _make_customer(db_session, label="owner")
    other, _ = await _make_customer(db_session, label="other")
    await _book(db_session, lead, project)

    mine = (await client.get("/api/v1/customer/notifications", headers=_auth(owner))).json()
    theirs = (await client.get("/api/v1/customer/notifications", headers=_auth(other))).json()
    assert mine["total"] == 1 and theirs["total"] == 0 and theirs["items"] == []

    notification_id = mine["items"][0]["id"]
    assert (await client.get(f"/api/v1/customer/notifications/{notification_id}", headers=_auth(owner))).status_code == 200
    assert (await client.get(f"/api/v1/customer/notifications/{notification_id}", headers=_auth(other))).status_code == 404
    assert (await client.get("/api/v1/customer/notifications")).status_code == 401
    staff_token = create_access_token(str(uuid.uuid4()), "ADMIN")
    assert (
        await client.get("/api/v1/customer/notifications", headers={"Authorization": f"Bearer {staff_token}"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_preferences_get_and_patch_only_touch_the_transactional_flag(client, db_session, world):
    account, _ = await _make_customer(db_session)
    resp = await client.get("/api/v1/customer/notification-preferences", headers=_auth(account))
    assert resp.json() == {"transactional_email_enabled": True, "marketing_email_enabled": False, "email_verified": True}

    resp = await client.patch(
        "/api/v1/customer/notification-preferences",
        json={"transactional_email_enabled": False, "marketing_email_enabled": True, "marketing_consent": True},
        headers=_auth(account),
    )
    assert resp.status_code == 200 and resp.json()["transactional_email_enabled"] is False
    assert resp.json()["marketing_email_enabled"] is False  # cannot be set through this endpoint
    await db_session.refresh(account)
    assert account.marketing_consent is False and account.notification_preferences_updated_at is not None

    assert (await client.patch("/api/v1/customer/notification-preferences", json={}, headers=_auth(account))).status_code == 422


@pytest.mark.asyncio
async def test_staff_access_follows_roles_and_admin_retry(client, db_session, world):
    users, project = world
    account, lead = await _make_customer(db_session)
    visit = await _book(db_session, lead, project)
    row = (await _deliveries(db_session, visit.id))[0]
    await _drain(db_session, FakeEmailProvider(error=EmailPermanentError("Provider rejected the message (422)")), visit.id)

    def staff(role):
        return {"Authorization": f"Bearer {create_access_token(str(users[role].id), users[role].role.value)}"}

    url = "/api/v1/admin/customer-notifications"
    assert (await client.get(url, headers=staff("exec"))).status_code == 403
    assert (await client.get(url)).status_code == 401
    listing = await client.get(url, params={"status": "FAILED"}, headers=staff("manager"))
    assert listing.status_code == 200
    ours = [i for i in listing.json()["items"] if i["id"] == str(row.id)]
    assert len(ours) == 1 and "recipient" not in ours[0] and "payload" not in ours[0]
    assert account.email not in listing.text

    assert (await client.post(f"{url}/{row.id}/retry", headers=staff("manager"))).status_code == 403
    assert (await client.post(f"{url}/{row.id}/retry", headers=staff("exec"))).status_code == 403
    retried = await client.post(f"{url}/{row.id}/retry", headers=staff("admin"))
    assert retried.status_code == 200 and retried.json()["status"] == "PENDING"
    again = await client.post(f"{url}/{row.id}/retry", headers=staff("admin"))
    assert again.status_code == 200 and again.json()["status"] == "PENDING"  # idempotent
    assert (await client.post(f"{url}/{uuid.uuid4()}/retry", headers=staff("admin"))).status_code == 404

    fake = FakeEmailProvider()
    await _drain(db_session, fake, visit.id)
    assert len(fake.sent) == 1
