from __future__ import annotations
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import BookingPrincipal, get_booking_principal, get_db_session, verify_same_origin
from backend.core.exceptions import ForbiddenException
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.models.user import UserRole
from backend.schemas.booking import (
    AttendanceUpdateRequest,
    BookingCreateRequest,
    BookingRescheduleRequest,
    SiteVisitDetail,
    SiteVisitDetailListResponse,
    SiteVisitListResponse,
    SiteVisitPublic,
)
from backend.schemas.reminder import VisitReminderListResponse, VisitReminderPublic
from backend.services.booking_service import BookingService
from backend.services.reminder_service import ReminderService
from backend.services.visit_display_service import VisitDisplayService

router = APIRouter(prefix="/bookings", tags=["Site Visit Bookings"])


def _require_access(principal: BookingPrincipal, visit: SiteVisit) -> None:
    """
    Staff (any authenticated role) may access any booking, matching the
    existing no-extra-RBAC pattern used for /leads and /conversations. A
    buyer may only access a booking tied to their own session-resolved lead.
    """
    if principal.is_staff:
        return
    if principal.buyer_lead_id != visit.lead_id:
        raise ForbiddenException("You do not have permission to access this booking")


def _require_executive_scope(principal: BookingPrincipal, visit: SiteVisit) -> None:
    """
    A sales executive may only access visits/reminders assigned to them;
    managers/admins (and buyers, already checked by _require_access) are
    unrestricted here.
    """
    if principal.is_staff and principal.user.role == UserRole.SALES_EXECUTIVE and visit.executive_id != principal.user.id:
        raise ForbiddenException("You do not have permission to access this booking")


@router.post(
    "", response_model=SiteVisitPublic, status_code=status.HTTP_201_CREATED, summary="Create a site-visit booking"
)
async def create_booking(
    payload: BookingCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    principal: BookingPrincipal = Depends(get_booking_principal),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    _origin_ok: None = Depends(verify_same_origin),
) -> SiteVisitPublic:
    if not principal.is_staff and principal.buyer_lead_id != payload.lead_id:
        raise ForbiddenException("You may only book a visit for your own lead")

    visit = await BookingService.book_site_visit(
        db,
        lead_id=payload.lead_id,
        project_id=payload.project_id,
        start_time=payload.start_time,
        idempotency_key=idempotency_key,
        actor_id=principal.user.id if principal.user else None,
    )
    return SiteVisitPublic.model_validate(visit)


@router.get("", response_model=SiteVisitDetailListResponse, summary="List authorized site-visit bookings")
async def list_bookings(
    project_id: Optional[uuid.UUID] = Query(default=None),
    executive_id: Optional[uuid.UUID] = Query(default=None),
    status_filter: Optional[SiteVisitStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    principal: BookingPrincipal = Depends(get_booking_principal),
) -> SiteVisitDetailListResponse:
    lead_id = None if principal.is_staff else principal.buyer_lead_id

    # A sales executive only sees visits assigned to them (spec section 8);
    # managers/admins keep the broader operational view and may still
    # filter by any executive_id.
    if principal.is_staff and principal.user.role == UserRole.SALES_EXECUTIVE:
        executive_id = principal.user.id

    visits, total = await BookingService.list_site_visits(
        db,
        lead_id=lead_id,
        project_id=project_id,
        executive_id=executive_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    items = await VisitDisplayService.to_details(db, visits)
    return SiteVisitDetailListResponse(items=items, total=total)


@router.get("/{booking_id}", response_model=SiteVisitDetail, summary="Retrieve a site-visit booking")
async def get_booking(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: BookingPrincipal = Depends(get_booking_principal),
) -> SiteVisitDetail:
    visit = await BookingService.get_site_visit(db, booking_id)
    _require_access(principal, visit)
    _require_executive_scope(principal, visit)
    details = await VisitDisplayService.to_details(db, [visit])
    return details[0]


@router.get(
    "/{booking_id}/reminders", response_model=VisitReminderListResponse, summary="Retrieve reminder history for a booking"
)
async def get_booking_reminders(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: BookingPrincipal = Depends(get_booking_principal),
) -> VisitReminderListResponse:
    if not principal.is_staff:
        raise ForbiddenException("Only staff may view reminder history")

    visit = await BookingService.get_site_visit(db, booking_id)
    _require_executive_scope(principal, visit)

    reminders = await ReminderService.list_reminders_for_visit(db, booking_id)
    return VisitReminderListResponse(
        items=[VisitReminderPublic.model_validate(r) for r in reminders], total=len(reminders)
    )


@router.post("/{booking_id}/cancel", response_model=SiteVisitPublic, summary="Cancel a site-visit booking")
async def cancel_booking(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: BookingPrincipal = Depends(get_booking_principal),
    _origin_ok: None = Depends(verify_same_origin),
) -> SiteVisitPublic:
    visit = await BookingService.get_site_visit(db, booking_id)
    _require_access(principal, visit)
    _require_executive_scope(principal, visit)
    updated = await BookingService.cancel_site_visit(
        db, booking_id, actor_id=principal.user.id if principal.user else None
    )
    return SiteVisitPublic.model_validate(updated)


@router.post("/{booking_id}/reschedule", response_model=SiteVisitPublic, summary="Reschedule a site-visit booking")
async def reschedule_booking(
    booking_id: uuid.UUID,
    payload: BookingRescheduleRequest,
    db: AsyncSession = Depends(get_db_session),
    principal: BookingPrincipal = Depends(get_booking_principal),
    _origin_ok: None = Depends(verify_same_origin),
) -> SiteVisitPublic:
    visit = await BookingService.get_site_visit(db, booking_id)
    _require_access(principal, visit)
    _require_executive_scope(principal, visit)
    updated = await BookingService.reschedule_site_visit(
        db, booking_id, new_start_time=payload.start_time, actor_id=principal.user.id if principal.user else None
    )
    return SiteVisitPublic.model_validate(updated)


@router.post(
    "/{booking_id}/attendance", response_model=SiteVisitPublic, summary="Record attendance for a site-visit booking"
)
async def record_attendance(
    booking_id: uuid.UUID,
    payload: AttendanceUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    principal: BookingPrincipal = Depends(get_booking_principal),
    _origin_ok: None = Depends(verify_same_origin),
) -> SiteVisitPublic:
    if not principal.is_staff:
        raise ForbiddenException("Only staff may record visit attendance")

    visit = await BookingService.get_site_visit(db, booking_id)
    _require_executive_scope(principal, visit)

    updated = await BookingService.record_attendance(
        db, booking_id, status=payload.status, actor_id=principal.user.id
    )
    return SiteVisitPublic.model_validate(updated)
