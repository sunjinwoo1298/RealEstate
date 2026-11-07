import asyncio
import secrets
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

from backend.main import app
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.ai.groq_client import StructuredCompletion
from backend.ai.schemas import ExtractionResult, OrchestratorReply
from backend.models.conversation import Conversation, ConversationStatus, OwnershipStatus
from backend.models.conversation_assignment import AssignmentStatus, ConversationAssignment
from backend.models.handoff import Handoff, HandoffReason, HandoffStatus
from backend.models.lead import Lead, LeadStatus
from backend.models.lead_source import LeadSource
from backend.models.message import Message
from backend.models.notification import Notification
from backend.models.user import User, UserRole
from backend.services import ai_orchestrator_service as orchestrator_module

ADMIN_EMAIL = "test-handoff-admin@estateflow.ai"
MANAGER_EMAIL = "test-handoff-manager@estateflow.ai"
EXEC1_EMAIL = "test-handoff-exec1@estateflow.ai"
EXEC2_EMAIL = "test-handoff-exec2@estateflow.ai"
PASSWORD = "SuperSecret123!"

# Pinned (not auto-generated) so pick_eligible_executive's ORDER BY User.id
# ascending deterministically picks exec1 first in every test run.
EXEC1_ID = uuid.UUID("00000000-0000-4000-8000-000000000101")
EXEC2_ID = uuid.UUID("00000000-0000-4000-8000-000000000102")


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

    admin = User(email=ADMIN_EMAIL, full_name="Handoff Admin", password_hash=hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True)
    manager = User(email=MANAGER_EMAIL, full_name="Handoff Manager", password_hash=hash_password(PASSWORD), role=UserRole.MANAGER, is_active=True)
    exec1 = User(id=EXEC1_ID, email=EXEC1_EMAIL, full_name="Handoff Exec One", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    exec2 = User(id=EXEC2_ID, email=EXEC2_EMAIL, full_name="Handoff Exec Two", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    db_session.add_all([admin, manager, exec1, exec2])
    await db_session.commit()

    yield {"admin": admin, "manager": manager, "exec1": exec1, "exec2": exec2}

    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()


@pytest_asyncio.fixture
async def test_lead(db_session):
    lead = Lead(full_name="HandoffTest Buyer", normalized_phone=_unique_phone(), lead_status=LeadStatus.QUALIFIED)
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    yield lead


@pytest_asyncio.fixture
async def test_conversation(db_session, test_lead):
    conversation = Conversation(lead_id=test_lead.id, status=ConversationStatus.ACTIVE)
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    yield conversation


@pytest_asyncio.fixture(autouse=True)
async def cleanup(db_session):
    yield
    test_lead_ids_result = await db_session.execute(select(Lead.id).where(Lead.full_name.like("HandoffTest%")))
    test_lead_ids = [row[0] for row in test_lead_ids_result.all()]
    conversation_ids_result = await db_session.execute(
        select(Conversation.id).where(Conversation.lead_id.in_(test_lead_ids)) if test_lead_ids else select(Conversation.id).where(False)
    )
    conversation_ids = [row[0] for row in conversation_ids_result.all()]

    handoff_ids_result = await db_session.execute(
        select(Handoff.id).where(Handoff.conversation_id.in_(conversation_ids)) if conversation_ids else select(Handoff.id).where(False)
    )
    handoff_ids = [row[0] for row in handoff_ids_result.all()]

    if handoff_ids:
        await db_session.execute(delete(Notification).where(Notification.reference_id.in_(handoff_ids)))
    await db_session.execute(delete(ConversationAssignment).where(ConversationAssignment.conversation_id.in_(conversation_ids)) if conversation_ids else delete(ConversationAssignment).where(False))
    await db_session.execute(delete(Handoff).where(Handoff.conversation_id.in_(conversation_ids)) if conversation_ids else delete(Handoff).where(False))
    await db_session.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)) if conversation_ids else delete(Message).where(False))
    await db_session.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)) if conversation_ids else delete(Conversation).where(False))
    if test_lead_ids:
        await db_session.execute(delete(LeadSource).where(LeadSource.lead_id.in_(test_lead_ids)))
        await db_session.execute(delete(Lead).where(Lead.id.in_(test_lead_ids)))
    await db_session.commit()


async def _login(client, email):
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_buyer_chat_session(client):
    resp = await client.post(
        "/api/v1/chat/sessions",
        json={"full_name": "HandoffTest Chat Buyer", "phone": _unique_phone(), "preferred_language": "EN", "consent_given": True},
    )
    assert resp.status_code == 201
    return resp


def _completion(data) -> StructuredCompletion:
    return StructuredCompletion(data=data, latency_ms=10.0, prompt_tokens=5, completion_tokens=5)


def _mock_groq(monkeypatch, *, extraction: ExtractionResult, reply: OrchestratorReply):
    responses = [_completion(extraction), _completion(reply)]

    async def fake_generate_structured(*, system_prompt, messages, schema, temperature=0.2, max_tokens=1024):
        return responses.pop(0)

    monkeypatch.setattr(orchestrator_module.GroqClient, "generate_structured", fake_generate_structured)


@pytest.mark.asyncio
async def test_buyer_requested_handoff_auto_assigns_and_notifies(client, db_session, seeded_users, test_conversation):
    create_resp = await _create_buyer_chat_session(client)
    cookie_conversation_id = create_resp.json()["id"]
    cookie = create_resp.cookies.get("estateflow_buyer_session")
    client.cookies.set("estateflow_buyer_session", cookie)

    resp = await client.post(f"/api/v1/conversations/{cookie_conversation_id}/handoff", json={})
    assert resp.status_code == 201
    body = resp.json()
    assert body["reason"] == "BUYER_REQUEST"
    assert body["status"] == "ASSIGNED"
    assert body["assigned_executive_id"] == str(seeded_users["exec1"].id)

    conversation = await db_session.get(Conversation, uuid.UUID(cookie_conversation_id))
    await db_session.refresh(conversation)
    assert conversation.ownership_status == OwnershipStatus.PENDING_ASSIGNMENT

    notif_result = await db_session.execute(select(Notification).where(Notification.reference_id == uuid.UUID(body["id"])))
    notifications = notif_result.scalars().all()
    assert len(notifications) == 1
    assert notifications[0].recipient_id == seeded_users["exec1"].id

    # Cleanup this buyer-chat-created lead/conversation too.
    await db_session.execute(delete(Notification).where(Notification.reference_id == uuid.UUID(body["id"])))
    await db_session.execute(delete(ConversationAssignment).where(ConversationAssignment.handoff_id == uuid.UUID(body["id"])))
    await db_session.execute(delete(Handoff).where(Handoff.id == uuid.UUID(body["id"])))
    await db_session.execute(delete(Message).where(Message.conversation_id == uuid.UUID(cookie_conversation_id)))
    lead_id = create_resp.json()["lead_id"]
    await db_session.execute(delete(Conversation).where(Conversation.id == uuid.UUID(cookie_conversation_id)))
    await db_session.execute(delete(LeadSource).where(LeadSource.lead_id == uuid.UUID(lead_id)))
    await db_session.execute(delete(Lead).where(Lead.id == uuid.UUID(lead_id)))
    await db_session.commit()


@pytest.mark.asyncio
async def test_duplicate_handoff_request_is_idempotent(client, seeded_users, test_conversation):
    admin_headers = await _login(client, ADMIN_EMAIL)
    resp1 = await client.post(f"/api/v1/conversations/{test_conversation.id}/handoff", json={}, headers=admin_headers)
    assert resp1.status_code == 201
    resp2 = await client.post(f"/api/v1/conversations/{test_conversation.id}/handoff", json={}, headers=admin_headers)
    assert resp2.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]

    headers = await _login(client, EXEC1_EMAIL)
    list_resp = await client.get("/api/v1/handoffs", params={"mine": "true"}, headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_ai_triggered_escalation_creates_assigned_handoff(client, db_session, seeded_users, monkeypatch):
    create_resp = await _create_buyer_chat_session(client)
    conversation_id = create_resp.json()["id"]
    cookie = create_resp.cookies.get("estateflow_buyer_session")
    client.cookies.set("estateflow_buyer_session", cookie)

    _mock_groq(
        monkeypatch,
        extraction=ExtractionResult(detected_language="EN", intent="HUMAN_HANDOFF_REQUEST", wants_human_handoff=True),
        reply=OrchestratorReply(reply_text="Sure, connecting you now.", language="EN"),
    )
    resp = await client.post(f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": "I want to talk to a human"})
    assert resp.status_code == 201

    result = await db_session.execute(select(Handoff).where(Handoff.conversation_id == uuid.UUID(conversation_id)))
    handoff = result.scalar_one()
    assert handoff.reason == HandoffReason.BUYER_REQUEST
    assert handoff.status == HandoffStatus.ASSIGNED
    assert handoff.summary and "Buyer:" in handoff.summary

    # Sending a second buyer message must not create a second handoff --
    # the AI is no longer AI_ACTIVE, so the orchestrator skips entirely.
    resp2 = await client.post(f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": "hello again"})
    assert resp2.status_code == 201
    count_result = await db_session.execute(select(Handoff).where(Handoff.conversation_id == uuid.UUID(conversation_id)))
    assert len(count_result.scalars().all()) == 1

    messages_result = await db_session.execute(select(Message).where(Message.conversation_id == uuid.UUID(conversation_id)))
    messages = messages_result.scalars().all()
    ai_messages = [m for m in messages if m.sender_type.value == "AI"]
    assert len(ai_messages) == 1  # no second AI reply once ownership left AI_ACTIVE

    lead_id = create_resp.json()["lead_id"]
    await db_session.execute(delete(Notification).where(Notification.reference_id == handoff.id))
    await db_session.execute(delete(ConversationAssignment).where(ConversationAssignment.handoff_id == handoff.id))
    await db_session.execute(delete(Handoff).where(Handoff.id == handoff.id))
    await db_session.execute(delete(Message).where(Message.conversation_id == uuid.UUID(conversation_id)))
    await db_session.execute(delete(Conversation).where(Conversation.id == uuid.UUID(conversation_id)))
    await db_session.execute(delete(LeadSource).where(LeadSource.lead_id == uuid.UUID(lead_id)))
    await db_session.execute(delete(Lead).where(Lead.id == uuid.UUID(lead_id)))
    await db_session.commit()


@pytest.mark.asyncio
async def test_accept_workflow_sets_human_active(client, db_session, seeded_users, test_conversation):
    admin_headers = await _login(client, ADMIN_EMAIL)
    resp = await client.post(f"/api/v1/conversations/{test_conversation.id}/handoff", json={}, headers=admin_headers)
    handoff_id = resp.json()["id"]

    headers1 = await _login(client, EXEC1_EMAIL)
    accept_resp = await client.post(f"/api/v1/handoffs/{handoff_id}/accept", headers=headers1)
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "ACCEPTED"

    conversation = await db_session.get(Conversation, test_conversation.id)
    await db_session.refresh(conversation)
    assert conversation.ownership_status == OwnershipStatus.HUMAN_ACTIVE


@pytest.mark.asyncio
async def test_non_assigned_executive_cannot_accept(client, seeded_users, test_conversation):
    admin_headers = await _login(client, ADMIN_EMAIL)
    resp = await client.post(f"/api/v1/conversations/{test_conversation.id}/handoff", json={}, headers=admin_headers)
    handoff_id = resp.json()["id"]

    headers2 = await _login(client, EXEC2_EMAIL)
    accept_resp = await client.post(f"/api/v1/handoffs/{handoff_id}/accept", headers=headers2)
    assert accept_resp.status_code == 403


@pytest.mark.asyncio
async def test_reject_reassigns_to_next_eligible_executive(client, db_session, seeded_users, test_conversation):
    admin_headers = await _login(client, ADMIN_EMAIL)
    resp = await client.post(f"/api/v1/conversations/{test_conversation.id}/handoff", json={}, headers=admin_headers)
    handoff_id = resp.json()["id"]
    assert resp.json()["assigned_executive_id"] == str(seeded_users["exec1"].id)

    headers1 = await _login(client, EXEC1_EMAIL)
    reject_resp = await client.post(f"/api/v1/handoffs/{handoff_id}/reject", json={"reason": "too busy"}, headers=headers1)
    assert reject_resp.status_code == 200
    assert reject_resp.json()["assigned_executive_id"] == str(seeded_users["exec2"].id)
    assert reject_resp.json()["status"] == "ASSIGNED"
    assert "too busy" in reject_resp.json()["summary"]

    assignments_result = await db_session.execute(
        select(ConversationAssignment).where(ConversationAssignment.handoff_id == uuid.UUID(handoff_id))
    )
    assignments = assignments_result.scalars().all()
    assert len(assignments) == 2
    rejected = [a for a in assignments if a.status == AssignmentStatus.REJECTED]
    assert len(rejected) == 1
    assert rejected[0].executive_id == seeded_users["exec1"].id


@pytest.mark.asyncio
async def test_manager_can_reassign_handoff(client, seeded_users, test_conversation):
    admin_headers = await _login(client, ADMIN_EMAIL)
    resp = await client.post(f"/api/v1/conversations/{test_conversation.id}/handoff", json={}, headers=admin_headers)
    handoff_id = resp.json()["id"]

    headers_mgr = await _login(client, MANAGER_EMAIL)
    reassign_resp = await client.post(
        f"/api/v1/handoffs/{handoff_id}/reassign", json={"executive_id": str(seeded_users["exec2"].id)}, headers=headers_mgr
    )
    assert reassign_resp.status_code == 200
    assert reassign_resp.json()["assigned_executive_id"] == str(seeded_users["exec2"].id)

    headers_exec1 = await _login(client, EXEC1_EMAIL)
    forbidden_resp = await client.post(
        f"/api/v1/handoffs/{handoff_id}/reassign", json={"executive_id": str(seeded_users["exec1"].id)}, headers=headers_exec1
    )
    assert forbidden_resp.status_code == 403


@pytest.mark.asyncio
async def test_resolve_handoff_and_authorized_return_to_ai(client, db_session, seeded_users, test_conversation):
    admin_headers = await _login(client, ADMIN_EMAIL)
    resp = await client.post(f"/api/v1/conversations/{test_conversation.id}/handoff", json={}, headers=admin_headers)
    handoff_id = resp.json()["id"]
    headers1 = await _login(client, EXEC1_EMAIL)
    await client.post(f"/api/v1/handoffs/{handoff_id}/accept", headers=headers1)

    resolve_resp = await client.post(f"/api/v1/handoffs/{handoff_id}/resolve", headers=headers1)
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["status"] == "RESOLVED"

    conversation = await db_session.get(Conversation, test_conversation.id)
    await db_session.refresh(conversation)
    assert conversation.ownership_status == OwnershipStatus.RESOLVED

    # A random sales executive may not unilaterally resume AI ownership...
    headers2 = await _login(client, EXEC2_EMAIL)
    denied = await client.post(
        f"/api/v1/conversations/{test_conversation.id}/ownership", json={"ownership_status": "AI_ACTIVE"}, headers=headers2
    )
    assert denied.status_code == 403

    # ...but a manager's explicit, authorized transition is allowed.
    headers_mgr = await _login(client, MANAGER_EMAIL)
    allowed = await client.post(
        f"/api/v1/conversations/{test_conversation.id}/ownership", json={"ownership_status": "AI_ACTIVE"}, headers=headers_mgr
    )
    assert allowed.status_code == 200
    assert allowed.json()["ownership_status"] == "AI_ACTIVE"


@pytest.mark.asyncio
async def test_concurrent_accept_only_one_succeeds(client, seeded_users, test_conversation):
    admin_headers = await _login(client, ADMIN_EMAIL)
    resp = await client.post(f"/api/v1/conversations/{test_conversation.id}/handoff", json={}, headers=admin_headers)
    handoff_id = resp.json()["id"]
    headers1 = await _login(client, EXEC1_EMAIL)

    results = await asyncio.gather(
        client.post(f"/api/v1/handoffs/{handoff_id}/accept", headers=headers1),
        client.post(f"/api/v1/handoffs/{handoff_id}/accept", headers=headers1),
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409]


@pytest.mark.asyncio
async def test_staff_reply_requires_human_active_and_assignment(client, db_session, seeded_users, test_conversation):
    admin_headers = await _login(client, ADMIN_EMAIL)
    resp = await client.post(f"/api/v1/conversations/{test_conversation.id}/handoff", json={}, headers=admin_headers)
    handoff_id = resp.json()["id"]
    headers1 = await _login(client, EXEC1_EMAIL)
    headers2 = await _login(client, EXEC2_EMAIL)

    # Not yet HUMAN_ACTIVE (still ASSIGNED, not accepted) -> rejected even for the assigned exec.
    too_early = await client.post(
        f"/api/v1/conversations/{test_conversation.id}/messages", json={"content": "Hi, this is Raj from sales"}, headers=headers1
    )
    assert too_early.status_code == 403

    await client.post(f"/api/v1/handoffs/{handoff_id}/accept", headers=headers1)

    wrong_exec = await client.post(
        f"/api/v1/conversations/{test_conversation.id}/messages", json={"content": "Hi there"}, headers=headers2
    )
    assert wrong_exec.status_code == 403

    ok = await client.post(
        f"/api/v1/conversations/{test_conversation.id}/messages", json={"content": "Hi, this is Raj from sales"}, headers=headers1
    )
    assert ok.status_code == 201
    assert ok.json()["sender_type"] == "STAFF"
