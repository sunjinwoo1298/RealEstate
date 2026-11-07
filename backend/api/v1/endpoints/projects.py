import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db_session, require_roles
from backend.models.user import UserRole
from backend.schemas.project import ProjectCreateRequest, ProjectListResponse, ProjectPublic, ProjectUpdateRequest
from backend.services.project_service import ProjectService

router = APIRouter(
    prefix="/admin/projects",
    tags=["Admin - Projects"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


@router.get("", response_model=ProjectListResponse, summary="List real-estate projects")
async def list_projects(
    is_active: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
) -> ProjectListResponse:
    projects, total = await ProjectService.list_projects(db, is_active=is_active, limit=limit, offset=offset)
    return ProjectListResponse(items=[ProjectPublic.model_validate(p) for p in projects], total=total)


@router.post("", response_model=ProjectPublic, status_code=status.HTTP_201_CREATED, summary="Create a project")
async def create_project(
    payload: ProjectCreateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ProjectPublic:
    project = await ProjectService.create_project(
        db, name=payload.name, description=payload.description, location=payload.location
    )
    return ProjectPublic.model_validate(project)


@router.get("/{project_id}", response_model=ProjectPublic, summary="Get project detail")
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ProjectPublic:
    project = await ProjectService.get_project(db, project_id)
    return ProjectPublic.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectPublic, summary="Update a project")
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ProjectPublic:
    project = await ProjectService.update_project(
        db,
        project_id,
        name=payload.name,
        description=payload.description,
        location=payload.location,
        is_active=payload.is_active,
    )
    return ProjectPublic.model_validate(project)
