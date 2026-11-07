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

ADMIN_EMAIL = "test-knowledge-admin@estateflow.ai"
EXEC_EMAIL = "test-knowledge-exec@estateflow.ai"
PASSWORD = "SuperSecret123!"

FACT_SHEET_TEXT = (
    b"Sunrise Towers offers 2 BHK and 3 BHK apartments with a rooftop garden, "
    b"a gymnasium, and dedicated visitor parking. The project is located five "
    b"minutes from the main highway junction."
)


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

    admin = User(email=ADMIN_EMAIL, full_name="Knowledge Admin", password_hash=hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True)
    exec_user = User(email=EXEC_EMAIL, full_name="Knowledge Exec", password_hash=hash_password(PASSWORD), role=UserRole.SALES_EXECUTIVE, is_active=True)
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


@pytest_asyncio.fixture(autouse=True)
async def cleanup_projects(db_session):
    yield
    await db_session.execute(delete(KnowledgeChunk))
    await db_session.execute(delete(KnowledgeDocument))
    await db_session.execute(delete(Project).where(Project.name.like("Test Project%")))
    await db_session.commit()


async def _login(client, email):
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_project(client, headers, name_suffix):
    resp = await client.post(
        "/api/v1/admin/projects",
        json={"name": f"Test Project {name_suffix}", "description": "A test project", "location": "Test City"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


async def _upload_document(client, headers, project_id, title="Fact Sheet", content: bytes = FACT_SHEET_TEXT):
    files = {"file": ("factsheet.txt", content, "text/plain")}
    data = {"project_id": project_id, "title": title}
    resp = await client.post("/api/v1/admin/knowledge/documents", data=data, files=files, headers=headers)
    return resp


@pytest.mark.asyncio
async def test_upload_creates_draft_document_with_chunks(client, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(client, headers, uuid.uuid4().hex[:8])

    resp = await _upload_document(client, headers, project["id"])
    assert resp.status_code == 201
    body = resp.json()
    assert body["approval_status"] == "DRAFT"
    assert body["version"] == 1
    assert body["chunk_count"] >= 1


@pytest.mark.asyncio
async def test_unapproved_documents_excluded_from_retrieval(client, seeded_users, db_session):
    headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(client, headers, uuid.uuid4().hex[:8])

    upload_resp = await _upload_document(client, headers, project["id"])
    document_id = upload_resp.json()["id"]

    from backend.services.retrieval_service import RetrievalService

    results = await RetrievalService.search_project_knowledge(
        db_session, project_id=uuid.UUID(project["id"]), query_text="gymnasium amenities"
    )
    assert results == []

    archive_resp = await client.post(f"/api/v1/admin/knowledge/documents/{document_id}/archive", headers=headers)
    assert archive_resp.status_code == 200
    assert archive_resp.json()["approval_status"] == "ARCHIVED"

    results_after_archive = await RetrievalService.search_project_knowledge(
        db_session, project_id=uuid.UUID(project["id"]), query_text="gymnasium amenities"
    )
    assert results_after_archive == []


@pytest.mark.asyncio
async def test_approved_document_is_retrievable_and_project_isolated(client, seeded_users, db_session):
    headers = await _login(client, ADMIN_EMAIL)
    project_a = await _create_project(client, headers, "A" + uuid.uuid4().hex[:8])
    project_b = await _create_project(client, headers, "B" + uuid.uuid4().hex[:8])

    upload_a = await _upload_document(client, headers, project_a["id"], content=FACT_SHEET_TEXT)
    approve_resp = await client.post(
        f"/api/v1/admin/knowledge/documents/{upload_a.json()['id']}/approve", headers=headers
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["approval_status"] == "APPROVED"

    from backend.services.retrieval_service import RetrievalService

    results_a = await RetrievalService.search_project_knowledge(
        db_session, project_id=uuid.UUID(project_a["id"]), query_text="rooftop garden gymnasium"
    )
    assert len(results_a) >= 1
    assert all(r.document_id == uuid.UUID(upload_a.json()["id"]) for r in results_a)

    # Project B has no approved documents at all, so a search against it must return nothing,
    # even though project A has matching approved content (project-specific retrieval isolation).
    results_b = await RetrievalService.search_project_knowledge(
        db_session, project_id=uuid.UUID(project_b["id"]), query_text="rooftop garden gymnasium"
    )
    assert results_b == []


@pytest.mark.asyncio
async def test_approving_new_version_archives_prior_approved_version(client, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(client, headers, uuid.uuid4().hex[:8])

    v1 = await _upload_document(client, headers, project["id"], title="Shared Title")
    v1_id = v1.json()["id"]
    approve_v1 = await client.post(f"/api/v1/admin/knowledge/documents/{v1_id}/approve", headers=headers)
    assert approve_v1.json()["approval_status"] == "APPROVED"

    v2 = await _upload_document(client, headers, project["id"], title="Shared Title", content=FACT_SHEET_TEXT + b" Updated.")
    assert v2.json()["version"] == 2
    v2_id = v2.json()["id"]
    approve_v2 = await client.post(f"/api/v1/admin/knowledge/documents/{v2_id}/approve", headers=headers)
    assert approve_v2.json()["approval_status"] == "APPROVED"

    list_resp = await client.get(f"/api/v1/admin/knowledge/documents?project_id={project['id']}", headers=headers)
    items = {item["id"]: item for item in list_resp.json()["items"]}
    assert items[v1_id]["approval_status"] == "ARCHIVED"
    assert items[v2_id]["approval_status"] == "APPROVED"


@pytest.mark.asyncio
async def test_non_admin_cannot_manage_knowledge(client, seeded_users):
    headers = await _login(client, EXEC_EMAIL)
    resp = await client.get("/api/v1/admin/knowledge/documents", headers=headers)
    assert resp.status_code == 403

    resp = await client.post(
        "/api/v1/admin/projects", json={"name": "Should Not Be Created"}, headers=headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unsupported_file_type_rejected(client, seeded_users):
    headers = await _login(client, ADMIN_EMAIL)
    project = await _create_project(client, headers, uuid.uuid4().hex[:8])

    files = {"file": ("factsheet.docx", b"not a real docx", "application/octet-stream")}
    data = {"project_id": project["id"], "title": "Bad File"}
    resp = await client.post("/api/v1/admin/knowledge/documents", data=data, files=files, headers=headers)
    assert resp.status_code == 422
