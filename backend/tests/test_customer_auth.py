import asyncio
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

from backend.main import app
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.models.customer_account import CustomerAccount, CustomerAccountStatus
from backend.models.customer_session import CustomerSession
from backend.models.customer_verification_token import CustomerVerificationToken, TokenPurpose
from backend.models.lead import Lead
from backend.models.lead_source import LeadSource, SourceType
from backend.models.user import User, UserRole
from backend.models.auth_session import AuthSession
import backend.api.v1.endpoints.customer_auth as customer_auth_endpoints

PASSWORD = "SuperSecret123!"
TEST_EMAIL_DOMAIN = "test-customer-auth.estateflow.ai"


def unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@{TEST_EMAIL_DOMAIN}"


class FakeEmailProvider:
    """Captures simulated emails instead of logging them, so tests can pull the token out of the link."""

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


async def _register(client, fake_email, cleanup_customers, *, email=None, phone=None, marketing_consent=False):
    email = email or unique_email("reg")
    cleanup_customers.append(email.lower())
    resp = await client.post(
        "/api/v1/customer-auth/register",
        json={
            "full_name": "Test Customer",
            "email": email,
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
            "phone": phone,
            "accepted_privacy_policy": True,
            "marketing_consent": marketing_consent,
        },
    )
    return resp, email


async def _register_and_verify(client, fake_email, cleanup_customers, **kwargs):
    resp, email = await _register(client, fake_email, cleanup_customers, **kwargs)
    assert resp.status_code == 201, resp.text
    token = fake_email.last_token()
    verify_resp = await client.post("/api/v1/customer-auth/verify-email", json={"token": token})
    assert verify_resp.status_code == 200, verify_resp.text
    return email, token, verify_resp.json()


# --- Registration ---


@pytest.mark.asyncio
async def test_register_valid_customer_pending_verification(client, fake_email, cleanup_customers, db_session):
    resp, email = await _register(client, fake_email, cleanup_customers)
    assert resp.status_code == 201
    assert resp.json()["email"].lower() == email.lower()
    assert len(fake_email.sent) == 1
    assert "token=" in fake_email.sent[0]["body"]

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    assert customer.status == CustomerAccountStatus.PENDING_VERIFICATION
    assert customer.email_verified_at is None
    assert customer.lead_id is None


@pytest.mark.asyncio
async def test_register_duplicate_normalized_email_rejected(client, fake_email, cleanup_customers):
    _, email = await _register(client, fake_email, cleanup_customers)
    resp2 = await client.post(
        "/api/v1/customer-auth/register",
        json={
            "full_name": "Someone Else",
            "email": email.upper(),  # same identity once normalized
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
            "accepted_privacy_policy": True,
        },
    )
    # Same response as a fresh signup: no account-existence oracle.
    assert resp2.status_code == 201


@pytest.mark.asyncio
async def test_register_invalid_email_rejected(client, fake_email, cleanup_customers):
    resp = await client.post(
        "/api/v1/customer-auth/register",
        json={
            "full_name": "Test",
            "email": "not-an-email",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
            "accepted_privacy_policy": True,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_weak_password_rejected(client, fake_email, cleanup_customers):
    email = unique_email("weak")
    resp = await client.post(
        "/api/v1/customer-auth/register",
        json={
            "full_name": "Test",
            "email": email,
            "password": "alllettersnodigits",
            "password_confirmation": "alllettersnodigits",
            "accepted_privacy_policy": True,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_consent_rejected(client, fake_email, cleanup_customers):
    email = unique_email("noconsent")
    resp = await client.post(
        "/api/v1/customer-auth/register",
        json={
            "full_name": "Test",
            "email": email,
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
            "accepted_privacy_policy": False,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_optional_marketing_consent(client, fake_email, cleanup_customers, db_session):
    resp, email = await _register(client, fake_email, cleanup_customers, marketing_consent=True)
    assert resp.status_code == 201
    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    assert customer.marketing_consent is True
    assert customer.privacy_policy_accepted_at is not None
    assert customer.marketing_consent_updated_at is not None


# --- Email verification ---


@pytest.mark.asyncio
async def test_verify_email_valid_token_activates_account(client, fake_email, cleanup_customers):
    email, token, body = await _register_and_verify(client, fake_email, cleanup_customers)
    assert body["status"] == "ACTIVE"
    assert body["email_verified"] is True


@pytest.mark.asyncio
async def test_verify_email_expired_token_rejected(client, fake_email, cleanup_customers, db_session):
    resp, email = await _register(client, fake_email, cleanup_customers)
    assert resp.status_code == 201
    token = fake_email.last_token()

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    token_result = await db_session.execute(
        select(CustomerVerificationToken).where(CustomerVerificationToken.customer_account_id == customer.id)
    )
    verification_token = token_result.scalar_one()
    verification_token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    verify_resp = await client.post("/api/v1/customer-auth/verify-email", json={"token": token})
    assert verify_resp.status_code == 422


@pytest.mark.asyncio
async def test_verify_email_reused_token_rejected(client, fake_email, cleanup_customers):
    email, token, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    reuse_resp = await client.post("/api/v1/customer-auth/verify-email", json={"token": token})
    assert reuse_resp.status_code == 422


@pytest.mark.asyncio
async def test_resend_verification_invalidates_old_token(client, fake_email, cleanup_customers):
    resp, email = await _register(client, fake_email, cleanup_customers)
    assert resp.status_code == 201
    old_token = fake_email.last_token()

    resend_resp = await client.post("/api/v1/customer-auth/resend-verification", json={"email": email})
    assert resend_resp.status_code == 200
    new_token = fake_email.last_token()
    assert new_token != old_token

    old_verify_resp = await client.post("/api/v1/customer-auth/verify-email", json={"token": old_token})
    assert old_verify_resp.status_code == 422

    new_verify_resp = await client.post("/api/v1/customer-auth/verify-email", json={"token": new_token})
    assert new_verify_resp.status_code == 200


@pytest.mark.asyncio
async def test_resend_verification_generic_response_for_unknown_email(client, fake_email, cleanup_customers):
    resp = await client.post(
        "/api/v1/customer-auth/resend-verification", json={"email": unique_email("unknown")}
    )
    assert resp.status_code == 200
    assert len(fake_email.sent) == 0


@pytest.mark.asyncio
async def test_unverified_account_cannot_login(client, fake_email, cleanup_customers):
    resp, email = await _register(client, fake_email, cleanup_customers)
    assert resp.status_code == 201
    login_resp = await client.post(
        "/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login_resp.status_code == 401


# --- Authentication ---


@pytest.mark.asyncio
async def test_login_success(client, fake_email, cleanup_customers):
    email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    resp = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["customer"]["email"].lower() == email.lower()
    assert "password_hash" not in data["customer"]
    assert "estateflow_customer_refresh_token" in resp.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(client, fake_email, cleanup_customers):
    email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    resp = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": "WrongPassword123"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_suspended_account_rejected(client, fake_email, cleanup_customers, db_session):
    email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.status = CustomerAccountStatus.SUSPENDED
    await db_session.commit()

    resp = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_suspended_customer_loses_access_with_existing_access_token(client, fake_email, cleanup_customers, db_session):
    email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    login_resp = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD})
    access_token = login_resp.json()["access_token"]

    me_resp = await client.get("/api/v1/customer-auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_resp.status_code == 200

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.status = CustomerAccountStatus.SUSPENDED
    await db_session.commit()

    me_resp_after = await client.get("/api/v1/customer-auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_resp_after.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_reuse_is_rejected(client, fake_email, cleanup_customers, monkeypatch):
    # Outside the BUG-18 recovery window a retried old token is genuine reuse.
    from backend.core.config import settings

    monkeypatch.setattr(settings, 'REFRESH_RECOVERY_GRACE_SECONDS', 0)
    email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    login_resp = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD})
    old_cookie = login_resp.cookies.get("estateflow_customer_refresh_token")
    assert old_cookie

    client.cookies.set("estateflow_customer_refresh_token", old_cookie)
    refresh_resp = await client.post("/api/v1/customer-auth/refresh")
    assert refresh_resp.status_code == 200
    new_cookie = refresh_resp.cookies.get("estateflow_customer_refresh_token")
    assert new_cookie and new_cookie != old_cookie

    client.cookies.set("estateflow_customer_refresh_token", old_cookie)
    reuse_resp = await client.post("/api/v1/customer-auth/refresh")
    assert reuse_resp.status_code == 401

    # Reuse detection must revoke the whole chain -- the freshly rotated token is dead too.
    client.cookies.set("estateflow_customer_refresh_token", new_cookie)
    after_reuse_resp = await client.post("/api/v1/customer-auth/refresh")
    assert after_reuse_resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_session(client, fake_email, cleanup_customers):
    email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    login_resp = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD})
    cookie = login_resp.cookies.get("estateflow_customer_refresh_token")

    client.cookies.set("estateflow_customer_refresh_token", cookie)
    logout_resp = await client.post("/api/v1/customer-auth/logout")
    assert logout_resp.status_code == 204

    client.cookies.set("estateflow_customer_refresh_token", cookie)
    refresh_after_logout = await client.post("/api/v1/customer-auth/refresh")
    assert refresh_after_logout.status_code == 401

    # Repeated logout must stay safe (idempotent), never error.
    second_logout = await client.post("/api/v1/customer-auth/logout")
    assert second_logout.status_code == 204


@pytest.mark.asyncio
async def test_me_endpoint_requires_customer_token(client, fake_email, cleanup_customers):
    resp = await client.get("/api/v1/customer-auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_customer_token_rejected_by_staff_endpoint(client, fake_email, cleanup_customers):
    email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    login_resp = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD})
    access_token = login_resp.json()["access_token"]

    staff_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert staff_resp.status_code == 401


@pytest.mark.asyncio
async def test_staff_token_rejected_by_customer_endpoint(client, fake_email, cleanup_customers, db_session):
    staff_email = f"test-customer-auth-staff-{uuid.uuid4().hex[:8]}@estateflow.ai"
    staff = User(
        email=staff_email, full_name="Staff", password_hash=hash_password(PASSWORD),
        role=UserRole.SALES_EXECUTIVE, is_active=True,
    )
    db_session.add(staff)
    await db_session.commit()

    try:
        login_resp = await client.post("/api/v1/auth/login", json={"email": staff_email, "password": PASSWORD})
        staff_access_token = login_resp.json()["access_token"]

        resp = await client.get(
            "/api/v1/customer-auth/me", headers={"Authorization": f"Bearer {staff_access_token}"}
        )
        assert resp.status_code == 401
    finally:
        await db_session.execute(delete(AuthSession).where(AuthSession.user_id == staff.id))
        await db_session.execute(delete(User).where(User.id == staff.id))
        await db_session.commit()


# --- Password recovery ---


@pytest.mark.asyncio
async def test_forgot_password_generic_response_for_unknown_email(client, fake_email, cleanup_customers):
    resp = await client.post("/api/v1/customer-auth/forgot-password", json={"email": unique_email("unknown")})
    assert resp.status_code == 200
    assert len(fake_email.sent) == 0


@pytest.mark.asyncio
async def test_forgot_password_and_reset_flow_revokes_sessions(client, fake_email, cleanup_customers):
    email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    login_resp = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD})
    old_refresh_cookie = login_resp.cookies.get("estateflow_customer_refresh_token")

    forgot_resp = await client.post("/api/v1/customer-auth/forgot-password", json={"email": email})
    assert forgot_resp.status_code == 200
    reset_token = fake_email.last_token()

    new_password = "BrandNewPassword456"
    reset_resp = await client.post(
        "/api/v1/customer-auth/reset-password",
        json={"token": reset_token, "new_password": new_password, "new_password_confirmation": new_password},
    )
    assert reset_resp.status_code == 200

    # Old session must be revoked by the reset.
    client.cookies.set("estateflow_customer_refresh_token", old_refresh_cookie)
    refresh_resp = await client.post("/api/v1/customer-auth/refresh")
    assert refresh_resp.status_code == 401

    # Old password no longer works; new password does.
    old_login = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": PASSWORD})
    assert old_login.status_code == 401
    new_login = await client.post("/api/v1/customer-auth/login", json={"email": email, "password": new_password})
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_expired_token_rejected(client, fake_email, cleanup_customers, db_session):
    email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    forgot_resp = await client.post("/api/v1/customer-auth/forgot-password", json={"email": email})
    assert forgot_resp.status_code == 200
    reset_token = fake_email.last_token()

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    token_result = await db_session.execute(
        select(CustomerVerificationToken).where(
            CustomerVerificationToken.customer_account_id == customer.id,
            CustomerVerificationToken.purpose == TokenPurpose.PASSWORD_RESET,
        )
    )
    verification_token = token_result.scalar_one()
    verification_token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/customer-auth/reset-password",
        json={"token": reset_token, "new_password": "SomethingNew789", "new_password_confirmation": "SomethingNew789"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reset_password_reused_token_rejected(client, fake_email, cleanup_customers):
    email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers)
    forgot_resp = await client.post("/api/v1/customer-auth/forgot-password", json={"email": email})
    assert forgot_resp.status_code == 200
    reset_token = fake_email.last_token()

    new_password = "FirstReset123"
    first_resp = await client.post(
        "/api/v1/customer-auth/reset-password",
        json={"token": reset_token, "new_password": new_password, "new_password_confirmation": new_password},
    )
    assert first_resp.status_code == 200

    second_resp = await client.post(
        "/api/v1/customer-auth/reset-password",
        json={"token": reset_token, "new_password": "SecondReset456", "new_password_confirmation": "SecondReset456"},
    )
    assert second_resp.status_code == 422


@pytest.mark.asyncio
async def test_reset_password_does_not_change_lead_association(client, fake_email, cleanup_customers, db_session):
    lead_email = unique_email("leadlink")
    lead = Lead(full_name="Lead Owner", normalized_email=lead_email.lower())
    db_session.add(lead)
    await db_session.commit()

    try:
        email, _, _ = await _register_and_verify(client, fake_email, cleanup_customers, email=lead_email)
        result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
        customer = result.scalar_one()
        assert customer.lead_id == lead.id

        forgot_resp = await client.post("/api/v1/customer-auth/forgot-password", json={"email": email})
        reset_token = fake_email.last_token()
        new_password = "ResetKeepsLead123"
        reset_resp = await client.post(
            "/api/v1/customer-auth/reset-password",
            json={"token": reset_token, "new_password": new_password, "new_password_confirmation": new_password},
        )
        assert reset_resp.status_code == 200

        await db_session.refresh(customer)
        assert customer.lead_id == lead.id
    finally:
        await db_session.execute(delete(Lead).where(Lead.id == lead.id))
        await db_session.commit()


# --- Customer-to-Lead identity linking ---


@pytest.mark.asyncio
async def test_verified_email_matches_one_existing_lead(client, fake_email, cleanup_customers, db_session):
    lead_email = unique_email("matchlead")
    lead = Lead(full_name="Existing Buyer", normalized_email=lead_email.lower())
    db_session.add(lead)
    await db_session.commit()

    try:
        email, _, body = await _register_and_verify(client, fake_email, cleanup_customers, email=lead_email)
        assert body["lead_linked"] is True

        result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
        customer = result.scalar_one()
        assert customer.lead_id == lead.id
    finally:
        await db_session.execute(delete(Lead).where(Lead.id == lead.id))
        await db_session.commit()


@pytest.mark.asyncio
async def test_no_match_creates_one_canonical_lead(client, fake_email, cleanup_customers, db_session):
    email, _, body = await _register_and_verify(client, fake_email, cleanup_customers)
    assert body["lead_linked"] is True

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    assert customer.lead_id is not None

    lead_result = await db_session.execute(select(Lead).where(Lead.id == customer.lead_id))
    lead = lead_result.scalar_one()
    assert lead.normalized_email == email.lower()

    source_result = await db_session.execute(select(LeadSource).where(LeadSource.lead_id == lead.id))
    sources = source_result.scalars().all()
    assert len(sources) == 1
    assert sources[0].campaign_name == "Customer Registration"

    await db_session.execute(delete(LeadSource).where(LeadSource.lead_id == lead.id))
    await db_session.execute(delete(Lead).where(Lead.id == lead.id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_unverified_email_cannot_trigger_linking(client, fake_email, cleanup_customers, db_session):
    resp, email = await _register(client, fake_email, cleanup_customers)
    assert resp.status_code == 201

    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    assert customer.lead_id is None
    assert customer.status == CustomerAccountStatus.PENDING_VERIFICATION

    lead_result = await db_session.execute(select(Lead).where(Lead.normalized_email == email.lower()))
    assert lead_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_lead_already_linked_to_another_customer_cannot_be_claimed(
    client, fake_email, cleanup_customers, db_session
):
    shared_email = unique_email("claimed")
    lead = Lead(full_name="Already Claimed Lead", normalized_email=shared_email.lower())
    db_session.add(lead)
    await db_session.commit()

    other_email = unique_email("owner")
    other_customer = CustomerAccount(
        email=other_email,
        normalized_email=other_email.lower(),
        password_hash=hash_password(PASSWORD),
        full_name="Other Owner",
        status=CustomerAccountStatus.ACTIVE,
        lead_id=lead.id,
        privacy_policy_accepted_at=datetime.now(timezone.utc),
        marketing_consent=False,
    )
    db_session.add(other_customer)
    await db_session.commit()

    try:
        email, _, body = await _register_and_verify(client, fake_email, cleanup_customers, email=shared_email)
        assert body["lead_linked"] is False

        result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
        customer = result.scalar_one()
        assert customer.lead_id is None

        # The original owner's link must be untouched.
        await db_session.refresh(other_customer)
        assert other_customer.lead_id == lead.id

        # No duplicate Lead was created for this email.
        lead_count = await db_session.execute(select(Lead).where(Lead.normalized_email == shared_email.lower()))
        assert len(lead_count.scalars().all()) == 1
    finally:
        await db_session.execute(delete(CustomerSession).where(CustomerSession.customer_account_id == other_customer.id))
        await db_session.execute(delete(CustomerAccount).where(CustomerAccount.id == other_customer.id))
        await db_session.execute(delete(LeadSource).where(LeadSource.lead_id == lead.id))
        await db_session.execute(delete(Lead).where(Lead.id == lead.id))
        await db_session.commit()


@pytest.mark.asyncio
async def test_existing_lead_sources_preserved_through_linking(client, fake_email, cleanup_customers, db_session):
    lead_email = unique_email("preserved")
    lead = Lead(full_name="Buyer With History", normalized_email=lead_email.lower())
    db_session.add(lead)
    await db_session.commit()

    original_source = LeadSource(
        lead_id=lead.id,
        source_type=SourceType.PROPERTY_PORTAL,
        campaign_name="Original Portal Campaign",
        raw_payload={"original": True},
        submitted_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(original_source)
    await db_session.commit()

    try:
        email, _, body = await _register_and_verify(client, fake_email, cleanup_customers, email=lead_email)
        assert body["lead_linked"] is True

        source_result = await db_session.execute(select(LeadSource).where(LeadSource.lead_id == lead.id))
        sources = {s.campaign_name for s in source_result.scalars().all()}
        assert "Original Portal Campaign" in sources
    finally:
        await db_session.execute(delete(LeadSource).where(LeadSource.lead_id == lead.id))
        await db_session.execute(delete(Lead).where(Lead.id == lead.id))
        await db_session.commit()


@pytest.mark.asyncio
async def test_concurrent_verification_requests_only_one_succeeds(client, fake_email, cleanup_customers):
    resp, email = await _register(client, fake_email, cleanup_customers)
    assert resp.status_code == 201
    token = fake_email.last_token()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c1, \
            AsyncClient(transport=transport, base_url="http://test") as c2:
        results = await asyncio.gather(
            c1.post("/api/v1/customer-auth/verify-email", json={"token": token}),
            c2.post("/api/v1/customer-auth/verify-email", json={"token": token}),
        )

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 422]
