import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db_session, require_roles
from backend.models.user import UserRole
from backend.schemas.user import (
    UserCreateRequest,
    UserListResponse,
    UserPublic,
    UserStatusUpdateRequest,
    UserUpdateRequest,
)
from backend.services.user_service import UserService

router = APIRouter(
    prefix="/admin/users",
    tags=["Admin - Staff Accounts"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


@router.get("", response_model=UserListResponse, summary="List staff accounts")
async def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
) -> UserListResponse:
    users, total = await UserService.list_users(db, limit=limit, offset=offset)
    return UserListResponse(items=[UserPublic.model_validate(u) for u in users], total=total)


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED, summary="Create staff account")
async def create_user(
    payload: UserCreateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> UserPublic:
    user = await UserService.create_user(
        db,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        role=payload.role,
    )
    return UserPublic.model_validate(user)


@router.patch("/{user_id}", response_model=UserPublic, summary="Update staff account")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> UserPublic:
    user = await UserService.update_user(db, user_id, full_name=payload.full_name, role=payload.role)
    return UserPublic.model_validate(user)


@router.patch("/{user_id}/status", response_model=UserPublic, summary="Activate/deactivate account")
async def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> UserPublic:
    user = await UserService.set_active_status(db, user_id, payload.is_active)
    return UserPublic.model_validate(user)
