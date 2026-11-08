import re
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

from backend.main import app
from backend.ai.groq_client import StructuredCompletion
from backend.ai.schemas import ExtractionResult, OrchestratorReply
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.models.auth_session import AuthSession
from backend.models.conversation import Conversation, OwnershipStatus
from backend.models.conversation_assignment import ConversationAssignment
from backend.models.customer_account import CustomerAccount, CustomerAccountStatus
from backend.models.customer_session import CustomerSession
from backend.models.customer_verification_token import CustomerVerificationToken
from backend.models.handoff import Handoff
from backend.models.lead import Lead
from backend.models.message import Message
from backend.models.user import User, UserRole
from backend.services import ai_orchestrator_service as orchestrator_module
import backend.api.v1.endpoints.customer_auth as customer_auth_endpoints

PASSWORD = "SuperSecret123!"
TEST_EMAIL_DOMAIN = "test-customer-chat.estateflow.ai"


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
            lead_ids_result = await db_session.execute(
                select(CustomerAccount.lead_id).where(CustomerAccount.id.in_(ids))
            )
            lead_ids = [row[0] for row in lead_ids_result.all() if row[0] is not None]

            conv_ids_result = await db_session.execute(
                select(Conversation.id).where(Conversation.customer_account_id.in_(ids))
            )
            conv_ids = [row[0] for row in conv_ids_result.all()]
            if conv_ids:
                handoff_ids_result = await db_session.execute(
                    select(Handoff.id).where(Handoff.conversation_id.in_(conv_ids))
                )
                handoff_ids = [row[0] for row in handoff_ids_result.all()]
                if handoff_ids:
                    await db_session.execute(
                        delete(ConversationAssignment).where(ConversationAssignment.handoff_id.in_(handoff_ids))
                    )
                    await db_session.execute(delete(Handoff).where(Handoff.id.in_(handoff_ids)))
                await db_session.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
                await db_session.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))

            await db_session.execute(delete(CustomerSession).where(CustomerSession.customer_account_id.in_(ids)))
            await db_session.execute(
                delete(CustomerVerificationToken).where(CustomerVerificationToken.customer_account_id.in_(ids))
            )
            await db_session.execute(delete(CustomerAccount).where(CustomerAccount.id.in_(ids)))
            if lead_ids:
                await db_session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
            await db_session.commit()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register_login_verify(client, fake_email, cleanup_customers, *, email=None):
    email = email or unique_email("chat")
    cleanup_customers.append(email.lower())
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


def _completion(data, latency_ms: float = 5.0, prompt_tokens: int = 5, completion_tokens: int = 5) -> StructuredCompletion:
    return StructuredCompletion(
        data=data, latency_ms=latency_ms, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )


def _mock_ai_reply(monkeypatch, *, reply_text: str = "Thanks for reaching out! How can I help you today?") -> None:
    responses = [
        _completion(ExtractionResult(detected_language="EN", intent="OTHER")),
        _completion(OrchestratorReply(reply_text=reply_text, language="EN")),
    ]

    async def fake_generate_structured(*, system_prompt, messages, schema, temperature=0.2, max_tokens=1024):
        return responses.pop(0)

    monkeypatch.setattr(orchestrator_module.GroqClient, "generate_structured", fake_generate_structured)


def _disable_ai_orchestrator(monkeypatch) -> None:
    async def fake_handle_buyer_message(db, conversation, lead, buyer_message_text):
        return orchestrator_module.OrchestratorResult(ai_message=None, skipped_reason="TEST_DISABLED")

    monkeypatch.setattr(orchestrator_module.AIOrchestratorService, "handle_buyer_message", fake_handle_buyer_message)


async def _create_conversation(client, access_token):
    resp = await client.post("/api/v1/customer/conversations", headers=auth_headers(access_token))
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- POST /customer/conversations ---


@pytest.mark.asyncio
async def test_customer_can_create_conversation(client, fake_email, cleanup_customers, db_session):
    email, access_token = await _register_login_verify(client, fake_email, cleanup_customers)
    conversation = await _create_conversation(client, access_token)

    assert conversation["ownership_status"] == "AI_ACTIVE"
    assert conversation["conversation_state"] == "DISCOVERY"
    assert conversation["status"] == "ACTIVE"

    result = await db_session.execute(
        select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower())
    )
    customer = result.scalar_one()

    conv_result = await db_session.execute(select(Conversation).where(Conversation.id == uuid.UUID(conversation["id"])))
    conv = conv_result.scalar_one()
    assert conv.customer_account_id == customer.id
    assert conv.lead_id == customer.lead_id


@pytest.mark.asyncio
async def test_create_conversation_without_linked_lead_rejected(client, fake_email, cleanup_customers, db_session):
    email, access_token = await _register_login_verify(client, fake_email, cleanup_customers)
    result = await db_session.execute(
        select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower())
    )
    customer = result.scalar_one()
    customer.lead_id = None
    await db_session.commit()

    resp = await client.post("/api/v1/customer/conversations", headers=auth_headers(access_token))
    assert resp.status_code == 422


# --- GET /customer/conversations ---


@pytest.mark.asyncio
async def test_customer_lists_only_own_conversations(client, fake_email, cleanup_customers, monkeypatch):
    _disable_ai_orchestrator(monkeypatch)
    _, token_a = await _register_login_verify(client, fake_email, cleanup_customers)
    _, token_b = await _register_login_verify(client, fake_email, cleanup_customers)

    conv_a = await _create_conversation(client, token_a)
    await _create_conversation(client, token_b)

    resp = await client.get("/api/v1/customer/conversations", headers=auth_headers(token_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == conv_a["id"]


@pytest.mark.asyncio
async def test_customer_can_have_multiple_conversations(client, fake_email, cleanup_customers, monkeypatch):
    _disable_ai_orchestrator(monkeypatch)
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    await _create_conversation(client, token)
    await _create_conversation(client, token)

    resp = await client.get("/api/v1/customer/conversations", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


# --- GET /customer/conversations/{id} ---


@pytest.mark.asyncio
async def test_customer_cannot_retrieve_another_customers_conversation(client, fake_email, cleanup_customers):
    _, token_a = await _register_login_verify(client, fake_email, cleanup_customers)
    _, token_b = await _register_login_verify(client, fake_email, cleanup_customers)

    conv_b = await _create_conversation(client, token_b)

    resp = await client.get(f"/api/v1/customer/conversations/{conv_b['id']}", headers=auth_headers(token_a))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_customer_cannot_retrieve_another_customers_messages(client, fake_email, cleanup_customers, monkeypatch):
    _mock_ai_reply(monkeypatch)
    _, token_a = await _register_login_verify(client, fake_email, cleanup_customers)
    _, token_b = await _register_login_verify(client, fake_email, cleanup_customers)

    conv_b = await _create_conversation(client, token_b)
    send_resp = await client.post(
        f"/api/v1/customer/conversations/{conv_b['id']}/messages",
        json={"content": "Hello, tell me about 2 BHK options."},
        headers=auth_headers(token_b),
    )
    assert send_resp.status_code == 201

    resp = await client.get(f"/api/v1/customer/conversations/{conv_b['id']}/messages", headers=auth_headers(token_a))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nonexistent_conversation_returns_404(client, fake_email, cleanup_customers):
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    resp = await client.get(f"/api/v1/customer/conversations/{uuid.uuid4()}", headers=auth_headers(token))
    assert resp.status_code == 404


# --- POST /customer/conversations/{id}/messages ---


@pytest.mark.asyncio
async def test_customer_can_send_message_to_ai_active_conversation(client, fake_email, cleanup_customers, monkeypatch):
    _mock_ai_reply(monkeypatch, reply_text="Sure, we have great 2 BHK and 3 BHK options.")
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    conversation = await _create_conversation(client, token)

    resp = await client.post(
        f"/api/v1/customer/conversations/{conversation['id']}/messages",
        json={"content": "Tell me about 2 BHK configurations"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["sender_type"] == "BUYER"

    messages_resp = await client.get(
        f"/api/v1/customer/conversations/{conversation['id']}/messages", headers=auth_headers(token)
    )
    body = messages_resp.json()
    assert body["total"] == 2
    assert body["items"][0]["sender_type"] == "BUYER"
    assert body["items"][1]["sender_type"] == "AI"
    assert body["items"][1]["content"] == "Sure, we have great 2 BHK and 3 BHK options."
    # Internal AI diagnostics must never reach the customer.
    assert "metadata" not in body["items"][1]


@pytest.mark.asyncio
async def test_customer_cannot_spoof_sender_role(client, fake_email, cleanup_customers, monkeypatch):
    _disable_ai_orchestrator(monkeypatch)
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    conversation = await _create_conversation(client, token)

    resp = await client.post(
        f"/api/v1/customer/conversations/{conversation['id']}/messages",
        json={"content": "hello", "sender_type": "STAFF", "sender_id": str(uuid.uuid4())},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["sender_type"] == "BUYER"


@pytest.mark.asyncio
async def test_empty_message_rejected(client, fake_email, cleanup_customers):
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    conversation = await _create_conversation(client, token)

    resp = await client.post(
        f"/api/v1/customer/conversations/{conversation['id']}/messages",
        json={"content": ""},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ai_not_invoked_during_human_active(client, fake_email, cleanup_customers, monkeypatch, db_session):
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    conversation = await _create_conversation(client, token)

    conv_result = await db_session.execute(select(Conversation).where(Conversation.id == uuid.UUID(conversation["id"])))
    conv = conv_result.scalar_one()
    conv.ownership_status = OwnershipStatus.HUMAN_ACTIVE
    await db_session.commit()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("AI orchestrator must not be invoked while HUMAN_ACTIVE")

    monkeypatch.setattr(orchestrator_module.AIOrchestratorService, "handle_buyer_message", fail_if_called)

    resp = await client.post(
        f"/api/v1/customer/conversations/{conversation['id']}/messages",
        json={"content": "Still there?"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201

    messages_resp = await client.get(
        f"/api/v1/customer/conversations/{conversation['id']}/messages", headers=auth_headers(token)
    )
    assert messages_resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_ai_not_invoked_during_pending_assignment(client, fake_email, cleanup_customers, monkeypatch, db_session):
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    conversation = await _create_conversation(client, token)

    conv_result = await db_session.execute(select(Conversation).where(Conversation.id == uuid.UUID(conversation["id"])))
    conv = conv_result.scalar_one()
    conv.ownership_status = OwnershipStatus.PENDING_ASSIGNMENT
    await db_session.commit()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("AI orchestrator must not be invoked while PENDING_ASSIGNMENT")

    monkeypatch.setattr(orchestrator_module.AIOrchestratorService, "handle_buyer_message", fail_if_called)

    resp = await client.post(
        f"/api/v1/customer/conversations/{conversation['id']}/messages",
        json={"content": "Any update?"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201

    messages_resp = await client.get(
        f"/api/v1/customer/conversations/{conversation['id']}/messages", headers=auth_headers(token)
    )
    assert messages_resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_resolved_conversation_rejects_messages(client, fake_email, cleanup_customers, db_session):
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    conversation = await _create_conversation(client, token)

    conv_result = await db_session.execute(select(Conversation).where(Conversation.id == uuid.UUID(conversation["id"])))
    conv = conv_result.scalar_one()
    conv.ownership_status = OwnershipStatus.RESOLVED
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/customer/conversations/{conversation['id']}/messages",
        json={"content": "Hello again"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409

    messages_resp = await client.get(
        f"/api/v1/customer/conversations/{conversation['id']}/messages", headers=auth_headers(token)
    )
    assert messages_resp.json()["total"] == 0

    await db_session.refresh(conv)
    assert conv.ownership_status == OwnershipStatus.RESOLVED


# --- POST /customer/conversations/{id}/handoff ---


@pytest.mark.asyncio
async def test_customer_can_request_handoff(client, fake_email, cleanup_customers, db_session):
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    conversation = await _create_conversation(client, token)

    resp = await client.post(
        f"/api/v1/customer/conversations/{conversation['id']}/handoff", headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] in ("PENDING", "ASSIGNED")

    conv_result = await db_session.execute(select(Conversation).where(Conversation.id == uuid.UUID(conversation["id"])))
    conv = conv_result.scalar_one()
    assert conv.ownership_status in (OwnershipStatus.PENDING_ASSIGNMENT, OwnershipStatus.HUMAN_ACTIVE)


@pytest.mark.asyncio
async def test_repeated_handoff_requests_do_not_duplicate(client, fake_email, cleanup_customers, db_session):
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    conversation = await _create_conversation(client, token)

    resp1 = await client.post(
        f"/api/v1/customer/conversations/{conversation['id']}/handoff", headers=auth_headers(token)
    )
    resp2 = await client.post(
        f"/api/v1/customer/conversations/{conversation['id']}/handoff", headers=auth_headers(token)
    )
    assert resp1.status_code == 201
    assert resp2.status_code == 201

    handoffs_result = await db_session.execute(
        select(Handoff).where(Handoff.conversation_id == uuid.UUID(conversation["id"]))
    )
    handoffs = handoffs_result.scalars().all()
    assert len(handoffs) == 1


@pytest.mark.asyncio
async def test_customer_cannot_request_handoff_for_another_customers_conversation(
    client, fake_email, cleanup_customers
):
    _, token_a = await _register_login_verify(client, fake_email, cleanup_customers)
    _, token_b = await _register_login_verify(client, fake_email, cleanup_customers)
    conv_b = await _create_conversation(client, token_b)

    resp = await client.post(
        f"/api/v1/customer/conversations/{conv_b['id']}/handoff", headers=auth_headers(token_a)
    )
    assert resp.status_code == 404


# --- Staff replies visible to customer; customer cannot post staff messages ---


@pytest.mark.asyncio
async def test_staff_reply_visible_to_owning_customer(
    client, fake_email, cleanup_customers, db_session
):
    staff_email = f"test-customer-chat-staff-{uuid.uuid4().hex[:8]}@estateflow.ai"
    staff = User(
        email=staff_email, full_name="Staff Exec", password_hash=hash_password(PASSWORD),
        role=UserRole.SALES_EXECUTIVE, is_active=True,
    )
    db_session.add(staff)
    await db_session.commit()

    try:
        _, token = await _register_login_verify(client, fake_email, cleanup_customers)
        conversation = await _create_conversation(client, token)

        handoff_resp = await client.post(
            f"/api/v1/customer/conversations/{conversation['id']}/handoff", headers=auth_headers(token)
        )
        assert handoff_resp.status_code == 201

        conv_result = await db_session.execute(
            select(Conversation).where(Conversation.id == uuid.UUID(conversation["id"]))
        )
        conv = conv_result.scalar_one()
        handoff_result = await db_session.execute(select(Handoff).where(Handoff.conversation_id == conv.id))
        handoff = handoff_result.scalar_one()
        handoff.assigned_executive_id = staff.id
        conv.ownership_status = OwnershipStatus.HUMAN_ACTIVE
        await db_session.commit()

        staff_login = await client.post("/api/v1/auth/login", json={"email": staff_email, "password": PASSWORD})
        staff_token = staff_login.json()["access_token"]

        staff_reply_resp = await client.post(
            f"/api/v1/conversations/{conv.id}/messages",
            json={"content": "Hi, this is Priya from sales."},
            headers=auth_headers(staff_token),
        )
        assert staff_reply_resp.status_code == 201, staff_reply_resp.text

        customer_messages_resp = await client.get(
            f"/api/v1/customer/conversations/{conversation['id']}/messages", headers=auth_headers(token)
        )
        items = customer_messages_resp.json()["items"]
        assert any(m["sender_type"] == "STAFF" and m["content"] == "Hi, this is Priya from sales." for m in items)
    finally:
        await db_session.execute(delete(AuthSession).where(AuthSession.user_id == staff.id))
        await db_session.execute(delete(User).where(User.id == staff.id))
        await db_session.commit()


@pytest.mark.asyncio
async def test_customer_message_endpoint_cannot_post_as_staff(client, fake_email, cleanup_customers):
    """
    There is no way for a customer to reach the staff-reply endpoint -- it
    requires a staff bearer token, which `get_current_user` rejects a
    customer access token for (distinct token-type claim).
    """
    _, token = await _register_login_verify(client, fake_email, cleanup_customers)
    conversation = await _create_conversation(client, token)

    resp = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "I am pretending to be staff"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 401


# --- Authorization: staff tokens / anonymous buyer sessions rejected ---


@pytest.mark.asyncio
async def test_customer_chat_endpoints_reject_staff_token(client, db_session):
    staff_email = f"test-customer-chat-staff2-{uuid.uuid4().hex[:8]}@estateflow.ai"
    staff = User(
        email=staff_email, full_name="Staff", password_hash=hash_password(PASSWORD),
        role=UserRole.SALES_EXECUTIVE, is_active=True,
    )
    db_session.add(staff)
    await db_session.commit()

    try:
        login_resp = await client.post("/api/v1/auth/login", json={"email": staff_email, "password": PASSWORD})
        staff_token = login_resp.json()["access_token"]

        resp = await client.post("/api/v1/customer/conversations", headers=auth_headers(staff_token))
        assert resp.status_code == 401
    finally:
        await db_session.execute(delete(AuthSession).where(AuthSession.user_id == staff.id))
        await db_session.execute(delete(User).where(User.id == staff.id))
        await db_session.commit()


@pytest.mark.asyncio
async def test_customer_chat_endpoints_reject_anonymous_buyer_session_cookie(client):
    client.cookies.set("estateflow_buyer_session", "some-opaque-buyer-session-token")
    resp = await client.post("/api/v1/customer/conversations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_customer_chat_endpoints_reject_missing_authentication(client):
    resp = await client.post("/api/v1/customer/conversations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_suspended_customer_cannot_access_chat(client, fake_email, cleanup_customers, db_session):
    email, token = await _register_login_verify(client, fake_email, cleanup_customers)
    result = await db_session.execute(select(CustomerAccount).where(CustomerAccount.normalized_email == email.lower()))
    customer = result.scalar_one()
    customer.status = CustomerAccountStatus.SUSPENDED
    await db_session.commit()

    resp = await client.post("/api/v1/customer/conversations", headers=auth_headers(token))
    assert resp.status_code == 401
