import asyncio
import secrets
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

from backend.main import app
from backend.core.config import settings
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.models.auth_session import AuthSession
from backend.models.buyer_session import BuyerSession
from backend.models.conversation import Conversation, ConversationStatus
from backend.models.lead import Lead
from backend.models.message import Message
from backend.models.user import User, UserRole

ADMIN_EMAIL = "test-conv-admin@estateflow.ai"
EXEC_EMAIL = "test-conv-exec@estateflow.ai"
PASSWORD = "SuperSecret123!"


def _unique_phone() -> str:
    return "9" + "".join(secrets.choice("0123456789") for _ in range(9))


@pytest_asyncio.fixture
async def db_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_users(db_session):
    emails = [ADMIN_EMAIL, EXEC_EMAIL]
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()

    admin = User(email=ADMIN_EMAIL, full_name="Conv Admin", password_hash=hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True)
    exec_user = User(email=EXEC_EMAIL, full_name="Conv Exec", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    db_session.add_all([admin, exec_user])
    await db_session.commit()

    yield {"admin": admin, "exec": exec_user}

    await db_session.execute(delete(AuthSession).where(AuthSession.user_id.in_([admin.id, exec_user.id])))
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


async def _create_chat_session(client, *, full_name="Test Buyer", phone=None):
    resp = await client.post(
        "/api/v1/chat/sessions",
        json={
            "full_name": full_name,
            "phone": phone or _unique_phone(),
            "preferred_language": "EN",
            "consent_given": True,
        },
    )
    return resp


@pytest_asyncio.fixture(autouse=True)
async def cleanup_conversations(db_session):
    yield
    await db_session.execute(delete(BuyerSession))
    await db_session.execute(delete(Message))
    await db_session.execute(delete(Conversation))
    await db_session.execute(delete(Lead))
    await db_session.commit()


@pytest.mark.asyncio
async def test_create_chat_session_creates_lead_and_conversation(client, db_session):
    resp = await _create_chat_session(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "ACTIVE"
    assert data["conversation_state"] == "DISCOVERY"
    assert data["ownership_status"] == "AI_ACTIVE"
    assert settings.BUYER_SESSION_COOKIE_NAME in resp.cookies

    lead = await db_session.get(Lead, uuid.UUID(data["lead_id"]))
    assert lead is not None
    assert lead.full_name == "Test Buyer"


@pytest.mark.asyncio
async def test_consent_required_to_create_session(client):
    resp = await client.post(
        "/api/v1/chat/sessions",
        json={"full_name": "No Consent", "phone": _unique_phone(), "preferred_language": "EN", "consent_given": False},
    )
    assert resp.status_code == 422 or resp.status_code == 400


@pytest.mark.asyncio
async def test_session_persists_across_requests(client):
    create_resp = await _create_chat_session(client)
    conversation_id = create_resp.json()["id"]
    cookie = create_resp.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)
    assert cookie

    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)
    session_resp = await client.get("/api/v1/chat/session")
    assert session_resp.status_code == 200
    assert session_resp.json()["id"] == conversation_id


@pytest.mark.asyncio
async def test_session_logout_revokes_session(client):
    create_resp = await _create_chat_session(client)
    cookie = create_resp.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)

    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)
    logout_resp = await client.post("/api/v1/chat/session/logout")
    assert logout_resp.status_code == 204

    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)
    after_logout = await client.get("/api/v1/chat/session")
    assert after_logout.status_code == 401


@pytest.mark.asyncio
async def test_expired_session_rejected(client, db_session):
    from datetime import datetime, timedelta, timezone
    from backend.core.security import hash_refresh_token

    create_resp = await _create_chat_session(client)
    cookie = create_resp.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)

    result = await db_session.execute(
        select(BuyerSession).where(BuyerSession.token_hash == hash_refresh_token(cookie))
    )
    session_obj = result.scalar_one()
    session_obj.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)
    resp = await client.get("/api/v1/chat/session")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unauthorized_access_to_other_conversation(client):
    first = await _create_chat_session(client)
    second = await _create_chat_session(client)

    first_conversation_id = first.json()["id"]
    second_cookie = second.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)

    # Using the second buyer's session cookie to access the first buyer's conversation must fail.
    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, second_cookie)
    resp = await client.get(f"/api/v1/chat/conversations/{first_conversation_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_send_and_retrieve_messages(client):
    create_resp = await _create_chat_session(client)
    conversation_id = create_resp.json()["id"]
    cookie = create_resp.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)
    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)

    send_resp = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": "Hello, I am interested"}
    )
    assert send_resp.status_code == 201
    assert send_resp.json()["sender_type"] == "BUYER"
    assert send_resp.json()["content"] == "Hello, I am interested"

    messages_resp = await client.get(f"/api/v1/chat/conversations/{conversation_id}/messages")
    assert messages_resp.status_code == 200
    body = messages_resp.json()
    assert body["total"] == 1
    assert body["items"][0]["content"] == "Hello, I am interested"


@pytest.mark.asyncio
async def test_message_pagination_and_ordering(client):
    create_resp = await _create_chat_session(client)
    conversation_id = create_resp.json()["id"]
    cookie = create_resp.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)
    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)

    for i in range(5):
        resp = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": f"message {i}"}
        )
        assert resp.status_code == 201

    page1 = await client.get(f"/api/v1/chat/conversations/{conversation_id}/messages?limit=2&offset=0")
    page2 = await client.get(f"/api/v1/chat/conversations/{conversation_id}/messages?limit=2&offset=2")
    assert page1.json()["total"] == 5
    assert [m["content"] for m in page1.json()["items"]] == ["message 0", "message 1"]
    assert [m["content"] for m in page2.json()["items"]] == ["message 2", "message 3"]


@pytest.mark.asyncio
async def test_empty_message_rejected(client):
    create_resp = await _create_chat_session(client)
    conversation_id = create_resp.json()["id"]
    cookie = create_resp.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)
    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)

    resp = await client.post(f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_oversized_message_rejected(client):
    create_resp = await _create_chat_session(client)
    conversation_id = create_resp.json()["id"]
    cookie = create_resp.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)
    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)

    oversized = "a" * (settings.CHAT_MESSAGE_MAX_LENGTH + 1)
    resp = await client.post(f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": oversized})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_closed_conversation_rejects_new_messages(client, db_session):
    create_resp = await _create_chat_session(client)
    conversation_id = create_resp.json()["id"]
    cookie = create_resp.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)
    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)

    conversation = await db_session.get(Conversation, uuid.UUID(conversation_id))
    conversation.status = ConversationStatus.CLOSED
    await db_session.commit()

    resp = await client.post(f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": "Hello"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_concurrent_message_submissions_all_persist(client):
    create_resp = await _create_chat_session(client)
    conversation_id = create_resp.json()["id"]
    cookie = create_resp.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)
    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)

    async def _send(i: int):
        return await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": f"concurrent {i}"}
        )

    results = await asyncio.gather(*[_send(i) for i in range(8)])
    assert all(r.status_code == 201 for r in results)
    ids = {r.json()["id"] for r in results}
    assert len(ids) == 8

    messages_resp = await client.get(f"/api/v1/chat/conversations/{conversation_id}/messages?limit=20")
    assert messages_resp.json()["total"] == 8


@pytest.mark.asyncio
async def test_staff_requires_authentication(client):
    resp = await client.get("/api/v1/conversations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_staff_can_list_and_view_conversation(client, seeded_users):
    create_resp = await _create_chat_session(client)
    conversation_id = create_resp.json()["id"]
    cookie = create_resp.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)
    client.cookies.set(settings.BUYER_SESSION_COOKIE_NAME, cookie)
    await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": "Looking for a 2BHK"}
    )
    client.cookies.delete(settings.BUYER_SESSION_COOKIE_NAME)

    headers = await _login(client, EXEC_EMAIL)
    list_resp = await client.get("/api/v1/conversations", headers=headers)
    assert list_resp.status_code == 200
    assert any(item["id"] == conversation_id for item in list_resp.json()["items"])

    detail_resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["lead_full_name"] == "Test Buyer"

    messages_resp = await client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=headers)
    assert messages_resp.status_code == 200
    assert messages_resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_lead_to_conversation_association(client, db_session):
    create_resp = await _create_chat_session(client)
    data = create_resp.json()

    lead = await db_session.get(Lead, data["lead_id"])
    assert lead is not None
    assert lead.full_name == "Test Buyer"
