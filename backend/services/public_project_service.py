from __future__ import annotations
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundException
from backend.models.project import Project, ProjectVisibility
from backend.schemas.public_project import PublicProjectCard, PublicProjectDetail

_DEFAULT_FEATURED_LIMIT = 6
_MAX_FEATURED_LIMIT = 20


def _to_card(project: Project) -> PublicProjectCard:
    images = project.images or []
    return PublicProjectCard(
        id=project.id,
        name=project.name,
        location=project.location,
        description=project.description,
        configurations=project.configurations or [],
        primary_image=images[0] if images else None,
        starting_price_label=(
            project.starting_price_label if project.price_display_approved else None
        ),
        is_featured=project.is_featured,
    )


def _to_detail(project: Project) -> PublicProjectDetail:
    card = _to_card(project)
    return PublicProjectDetail(
        **card.model_dump(),
        amenities=project.amenities or [],
        images=project.images or [],
        rera_number=project.rera_number,
        floor_plan_url=project.floor_plan_url,
    )


class PublicProjectService:
    """
    Read-only, publication-gated access to `Project` for the unauthenticated
    public website (Feature 09). Every query filters on
    `visibility_status == PUBLISHED` at the database level -- a draft or
    archived project is never reachable through this service, even by id.
    """

    @staticmethod
    async def list_published(
        db: AsyncSession,
        *,
        search: Optional[str] = None,
        location: Optional[str] = None,
        configuration: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[PublicProjectCard], int]:
        base_query = select(Project).where(Project.visibility_status == ProjectVisibility.PUBLISHED)
        count_query = select(func.count()).select_from(Project).where(
            Project.visibility_status == ProjectVisibility.PUBLISHED
        )

        if search:
            name_filter = Project.name.ilike(f"%{search.strip()}%")
            base_query = base_query.where(name_filter)
            count_query = count_query.where(name_filter)
        if location:
            location_filter = Project.location.ilike(f"%{location.strip()}%")
            base_query = base_query.where(location_filter)
            count_query = count_query.where(location_filter)
        if configuration:
            # JSONB "?" operator: does the `configurations` array contain this
            # exact string as a top-level element?
            config_filter = Project.configurations.op("?")(configuration.strip())
            base_query = base_query.where(config_filter)
            count_query = count_query.where(config_filter)

        total = (await db.execute(count_query)).scalar_one()
        base_query = base_query.order_by(Project.name.asc()).limit(limit).offset(offset)
        result = await db.execute(base_query)
        projects = list(result.scalars().all())
        return [_to_card(p) for p in projects], total

    @staticmethod
    async def list_featured(db: AsyncSession, *, limit: int = _DEFAULT_FEATURED_LIMIT) -> List[PublicProjectCard]:
        limit = min(limit, _MAX_FEATURED_LIMIT)
        query = (
            select(Project)
            .where(
                Project.visibility_status == ProjectVisibility.PUBLISHED,
                Project.is_featured.is_(True),
            )
            .order_by(Project.name.asc())
            .limit(limit)
        )
        result = await db.execute(query)
        return [_to_card(p) for p in result.scalars().all()]

    @staticmethod
    async def get_published(db: AsyncSession, project_id: uuid.UUID) -> PublicProjectDetail:
        result = await db.execute(
            select(Project).where(
                Project.id == project_id, Project.visibility_status == ProjectVisibility.PUBLISHED
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise NotFoundException("Project not found")
        return _to_detail(project)
