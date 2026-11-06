from __future__ import annotations
import hashlib
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db_session, require_roles
from backend.core.exceptions import ValidationException
from backend.core.logging import logger
from backend.models.lead import Lead, LeadStatus
from backend.models.lead_source import LeadSource, SourceType
from backend.models.potential_duplicate import DuplicateReviewStatus
from backend.models.user import User, UserRole
from backend.models.webhook_event import WebhookEvent
from backend.schemas.lead import (
    CsvImportResponse,
    DuplicateReviewRequest,
    IngestionResponse,
    LeadDetailResponse,
    LeadListItem,
    LeadListResponse,
    LeadSourcePublic,
    LeadUpdateRequest,
    ManualLeadCreateRequest,
    PotentialDuplicateListResponse,
    PotentialDuplicatePublic,
    WebhookLeadPayload,
)
from backend.services.csv_import_service import CsvImportService
from backend.services.lead_ingestion_service import LeadIngestionService
from backend.services.lead_service import LeadService
from backend.services.webhook_security_service import verify_webhook_signature

router = APIRouter(prefix="/leads", tags=["Leads"])

WEBHOOK_ELIGIBLE_SOURCES = {
    SourceType.WEBSITE,
    SourceType.PROPERTY_PORTAL,
    SourceType.SOCIAL_AD,
    SourceType.HOARDING,
}


@router.post("", response_model=IngestionResponse, status_code=status.HTTP_201_CREATED, summary="Create a manual lead")
async def create_manual_lead(
    payload: ManualLeadCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> IngestionResponse:
    result = await LeadIngestionService.ingest(
        db,
        full_name=payload.full_name,
        raw_phone=payload.phone,
        raw_email=payload.email,
        preferred_language=payload.preferred_language,
        source_type=SourceType.MANUAL,
        external_lead_id=None,
        campaign_name=payload.campaign_name,
        raw_payload={"notes": payload.notes} if payload.notes else {},
        consent_status=payload.consent_status,
    )
    return IngestionResponse(
        lead_id=result.lead.id,
        lead_source_id=result.lead_source.id,
        created_new_lead=result.created_new_lead,
        match_reason=result.resolution.match_reason,
    )


@router.post(
    "/webhooks/{source}",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Verified external-source webhook / website enquiry intake",
)
async def ingest_webhook_lead(
    source: str,
    request: Request,
    payload: WebhookLeadPayload,
    db: AsyncSession = Depends(get_db_session),
    x_webhook_signature: Optional[str] = Header(default=None, alias="X-Webhook-Signature"),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> IngestionResponse:
    try:
        source_type = SourceType(source.upper())
    except ValueError:
        raise ValidationException(f"Unknown source: {source}")

    if source_type not in WEBHOOK_ELIGIBLE_SOURCES:
        raise ValidationException(f"Source '{source}' does not accept webhook ingestion")

    raw_body = await request.body()
    verify_webhook_signature(source_type.value, raw_body, x_webhook_signature)

    resolved_idempotency_key = idempotency_key or hashlib.sha256(raw_body).hexdigest()

    existing_event_result = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.source_type == source_type,
            WebhookEvent.idempotency_key == resolved_idempotency_key,
        )
    )
    existing_event = existing_event_result.scalar_one_or_none()
    if existing_event is not None and existing_event.lead_source_id is not None:
        source_result = await db.execute(select(LeadSource).where(LeadSource.id == existing_event.lead_source_id))
        existing_source = source_result.scalar_one()
        return IngestionResponse(
            lead_id=existing_source.lead_id,
            lead_source_id=existing_source.id,
            created_new_lead=False,
            match_reason="IDEMPOTENT_REPLAY",
            idempotent_replay=True,
        )

    webhook_event = existing_event or WebhookEvent(source_type=source_type, idempotency_key=resolved_idempotency_key)
    if existing_event is None:
        db.add(webhook_event)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            logger.warning("Concurrent webhook idempotency key collision; request will be reprocessed as new")

    ingestion = await LeadIngestionService.ingest(
        db,
        full_name=payload.full_name,
        raw_phone=payload.phone,
        raw_email=payload.email,
        preferred_language=payload.preferred_language,
        source_type=source_type,
        external_lead_id=payload.external_lead_id,
        campaign_name=payload.campaign_name,
        raw_payload=payload.model_dump(mode="json"),
        submitted_at=payload.submitted_at,
        consent_status=payload.consent_status,
    )

    webhook_event.lead_source_id = ingestion.lead_source.id
    db.add(webhook_event)
    await db.commit()

    return IngestionResponse(
        lead_id=ingestion.lead.id,
        lead_source_id=ingestion.lead_source.id,
        created_new_lead=ingestion.created_new_lead,
        match_reason=ingestion.resolution.match_reason,
    )


@router.post(
    "/import",
    response_model=CsvImportResponse,
    summary="Bulk CSV lead import",
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
)
async def import_leads_csv(
    db: AsyncSession = Depends(get_db_session),
    file: UploadFile = File(...),
) -> CsvImportResponse:
    file_bytes = await file.read()
    return await CsvImportService.import_csv(db, file_bytes, file.filename or "upload.csv")


@router.get("", response_model=LeadListResponse, summary="List leads")
async def list_leads(
    search: Optional[str] = Query(default=None),
    source: Optional[SourceType] = Query(default=None),
    lead_status: Optional[LeadStatus] = Query(default=None),
    assigned_executive_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> LeadListResponse:
    leads, total, new_count = await LeadService.list_leads(
        db,
        search=search,
        source_type=source,
        lead_status=lead_status,
        assigned_executive_id=assigned_executive_id,
        limit=limit,
        offset=offset,
    )
    items = []
    for lead in leads:
        sources = await LeadService.get_sources_for_lead(db, lead.id)
        item = LeadListItem.model_validate(lead).model_copy(
            update={
                "source_count": len(sources),
                "latest_source_type": sources[0].source_type if sources else None,
            }
        )
        items.append(item)
    return LeadListResponse(items=items, total=total, new_count=new_count)


@router.get("/duplicates", response_model=PotentialDuplicateListResponse, summary="List potential duplicate matches")
async def list_potential_duplicates(
    review_status: Optional[DuplicateReviewStatus] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER)),
) -> PotentialDuplicateListResponse:
    matches, total = await LeadService.list_potential_duplicates(db, status=review_status, limit=limit, offset=offset)
    return PotentialDuplicateListResponse(
        items=[PotentialDuplicatePublic.model_validate(m) for m in matches], total=total
    )


@router.patch("/duplicates/{match_id}", response_model=PotentialDuplicatePublic, summary="Resolve a potential duplicate review")
async def review_potential_duplicate(
    match_id: uuid.UUID,
    payload: DuplicateReviewRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER)),
) -> PotentialDuplicatePublic:
    match = await LeadService.review_potential_duplicate(
        db, match_id, status=payload.status, reviewed_by_id=current_user.id
    )
    return PotentialDuplicatePublic.model_validate(match)


@router.get("/{lead_id}", response_model=LeadDetailResponse, summary="Get lead detail")
async def get_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> LeadDetailResponse:
    lead = await LeadService.get_lead_by_id(db, lead_id)
    sources = await LeadService.get_sources_for_lead(db, lead_id)
    return LeadDetailResponse.model_validate(lead).model_copy(
        update={"sources": [LeadSourcePublic.model_validate(s) for s in sources]}
    )


@router.patch("/{lead_id}", response_model=LeadDetailResponse, summary="Update a lead")
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> LeadDetailResponse:
    lead = await LeadService.update_lead(
        db,
        lead_id,
        full_name=payload.full_name,
        preferred_language=payload.preferred_language,
        lead_status=payload.lead_status,
        assigned_executive_id=payload.assigned_executive_id,
        consent_status=payload.consent_status,
    )
    sources = await LeadService.get_sources_for_lead(db, lead_id)
    return LeadDetailResponse.model_validate(lead).model_copy(
        update={"sources": [LeadSourcePublic.model_validate(s) for s in sources]}
    )


@router.get("/{lead_id}/sources", response_model=list[LeadSourcePublic], summary="List a lead's source enquiries")
async def get_lead_sources(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> list[LeadSourcePublic]:
    sources = await LeadService.get_sources_for_lead(db, lead_id)
    return [LeadSourcePublic.model_validate(s) for s in sources]
