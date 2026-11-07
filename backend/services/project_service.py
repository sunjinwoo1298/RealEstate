from __future__ import annotations
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ConflictException, NotFoundException
from backend.models.project import Project


class ProjectService:
    """CRUD for real-estate Project records (admin-managed project catalog)."""

    @staticmethod
    async def create_project(
        db: AsyncSession, *, name: str, description: Optional[str], location: Optional[str]
    ) -> Project:
        existing = await db.execute(select(Project).where(func.lower(Project.name) == name.strip().lower()))
        if existing.scalar_one_or_none() is not None:
            raise ConflictException("A project with this name already exists")

        project = Project(name=name.strip(), description=description, location=location, is_active=True)
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
        await db.commit()
        await db.refresh(project)
        return project
