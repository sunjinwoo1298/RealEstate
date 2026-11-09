"""BUG-18: idempotent recovery of the immediately previous refresh token."""
import asyncio
import base64
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from backend.core import refresh_recovery
from backend.core.config import settings
from backend.core.database import get_session_factory
from backend.core.security import hash_password, hash_refresh_token
from backend.main import app
from backend.models.auth_session import AuthSession
from backend.models.user import User, UserRole

COOKIE = "estateflow_refresh_token"
PASSWORD = "SuperSecret123!"


@pytest.fixture(autouse=True)
def recovery_enabled(monkeypatch):
    monkeypatch.setattr(settings, "REFRESH_RECOVERY_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setattr(settings, "REFRESH_RECOVERY_GRACE_SECONDS", 20)


@pytest_asyncio.fixture
async def db_session():
    async with get_session_factory()() as session:
        yield session


async def _make_user(db, label):
    email = f"refresh-recovery-{label}-{uuid.uuid4().hex[:8]}@estateflow.ai"
    u = User(
        email=email, full_name="Recovery Tester",
        password_hash=hash_password(PASSWORD), role=UserRole.MANAGER, is_active=True,
    )
    db.add(u)
    await db.commit()
    return u.id, email


async def _drop_user(db, user_id):
    await db.rollback()
    await db.execute(update(AuthSession).where(AuthSession.user_id == user_id).values(replaced_by_id=None))
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()


@pytest_asyncio.fixture
async def user(db_session):
    user_id, email = await _make_user(db_session, "main")
    yield {"id": user_id, "email": email}
    await _drop_user(db_session, user_id)


def _new_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client, email) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.cookies.get(COOKIE)


async def _refresh(client, cookie):
    client.cookies.clear()
    client.cookies.set(COOKIE, cookie)
    return await client.post("/api/v1/auth/refresh")


async def _session(db, raw_token):
    db.expire_all()
    return (
        await db.execute(
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == hash_refresh_token(raw_token))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_normal_rotation_stores_only_encrypted_successor(user, db_session):
    async with _new_client() as c:
        t0 = await _login(c, user["email"])
        r = await _refresh(c, t0)
        assert r.status_code == 200
        t1 = r.cookies.get(COOKIE)
        assert t1 and t1 != t0

    prev = await _session(db_session, t0)
    prev_revoked_at, prev_replaced_by = prev.revoked_at, prev.replaced_by_id
    prev_blob, prev_until = prev.successor_token_encrypted, prev.successor_recoverable_until
    succ = await _session(db_session, t1)
    assert prev_revoked_at is not None and prev_replaced_by == succ.id
    assert succ.revoked_at is None
    assert prev_blob and t1 not in prev_blob
    assert prev_until > datetime.now(timezone.utc)
    assert succ.successor_token_encrypted is None


@pytest.mark.asyncio
async def test_retry_within_grace_returns_exact_same_successor(user, db_session):
    async with _new_client() as c:
        t0 = await _login(c, user["email"])
        t1 = (await _refresh(c, t0)).cookies.get(COOKIE)
        retry = await _refresh(c, t0)  # response was lost; browser re-sends the old cookie
        assert retry.status_code == 200
        assert retry.cookies.get(COOKIE) == t1
        assert (await _refresh(c, t0)).cookies.get(COOKIE) == t1

    rows = (await db_session.execute(select(AuthSession).where(AuthSession.user_id == user["id"]))).scalars().all()
    assert len(rows) == 2  # retries mint no extra session
    assert (await _session(db_session, t1)).revoked_at is None


@pytest.mark.asyncio
async def test_retry_after_grace_expiry_is_reuse_and_revokes_chain(user, db_session):
    async with _new_client() as c:
        t0 = await _login(c, user["email"])
        t1 = (await _refresh(c, t0)).cookies.get(COOKIE)
        prev = await _session(db_session, t0)
        prev.successor_recoverable_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db_session.commit()

        assert (await _refresh(c, t0)).status_code == 401
        assert (await _session(db_session, t1)).revoked_at is not None
        assert (await _refresh(c, t1)).status_code == 401


@pytest.mark.asyncio
async def test_previous_token_only_recovers_immediate_successor(user, db_session):
    async with _new_client() as c:
        t0 = await _login(c, user["email"])
        t1 = (await _refresh(c, t0)).cookies.get(COOKIE)
        t2 = (await _refresh(c, t1)).cookies.get(COOKIE)
        assert t2 != t1
        assert (await _session(db_session, t0)).successor_token_encrypted is None
        assert (await _refresh(c, t0)).status_code == 401


@pytest.mark.asyncio
async def test_recovery_cleared_when_successor_rotates(user, db_session):
    async with _new_client() as c:
        t0 = await _login(c, user["email"])
        t1 = (await _refresh(c, t0)).cookies.get(COOKIE)
        await _refresh(c, t1)
        assert (await _session(db_session, t0)).successor_token_encrypted is None
        assert (await _session(db_session, t1)).successor_token_encrypted is not None


@pytest.mark.asyncio
async def test_two_simultaneous_refreshes_serialize_to_one_successor(user, db_session):
    async with _new_client() as a, _new_client() as b:
        t0 = await _login(a, user["email"])
        ra, rb = await asyncio.gather(_refresh(a, t0), _refresh(b, t0))
        assert ra.status_code == 200 and rb.status_code == 200
        assert ra.cookies.get(COOKIE) == rb.cookies.get(COOKIE)

    rows = (await db_session.execute(select(AuthSession).where(AuthSession.user_id == user["id"]))).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_three_rapid_reloads_keep_session_alive(user):
    async with _new_client() as c:
        t0 = await _login(c, user["email"])
        results = [await _refresh(c, t0) for _ in range(3)]
        assert [r.status_code for r in results] == [200, 200, 200]
        assert len({r.cookies.get(COOKIE) for r in results}) == 1


@pytest.mark.asyncio
async def test_refresh_after_logout_is_rejected_and_recovery_invalidated(user, db_session):
    async with _new_client() as c:
        t0 = await _login(c, user["email"])
        t1 = (await _refresh(c, t0)).cookies.get(COOKIE)
        c.cookies.clear()
        c.cookies.set(COOKIE, t1)
        assert (await c.post("/api/v1/auth/logout")).status_code == 204
        assert (await _session(db_session, t0)).successor_token_encrypted is None
        assert (await _refresh(c, t0)).status_code == 401
        assert (await _refresh(c, t1)).status_code == 401


@pytest.mark.asyncio
async def test_recovery_refused_after_account_deactivation(user, db_session):
    async with _new_client() as c:
        t0 = await _login(c, user["email"])
        await _refresh(c, t0)
        await db_session.execute(update(User).where(User.id == user["id"]).values(is_active=False))
        await db_session.commit()
        assert (await _refresh(c, t0)).status_code == 401


@pytest.mark.asyncio
async def test_recovery_refused_after_session_expiry(user, db_session):
    async with _new_client() as c:
        t0 = await _login(c, user["email"])
        t1 = (await _refresh(c, t0)).cookies.get(COOKIE)
        succ = await _session(db_session, t1)
        succ.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db_session.commit()
        assert (await _refresh(c, t0)).status_code == 401


@pytest.mark.asyncio
async def test_unrelated_session_ciphertext_cannot_recover(user, db_session):
    other_id, other_email = await _make_user(db_session, "other")
    try:
        async with _new_client() as c:
            t0 = await _login(c, user["email"])
            await _refresh(c, t0)
            o0 = await _login(c, other_email)
            await _refresh(c, o0)
            stolen = (await _session(db_session, o0)).successor_token_encrypted
            prev = await _session(db_session, t0)
            prev.successor_token_encrypted = stolen
            await db_session.commit()
            assert (await _refresh(c, t0)).status_code == 401  # AAD binding rejects it
    finally:
        await _drop_user(db_session, other_id)


@pytest.mark.asyncio
async def test_genuine_reuse_still_revokes_when_recovery_disabled(user, db_session, monkeypatch):
    monkeypatch.setattr(settings, "REFRESH_RECOVERY_GRACE_SECONDS", 0)
    async with _new_client() as c:
        t0 = await _login(c, user["email"])
        t1 = (await _refresh(c, t0)).cookies.get(COOKIE)
        assert (await _session(db_session, t0)).successor_token_encrypted is None
        assert (await _refresh(c, t0)).status_code == 401
        assert (await _refresh(c, t1)).status_code == 401


def test_encryption_roundtrip_and_aad_binding():
    a, b = uuid.uuid4(), uuid.uuid4()
    blob = refresh_recovery.encrypt_successor("secret-token", a, b)
    assert "secret-token" not in blob
    assert refresh_recovery.decrypt_successor(blob, a, b) == "secret-token"
    assert refresh_recovery.decrypt_successor(blob, a, uuid.uuid4()) is None
    assert refresh_recovery.decrypt_successor(blob[:-4] + "AAAA", a, b) is None
