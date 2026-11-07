from __future__ import annotations
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.api.deps import get_current_user, get_db_session, verify_same_origin
from backend.core.exceptions import ForbiddenException
from backend.models.user import User, UserRole
from backend.models.visit_reminder import ReminderStatus, ReminderType
from backend.schemas.reminder import VisitReminderListResponse, VisitReminderPublic
from backend.services.reminder_service import ReminderService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/reminders", tags=["Reminders"])


@router.get("", response_model=VisitReminderListResponse, summary="List site-visit reminders")
async def list_reminders(
    reminder_status: Optional[ReminderStatus] = Query(default=None, alias="status"),
    reminder_type: Optional[ReminderType] = Query(default=None, alias="type"),
    site_visit_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> VisitReminderListResponse:
    # A sales executive only sees reminders for visits assigned to them
    # (spec section 8); managers/admins get the broader operational view.
    executive_id = current_user.id if current_user.role == UserRole.SALES_EXECUTIVE else None

    reminders, total = await ReminderService.list_reminders(
        db,
        executive_id=executive_id,
        status=reminder_status,
        reminder_type=reminder_type,
        site_visit_id=site_visit_id,
        limit=limit,
        offset=offset,
    )
    return VisitReminderListResponse(items=[VisitReminderPublic.model_validate(r) for r in reminders], total=total)


@router.post("/{reminder_id}/retry", response_model=VisitReminderPublic, summary="Retry a failed reminder")
async def retry_reminder(
    reminder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    _origin_ok: None = Depends(verify_same_origin),
) -> VisitReminderPublic:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException("Only an admin may retry a reminder")

    reminder = await ReminderService.retry_reminder(db, reminder_id)
    return VisitReminderPublic.model_validate(reminder)
