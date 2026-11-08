from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import logger
from backend.models.lead import ConsentStatus, Lead
from backend.models.lead_source import LeadSource, SourceType
from backend.services.identity_resolution_service import IdentityResolutionService, ResolutionResult
from backend.services.normalization_service import normalize_email, normalize_phone_optional


@dataclass
class IngestionResult:
    lead: Lead
    lead_source: LeadSource
    created_new_lead: bool
    resolution: ResolutionResult


class LeadIngestionService:
    """
    Coordinates identity resolution and source attribution for every lead
    ingestion channel (website, webhook, manual, CSV import). Each call is
    one atomic unit: either both the Lead (if new) and its LeadSource commit
    together, or neither does.
    """

    @staticmethod
    async def ingest(
        db: AsyncSession,
        *,
        full_name: str,
        raw_phone: Optional[str],
        raw_email: Optional[str],
        preferred_language: Optional[str],
        source_type: SourceType,
        external_lead_id: Optional[str],
        campaign_name: Optional[str],
        raw_payload: Dict[str, Any],
        submitted_at: Optional[datetime] = None,
        consent_status: ConsentStatus = ConsentStatus.NOT_RECORDED,
    ) -> IngestionResult:
        normalized_phone = normalize_phone_optional(raw_phone)
        normalized_email_value = normalize_email(raw_email)

        resolution = await IdentityResolutionService.resolve_or_create(
            db,
            full_name=full_name,
            normalized_phone=normalized_phone,
            normalized_email=normalized_email_value,
            source_type=source_type,
            external_lead_id=external_lead_id,
            preferred_language=preferred_language,
            consent_status=consent_status,
        )

        lead_source = LeadSource(
            lead_id=resolution.lead.id,
            source_type=source_type,
            external_lead_id=external_lead_id,
            campaign_name=campaign_name,
            raw_payload=raw_payload,
            submitted_at=submitted_at or datetime.now(timezone.utc),
        )
        db.add(lead_source)
        try:
            await db.commit()
        except IntegrityError:
            # Same (source_type, external_lead_id) already recorded, most likely
            # a duplicate resubmission that bypassed the webhook idempotency
            # ledger (e.g. manual/CSV re-entry). Recover the existing record
            # rather than failing the request.
            await db.rollback()
            logger.warning("Duplicate lead_source resubmission detected; returning existing record")
            if external_lead_id:
                result = await db.execute(
                    select(LeadSource).where(
                        LeadSource.source_type == source_type,
                        LeadSource.external_lead_id == external_lead_id,
                    )
                )
                existing_source = result.scalar_one_or_none()
                if existing_source is not None:
                    lead_result = await db.execute(select(Lead).where(Lead.id == existing_source.lead_id))
                    resolution.lead = lead_result.scalar_one()
                    lead_source = existing_source
                    resolution.created_new_lead = False
                else:
                    raise
            else:
                raise
        else:
            await db.refresh(resolution.lead)
            await db.refresh(lead_source)

        return IngestionResult(
            lead=resolution.lead,
            lead_source=lead_source,
            created_new_lead=resolution.created_new_lead,
            resolution=resolution,
        )
