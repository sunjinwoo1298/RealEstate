from __future__ import annotations
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.conversation import ConversationLanguage
from backend.models.lead_qualification import ConfigurationType, LeadQualification, PurchasePurpose


class QualificationService:
    """
    Maintains the single current LeadQualification snapshot per buyer.
    Updates only ever merge newly-extracted, non-null fields in; previously
    captured information is never cleared by a later message that simply
    didn't mention it.
    """

    @staticmethod
    async def get_for_lead(db: AsyncSession, lead_id: uuid.UUID) -> Optional[LeadQualification]:
        result = await db.execute(select(LeadQualification).where(LeadQualification.lead_id == lead_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert(
        db: AsyncSession,
        lead_id: uuid.UUID,
        *,
        project_id: Optional[uuid.UUID] = None,
        configuration: Optional[ConfigurationType] = None,
        budget_min: Optional[float] = None,
        budget_max: Optional[float] = None,
        purchase_purpose: Optional[PurchasePurpose] = None,
        preferred_language: Optional[ConversationLanguage] = None,
        preferred_visit_date: Optional[date] = None,
    ) -> LeadQualification:
        qualification = await QualificationService.get_for_lead(db, lead_id)
        if qualification is None:
            qualification = LeadQualification(lead_id=lead_id)
            db.add(qualification)

        if project_id is not None:
            qualification.project_id = project_id
        if configuration is not None:
            qualification.configuration = configuration
        if budget_min is not None:
            qualification.budget_min = budget_min
        if budget_max is not None:
            qualification.budget_max = budget_max
        if purchase_purpose is not None:
            qualification.purchase_purpose = purchase_purpose
        if preferred_language is not None:
            qualification.preferred_language = preferred_language
        if preferred_visit_date is not None:
            qualification.preferred_visit_date = preferred_visit_date

        await db.commit()
        await db.refresh(qualification)
        return qualification

    @staticmethod
    def is_fully_qualified(qualification: Optional[LeadQualification]) -> bool:
        if qualification is None:
            return False
        return bool(
            qualification.project_id
            and qualification.configuration
            and qualification.budget_min is not None
            and qualification.purchase_purpose
        )
