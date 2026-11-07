import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db_session, require_roles
from backend.core.exceptions import ValidationException
from backend.models.knowledge_chunk import KnowledgeChunk
from backend.models.user import User, UserRole
from backend.schemas.knowledge import KnowledgeDocumentListResponse, KnowledgeDocumentPublic
from backend.services.knowledge_service import KnowledgeService

router = APIRouter(
    prefix="/admin/knowledge",
    tags=["Admin - Knowledge Documents"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)

_MAX_UPLOAD_BYTES = 10_000_000


def _to_public(document, chunk_count: int) -> KnowledgeDocumentPublic:
    public = KnowledgeDocumentPublic.model_validate(document)
    public.chunk_count = chunk_count
    return public


async def _count_chunks(db: AsyncSession, document_id: uuid.UUID) -> int:
    result = await db.execute(select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
    return result.scalar_one()


@router.get("/documents", response_model=KnowledgeDocumentListResponse, summary="List knowledge documents")
async def list_documents(
    project_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
) -> KnowledgeDocumentListResponse:
    rows, total = await KnowledgeService.list_documents(db, project_id=project_id, limit=limit, offset=offset)
    return KnowledgeDocumentListResponse(items=[_to_public(doc, count) for doc, count in rows], total=total)


@router.post(
    "/documents",
    response_model=KnowledgeDocumentPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a project fact sheet (PDF or text) as a new DRAFT version",
)
async def upload_document(
    project_id: uuid.UUID = Form(...),
    title: str = Form(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> KnowledgeDocumentPublic:
    raw_bytes = await file.read()
    if len(raw_bytes) > _MAX_UPLOAD_BYTES:
        raise ValidationException("File exceeds the maximum allowed upload size")

    document = await KnowledgeService.upload_document(
        db,
        project_id=project_id,
        title=title,
        filename=file.filename or "upload",
        raw_bytes=raw_bytes,
        uploaded_by=current_user.id,
    )
    chunk_count = await _count_chunks(db, document.id)
    return _to_public(document, chunk_count=chunk_count)


@router.post(
    "/documents/{document_id}/approve",
    response_model=KnowledgeDocumentPublic,
    summary="Approve a document version, superseding any prior approved version",
)
async def approve_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> KnowledgeDocumentPublic:
    document = await KnowledgeService.approve_document(db, document_id, approved_by=current_user.id)
    chunk_count = await _count_chunks(db, document.id)
    return _to_public(document, chunk_count=chunk_count)


@router.post(
    "/documents/{document_id}/archive",
    response_model=KnowledgeDocumentPublic,
    summary="Archive a document version so it can no longer ground AI responses",
)
async def archive_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> KnowledgeDocumentPublic:
    document = await KnowledgeService.archive_document(db, document_id)
    chunk_count = await _count_chunks(db, document.id)
    return _to_public(document, chunk_count=chunk_count)
