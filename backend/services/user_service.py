from __future__ import annotations
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ConflictException, NotFoundException
from backend.core.security import hash_password
from backend.models.user import User, UserRole


class UserService:
    """Admin-facing CRUD operations for staff accounts."""

    @staticmethod
    async def list_users(db: AsyncSession, limit: int = 50, offset: int = 0) -> Tuple[List[User], int]:
        total_result = await db.execute(select(func.count()).select_from(User))
        total = total_result.scalar_one()

        result = await db.execute(
            select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundException("Staff account not found")
        return user

    @staticmethod
    async def create_user(
        db: AsyncSession, email: str, full_name: str, password: str, role: UserRole
    ) -> User:
        normalized_email = email.strip().lower()
        existing = await db.execute(select(User).where(User.email == normalized_email))
        if existing.scalar_one_or_none() is not None:
            raise ConflictException("A staff account with this email already exists")

        user = User(
            email=normalized_email,
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def update_user(
        db: AsyncSession, user_id: uuid.UUID, full_name: Optional[str], role: Optional[UserRole]
    ) -> User:
        user = await UserService.get_user_by_id(db, user_id)
        if full_name is not None:
            user.full_name = full_name
        if role is not None:
            user.role = role
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def set_active_status(db: AsyncSession, user_id: uuid.UUID, is_active: bool) -> User:
        user = await UserService.get_user_by_id(db, user_id)
        user.is_active = is_active
        await db.commit()
        await db.refresh(user)
        return user
