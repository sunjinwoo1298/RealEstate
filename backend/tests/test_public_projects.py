import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from backend.main import app
from backend.core.database import get_session_factory
from backend.core.security import hash_password
from backend.models.auth_session import AuthSession
from backend.models.knowledge_chunk import KnowledgeChunk
from backend.models.knowledge_document import KnowledgeDocument
from backend.models.project import Project
from backend.models.user import User, UserRole

ADMIN_EMAIL = "test-public-admin@estateflow.ai"
EXEC_EMAIL = "test-public-exec@estateflow.ai"
MANAGER_EMAIL = "test-public-manager@estateflow.ai"
PASSWORD = "SuperSecret123!"


@pytest_asyncio.fixture
async def db_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_users(db_session):
    emails = [ADMIN_EMAIL, EXEC_EMAIL, MANAGER_EMAIL]
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()

    admin = User(email=ADMIN_EMAIL, full_name="Public Admin", password_hash=hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True)
    exec_user = User(email=EXEC_EMAIL, full_name="Public Exec", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
    manager = User(email=MANAGER_EMAIL, full_name="Public Manager", password_hash=hash_password(PASSWORD), role=UserRole.MANAGER, is_active=True)
    db_session.add_all([admin, exec_user, manager])
    await db_session.commit()

    yield {"admin": admin, "exec": exec_user, "manager": manager}

    await db_session.execute(delete(AuthSession).where(AuthSession.user_id.in_([admin.id, exec_user.id, manager.id])))
    await db_session.execute(delete(User).where(User.email.in_(emails)))
    await db_session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def cleanup_projects(db_session):
    yield
    await db_session.execute(delete(KnowledgeChunk))
    await db_session.execute(delete(KnowledgeDocument))
    await db_session.execute(delete(Project).where(Project.name.like("Public Test Project%")))
    await db_session.commit()


async def _login(client, email):
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_project(client, headers, name_suffix, **extra):
    resp = await client.post(
        "/api/v1/admin/projects",
        json={
            "name": f"Public Test Project {name_suffix}",
            "description": "A test project",
            "location": "Test City",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    project = resp.json()
    if extra:
        patch_resp = await client.patch(f"/api/v1/admin/projects/{project['id']}", json=extra, headers=headers)
        assert patch_resp.status_code == 200
        project = patch_resp.json()
    return project


# --- Publication rules ---


@pytest.mark.asyncio
async def test_new_project_defaults_to_draft(client, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(client, headers, "Draft Default")
    assert project["visibility_status"] == "DRAFT"


@pytest.mark.asyncio
async def test_admin_can_publish_a_project(client, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(client, headers, "Publishable")

    resp = await client.patch(
        f"/api/v1/admin/projects/{project['id']}", json={"visibility_status": "PUBLISHED"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["visibility_status"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_unauthorized_staff_cannot_publish(client, seeded_users):
    admin_headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(client, admin_headers, "Locked Down")

    exec_headers = await _login(client, EXEC_EMAIL)
    resp = await client.patch(
        f"/api/v1/admin/projects/{project['id']}", json={"visibility_status": "PUBLISHED"}, headers=exec_headers
    )
    assert resp.status_code == 403

    manager_headers = await _login(client, MANAGER_EMAIL)
    resp = await client.patch(
        f"/api/v1/admin/projects/{project['id']}", json={"visibility_status": "PUBLISHED"}, headers=manager_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_manager_can_view_but_not_create(client, seeded_users):
    manager_headers = await _login(client, MANAGER_EMAIL)
    resp = await client.get("/api/v1/admin/projects", headers=manager_headers)
    assert resp.status_code == 200

    resp = await client.post(
        "/api/v1/admin/projects", json={"name": "Public Test Project Manager Blocked"}, headers=manager_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_archived_project_hidden_from_public_listing_and_detail(client, seeded_users):
    admin_headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(client, admin_headers, "Archived", visibility_status="ARCHIVED")

    list_resp = await client.get("/api/v1/public/projects")
    ids = [item["id"] for item in list_resp.json()["items"]]
    assert project["id"] not in ids

    detail_resp = await client.get(f"/api/v1/public/projects/{project['id']}")
    assert detail_resp.status_code == 404


@pytest.mark.asyncio
async def test_draft_project_returns_404_through_public_detail_api(client, seeded_users):
    admin_headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(client, admin_headers, "Still Draft")

    resp = await client.get(f"/api/v1/public/projects/{project['id']}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unpublished_project_never_appears_in_featured_listing(client, seeded_users):
    admin_headers = await _login(client, ADMIN_EMAIL)
    draft_project = await _create_project(client, admin_headers, "Featured Draft", is_featured=True)

    resp = await client.get("/api/v1/public/projects/featured")
    ids = [item["id"] for item in resp.json()["items"]]
    assert draft_project["id"] not in ids


@pytest.mark.asyncio
async def test_nonexistent_project_returns_404(client, seeded_users):
    resp = await client.get(f"/api/v1/public/projects/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- Public APIs ---


@pytest.mark.asyncio
async def test_published_project_listing_and_detail(client, seeded_users):
    admin_headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(
        client,
        admin_headers,
        "Visible",
        visibility_status="PUBLISHED",
        configurations=["2 BHK", "3 BHK"],
        amenities=["Gym", "Pool"],
        images=["https://example.com/a.jpg", "https://example.com/b.jpg"],
        rera_number="RERA123",
    )

    list_resp = await client.get("/api/v1/public/projects")
    assert list_resp.status_code == 200
    items = {item["id"]: item for item in list_resp.json()["items"]}
    assert project["id"] in items
    card = items[project["id"]]
    assert card["name"] == project["name"]
    assert card["configurations"] == ["2 BHK", "3 BHK"]
    assert card["primary_image"] == "https://example.com/a.jpg"
    # Price was never explicitly approved for display -- must never appear.
    assert card["starting_price_label"] is None

    detail_resp = await client.get(f"/api/v1/public/projects/{project['id']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["amenities"] == ["Gym", "Pool"]
    assert detail["images"] == ["https://example.com/a.jpg", "https://example.com/b.jpg"]
    assert detail["rera_number"] == "RERA123"
    # Internal-only fields must never leak through the public schema.
    assert "price_display_approved" not in detail
    assert "is_active" not in detail


@pytest.mark.asyncio
async def test_public_pricing_returned_only_when_explicitly_approved(client, seeded_users):
    admin_headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(
        client,
        admin_headers,
        "Priced",
        visibility_status="PUBLISHED",
        starting_price_label="Starting at Rs. 85 Lakh",
        price_display_approved=False,
    )
    resp = await client.get(f"/api/v1/public/projects/{project['id']}")
    assert resp.json()["starting_price_label"] is None

    await client.patch(
        f"/api/v1/admin/projects/{project['id']}", json={"price_display_approved": True}, headers=admin_headers
    )
    resp = await client.get(f"/api/v1/public/projects/{project['id']}")
    assert resp.json()["starting_price_label"] == "Starting at Rs. 85 Lakh"


@pytest.mark.asyncio
async def test_public_search_and_location_filters(client, seeded_users):
    admin_headers = await _login(client, ADMIN_EMAIL)
    await _create_project(
        client, admin_headers, "Sunrise Heights", visibility_status="PUBLISHED", location="Pune"
    )
    await _create_project(
        client, admin_headers, "Lakeview Residency", visibility_status="PUBLISHED", location="Mumbai"
    )

    resp = await client.get("/api/v1/public/projects?search=Sunrise")
    names = [item["name"] for item in resp.json()["items"]]
    assert any("Sunrise" in n for n in names)
    assert not any("Lakeview" in n for n in names)

    resp = await client.get("/api/v1/public/projects?location=Mumbai")
    names = [item["name"] for item in resp.json()["items"]]
    assert any("Lakeview" in n for n in names)
    assert not any("Sunrise" in n for n in names)


@pytest.mark.asyncio
async def test_public_configuration_filter(client, seeded_users):
    admin_headers = await _login(client, ADMIN_EMAIL)
    two_bhk = await _create_project(
        client, admin_headers, "Two Bhk Only", visibility_status="PUBLISHED", configurations=["2 BHK"]
    )
    three_bhk = await _create_project(
        client, admin_headers, "Three Bhk Only", visibility_status="PUBLISHED", configurations=["3 BHK"]
    )

    resp = await client.get("/api/v1/public/projects?configuration=2 BHK")
    ids = [item["id"] for item in resp.json()["items"]]
    assert two_bhk["id"] in ids
    assert three_bhk["id"] not in ids


@pytest.mark.asyncio
async def test_public_pagination(client, seeded_users):
    admin_headers = await _login(client, ADMIN_EMAIL)
    for i in range(3):
        await _create_project(client, admin_headers, f"Paginated {i}", visibility_status="PUBLISHED")

    resp = await client.get("/api/v1/public/projects?limit=2&offset=0&search=Paginated")
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

    resp2 = await client.get("/api/v1/public/projects?limit=2&offset=2&search=Paginated")
    data2 = resp2.json()
    assert len(data2["items"]) == 1


@pytest.mark.asyncio
async def test_featured_listing_only_returns_published_featured_projects(client, seeded_users):
    admin_headers = await _login(client, ADMIN_EMAIL)
    featured = await _create_project(
        client, admin_headers, "Showcase", visibility_status="PUBLISHED", is_featured=True
    )
    not_featured = await _create_project(
        client, admin_headers, "Regular", visibility_status="PUBLISHED", is_featured=False
    )

    resp = await client.get("/api/v1/public/projects/featured")
    ids = [item["id"] for item in resp.json()["items"]]
    assert featured["id"] in ids
    assert not_featured["id"] not in ids


@pytest.mark.asyncio
async def test_public_endpoints_require_no_authentication(client, seeded_users):
    # No Authorization header at all -- must not 401.
    resp = await client.get("/api/v1/public/projects")
    assert resp.status_code == 200
    resp = await client.get("/api/v1/public/projects/featured")
    assert resp.status_code == 200
