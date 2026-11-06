from __future__ import annotations
import difflib
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.logging import logger
from backend.models.lead import ConsentStatus, Lead
from backend.models.lead_source import LeadSource, SourceType
from backend.models.potential_duplicate import PotentialDuplicateMatch


@dataclass
class ResolutionResult:
    lead: Lead
    created_new_lead: bool
    match_reason: str
    potential_duplicate: Optional[PotentialDuplicateMatch] = None


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


class IdentityResolutionService:
    """
    Resolves an incoming enquiry to an existing buyer (Lead) or creates a new
    canonical Lead. Matching priority: exact phone -> exact email -> matching
    external lead id within its source -> name similarity (signal only, never
    auto-merged; stored for manual review instead).
    """

    @staticmethod
    async def _find_by_phone(db: AsyncSession, normalized_phone: str) -> Optional[Lead]:
        result = await db.execute(select(Lead).where(Lead.normalized_phone == normalized_phone))
        return result.scalar_one_or_none()

    @staticmethod
    async def _find_by_email(db: AsyncSession, normalized_email: str) -> Optional[Lead]:
        result = await db.execute(select(Lead).where(Lead.normalized_email == normalized_email))
        return result.scalar_one_or_none()

    @staticmethod
    async def _find_by_external_id(
        db: AsyncSession, source_type: SourceType, external_lead_id: str
    ) -> Optional[Lead]:
        result = await db.execute(
            select(LeadSource).where(
                LeadSource.source_type == source_type,
                LeadSource.external_lead_id == external_lead_id,
            )
        )
        existing_source = result.scalar_one_or_none()
        if existing_source is None:
            return None
        lead_result = await db.execute(select(Lead).where(Lead.id == existing_source.lead_id))
        return lead_result.scalar_one_or_none()

    @staticmethod
    async def _find_best_name_match(db: AsyncSession, full_name: str) -> Optional[tuple]:
        normalized_target = _normalize_name(full_name)
        result = await db.execute(select(Lead))
        best_lead: Optional[Lead] = None
        best_score = 0.0
        for lead in result.scalars().all():
            score = difflib.SequenceMatcher(None, normalized_target, _normalize_name(lead.full_name)).ratio()
            if score > best_score:
                best_score = score
                best_lead = lead
        if best_lead is not None and best_score >= settings.LEAD_NAME_SIMILARITY_THRESHOLD:
            return best_lead, best_score
        return None

    @staticmethod
    async def resolve_or_create(
        db: AsyncSession,
        *,
        full_name: str,
        normalized_phone: Optional[str],
        normalized_email: Optional[str],
        source_type: SourceType,
        external_lead_id: Optional[str],
        preferred_language: Optional[str],
        consent_status: ConsentStatus,
    ) -> ResolutionResult:
        if normalized_phone:
            existing = await IdentityResolutionService._find_by_phone(db, normalized_phone)
            if existing is not None:
                return ResolutionResult(lead=existing, created_new_lead=False, match_reason="EXACT_PHONE")

        if normalized_email:
            existing = await IdentityResolutionService._find_by_email(db, normalized_email)
            if existing is not None:
                return ResolutionResult(lead=existing, created_new_lead=False, match_reason="EXACT_EMAIL")

        if external_lead_id:
            existing = await IdentityResolutionService._find_by_external_id(db, source_type, external_lead_id)
            if existing is not None:
                return ResolutionResult(lead=existing, created_new_lead=False, match_reason="EXTERNAL_ID_MATCH")

        name_match = await IdentityResolutionService._find_best_name_match(db, full_name)

        new_lead = Lead(
            full_name=full_name,
            normalized_phone=normalized_phone,
            normalized_email=normalized_email,
            preferred_language=preferred_language,
            consent_status=consent_status,
        )
        db.add(new_lead)
        try:
            await db.flush()
        except IntegrityError:
            # Concurrent request created a Lead with the same phone/email between
            # our lookup and insert. Roll back and resolve to the now-existing row.
            await db.rollback()
            logger.warning("Concurrent lead identity collision resolved via re-lookup")
            recovered: Optional[Lead] = None
            if normalized_phone:
                recovered = await IdentityResolutionService._find_by_phone(db, normalized_phone)
            if recovered is None and normalized_email:
                recovered = await IdentityResolutionService._find_by_email(db, normalized_email)
            if recovered is None:
                raise
            return ResolutionResult(lead=recovered, created_new_lead=False, match_reason="EXACT_MATCH_CONCURRENT")

        potential_duplicate = None
        if name_match is not None:
            candidate_lead, score = name_match
            potential_duplicate = PotentialDuplicateMatch(
                new_lead_id=new_lead.id,
                existing_lead_id=candidate_lead.id,
                match_reason="NAME_SIMILARITY",
                similarity_score=score,
            )
            db.add(potential_duplicate)
            await db.flush()

        return ResolutionResult(
            lead=new_lead,
            created_new_lead=True,
            match_reason="NEW_BUYER",
            potential_duplicate=potential_duplicate,
        )
