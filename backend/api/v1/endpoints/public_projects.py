import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db_session
from backend.schemas.public_project import PublicProjectDetail, PublicProjectListResponse
from backend.services.public_project_service import PublicProjectService

router = APIRouter(prefix="/public/projects", tags=["Public - Project Discovery"])

# No auth dependency anywhere in this router -- the public website must work
# without authentication, and these endpoints never return anything beyond
# what PublicProjectService already gates to PUBLISHED projects (spec section 6/11).


@router.get("/featured", response_model=PublicProjectListResponse, summary="Featured published projects")
async def list_featured_projects(
    limit: int = Query(default=6, ge=1, le=20),
    db: AsyncSession = Depends(get_db_session),
) -> PublicProjectListResponse:
    items = await PublicProjectService.list_featured(db, limit=limit)
    return PublicProjectListResponse(items=items, total=len(items))


@router.get("", response_model=PublicProjectListResponse, summary="List published projects")
async def list_projects(
    search: Optional[str] = Query(default=None, max_length=255),
    location: Optional[str] = Query(default=None, max_length=255),
    configuration: Optional[str] = Query(default=None, max_length=50),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
) -> PublicProjectListResponse:
    items, total = await PublicProjectService.list_published(
        db, search=search, location=location, configuration=configuration, limit=limit, offset=offset
    )
    return PublicProjectListResponse(items=items, total=total)


@router.get("/{project_id}", response_model=PublicProjectDetail, summary="Published project detail")
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> PublicProjectDetail:
    return await PublicProjectService.get_published(db, project_id)
