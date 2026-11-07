from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin


class ApprovalStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


class KnowledgeDocument(Base, TimestampMixin):
    """
    One version of an uploaded project fact sheet. Multiple rows can share the
    same (project_id, title) across versions; only the single most-recently
    approved version is eligible to ground AI responses (enforced by
    KnowledgeService, not a DB constraint, since ARCHIVED/DRAFT history must
    be preserved rather than deleted).
    """

    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status", native_enum=True),
        nullable=False,
        default=ApprovalStatus.DRAFT,
    )
    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="documents")
    chunks: Mapped[List["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk", back_populates="document", cascade="all, delete-orphan"
    )
