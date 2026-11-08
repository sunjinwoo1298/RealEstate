from __future__ import annotations
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db_session
from backend.models.lead_source import SourceType
from backend.models.user import User
from backend.schemas.analytics import (
    DateRangePreset,
    ExecutiveAnalyticsResponse,
    FunnelAnalyticsResponse,
    LeadAnalyticsResponse,
    OverviewResponse,
    QualificationAnalyticsResponse,
    ReminderAnalyticsResponse,
    ReminderDateBasis,
    ResponseTimeAnalyticsResponse,
    SiteVisitAnalyticsResponse,
    SourceAnalyticsResponse,
    VisitDateBasis,
)
from backend.services.analytics_service import AnalyticsFilters, AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


async def get_analytics_filters(
    date_range: DateRangePreset = Query(default=DateRangePreset.LAST_30_DAYS, alias="range"),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    project_id: Optional[uuid.UUID] = Query(default=None),
    source_type: Optional[SourceType] = Query(default=None),
    executive_id: Optional[uuid.UUID] = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> AnalyticsFilters:
    """
    Shared filter dependency for every analytics endpoint. Role scoping
    (spec section 3) is enforced here, not in the frontend: a SALES_EXECUTIVE
    caller's executive_id is always forced to their own id regardless of
    what (if anything) was requested in the query string.
    """
    return AnalyticsService.build_filters(
        preset=date_range,
        date_from=date_from,
        date_to=date_to,
        project_id=project_id,
        source_type=source_type,
        executive_id=executive_id,
        current_user=current_user,
    )


@router.get("/overview", response_model=OverviewResponse, summary="Top-level analytics overview")
async def get_overview(
    filters: AnalyticsFilters = Depends(get_analytics_filters),
    db: AsyncSession = Depends(get_db_session),
) -> OverviewResponse:
    result = await AnalyticsService.get_overview(db, filters)
    return OverviewResponse(**result)


@router.get("/leads", response_model=LeadAnalyticsResponse, summary="Lead acquisition analytics")
async def get_lead_analytics(
    filters: AnalyticsFilters = Depends(get_analytics_filters),
    db: AsyncSession = Depends(get_db_session),
) -> LeadAnalyticsResponse:
    result = await AnalyticsService.get_leads(db, filters)
    return LeadAnalyticsResponse(**result)


@router.get("/sources", response_model=SourceAnalyticsResponse, summary="Lead source performance analytics")
async def get_source_analytics(
    filters: AnalyticsFilters = Depends(get_analytics_filters),
    db: AsyncSession = Depends(get_db_session),
) -> SourceAnalyticsResponse:
    result = await AnalyticsService.get_sources(db, filters)
    return SourceAnalyticsResponse(**result)


@router.get("/response-times", response_model=ResponseTimeAnalyticsResponse, summary="First-response time analytics")
async def get_response_time_analytics(
    filters: AnalyticsFilters = Depends(get_analytics_filters),
    db: AsyncSession = Depends(get_db_session),
) -> ResponseTimeAnalyticsResponse:
    result = await AnalyticsService.get_response_times(db, filters)
    return ResponseTimeAnalyticsResponse(**result)


@router.get("/qualification", response_model=QualificationAnalyticsResponse, summary="AI qualification analytics")
async def get_qualification_analytics(
    filters: AnalyticsFilters = Depends(get_analytics_filters),
    db: AsyncSession = Depends(get_db_session),
) -> QualificationAnalyticsResponse:
    result = await AnalyticsService.get_qualification(db, filters)
    return QualificationAnalyticsResponse(**result)


@router.get("/funnel", response_model=FunnelAnalyticsResponse, summary="Sales funnel analytics")
async def get_funnel_analytics(
    filters: AnalyticsFilters = Depends(get_analytics_filters),
    db: AsyncSession = Depends(get_db_session),
) -> FunnelAnalyticsResponse:
    result = await AnalyticsService.get_funnel(db, filters)
    return FunnelAnalyticsResponse(**result)


@router.get("/site-visits", response_model=SiteVisitAnalyticsResponse, summary="Site visit and attendance analytics")
async def get_site_visit_analytics(
    date_basis: VisitDateBasis = Query(default=VisitDateBasis.BOOKING),
    filters: AnalyticsFilters = Depends(get_analytics_filters),
    db: AsyncSession = Depends(get_db_session),
) -> SiteVisitAnalyticsResponse:
    result = await AnalyticsService.get_site_visits(db, filters, date_basis)
    return SiteVisitAnalyticsResponse(**result)


@router.get("/executives", response_model=ExecutiveAnalyticsResponse, summary="Sales executive performance comparison")
async def get_executive_analytics(
    filters: AnalyticsFilters = Depends(get_analytics_filters),
    db: AsyncSession = Depends(get_db_session),
) -> ExecutiveAnalyticsResponse:
    # No extra role gate needed beyond authentication: get_analytics_filters
    # already forces executive_id to "self" for SALES_EXECUTIVE, so the
    # executives list naturally contains at most their own row (spec
    # section 10's "sales executives should see only their own performance").
    result = await AnalyticsService.get_executives(db, filters)
    return ExecutiveAnalyticsResponse(**result)


@router.get("/reminders", response_model=ReminderAnalyticsResponse, summary="Reminder execution analytics")
async def get_reminder_analytics(
    date_basis: ReminderDateBasis = Query(default=ReminderDateBasis.CREATED),
    filters: AnalyticsFilters = Depends(get_analytics_filters),
    db: AsyncSession = Depends(get_db_session),
) -> ReminderAnalyticsResponse:
    result = await AnalyticsService.get_reminders(db, filters, date_basis)
    return ReminderAnalyticsResponse(**result)
