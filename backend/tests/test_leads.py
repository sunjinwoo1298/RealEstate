import asyncio
import hashlib
import hmac
import json
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from backend.main import app
from backend.core.config import settings
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.models.auth_session import AuthSession
from backend.models.lead import Lead
from backend.models.lead_source import LeadSource
from backend.models.potential_duplicate import PotentialDuplicateMatch
from backend.models.user import User, UserRole
from backend.models.webhook_event import WebhookEvent

ADMIN_EMAIL = "test-leads-admin@estateflow.ai"
MANAGER_EMAIL = "test-leads-manager@estateflow.ai"
EXEC_EMAIL = "test-leads-exec@estateflow.ai"
PASSWORD = "SuperSecret123!"

WEBSITE_SECRET = settings.webhook_source_secrets_map["WEBSITE"]


@pytest_asyncio.fixture
async def db_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_users(db_session):
    emails = [ADMIN_EMAIL, MANAGER_EMAIL, EXEC_EMAIL]
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()

    admin = User(email=ADMIN_EMAIL, full_name="Leads Admin", password_hash=hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True)
    manager = User(email=MANAGER_EMAIL, full_name="Leads Manager", password_hash=hash_password(PASSWORD), role=UserRole.MANAGER, is_active=True)
    exec_user = User(email=EXEC_EMAIL, full_name="Leads Exec", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    db_session.add_all([admin, manager, exec_user])
    await db_session.commit()

    yield {"admin": admin, "manager": manager, "exec": exec_user}

    await db_session.execute(delete(AuthSession).where(AuthSession.user_id.in_([admin.id, manager.id, exec_user.id])))
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _login(client, email):
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture(autouse=True)
async def cleanup_leads(db_session):
    yield
    await db_session.execute(delete(PotentialDuplicateMatch))
    await db_session.execute(delete(WebhookEvent))
    await db_session.execute(delete(LeadSource))
    await db_session.execute(delete(Lead))
    await db_session.commit()


def _sign(body: bytes, secret: str = WEBSITE_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_manual_lead_creation(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    resp = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={"full_name": "Ramesh Kumar", "phone": "9876543210", "email": "ramesh@example.com"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["created_new_lead"] is True
    assert data["match_reason"] == "NEW_BUYER"


@pytest.mark.asyncio
async def test_existing_buyer_matched_by_phone(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    first = await client.post(
        "/api/v1/leads", headers=headers, json={"full_name": "Suresh Mehta", "phone": "9123456780"}
    )
    second = await client.post(
        "/api/v1/leads", headers=headers, json={"full_name": "Suresh M.", "phone": "+919123456780"}
    )
    assert first.status_code == 201 and second.status_code == 201
    assert second.json()["match_reason"] == "EXACT_PHONE"
    assert second.json()["lead_id"] == first.json()["lead_id"]


@pytest.mark.asyncio
async def test_existing_buyer_matched_by_email(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    first = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={"full_name": "Priya Nair", "phone": "9000000001", "email": "Priya@Example.com"},
    )
    second = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={"full_name": "Priya Nair", "phone": "9000000002", "email": "priya@example.com"},
    )
    assert second.json()["match_reason"] == "EXACT_EMAIL"
    assert second.json()["lead_id"] == first.json()["lead_id"]


@pytest.mark.asyncio
async def test_invalid_phone_rejected(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    resp = await client.post("/api/v1/leads", headers=headers, json={"full_name": "Bad Phone", "phone": "123"})
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_invalid_email_rejected(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    resp = await client.post(
        "/api/v1/leads", headers=headers, json={"full_name": "Bad Email", "phone": "9876500000", "email": "not-an-email"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_similar_names_different_identities_no_merge(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    first = await client.post("/api/v1/leads", headers=headers, json={"full_name": "Hardik Patel", "phone": "9111111111"})
    second = await client.post("/api/v1/leads", headers=headers, json={"full_name": "Nidhi Shah", "phone": "9222222222"})
    assert first.json()["lead_id"] != second.json()["lead_id"]
    assert second.json()["match_reason"] == "NEW_BUYER"


@pytest.mark.asyncio
async def test_ambiguous_name_similarity_creates_duplicate_review(client, seeded_users):
    headers = await _login(client, MANAGER_EMAIL)
    first = await client.post("/api/v1/leads", headers=headers, json={"full_name": "Rajesh Kumar Shah", "phone": "9333333331"})
    second = await client.post("/api/v1/leads", headers=headers, json={"full_name": "Rajesh Kumar Shaha", "phone": "9333333332"})
    assert first.json()["lead_id"] != second.json()["lead_id"]

    dup_resp = await client.get("/api/v1/leads/duplicates", headers=headers)
    assert dup_resp.status_code == 200
    items = dup_resp.json()["items"]
    assert any(item["new_lead_id"] == second.json()["lead_id"] for item in items)

    match_id = next(item["id"] for item in items if item["new_lead_id"] == second.json()["lead_id"])
    review_resp = await client.patch(
        f"/api/v1/leads/duplicates/{match_id}", headers=headers, json={"status": "REJECTED"}
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_multiple_sources_linked_to_one_buyer(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    first = await client.post("/api/v1/leads", headers=headers, json={"full_name": "Anita Rao", "phone": "9444444444"})
    lead_id = first.json()["lead_id"]

    body = json.dumps({"full_name": "Anita Rao", "phone": "9444444444", "external_lead_id": "EXT-1"}).encode()
    webhook_resp = await client.post(
        "/api/v1/leads/webhooks/website",
        headers={"X-Webhook-Signature": _sign(body)},
        content=body,
    )
    assert webhook_resp.status_code == 201
    assert webhook_resp.json()["lead_id"] == lead_id

    sources_resp = await client.get(f"/api/v1/leads/{lead_id}/sources", headers=headers)
    assert sources_resp.status_code == 200
    assert len(sources_resp.json()) == 2


@pytest.mark.asyncio
async def test_webhook_requires_valid_signature(client):
    body = json.dumps({"full_name": "No Sig", "phone": "9555555555"}).encode()
    resp = await client.post("/api/v1/leads/webhooks/website", content=body)
    assert resp.status_code == 401

    bad_sig_resp = await client.post(
        "/api/v1/leads/webhooks/website", headers={"X-Webhook-Signature": "deadbeef"}, content=body
    )
    assert bad_sig_resp.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_webhook_submission_is_idempotent(client):
    body = json.dumps({"full_name": "Webhook Buyer", "phone": "9666666666"}).encode()
    headers = {"X-Webhook-Signature": _sign(body), "Idempotency-Key": "fixed-key-123"}

    first_resp = await client.post("/api/v1/leads/webhooks/website", headers=headers, content=body)
    assert first_resp.status_code == 201
    second_resp = await client.post("/api/v1/leads/webhooks/website", headers=headers, content=body)
    assert second_resp.status_code == 201
    assert second_resp.json()["idempotent_replay"] is True
    assert second_resp.json()["lead_id"] == first_resp.json()["lead_id"]

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(delete(LeadSource))
        await session.commit()


@pytest.mark.asyncio
async def test_concurrent_duplicate_ingestion_resolves_to_one_lead(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    payload = {"full_name": "Concurrent Buyer", "phone": "9777777777"}
    results = await asyncio.gather(
        client.post("/api/v1/leads", headers=headers, json=payload),
        client.post("/api/v1/leads", headers=headers, json=payload),
    )
    assert all(r.status_code == 201 for r in results)
    lead_ids = {r.json()["lead_id"] for r in results}
    assert len(lead_ids) == 1


@pytest.mark.asyncio
async def test_csv_import_validation_and_partial_failure(client, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    csv_content = (
        "full_name,phone,email\n"
        "Good Row,9888800001,good@example.com\n"
        ",9888800002,missing-name@example.com\n"
        "Another Good,9888800003,\n"
    )
    files = {"file": ("leads.csv", csv_content, "text/csv")}
    resp = await client.post("/api/v1/leads/import", headers=headers, files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 3
    assert data["created"] == 2
    assert data["failed"] == 1


@pytest.mark.asyncio
async def test_csv_import_rejects_non_csv_file(client, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    files = {"file": ("leads.txt", "full_name,phone\nA,9000000000\n", "text/plain")}
    resp = await client.post("/api/v1/leads/import", headers=headers, files=files)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_csv_import_requires_manager_or_admin(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    files = {"file": ("leads.csv", "full_name,phone\nA,9000000000\n", "text/csv")}
    resp = await client.post("/api/v1/leads/import", headers=headers, files=files)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_role_based_api_permissions(client, seeded_users):
    headers_exec = await _login(client, EXEC_EMAIL)
    resp = await client.get("/api/v1/leads/duplicates", headers=headers_exec)
    assert resp.status_code == 403

    unauth_resp = await client.get("/api/v1/leads")
    assert unauth_resp.status_code == 401


@pytest.mark.asyncio
async def test_lead_listing_filtering_and_pagination(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    for i in range(3):
        await client.post("/api/v1/leads", headers=headers, json={"full_name": f"Pager Buyer {i}", "phone": f"970000000{i}"})

    resp = await client.get("/api/v1/leads", headers=headers, params={"limit": 2, "offset": 0, "search": "Pager"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 3


@pytest.mark.asyncio
async def test_lead_detail_and_update_include_sources(client, seeded_users):
    """
    Regression (E2E BUG-1): GET/PATCH /leads/{id} returned 500 (MissingGreenlet)
    because the response was validated straight from the ORM Lead, lazily
    loading Lead.sources outside the async greenlet.
    """
    headers = await _login(client, ADMIN_EMAIL)
    created = await client.post(
        "/api/v1/leads", headers=headers, json={"full_name": "Detail Buyer", "phone": "9555555551", "email": "Detail@Example.com"}
    )
    lead_id = created.json()["lead_id"]
    await client.post("/api/v1/leads", headers=headers, json={"full_name": "Detail Buyer", "phone": "+91 95555 55551"})

    detail = await client.get(f"/api/v1/leads/{lead_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["normalized_phone"] == "+919555555551"
    assert body["normalized_email"] == "detail@example.com"
    assert len(body["sources"]) == 2

    updated = await client.patch(f"/api/v1/leads/{lead_id}", headers=headers, json={"lead_status": "QUALIFIED"})
    assert updated.status_code == 200
    assert updated.json()["lead_status"] == "QUALIFIED"
    assert len(updated.json()["sources"]) == 2


async def _user_id(email):
    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import select as _select
        return (await session.execute(_select(User.id).where(User.email == email))).scalar_one()


@pytest.mark.asyncio
async def test_sales_executive_only_sees_and_manages_assigned_leads(client, seeded_users):
    """Spec 01/08 (E2E BUG-7): executives are limited to leads assigned to them."""
    admin = await _login(client, ADMIN_EMAIL)
    manager = await _login(client, MANAGER_EMAIL)
    exec_headers = await _login(client, EXEC_EMAIL)
    exec_id = str(await _user_id(EXEC_EMAIL))
    admin_id = str(await _user_id(ADMIN_EMAIL))

    unassigned = (await client.post("/api/v1/leads", headers=admin, json={"full_name": "Scope Unassigned", "phone": "9666666601"})).json()["lead_id"]
    assigned = (await client.post("/api/v1/leads", headers=admin, json={"full_name": "Scope Assigned", "phone": "9666666602"})).json()["lead_id"]
    resp = await client.patch(f"/api/v1/leads/{assigned}", headers=manager, json={"assigned_executive_id": exec_id})
    assert resp.status_code == 200

    # list: only the assigned lead, even when asking for another executive's leads
    listed = await client.get("/api/v1/leads", headers=exec_headers, params={"search": "Scope", "assigned_executive_id": admin_id})
    assert listed.status_code == 200
    assert [i["id"] for i in listed.json()["items"]] == [assigned]
    # the "new" counter shares the executive's scope (E2E round 4: it counted every NEW lead)
    assert listed.json()["new_count"] == 1
    assert len((await client.get("/api/v1/leads", headers=manager, params={"search": "Scope"})).json()["items"]) == 2

    # detail / sources / update of a lead not assigned to the executive
    assert (await client.get(f"/api/v1/leads/{unassigned}", headers=exec_headers)).status_code == 403
    assert (await client.get(f"/api/v1/leads/{unassigned}/sources", headers=exec_headers)).status_code == 403
    assert (await client.patch(f"/api/v1/leads/{unassigned}", headers=exec_headers, json={"assigned_executive_id": exec_id})).status_code == 403

    # own lead: may read and update status, but may not reassign it
    assert (await client.get(f"/api/v1/leads/{assigned}", headers=exec_headers)).status_code == 200
    ok = await client.patch(f"/api/v1/leads/{assigned}", headers=exec_headers, json={"lead_status": "QUALIFIED"})
    assert ok.status_code == 200 and ok.json()["lead_status"] == "QUALIFIED"
    reassign = await client.patch(f"/api/v1/leads/{assigned}", headers=exec_headers, json={"assigned_executive_id": admin_id})
    assert reassign.status_code == 403
    assert (await client.get(f"/api/v1/leads/{assigned}", headers=manager)).json()["assigned_executive_id"] == exec_id


@pytest.mark.asyncio
async def test_new_manual_lead_from_executive_is_assigned_to_them(client, seeded_users):
    exec_headers = await _login(client, EXEC_EMAIL)
    exec_id = str(await _user_id(EXEC_EMAIL))
    created = await client.post("/api/v1/leads", headers=exec_headers, json={"full_name": "Walk In Buyer", "phone": "9666666603"})
    assert created.status_code == 201
    detail = await client.get(f"/api/v1/leads/{created.json()['lead_id']}", headers=exec_headers)
    assert detail.status_code == 200
    assert detail.json()["assigned_executive_id"] == exec_id


# --- first contact + flagged chats (client brief, round 5) -------------------------------------


async def _conversations_for_lead(db_session, lead_id):
    from sqlalchemy import select
    from backend.models.conversation import Conversation
    from backend.models.message import Message

    conversations = (await db_session.execute(select(Conversation).where(Conversation.lead_id == uuid.UUID(lead_id)))).scalars().all()
    messages = []
    for conversation in conversations:
        messages += (await db_session.execute(select(Message).where(Message.conversation_id == conversation.id))).scalars().all()
    return conversations, messages


async def _purge_conversations(db_session):
    from backend.models.conversation import Conversation
    from backend.models.message import Message

    await db_session.execute(delete(Message))
    await db_session.execute(delete(Conversation))
    await db_session.commit()


@pytest.mark.asyncio
async def test_portal_enquiry_is_contacted_immediately_once(client, db_session):
    body = json.dumps({"full_name": "Hardik Patel", "phone": "9444455501", "external_lead_id": "FC-1"}).encode()
    resp = await client.post("/api/v1/leads/webhooks/website", headers={"X-Webhook-Signature": _sign(body)}, content=body)
    assert resp.status_code == 201
    lead_id = resp.json()["lead_id"]
    try:
        conversations, messages = await _conversations_for_lead(db_session, lead_id)
        assert len(conversations) == 1 and len(messages) == 1
        assert messages[0].extra_metadata["first_contact"] is True
        assert "Hardik" in messages[0].content and "STOP" in messages[0].content
        lead = await db_session.get(Lead, uuid.UUID(lead_id))
        await db_session.refresh(lead)
        assert lead.lead_status.value == "AI_CONTACTED"

        # a second enquiry from the same buyer must not be greeted again
        body2 = json.dumps({"full_name": "Hardik Patel", "phone": "9444455501", "external_lead_id": "FC-2"}).encode()
        again = await client.post("/api/v1/leads/webhooks/website", headers={"X-Webhook-Signature": _sign(body2)}, content=body2)
        assert again.status_code == 201
        _, messages_after = await _conversations_for_lead(db_session, lead_id)
        assert len(messages_after) == 1
    finally:
        await _purge_conversations(db_session)


@pytest.mark.asyncio
async def test_no_first_contact_without_consent_or_contact_details(client, db_session):
    declined = json.dumps({"full_name": "No Consent", "phone": "9444455502", "consent_status": "DECLINED"}).encode()
    r1 = await client.post("/api/v1/leads/webhooks/website", headers={"X-Webhook-Signature": _sign(declined)}, content=declined)
    assert r1.status_code == 201
    try:
        _, messages = await _conversations_for_lead(db_session, r1.json()["lead_id"])
        assert messages == []
    finally:
        await _purge_conversations(db_session)


@pytest.mark.asyncio
async def test_flagged_chats_are_for_admin_and_manager_only(client, db_session, seeded_users):
    from backend.models.conversation import ChannelType, Conversation, ConversationLanguage, ConversationState, ConversationStatus
    from backend.models.message import Message, MessageType, SenderType

    lead = Lead(full_name="Flag Buyer", normalized_phone="+919444455503")
    db_session.add(lead)
    await db_session.flush()
    conversation = Conversation(
        lead_id=lead.id, channel=ChannelType.WEB_CHAT, status=ConversationStatus.ACTIVE,
        language=ConversationLanguage.EN, conversation_state=ConversationState.DISCOVERY,
    )
    db_session.add(conversation)
    await db_session.flush()
    db_session.add(Message(
        conversation_id=conversation.id, sender_type=SenderType.AI, content="I cannot quote prices.", message_type=MessageType.TEXT,
        extra_metadata={"guardrail_flags": {"pricing_or_discount_requested": True, "complaint_detected": True}},
    ))
    clean = Conversation(
        lead_id=lead.id, channel=ChannelType.WEB_CHAT, status=ConversationStatus.ACTIVE,
        language=ConversationLanguage.EN, conversation_state=ConversationState.DISCOVERY,
    )
    db_session.add(clean)
    await db_session.flush()
    db_session.add(Message(conversation_id=clean.id, sender_type=SenderType.AI, content="Hello", message_type=MessageType.TEXT,
                           extra_metadata={"guardrail_flags": {"pricing_or_discount_requested": False}}))
    await db_session.commit()
    try:
        manager = await _login(client, MANAGER_EMAIL)
        listed = await client.get("/api/v1/conversations", headers=manager, params={"flagged": "true"})
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert [i["id"] for i in items] == [str(conversation.id)]  # the unflagged chat is not listed
        assert set(items[0]["flag_reasons"]) == {"Price or discount ask", "Complaint"}

        exec_headers = await _login(client, EXEC_EMAIL)
        denied = await client.get("/api/v1/conversations", headers=exec_headers, params={"flagged": "true"})
        assert denied.status_code == 403

        yesterday = await client.get("/api/v1/conversations", headers=manager, params={"flagged": "true", "flagged_date": "2000-01-01"})
        assert yesterday.json()["total"] == 0
    finally:
        await _purge_conversations(db_session)
