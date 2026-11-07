from __future__ import annotations
import uuid
from datetime import date, time
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import BookingPrincipal, get_booking_principal, get_db_session, require_roles
from backend.core.exceptions import NotFoundException, ValidationException
from backend.models.availability_rule import AvailabilityRule
from backend.models.blocked_period import BlockedPeriod
from backend.models.user import User, UserRole
from backend.schemas.availability import (
    AvailabilityRuleCreateRequest,
    AvailabilityRuleListResponse,
    AvailabilityRulePublic,
    AvailabilityRuleUpdateRequest,
    AvailableSlotPublic,
    AvailableSlotsResponse,
    BlockedPeriodCreateRequest,
    BlockedPeriodPublic,
    ProjectVisitCapacityPublic,
    ProjectVisitCapacityUpsertRequest,
)
from backend.services.availability_service import AvailabilityService

router = APIRouter(prefix="/availability", tags=["Availability"])
admin_rules_router = APIRouter(
    prefix="/admin/availability-rules",
    tags=["Admin - Availability Rules"],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
)
admin_blocked_router = APIRouter(
    prefix="/admin/blocked-periods",
    tags=["Admin - Blocked Periods"],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
)
admin_capacity_router = APIRouter(
    prefix="/admin/visit-capacity",
    tags=["Admin - Visit Capacity"],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
)


@router.get("", response_model=AvailableSlotsResponse, summary="Retrieve dynamically available site-visit slots")
async def get_available_slots(
    project_id: uuid.UUID = Query(...),
    target_date: date = Query(..., alias="date"),
    preferred_start_time: Optional[time] = Query(default=None),
    preferred_end_time: Optional[time] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    _principal: BookingPrincipal = Depends(get_booking_principal),
) -> AvailableSlotsResponse:
    slots = await AvailabilityService.get_available_slots(
        db,
        project_id=project_id,
        target_date=target_date,
        preferred_start_time=preferred_start_time,
        preferred_end_time=preferred_end_time,
    )
    return AvailableSlotsResponse(
        project_id=project_id,
        date=target_date,
        slots=[
            AvailableSlotPublic(
                start_time=s.start_time, end_time=s.end_time, available_executive_count=s.available_executive_count
            )
            for s in slots
        ],
    )


# --- Admin: executive availability rules ---


@admin_rules_router.get("", response_model=AvailabilityRuleListResponse, summary="List availability rules")
async def list_availability_rules(
    executive_id: Optional[uuid.UUID] = Query(default=None),
    project_id: Optional[uuid.UUID] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> AvailabilityRuleListResponse:
    query = select(AvailabilityRule)
    if executive_id is not None:
        query = query.where(AvailabilityRule.executive_id == executive_id)
    if project_id is not None:
        query = query.where(AvailabilityRule.project_id == project_id)
    result = await db.execute(query.order_by(AvailabilityRule.day_of_week, AvailabilityRule.start_time))
    rules = list(result.scalars().all())
    return AvailabilityRuleListResponse(
        items=[AvailabilityRulePublic.model_validate(r) for r in rules], total=len(rules)
    )


@admin_rules_router.post(
    "", response_model=AvailabilityRulePublic, status_code=status.HTTP_201_CREATED, summary="Create availability rule"
)
async def create_availability_rule(
    payload: AvailabilityRuleCreateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AvailabilityRulePublic:
    executive_result = await db.execute(
        select(User).where(User.id == payload.executive_id, User.role == UserRole.SALES_EXECUTIVE)
    )
    if executive_result.scalar_one_or_none() is None:
        raise NotFoundException("Sales executive not found")

    rule = AvailabilityRule(
        executive_id=payload.executive_id,
        project_id=payload.project_id,
        day_of_week=payload.day_of_week,
        start_time=payload.start_time,
        end_time=payload.end_time,
        is_active=payload.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return AvailabilityRulePublic.model_validate(rule)


@admin_rules_router.put("/{rule_id}", response_model=AvailabilityRulePublic, summary="Update availability rule")
async def update_availability_rule(
    rule_id: uuid.UUID,
    payload: AvailabilityRuleUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AvailabilityRulePublic:
    result = await db.execute(select(AvailabilityRule).where(AvailabilityRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise NotFoundException("Availability rule not found")

    if payload.day_of_week is not None:
        rule.day_of_week = payload.day_of_week
    if payload.start_time is not None:
        rule.start_time = payload.start_time
    if payload.end_time is not None:
        rule.end_time = payload.end_time
    if payload.is_active is not None:
        rule.is_active = payload.is_active

    if rule.end_time <= rule.start_time:
        raise ValidationException("end_time must be after start_time")

    await db.commit()
    await db.refresh(rule)
    return AvailabilityRulePublic.model_validate(rule)


@admin_rules_router.delete(
    "/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove an availability rule"
)
async def delete_availability_rule(rule_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)) -> None:
    result = await db.execute(select(AvailabilityRule).where(AvailabilityRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise NotFoundException("Availability rule not found")
    await db.delete(rule)
    await db.commit()


# --- Admin: blocked periods ---


@admin_blocked_router.get("", response_model=list[BlockedPeriodPublic], summary="List blocked periods")
async def list_blocked_periods(
    executive_id: Optional[uuid.UUID] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> list[BlockedPeriodPublic]:
    query = select(BlockedPeriod)
    if executive_id is not None:
        query = query.where(BlockedPeriod.executive_id == executive_id)
    result = await db.execute(query.order_by(BlockedPeriod.start_time.desc()))
    return [BlockedPeriodPublic.model_validate(bp) for bp in result.scalars().all()]


@admin_blocked_router.post(
    "", response_model=BlockedPeriodPublic, status_code=status.HTTP_201_CREATED, summary="Block executive availability"
)
async def create_blocked_period(
    payload: BlockedPeriodCreateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> BlockedPeriodPublic:
    executive_result = await db.execute(
        select(User).where(User.id == payload.executive_id, User.role == UserRole.SALES_EXECUTIVE)
    )
    if executive_result.scalar_one_or_none() is None:
        raise NotFoundException("Sales executive not found")

    blocked_period = BlockedPeriod(
        executive_id=payload.executive_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        reason=payload.reason,
    )
    db.add(blocked_period)
    await db.commit()
    await db.refresh(blocked_period)
    return BlockedPeriodPublic.model_validate(blocked_period)


@admin_blocked_router.delete(
    "/{blocked_period_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a blocked period"
)
async def delete_blocked_period(blocked_period_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)) -> None:
    result = await db.execute(select(BlockedPeriod).where(BlockedPeriod.id == blocked_period_id))
    blocked_period = result.scalar_one_or_none()
    if blocked_period is None:
        raise NotFoundException("Blocked period not found")
    await db.delete(blocked_period)
    await db.commit()


# --- Admin: project visit capacity ---


@admin_capacity_router.get(
    "/{project_id}", response_model=ProjectVisitCapacityPublic, summary="Get project visit capacity configuration"
)
async def get_visit_capacity(project_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)) -> ProjectVisitCapacityPublic:
    capacity = await AvailabilityService.get_visit_capacity(db, project_id)
    return ProjectVisitCapacityPublic.model_validate(capacity)


@admin_capacity_router.put(
    "", response_model=ProjectVisitCapacityPublic, summary="Configure project visit capacity/duration/buffer"
)
async def upsert_visit_capacity(
    payload: ProjectVisitCapacityUpsertRequest, db: AsyncSession = Depends(get_db_session)
) -> ProjectVisitCapacityPublic:
    capacity = await AvailabilityService.upsert_visit_capacity(
        db,
        payload.project_id,
        capacity=payload.capacity,
        visit_duration_minutes=payload.visit_duration_minutes,
        buffer_minutes=payload.buffer_minutes,
    )
    return ProjectVisitCapacityPublic.model_validate(capacity)
