from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ConflictException, NotFoundException, ValidationException
from backend.models.knowledge_chunk import KnowledgeChunk
from backend.models.knowledge_document import ApprovalStatus, KnowledgeDocument
from backend.services.document_processing_service import DocumentProcessingService
from backend.services.embedding_service import EmbeddingService
from backend.services.project_service import ProjectService


class KnowledgeService:
    """
    Admin-facing knowledge document pipeline: upload -> extract -> chunk ->
    embed -> (pending) approval -> versioning. Only APPROVED documents are
    ever readable by RetrievalService.
    """

    @staticmethod
    async def upload_document(
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        title: str,
        filename: str,
        raw_bytes: bytes,
        uploaded_by: uuid.UUID,
    ) -> KnowledgeDocument:
        await ProjectService.get_project(db, project_id)  # 404s if the project does not exist

        text = DocumentProcessingService.extract_text(filename=filename, raw_bytes=raw_bytes)
        chunks = DocumentProcessingService.chunk_text(text)

        existing_version_result = await db.execute(
            select(func.max(KnowledgeDocument.version)).where(
                KnowledgeDocument.project_id == project_id,
                KnowledgeDocument.title == title,
            )
        )
        next_version = (existing_version_result.scalar_one_or_none() or 0) + 1

        document = KnowledgeDocument(
            project_id=project_id,
            title=title,
            version=next_version,
            approval_status=ApprovalStatus.DRAFT,
            source_filename=filename,
            uploaded_by=uploaded_by,
        )
        db.add(document)
        await db.flush()  # assigns document.id for the chunk FK before embedding

        embeddings = await EmbeddingService.embed_texts(chunks)
        for index, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(
                KnowledgeChunk(
                    document_id=document.id,
                    project_id=project_id,
                    content=chunk_text,
                    embedding=embedding,
                    chunk_index=index,
                )
            )

        await db.commit()
        await db.refresh(document)
        return document

    @staticmethod
    async def get_document(db: AsyncSession, document_id: uuid.UUID) -> KnowledgeDocument:
        result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
        document = result.scalar_one_or_none()
        if document is None:
            raise NotFoundException("Knowledge document not found")
        return document

    @staticmethod
    async def approve_document(db: AsyncSession, document_id: uuid.UUID, approved_by: uuid.UUID) -> KnowledgeDocument:
        document = await KnowledgeService.get_document(db, document_id)
        if document.approval_status == ApprovalStatus.ARCHIVED:
            raise ConflictException("Cannot approve an archived document")

        # Preserve history: superseded prior approved versions of the same
        # document become ARCHIVED rather than being deleted or left to
        # ground responses alongside the new version.
        prior_approved_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.project_id == document.project_id,
                KnowledgeDocument.title == document.title,
                KnowledgeDocument.approval_status == ApprovalStatus.APPROVED,
                KnowledgeDocument.id != document.id,
            )
        )
        for prior in prior_approved_result.scalars().all():
            prior.approval_status = ApprovalStatus.ARCHIVED

        document.approval_status = ApprovalStatus.APPROVED
        document.approved_by = approved_by
        document.approved_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(document)
        return document

    @staticmethod
    async def archive_document(db: AsyncSession, document_id: uuid.UUID) -> KnowledgeDocument:
        document = await KnowledgeService.get_document(db, document_id)
        document.approval_status = ApprovalStatus.ARCHIVED
        await db.commit()
        await db.refresh(document)
        return document

    @staticmethod
    async def list_documents(
        db: AsyncSession, *, project_id: Optional[uuid.UUID] = None, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Tuple[KnowledgeDocument, int]], int]:
        base_query = select(KnowledgeDocument, func.count(KnowledgeChunk.id)).outerjoin(
            KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id
        )
        count_query = select(func.count()).select_from(KnowledgeDocument)

        if project_id is not None:
            base_query = base_query.where(KnowledgeDocument.project_id == project_id)
            count_query = count_query.where(KnowledgeDocument.project_id == project_id)

        total = (await db.execute(count_query)).scalar_one()

        base_query = (
            base_query.group_by(KnowledgeDocument.id)
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(base_query)
        return [(row[0], row[1]) for row in result.all()], total
