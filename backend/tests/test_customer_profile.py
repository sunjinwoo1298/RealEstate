import re
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

from backend.main import app
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.models.auth_session import AuthSession
from backend.models.customer_account import CustomerAccount, CustomerAccountStatus
from backend.models.customer_session import CustomerSession
from backend.models.customer_verification_token import CustomerVerificationToken
from backend.models.lead import ConsentStatus, Lead, LeadStatus
from backend.models.lead_qualification import ConfigurationType, LeadQualification
from backend.models.lead_source import LeadSource, SourceType
from backend.models.project import Project, ProjectVisibility
from backend.models.user import User, UserRole
import backend.api.v1.endpoints.customer_auth as customer_auth_endpoints

PASSWORD = "SuperSecret123!"
TEST_EMAIL_DOMAIN = "test-customer-profile.estateflow.ai"


def unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@{TEST_EMAIL_DOMAIN}"


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
async def cleanup_customers(db_session):
    created_emails = []
    yield created_emails
    if created_emails:
        result = await db_session.execute(
            select(CustomerAccount.id).where(CustomerAccount.normalized_email.in_(created_emails))
        )
        ids = [row[0] for row in result.all()]
        if ids:
            await db_session.execute(delete(CustomerSession).where(CustomerSession.customer_account_id.in_(ids)))
            await db_session.execute(
                delete(CustomerVerificationToken).where(CustomerVerificationToken.customer_account_id.in_(ids))
            )
            await db_session.execute(delete(CustomerAccount).where(CustomerAccount.id.in_(ids)))
            await db_session.commit()


@pytest_asyncio.fixture
async def cleanup_leads(db_session):
    created_lead_ids = []
    yield created_lead_ids
    if created_lead_ids:
        await db_session.execute(delete(LeadQualification).where(LeadQualification.lead_id.in_(created_lead_ids)))
        await db_session.execute(delete(LeadSource).where(LeadSource.lead_id.in_(created_lead_ids)))
        await db_session.execute(delete(Lead).where(Lead.id.in_(created_lead_ids)))
        await db_session.commit()


@pytest_asyncio.fixture
async def cleanup_projects(db_session):
    created_project_ids = []
    yield created_project_ids
    if created_project_ids:
        await db_session.execute(delete(Project).where(Project.id.in_(created_project_ids)))
        await db_session.commit()


async def _register_login_verify(client, fake_email, cleanup_customers, *, email=None):
    email = email or unique_email("profile")
    cleanup_customers.append(email.lower())
    resp = await client.post(
        "/api/v1/customer-auth/register",
        json={
            "full_name": "Priya Sharma",
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
    refresh_cookie = login_resp.cookies.get("estateflow_customer_refresh_token")
    return email, access_token, refresh_cookie


async def _create_lead_with_enquiry(
    db_session, cleanup_leads, cleanup_projects, *, project_visibility=ProjectVisibility.PUBLISHED, configuration=ConfigurationType.BHK_2
):
    project = Project(
        name=f"Test Enquiry Project {uuid.uuid4().hex[:8]}",
        visibility_status=project_visibility,
    )
    db_session.add(project)
    await db_session.flush()
    cleanup_projects.append(project.id)

    lead = Lead(full_name="Priya Sharma", lead_status=LeadStatus.QUALIFIED, consent_status=ConsentStatus.GRANTED)
    db_session.add(lead)
    await db_session.flush()
    cleanup_leads.append(lead.id)

    source = LeadSource(
        lead_id=lead.id,
        source_type=SourceType.WEBSITE,
        submitted_at=datetime.now(timezone.utc),
        raw_payload={},
    )
    db_session.add(source)

    qualification = LeadQualification(lead_id=lead.id, project_id=project.id, configuration=configuration)
    db_session.add(qualification)

    await db_session.commit()
    return lead, project


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- GET /customer/me ---


@pytest.mark.asyncio
async def test_get_profile_returns_authenticated_customer_profile(client, fake_email, cleanup_customers):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    resp = await client.get("/api/v1/customer/me", headers=auth_headers(access_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"].lower() == email.lower()
    assert body["full_name"] == "Priya Sharma"
    # Feature 10's CustomerLeadLinkingService runs unconditionally right
    # after email verification (match-or-create) -- a freshly verified
    # customer is therefore always linked to some Lead, even a bare one
    # with no qualification data yet.
    assert body["lead_linked"] is True
    assert body["phone_verified"] is False
    assert 0 <= body["profile_completeness"] <= 100


# --- PATCH /customer/me ---


@pytest.mark.asyncio
async def test_update_profile_full_name_and_phone(client, fake_email, cleanup_customers):
    _, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    resp = await client.patch(
        "/api/v1/customer/me",
        json={"full_name": "Priya Updated", "phone": "9876543210"},
        headers=auth_headers(access_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["full_name"] == "Priya Updated"
    assert body["phone"] == "+919876543210"
    assert body["phone_verified"] is False


@pytest.mark.asyncio
async def test_update_profile_invalid_phone_rejected(client, fake_email, cleanup_customers):
    _, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    resp = await client.patch(
        "/api/v1/customer/me",
        json={"phone": "not-a-phone-number"},
        headers=auth_headers(access_token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_email_cannot_be_changed_through_profile_update(client, fake_email, cleanup_customers):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    resp = await client.patch(
        "/api/v1/customer/me",
        json={"full_name": "Still Priya", "email": "hijacked@example.com"},
        headers=auth_headers(access_token),
    )
    assert resp.status_code == 200
    assert resp.json()["email"].lower() == email.lower()


@pytest.mark.asyncio
async def test_phone_update_does_not_mark_phone_verified(client, fake_email, cleanup_customers, db_session):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    resp = await client.patch(
        "/api/v1/customer/me", json={"phone": "9876543211"}, headers=auth_headers(access_token)
    )
    assert resp.status_code == 200
    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    assert customer.phone_verified_at is None


@pytest.mark.asyncio
async def test_profile_update_does_not_change_lead_association(
    client, fake_email, cleanup_customers, cleanup_leads, cleanup_projects, db_session
):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    lead, _ = await _create_lead_with_enquiry(db_session, cleanup_leads, cleanup_projects)

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.lead_id = lead.id
    await db_session.commit()

    resp = await client.patch(
        "/api/v1/customer/me", json={"full_name": "Renamed"}, headers=auth_headers(access_token)
    )
    assert resp.status_code == 200
    assert resp.json()["lead_linked"] is True

    await db_session.refresh(customer)
    assert customer.lead_id == lead.id


# --- GET /customer/me/enquiry ---


@pytest.mark.asyncio
async def test_enquiry_with_existing_lead(
    client, fake_email, cleanup_customers, cleanup_leads, cleanup_projects, db_session
):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    lead, project = await _create_lead_with_enquiry(db_session, cleanup_leads, cleanup_projects)

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.lead_id = lead.id
    await db_session.commit()

    resp = await client.get("/api/v1/customer/me/enquiry", headers=auth_headers(access_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_enquiry"] is True
    assert body["enquiry_reference"] == f"ENQ-{str(lead.id)[:8].upper()}"
    assert body["project_id"] == str(project.id)
    assert body["project_name"] == project.name
    assert body["configuration"] == "2 BHK"
    assert body["customer_status"] == "In Progress"
    assert body["enquiry_date"] is not None


@pytest.mark.asyncio
async def test_enquiry_without_linked_lead(client, fake_email, cleanup_customers, db_session):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)

    # Feature 10's linking service always matches-or-creates a Lead right
    # after verification, so an unlinked account is otherwise only reached
    # via the (structurally rare) ambiguous-match branch. Simulate that
    # "no Lead" state directly to exercise this endpoint's own has_enquiry
    # == False path.
    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.lead_id = None
    await db_session.commit()

    resp = await client.get("/api/v1/customer/me/enquiry", headers=auth_headers(access_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_enquiry"] is False
    assert body["enquiry_reference"] is None
    assert body["project_id"] is None


@pytest.mark.asyncio
async def test_customer_cannot_access_another_customers_enquiry(
    client, fake_email, cleanup_customers, cleanup_leads, cleanup_projects, db_session
):
    # Customer A keeps whatever Lead Feature 10's linking service
    # auto-created for them at verification -- it is never the crafted
    # `lead` below, which is only ever assigned to customer B.
    _, access_token_a, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    email_b, access_token_b, _ = await _register_login_verify(client, fake_email, cleanup_customers)

    lead, project = await _create_lead_with_enquiry(db_session, cleanup_leads, cleanup_projects)
    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email_b.lower()))
    customer_b = result.scalar_one()
    customer_b.lead_id = lead.id
    await db_session.commit()

    resp_a = await client.get("/api/v1/customer/me/enquiry", headers=auth_headers(access_token_a))
    resp_b = await client.get("/api/v1/customer/me/enquiry", headers=auth_headers(access_token_b))

    body_a = resp_a.json()
    body_b = resp_b.json()

    # A never sees B's crafted enquiry (reference, project, or anything else
    # tied to `lead`/`project`) even though both calls hit the exact same
    # endpoint with no id parameter.
    assert body_a["enquiry_reference"] != body_b["enquiry_reference"]
    assert body_a["project_id"] != str(project.id)
    assert body_a["project_name"] != project.name

    assert body_b["has_enquiry"] is True
    assert body_b["project_id"] == str(project.id)


@pytest.mark.asyncio
async def test_internal_lead_fields_not_exposed(
    client, fake_email, cleanup_customers, cleanup_leads, cleanup_projects, db_session
):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    lead, _ = await _create_lead_with_enquiry(db_session, cleanup_leads, cleanup_projects)

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.lead_id = lead.id
    await db_session.commit()

    resp = await client.get("/api/v1/customer/me/enquiry", headers=auth_headers(access_token))
    assert resp.status_code == 200
    body = resp.json()
    for forbidden_field in ("lead_status", "assigned_executive_id", "consent_status", "normalized_phone", "normalized_email"):
        assert forbidden_field not in body


@pytest.mark.asyncio
async def test_draft_project_not_leaked_in_enquiry(
    client, fake_email, cleanup_customers, cleanup_leads, cleanup_projects, db_session
):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    lead, project = await _create_lead_with_enquiry(
        db_session, cleanup_leads, cleanup_projects, project_visibility=ProjectVisibility.DRAFT
    )

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.lead_id = lead.id
    await db_session.commit()

    resp = await client.get("/api/v1/customer/me/enquiry", headers=auth_headers(access_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_enquiry"] is True
    assert body["project_id"] is None
    assert body["project_name"] is None


@pytest.mark.asyncio
async def test_archived_project_not_leaked_in_enquiry(
    client, fake_email, cleanup_customers, cleanup_leads, cleanup_projects, db_session
):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    lead, project = await _create_lead_with_enquiry(
        db_session, cleanup_leads, cleanup_projects, project_visibility=ProjectVisibility.ARCHIVED
    )

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.lead_id = lead.id
    await db_session.commit()

    resp = await client.get("/api/v1/customer/me/enquiry", headers=auth_headers(access_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] is None
    assert body["project_name"] is None


# --- POST /customer/me/change-password ---


@pytest.mark.asyncio
async def test_change_password_with_correct_current_password(client, fake_email, cleanup_customers):
    _, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    resp = await client.post(
        "/api/v1/customer/me/change-password",
        json={
            "current_password": PASSWORD,
            "new_password": "BrandNew456!",
            "confirm_new_password": "BrandNew456!",
        },
        headers=auth_headers(access_token),
    )
    assert resp.status_code == 200, resp.text
    assert "sign in" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_change_password_with_incorrect_current_password(client, fake_email, cleanup_customers):
    _, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    resp = await client.post(
        "/api/v1/customer/me/change-password",
        json={
            "current_password": "WrongPassword123!",
            "new_password": "BrandNew456!",
            "confirm_new_password": "BrandNew456!",
        },
        headers=auth_headers(access_token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_change_password_weak_new_password_rejected(client, fake_email, cleanup_customers):
    _, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    resp = await client.post(
        "/api/v1/customer/me/change-password",
        json={
            "current_password": PASSWORD,
            "new_password": "alllettersnodigits",
            "confirm_new_password": "alllettersnodigits",
        },
        headers=auth_headers(access_token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_change_password_mismatched_confirmation_rejected(client, fake_email, cleanup_customers):
    _, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    resp = await client.post(
        "/api/v1/customer/me/change-password",
        json={
            "current_password": PASSWORD,
            "new_password": "BrandNew456!",
            "confirm_new_password": "SomethingElse789!",
        },
        headers=auth_headers(access_token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_change_password_revokes_existing_customer_sessions(client, fake_email, cleanup_customers):
    email, access_token, refresh_cookie = await _register_login_verify(client, fake_email, cleanup_customers)
    assert refresh_cookie

    resp = await client.post(
        "/api/v1/customer/me/change-password",
        json={
            "current_password": PASSWORD,
            "new_password": "BrandNew456!",
            "confirm_new_password": "BrandNew456!",
        },
        headers=auth_headers(access_token),
    )
    assert resp.status_code == 200

    client.cookies.set("estateflow_customer_refresh_token", refresh_cookie)
    refresh_resp = await client.post("/api/v1/customer-auth/refresh")
    assert refresh_resp.status_code == 401

    old_login_resp = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD})
    assert old_login_resp.status_code == 401

    new_login_resp = await client.post(
        "/api/v1/customer-auth/login", json={"email": email, "password": "BrandNew456!"}
    )
    assert new_login_resp.status_code == 200


# --- Authorization edge cases ---


@pytest.mark.asyncio
async def test_customer_endpoints_reject_staff_token(client, db_session):
    staff_email = f"test-customer-profile-staff-{uuid.uuid4().hex[:8]}@estateflow.ai"
    staff = User(
        email=staff_email,
        full_name="Staff",
        password_hash=hash_password(PASSWORD),
        role=UserRole.SALES_EXECUTIVE,
        is_active=True,
    )
    db_session.add(staff)
    await db_session.commit()

    try:
        login_resp = await client.post("/api/v1/auth/login", json={"email": staff_email, "password": PASSWORD})
        staff_access_token = login_resp.json()["access_token"]

        resp = await client.get("/api/v1/customer/me", headers=auth_headers(staff_access_token))
        assert resp.status_code == 401
    finally:
        await db_session.execute(delete(AuthSession).where(AuthSession.user_id == staff.id))
        await db_session.execute(delete(User).where(User.id == staff.id))
        await db_session.commit()


@pytest.mark.asyncio
async def test_customer_endpoints_reject_missing_authentication(client):
    resp = await client.get("/api/v1/customer/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_customer_endpoints_reject_anonymous_buyer_session_cookie(client):
    # An anonymous buyer-chat session is a cookie, never a bearer token --
    # with no Authorization header at all, get_current_customer must still
    # reject the request regardless of any cookie present.
    client.cookies.set("estateflow_buyer_session", "some-opaque-buyer-session-token")
    resp = await client.get("/api/v1/customer/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_suspended_customer_cannot_access_customer_resources(client, fake_email, cleanup_customers, db_session):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.status = CustomerAccountStatus.SUSPENDED
    await db_session.commit()

    resp = await client.get("/api/v1/customer/me", headers=auth_headers(access_token))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_deactivated_customer_cannot_access_customer_resources(
    client, fake_email, cleanup_customers, db_session
):
    email, access_token, _ = await _register_login_verify(client, fake_email, cleanup_customers)
    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.status = CustomerAccountStatus.DEACTIVATED
    await db_session.commit()

    resp = await client.get("/api/v1/customer/me", headers=auth_headers(access_token))
    assert resp.status_code == 401
