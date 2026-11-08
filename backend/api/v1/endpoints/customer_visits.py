from __future__ import annotations
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_customer, get_db_session
from backend.models.customer_account import CustomerAccount
from backend.models.site_visit import SiteVisitStatus
from backend.schemas.customer_visit import (
    CustomerAvailableSlotPublic,
    CustomerAvailableSlotsResponse,
    CustomerSiteVisitListResponse,
    CustomerSiteVisitPublic,
    CustomerVisitCreateRequest,
    CustomerVisitRescheduleRequest,
)
from backend.services.customer_visit_display_service import CustomerVisitDisplayService
from backend.services.customer_visit_service import CustomerVisitService

# Prefix order matters: "/availability" must be registered before the
# dynamic "/{visit_id}" routes below, or FastAPI will try (and fail) to
# parse the literal path segment "availability" as a UUID.
router = APIRouter(prefix="/customer/visits", tags=["Customer Site Visits"])


@router.get(
    "/availability",
    response_model=CustomerAvailableSlotsResponse,
    summary="Get available site-visit slots for a published project and date",
)
async def get_customer_available_slots(
    project_id: uuid.UUID = Query(...),
    target_date: date = Query(..., alias="date"),
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerAvailableSlotsResponse:
    slots = await CustomerVisitService.get_available_slots(db, project_id=project_id, target_date=target_date)
    return CustomerAvailableSlotsResponse(
        project_id=project_id,
        date=target_date,
        slots=[CustomerAvailableSlotPublic(start_time=s.start_time, end_time=s.end_time) for s in slots],
    )


@router.post(
    "",
    response_model=CustomerSiteVisitPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Book a site visit for the authenticated customer's own enquiry",
)
async def create_customer_booking(
    payload: CustomerVisitCreateRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerSiteVisitPublic:
    visit = await CustomerVisitService.create_booking(
        db,
        current_customer,
        project_id=payload.project_id,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        idempotency_key=idempotency_key,
    )
    details = await CustomerVisitDisplayService.to_details(db, [visit])
    return details[0]


@router.get(
    "",
    response_model=CustomerSiteVisitListResponse,
    summary="List the authenticated customer's own site-visit bookings",
)
async def list_customer_bookings(
    status_filter: Optional[SiteVisitStatus] = Query(default=None, alias="status"),
    upcoming: Optional[bool] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerSiteVisitListResponse:
    visits, total = await CustomerVisitService.list_visits(
        db, current_customer, status=status_filter, upcoming=upcoming, limit=limit, offset=offset
    )
    items = await CustomerVisitDisplayService.to_details(db, visits)
    return CustomerSiteVisitListResponse(items=items, total=total)


@router.get(
    "/{visit_id}",
    response_model=CustomerSiteVisitPublic,
    summary="Retrieve the customer's own site-visit booking",
)
async def get_customer_booking(
    visit_id: uuid.UUID,
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerSiteVisitPublic:
    visit = await CustomerVisitService.get_owned_visit(db, current_customer, visit_id)
    details = await CustomerVisitDisplayService.to_details(db, [visit])
    return details[0]


@router.patch(
    "/{visit_id}/reschedule",
    response_model=CustomerSiteVisitPublic,
    summary="Reschedule the customer's own eligible site-visit booking",
)
async def reschedule_customer_booking(
    visit_id: uuid.UUID,
    payload: CustomerVisitRescheduleRequest,
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerSiteVisitPublic:
    visit = await CustomerVisitService.reschedule_visit(
        db,
        current_customer,
        visit_id,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
    )
    details = await CustomerVisitDisplayService.to_details(db, [visit])
    return details[0]


@router.post(
    "/{visit_id}/cancel",
    response_model=CustomerSiteVisitPublic,
    summary="Cancel the customer's own eligible site-visit booking",
)
async def cancel_customer_booking(
    visit_id: uuid.UUID,
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerSiteVisitPublic:
    visit = await CustomerVisitService.cancel_visit(db, current_customer, visit_id)
    details = await CustomerVisitDisplayService.to_details(db, [visit])
    return details[0]
