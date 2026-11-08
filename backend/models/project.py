from __future__ import annotations
import enum
import uuid
from typing import List, Optional

from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin


class ProjectVisibility(str, enum.Enum):
    """
    Publication status gating public discovery, independent of `is_active`
    (which reflects whether a project is still an operational/sellable
    listing at all, used by AI retrieval and admin tooling since Feature 04).
    """

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class Project(Base, TimestampMixin):
    """
    A real-estate project (development) that buyers enquire about. Backs the
    structured "exact fact" half of hybrid retrieval (name/location/description)
    and owns the approved KnowledgeDocument/KnowledgeChunk rows used for
    descriptive, semantic retrieval. Also carries the small set of fields
    needed to publish a controlled public representation of the project
    (Feature 09) -- visibility/publication status is separate from
    `is_active`, which already meant "operational for internal use."
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- Public website fields (Feature 09) ---
    visibility_status: Mapped[ProjectVisibility] = mapped_column(
        Enum(ProjectVisibility, name="project_visibility", native_enum=True),
        nullable=False,
        default=ProjectVisibility.DRAFT,
        index=True,
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    configurations: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    amenities: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    images: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    starting_price_label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    price_display_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rera_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    floor_plan_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    documents: Mapped[List["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument", back_populates="project", cascade="all, delete-orphan"
    )
