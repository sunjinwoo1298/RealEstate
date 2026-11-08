from __future__ import annotations
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ConflictException, NotFoundException
from backend.models.project import Project, ProjectVisibility


class ProjectService:
    """CRUD for real-estate Project records (admin-managed project catalog)."""

    @staticmethod
    async def create_project(
        db: AsyncSession, *, name: str, description: Optional[str], location: Optional[str]
    ) -> Project:
        existing = await db.execute(select(Project).where(func.lower(Project.name) == name.strip().lower()))
        if existing.scalar_one_or_none() is not None:
            raise ConflictException("A project with this name already exists")

        # New projects always start DRAFT -- only an explicit ADMIN publish
        # action (ProjectService.update_project) can make one publicly visible.
        project = Project(
            name=name.strip(),
            description=description,
            location=location,
            is_active=True,
            visibility_status=ProjectVisibility.DRAFT,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project

    @staticmethod
    async def get_project(db: AsyncSession, project_id: uuid.UUID) -> Project:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project is None:
            raise NotFoundException("Project not found")
        return project

    @staticmethod
    async def find_by_name(db: AsyncSession, name: str) -> Optional[Project]:
        """Case-insensitive exact-name lookup used by the AI orchestrator to resolve which project a buyer is asking about."""
        result = await db.execute(
            select(Project).where(func.lower(Project.name) == name.strip().lower(), Project.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_projects(
        db: AsyncSession, *, is_active: Optional[bool] = None, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Project], int]:
        base_query = select(Project)
        count_query = select(func.count()).select_from(Project)
        if is_active is not None:
            base_query = base_query.where(Project.is_active == is_active)
            count_query = count_query.where(Project.is_active == is_active)

        total = (await db.execute(count_query)).scalar_one()
        base_query = base_query.order_by(Project.name.asc()).limit(limit).offset(offset)
        result = await db.execute(base_query)
        return list(result.scalars().all()), total

    @staticmethod
    async def update_project(
        db: AsyncSession,
        project_id: uuid.UUID,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        is_active: Optional[bool] = None,
        visibility_status: Optional[ProjectVisibility] = None,
        is_featured: Optional[bool] = None,
        configurations: Optional[List[str]] = None,
        amenities: Optional[List[str]] = None,
        images: Optional[List[str]] = None,
        starting_price_label: Optional[str] = None,
        price_display_approved: Optional[bool] = None,
        rera_number: Optional[str] = None,
        floor_plan_url: Optional[str] = None,
    ) -> Project:
        project = await ProjectService.get_project(db, project_id)
        if name is not None:
            project.name = name.strip()
        if description is not None:
            project.description = description
        if location is not None:
            project.location = location
        if is_active is not None:
            project.is_active = is_active
        if visibility_status is not None:
            project.visibility_status = visibility_status
        if is_featured is not None:
            project.is_featured = is_featured
        if configurations is not None:
            project.configurations = configurations
        if amenities is not None:
            project.amenities = amenities
        if images is not None:
            project.images = images
        if starting_price_label is not None:
            project.starting_price_label = starting_price_label
        if price_display_approved is not None:
            project.price_display_approved = price_display_approved
        if rera_number is not None:
            project.rera_number = rera_number
        if floor_plan_url is not None:
            project.floor_plan_url = floor_plan_url
        await db.commit()
        await db.refresh(project)
        return project
