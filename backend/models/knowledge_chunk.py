from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.config import settings
from backend.models.base import Base


class KnowledgeChunk(Base):
    """
    One embedded passage of a KnowledgeDocument. project_id is denormalized
    from the parent document so retrieval can filter by project without a
    join on the hot path. Only chunks whose document is APPROVED should ever
    be read by retrieval (enforced by RetrievalService's query, not here).
    """

    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(settings.EMBEDDING_DIMENSION), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    document: Mapped["KnowledgeDocument"] = relationship("KnowledgeDocument", back_populates="chunks")
