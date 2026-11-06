import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from backend.main import app
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.models.auth_session import AuthSession
from backend.models.user import User, UserRole

ADMIN_EMAIL = "test-admin@estateflow.ai"
MANAGER_EMAIL = "test-manager@estateflow.ai"
INACTIVE_EMAIL = "test-inactive@estateflow.ai"
PASSWORD = "SuperSecret123!"


@pytest_asyncio.fixture
async def db_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_users(db_session):
    emails = [ADMIN_EMAIL, MANAGER_EMAIL, INACTIVE_EMAIL]
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()

    admin = User(
        email=ADMIN_EMAIL, full_name="Test Admin",
        password_hash=hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True,
    )
    manager = User(
        email=MANAGER_EMAIL, full_name="Test Manager",
        password_hash=hash_password(PASSWORD), role=UserRole.MANAGER, is_active=True,
    )
    inactive = User(
        email=INACTIVE_EMAIL, full_name="Test Inactive",
        password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=False,
    )
    db_session.add_all([admin, manager, inactive])
    await db_session.commit()

    yield {"admin": admin, "manager": manager, "inactive": inactive}

    await db_session.execute(delete(AuthSession).where(AuthSession.user_id.in_([admin.id, manager.id, inactive.id])))
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_login_success(client, seeded_users):
    resp = await client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == ADMIN_EMAIL
    assert data["user"]["role"] == "ADMIN"
    assert "password_hash" not in data["user"]
    assert "estateflow_refresh_token" in resp.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(client, seeded_users):
    resp = await client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_same_error_as_wrong_password(client, seeded_users):
    resp_unknown = await client.post("/api/v1/auth/login", json={"email": "nobody@estateflow.ai", "password": PASSWORD})
    resp_wrong = await client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"})
    assert resp_unknown.status_code == 401
    assert resp_wrong.status_code == 401
    assert resp_unknown.json()["error"]["message"] == resp_wrong.json()["error"]["message"]


@pytest.mark.asyncio
async def test_login_inactive_account_rejected(client, seeded_users):
    resp = await client.post("/api/v1/auth/login", json={"email": INACTIVE_EMAIL, "password": PASSWORD})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_bearer_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client, seeded_users):
    login_resp = await client.post("/api/v1/auth/login", json={"email": MANAGER_EMAIL, "password": PASSWORD})
    access_token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == MANAGER_EMAIL


@pytest.mark.asyncio
async def test_invalid_token_rejected(client):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_reuse_is_rejected(client, seeded_users):
    login_resp = await client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    old_refresh_cookie = login_resp.cookies.get("estateflow_refresh_token")
    assert old_refresh_cookie

    client.cookies.set("estateflow_refresh_token", old_refresh_cookie)
    refresh_resp = await client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()

    new_refresh_cookie = refresh_resp.cookies.get("estateflow_refresh_token")
    assert new_refresh_cookie and new_refresh_cookie != old_refresh_cookie

    # Reusing the rotated (now-revoked) refresh token must be rejected.
    client.cookies.set("estateflow_refresh_token", old_refresh_cookie)
    reuse_resp = await client.post("/api/v1/auth/refresh")
    assert reuse_resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_session(client, seeded_users):
    login_resp = await client.post("/api/v1/auth/login", json={"email": MANAGER_EMAIL, "password": PASSWORD})
    refresh_cookie = login_resp.cookies.get("estateflow_refresh_token")

    client.cookies.set("estateflow_refresh_token", refresh_cookie)
    logout_resp = await client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 204

    client.cookies.set("estateflow_refresh_token", refresh_cookie)
    refresh_after_logout = await client.post("/api/v1/auth/refresh")
    assert refresh_after_logout.status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoint_requires_admin_role(client, seeded_users):
    login_resp = await client.post("/api/v1/auth/login", json={"email": MANAGER_EMAIL, "password": PASSWORD})
    access_token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_and_manage_staff(client, seeded_users, db_session):
    login_resp = await client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    access_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    new_email = f"new-staff-{uuid.uuid4().hex[:8]}@estateflow.ai"
    create_resp = await client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={"email": new_email, "full_name": "New Staff", "password": "AnotherSecret123!", "role": "SALES_EXECUTIVE"},
    )
    assert create_resp.status_code == 201
    created_user = create_resp.json()
    assert created_user["email"] == new_email
    assert "password_hash" not in created_user

    list_resp = await client.get("/api/v1/admin/users", headers=headers)
    assert list_resp.status_code == 200
    assert any(u["email"] == new_email for u in list_resp.json()["items"])

    status_resp = await client.patch(
        f"/api/v1/admin/users/{created_user['id']}/status",
        headers=headers,
        json={"is_active": False},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["is_active"] is False

    await db_session.execute(delete(User).where(User.email == new_email))
    await db_session.commit()
