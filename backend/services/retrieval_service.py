from __future__ import annotations
import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.models.knowledge_chunk import KnowledgeChunk
from backend.models.knowledge_document import ApprovalStatus, KnowledgeDocument
from backend.models.project import Project
from backend.services.embedding_service import EmbeddingService


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    document_version: int
    content: str
    similarity: float


class RetrievalService:
    """
    Hybrid retrieval: exact structured SQL for project facts, pgvector
    cosine similarity for descriptive content. Only chunks belonging to a
    currently APPROVED document version are ever returned, so stale DRAFT
    or superseded ARCHIVED content can never ground a response.
    """

    @staticmethod
    async def get_project_information(db: AsyncSession, project_id: uuid.UUID) -> Optional[dict]:
        result = await db.execute(select(Project).where(Project.id == project_id, Project.is_active.is_(True)))
        project = result.scalar_one_or_none()
        if project is None:
            return None
        return {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "location": project.location,
        }

    @staticmethod
    async def search_project_knowledge(
        db: AsyncSession, *, project_id: uuid.UUID, query_text: str, top_k: Optional[int] = None
    ) -> List[RetrievedChunk]:
        query_embedding = await EmbeddingService.embed_text(query_text)
        limit = top_k or settings.RAG_TOP_K

        distance = KnowledgeChunk.embedding.cosine_distance(query_embedding)
        result = await db.execute(
            select(KnowledgeChunk, KnowledgeDocument, distance.label("distance"))
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(
                KnowledgeChunk.project_id == project_id,
                KnowledgeDocument.approval_status == ApprovalStatus.APPROVED,
            )
            .order_by(distance.asc())
            .limit(limit)
        )

        retrieved: List[RetrievedChunk] = []
        for chunk, document, dist in result.all():
            retrieved.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    document_version=document.version,
                    content=chunk.content,
                    similarity=1.0 - float(dist),
                )
            )
        return retrieved
