from __future__ import annotations
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db_session, verify_same_origin
from backend.core.exceptions import ForbiddenException
from backend.models.handoff import HandoffStatus
from backend.models.user import User, UserRole
from backend.schemas.handoff import (
    ConversationAssignmentPublic,
    HandoffDetail,
    HandoffListItem,
    HandoffListResponse,
    HandoffPublic,
    HandoffQualificationSummary,
    HandoffReassignRequest,
    HandoffRejectRequest,
    HandoffSiteVisitSummary,
)
from backend.services.assignment_service import AssignmentService
from backend.services.handoff_service import HandoffService

router = APIRouter(prefix="/handoffs", tags=["Human Handoff"])


def _require_manager_or_admin(current_user: User) -> None:
    if current_user.role not in (UserRole.MANAGER, UserRole.ADMIN):
        raise ForbiddenException("Only a manager or admin may perform this action")


def _require_sales_executive(current_user: User) -> None:
    if current_user.role != UserRole.SALES_EXECUTIVE:
        raise ForbiddenException("Only the assigned sales executive may perform this action")


async def _to_detail(db: AsyncSession, handoff) -> HandoffDetail:
    context = await HandoffService.get_detail_context(db, handoff)
    lead = context["lead"]
    qualification = context["qualification"]

    qualification_summary = None
    if qualification is not None:
        qualification_summary = HandoffQualificationSummary(
            project_id=qualification.project_id,
            configuration=qualification.configuration,
            budget_min=float(qualification.budget_min) if qualification.budget_min is not None else None,
            budget_max=float(qualification.budget_max) if qualification.budget_max is not None else None,
            purchase_purpose=qualification.purchase_purpose,
            preferred_visit_date=(
                qualification.preferred_visit_date.isoformat() if qualification.preferred_visit_date else None
            ),
        )

    # Built from HandoffPublic (the Handoff row's own columns only) rather
    # than HandoffDetail.model_validate(handoff) directly: HandoffDetail's
    # field names overlap with Handoff's unloaded ORM relationships (e.g.
    # "assignments"), and pydantic reading those via getattr triggers a
    # lazy-load outside of any async greenlet.
    base = HandoffPublic.model_validate(handoff).model_dump()
    return HandoffDetail(
        **base,
        lead_full_name=lead.full_name,
        lead_normalized_phone=lead.normalized_phone,
        lead_normalized_email=lead.normalized_email,
        lead_preferred_language=lead.preferred_language,
        source_types=context["source_types"],
        qualification=qualification_summary,
        site_visits=[HandoffSiteVisitSummary.model_validate(v) for v in context["site_visits"]],
        assignments=[ConversationAssignmentPublic.model_validate(a) for a in context["assignments"]],
        conversation_ownership_status=context["conversation"].ownership_status,
    )


@router.get("", response_model=HandoffListResponse, summary="List handoffs")
async def list_handoffs(
    handoff_status: Optional[HandoffStatus] = Query(default=None, alias="status"),
    mine: bool = Query(default=False, description="Only handoffs assigned to the current user"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> HandoffListResponse:
    assigned_executive_id = current_user.id if mine else None
    rows, total = await HandoffService.list_handoffs(
        db, status=handoff_status, assigned_executive_id=assigned_executive_id, limit=limit, offset=offset
    )
    items = [
        HandoffListItem.model_validate(handoff).model_copy(
            update={"lead_full_name": lead.full_name, "lead_normalized_phone": lead.normalized_phone}
        )
        for handoff, lead in rows
    ]
    return HandoffListResponse(items=items, total=total)


@router.get("/{handoff_id}", response_model=HandoffDetail, summary="Get full handoff context")
async def get_handoff(
    handoff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> HandoffDetail:
    handoff = await HandoffService.get_handoff(db, handoff_id)
    return await _to_detail(db, handoff)


@router.post("/{handoff_id}/accept", response_model=HandoffDetail, summary="Accept an assigned handoff")
async def accept_handoff(
    handoff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    _origin_ok: None = Depends(verify_same_origin),
) -> HandoffDetail:
    _require_sales_executive(current_user)
    handoff = await AssignmentService.accept(db, handoff_id, executive=current_user)
    return await _to_detail(db, handoff)


@router.post("/{handoff_id}/reject", response_model=HandoffDetail, summary="Reject an assigned handoff")
async def reject_handoff(
    handoff_id: uuid.UUID,
    payload: HandoffRejectRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    _origin_ok: None = Depends(verify_same_origin),
) -> HandoffDetail:
    _require_sales_executive(current_user)
    handoff = await AssignmentService.reject(db, handoff_id, executive=current_user, reason=payload.reason)
    return await _to_detail(db, handoff)


@router.post("/{handoff_id}/reassign", response_model=HandoffDetail, summary="Manually reassign a handoff")
async def reassign_handoff(
    handoff_id: uuid.UUID,
    payload: HandoffReassignRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    _origin_ok: None = Depends(verify_same_origin),
) -> HandoffDetail:
    _require_manager_or_admin(current_user)
    await AssignmentService.reassign(
        db, handoff_id, new_executive_id=payload.executive_id, assigned_by=current_user.id
    )
    handoff = await HandoffService.get_handoff(db, handoff_id)
    return await _to_detail(db, handoff)


@router.post("/{handoff_id}/resolve", response_model=HandoffDetail, summary="Resolve a handoff")
async def resolve_handoff(
    handoff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    _origin_ok: None = Depends(verify_same_origin),
) -> HandoffDetail:
    handoff = await HandoffService.get_handoff(db, handoff_id)
    if current_user.role not in (UserRole.MANAGER, UserRole.ADMIN) and handoff.assigned_executive_id != current_user.id:
        raise ForbiddenException("Only the assigned executive or a manager/admin may resolve this handoff")

    handoff = await HandoffService.resolve_handoff(db, handoff_id, actor_id=current_user.id)
    return await _to_detail(db, handoff)
