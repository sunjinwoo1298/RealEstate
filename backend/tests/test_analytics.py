import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

from backend.main import app
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.models.conversation import Conversation
from backend.models.conversation_assignment import AssignmentStatus, ConversationAssignment
from backend.models.handoff import Handoff, HandoffReason, HandoffStatus
from backend.models.lead import Lead, LeadStatus
from backend.models.lead_qualification import ConfigurationType, LeadQualification, PurchasePurpose
from backend.models.lead_source import LeadSource, SourceType
from backend.models.message import Message, MessageType, SenderType
from backend.models.project import Project
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.models.user import User, UserRole
from backend.models.visit_reminder import ReminderStatus, ReminderType, VisitReminder

PASSWORD = "SuperSecret123!"
ADMIN_EMAIL = "test-analytics-admin@estateflow.ai"
MANAGER_EMAIL = "test-analytics-manager@estateflow.ai"
EXEC1_EMAIL = "test-analytics-exec1@estateflow.ai"
EXEC2_EMAIL = "test-analytics-exec2@estateflow.ai"


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
    emails = [ADMIN_EMAIL, MANAGER_EMAIL, EXEC1_EMAIL, EXEC2_EMAIL]
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()

    admin = User(email=ADMIN_EMAIL, full_name="Analytics Admin", password_hash=hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True)
    manager = User(email=MANAGER_EMAIL, full_name="Analytics Manager", password_hash=hash_password(PASSWORD), role=UserRole.MANAGER, is_active=True)
    exec1 = User(email=EXEC1_EMAIL, full_name="Analytics Exec One", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    exec2 = User(email=EXEC2_EMAIL, full_name="Analytics Exec Two", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    db_session.add_all([admin, manager, exec1, exec2])
    await db_session.commit()
    for u in (admin, manager, exec1, exec2):
        await db_session.refresh(u)

    yield {"admin": admin, "manager": manager, "exec1": exec1, "exec2": exec2}

    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()


@pytest_asyncio.fixture
async def project(db_session):
    p = Project(name=f"AnalyticsTest Project {uuid.uuid4().hex[:8]}", description="Test", location="Test City", is_active=True)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    yield p


@pytest_asyncio.fixture(autouse=True)
async def cleanup(db_session):
    yield
    lead_ids_result = await db_session.execute(select(Lead.id).where(Lead.full_name.like("AnalyticsTest%")))
    lead_ids = [row[0] for row in lead_ids_result.all()]

    conv_ids_result = await db_session.execute(select(Conversation.id).where(Conversation.lead_id.in_(lead_ids))) if lead_ids else None
    conv_ids = [row[0] for row in conv_ids_result.all()] if conv_ids_result is not None else []

    if conv_ids:
        handoff_ids_result = await db_session.execute(select(Handoff.id).where(Handoff.conversation_id.in_(conv_ids)))
        handoff_ids = [row[0] for row in handoff_ids_result.all()]
        if handoff_ids:
            await db_session.execute(delete(ConversationAssignment).where(ConversationAssignment.handoff_id.in_(handoff_ids)))
            await db_session.execute(delete(Handoff).where(Handoff.id.in_(handoff_ids)))
        await db_session.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
        await db_session.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))

    if lead_ids:
        visit_ids_result = await db_session.execute(select(SiteVisit.id).where(SiteVisit.lead_id.in_(lead_ids)))
        visit_ids = [row[0] for row in visit_ids_result.all()]
        if visit_ids:
            await db_session.execute(delete(VisitReminder).where(VisitReminder.site_visit_id.in_(visit_ids)))
            await db_session.execute(delete(SiteVisit).where(SiteVisit.id.in_(visit_ids)))
        await db_session.execute(delete(LeadQualification).where(LeadQualification.lead_id.in_(lead_ids)))
        await db_session.execute(delete(LeadSource).where(LeadSource.lead_id.in_(lead_ids)))
        await db_session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
    await db_session.commit()

    await db_session.execute(delete(Project).where(Project.name.like("AnalyticsTest%")))
    await db_session.commit()


async def _login(client, email):
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _make_lead(db_session, *, created_at=None, status=LeadStatus.NEW, executive_id=None):
    lead = Lead(
        full_name="AnalyticsTest Buyer",
        normalized_phone=_unique_phone(),
        lead_status=status,
        assigned_executive_id=executive_id,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    if created_at is not None:
        await db_session.execute(
            Lead.__table__.update().where(Lead.id == lead.id).values(created_at=created_at)
        )
        await db_session.commit()
        await db_session.refresh(lead)
    return lead


async def _add_source(db_session, lead, *, source_type=SourceType.WEBSITE, submitted_at=None):
    source = LeadSource(
        lead_id=lead.id,
        source_type=source_type,
        raw_payload={},
        submitted_at=submitted_at or datetime.now(timezone.utc),
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


async def _add_conversation_with_message(db_session, lead, *, sender_type, message_type=MessageType.TEXT, created_at=None):
    conversation = Conversation(lead_id=lead.id)
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    message = Message(
        conversation_id=conversation.id,
        sender_type=sender_type,
        content="hello",
        message_type=message_type,
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)
    if created_at is not None:
        await db_session.execute(Message.__table__.update().where(Message.id == message.id).values(created_at=created_at))
        await db_session.commit()
    return conversation, message


NOW = datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_unique_lead_counting_with_multiple_sources(client, db_session, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    lead = await _make_lead(db_session, created_at=NOW - timedelta(hours=2))
    await _add_source(db_session, lead, source_type=SourceType.WEBSITE)
    await _add_source(db_session, lead, source_type=SourceType.SOCIAL_AD)

    resp = await client.get("/api/v1/analytics/leads", params={"range": "TODAY"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_unique_leads"] == 1
    assert body["total_enquiry_records"] == 2


@pytest.mark.asyncio
async def test_source_attribution_breakdown(client, db_session, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    lead1 = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))
    await _add_source(db_session, lead1, source_type=SourceType.WEBSITE)
    lead2 = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))
    await _add_source(db_session, lead2, source_type=SourceType.PROPERTY_PORTAL)

    resp = await client.get("/api/v1/analytics/sources", params={"range": "TODAY"}, headers=headers)
    assert resp.status_code == 200
    by_type = {row["source_type"]: row for row in resp.json()["sources"]}
    assert by_type["WEBSITE"]["unique_lead_count"] == 1
    assert by_type["PROPERTY_PORTAL"]["unique_lead_count"] == 1


@pytest.mark.asyncio
async def test_project_level_filtering(client, db_session, seeded_users, project):
    headers = await _login(client, ADMIN_EMAIL)
    lead_in_project = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))
    db_session.add(LeadQualification(lead_id=lead_in_project.id, project_id=project.id))
    await db_session.commit()
    lead_other = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))

    resp = await client.get(
        "/api/v1/analytics/leads", params={"range": "TODAY", "project_id": str(project.id)}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["total_unique_leads"] == 1


@pytest.mark.asyncio
async def test_date_boundary_excludes_leads_outside_range(client, db_session, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    await _make_lead(db_session, created_at=NOW - timedelta(days=10))

    resp = await client.get("/api/v1/analytics/leads", params={"range": "TODAY"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total_unique_leads"] == 0


@pytest.mark.asyncio
async def test_invalid_custom_date_range_rejected(client, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    resp = await client.get("/api/v1/analytics/leads", params={"range": "CUSTOM"}, headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_first_ai_response_and_system_message_exclusion(client, db_session, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    lead = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))
    # A SYSTEM message right after creation must never count as the response.
    await _add_conversation_with_message(
        db_session, lead, sender_type=SenderType.SYSTEM, message_type=MessageType.SYSTEM_EVENT, created_at=NOW - timedelta(minutes=55)
    )
    conversation, _ = await _add_conversation_with_message(
        db_session, lead, sender_type=SenderType.AI, created_at=NOW - timedelta(minutes=50)
    )

    resp = await client.get("/api/v1/analytics/response-times", params={"range": "TODAY"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["leads_with_response"] == 1
    assert body["average_response_time_seconds"] == pytest.approx(600, abs=5)


@pytest.mark.asyncio
async def test_first_staff_response_uses_earliest_qualifying_message(client, db_session, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    lead = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))
    await _add_conversation_with_message(db_session, lead, sender_type=SenderType.AI, created_at=NOW - timedelta(minutes=40))
    # A second, later conversation's staff reply must not overwrite the earlier one.
    await _add_conversation_with_message(db_session, lead, sender_type=SenderType.STAFF, created_at=NOW - timedelta(minutes=10))

    resp = await client.get("/api/v1/analytics/response-times", params={"range": "TODAY"}, headers=headers)
    body = resp.json()
    assert body["average_response_time_seconds"] == pytest.approx(1200, abs=5)


@pytest.mark.asyncio
async def test_unresponded_leads_not_given_artificial_time(client, db_session, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    await _make_lead(db_session, created_at=NOW - timedelta(hours=1))

    resp = await client.get("/api/v1/analytics/response-times", params={"range": "TODAY"}, headers=headers)
    body = resp.json()
    assert body["leads_without_response"] == 1
    assert body["leads_with_response"] == 0
    assert body["average_response_time_seconds"] is None
    assert body["median_response_time_seconds"] is None


@pytest.mark.asyncio
async def test_qualified_lead_calculation(client, db_session, seeded_users, project):
    headers = await _login(client, ADMIN_EMAIL)
    complete = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))
    db_session.add(
        LeadQualification(
            lead_id=complete.id,
            project_id=project.id,
            configuration=ConfigurationType.BHK_2,
            budget_min=5000000,
            purchase_purpose=PurchasePurpose.SELF_USE,
        )
    )
    incomplete = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))
    db_session.add(LeadQualification(lead_id=incomplete.id, project_id=project.id))
    await db_session.commit()

    resp = await client.get("/api/v1/analytics/qualification", params={"range": "TODAY"}, headers=headers)
    body = resp.json()
    assert body["leads_in_cohort"] == 2
    assert body["qualified_leads"] == 1
    assert body["qualification_completion_rate_percent"] == 50.0


@pytest.mark.asyncio
async def test_funnel_stage_counts_no_double_counting(client, db_session, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    await _make_lead(db_session, created_at=NOW - timedelta(hours=1), status=LeadStatus.NEW)
    await _make_lead(db_session, created_at=NOW - timedelta(hours=1), status=LeadStatus.QUALIFIED)
    await _make_lead(db_session, created_at=NOW - timedelta(hours=1), status=LeadStatus.VISIT_COMPLETED)
    await _make_lead(db_session, created_at=NOW - timedelta(hours=1), status=LeadStatus.LOST)

    resp = await client.get("/api/v1/analytics/funnel", params={"range": "TODAY"}, headers=headers)
    body = resp.json()
    stages = {s["stage"]: s["count"] for s in body["stages"]}
    assert body["cohort_size"] == 4
    assert body["excluded_lost"] == 1
    assert stages["New Leads"] == 3  # LOST excluded from the forward ladder
    assert stages["Qualified"] == 2
    assert stages["Site Visit Completed"] == 1
    assert stages["Converted"] == 0  # no lead has the explicit CONVERTED status


@pytest.mark.asyncio
async def test_site_visit_attendance_and_no_show_rate_excludes_cancelled(client, db_session, seeded_users, project):
    headers = await _login(client, ADMIN_EMAIL)
    lead = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))

    def _visit(status):
        return SiteVisit(
            lead_id=lead.id,
            project_id=project.id,
            start_time=NOW + timedelta(days=1),
            end_time=NOW + timedelta(days=1, minutes=30),
            status=status,
            booking_reference=uuid.uuid4().hex[:12].upper(),
        )

    completed = _visit(SiteVisitStatus.COMPLETED)
    no_show = _visit(SiteVisitStatus.NO_SHOW)
    cancelled = _visit(SiteVisitStatus.CANCELLED)
    db_session.add_all([completed, no_show, cancelled])
    await db_session.commit()

    resp = await client.get("/api/v1/analytics/site-visits", params={"range": "TODAY"}, headers=headers)
    body = resp.json()
    assert body["total_booked"] == 3
    assert body["completed"] == 1
    assert body["no_show"] == 1
    assert body["cancelled"] == 1
    # denominator is completed+no_show only -- cancelled must not dilute it
    assert body["attendance_rate_percent"] == 50.0
    assert body["no_show_rate_percent"] == 50.0


@pytest.mark.asyncio
async def test_division_by_zero_returns_null_not_error(client, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    resp = await client.get("/api/v1/analytics/site-visits", params={"range": "TODAY"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["attendance_rate_percent"] is None
    assert body["no_show_rate_percent"] is None


@pytest.mark.asyncio
async def test_reminder_status_breakdown_distinguishes_simulated_from_sent(client, db_session, seeded_users, project):
    headers = await _login(client, ADMIN_EMAIL)
    lead = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))
    visit = SiteVisit(
        lead_id=lead.id,
        project_id=project.id,
        start_time=NOW + timedelta(days=1),
        end_time=NOW + timedelta(days=1, minutes=30),
        status=SiteVisitStatus.CONFIRMED,
        booking_reference=uuid.uuid4().hex[:12].upper(),
    )
    db_session.add(visit)
    await db_session.commit()
    await db_session.refresh(visit)

    simulated = VisitReminder(site_visit_id=visit.id, reminder_type=ReminderType.H24, scheduled_at=NOW, status=ReminderStatus.SIMULATED)
    failed = VisitReminder(site_visit_id=visit.id, reminder_type=ReminderType.H2, scheduled_at=NOW, status=ReminderStatus.FAILED)
    db_session.add_all([simulated, failed])
    await db_session.commit()

    resp = await client.get("/api/v1/analytics/reminders", params={"range": "TODAY"}, headers=headers)
    body = resp.json()
    assert body["simulated"] == 1
    assert body["sent"] == 0
    assert body["failed"] == 1
    # failed / (sent+simulated+failed) = 1/2
    assert body["failure_rate_percent"] == 50.0


@pytest.mark.asyncio
async def test_executive_data_isolation(client, db_session, seeded_users):
    headers_exec1 = await _login(client, EXEC1_EMAIL)
    await _make_lead(db_session, created_at=NOW - timedelta(hours=1), executive_id=seeded_users["exec1"].id)
    await _make_lead(db_session, created_at=NOW - timedelta(hours=1), executive_id=seeded_users["exec2"].id)

    resp = await client.get("/api/v1/analytics/executives", params={"range": "TODAY"}, headers=headers_exec1)
    assert resp.status_code == 200
    executives = resp.json()["executives"]
    assert len(executives) == 1
    assert executives[0]["executive_id"] == str(seeded_users["exec1"].id)


@pytest.mark.asyncio
async def test_manager_sees_all_executives(client, db_session, seeded_users):
    headers = await _login(client, MANAGER_EMAIL)
    resp = await client.get("/api/v1/analytics/executives", params={"range": "TODAY"}, headers=headers)
    assert resp.status_code == 200
    executive_ids = {row["executive_id"] for row in resp.json()["executives"]}
    assert str(seeded_users["exec1"].id) in executive_ids
    assert str(seeded_users["exec2"].id) in executive_ids


@pytest.mark.asyncio
async def test_sales_executive_leads_scoped_to_own_assignment(client, db_session, seeded_users):
    headers_exec1 = await _login(client, EXEC1_EMAIL)
    await _make_lead(db_session, created_at=NOW - timedelta(hours=1), executive_id=seeded_users["exec1"].id)
    await _make_lead(db_session, created_at=NOW - timedelta(hours=1), executive_id=seeded_users["exec2"].id)

    resp = await client.get("/api/v1/analytics/leads", params={"range": "TODAY"}, headers=headers_exec1)
    assert resp.status_code == 200
    assert resp.json()["total_unique_leads"] == 1

    # A sales executive cannot widen scope by requesting another executive's id.
    resp2 = await client.get(
        "/api/v1/analytics/leads",
        params={"range": "TODAY", "executive_id": str(seeded_users["exec2"].id)},
        headers=headers_exec1,
    )
    assert resp2.json()["total_unique_leads"] == 1


@pytest.mark.asyncio
async def test_empty_dataset_returns_zeroed_response(client, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    resp = await client.get("/api/v1/analytics/overview", params={"range": "TODAY"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_unique_leads"] == 0
    assert body["qualification_rate_percent"] is None


@pytest.mark.asyncio
async def test_handoff_counts_use_persisted_handoff_records(client, db_session, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    lead = await _make_lead(db_session, created_at=NOW - timedelta(hours=1))
    conversation, _ = await _add_conversation_with_message(db_session, lead, sender_type=SenderType.AI, created_at=NOW - timedelta(minutes=30))
    handoff = Handoff(conversation_id=conversation.id, lead_id=lead.id, status=HandoffStatus.PENDING, reason=HandoffReason.BUYER_REQUEST)
    db_session.add(handoff)
    await db_session.commit()

    resp = await client.get("/api/v1/analytics/qualification", params={"range": "TODAY"}, headers=headers)
    body = resp.json()
    assert body["ai_handled_conversations"] == 1
    assert body["handed_off_conversations"] == 1
    assert body["handoff_rate_percent"] == 100.0
