from __future__ import annotations
import uuid
from typing import List, Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    """
    A real-estate project (development) that buyers enquire about. Backs the
    structured "exact fact" half of hybrid retrieval (name/location/description)
    and owns the approved KnowledgeDocument/KnowledgeChunk rows used for
    descriptive, semantic retrieval.
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    documents: Mapped[List["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument", back_populates="project", cascade="all, delete-orphan"
    )
