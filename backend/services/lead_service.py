from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.exceptions import ForbiddenException, NotFoundException
from backend.models.lead import ConsentStatus, Lead, LeadStatus
from backend.models.lead_source import LeadSource, SourceType
from backend.models.potential_duplicate import DuplicateReviewStatus, PotentialDuplicateMatch
from backend.models.user import User, UserRole


class LeadService:
    """Read/update operations for leads backing the staff-facing API."""

    # --- Staff lead visibility -------------------------------------------
    # Spec 01/08: a SALES_EXECUTIVE may only view and manage leads assigned
    # to them (Lead.assigned_executive_id, the same definition analytics
    # uses for "assigned leads"). Managers and admins see every lead, and
    # only they may (re)assign a lead.

    @staticmethod
    def is_scoped_to_assigned_leads(user: User) -> bool:
        return user.role == UserRole.SALES_EXECUTIVE

    @staticmethod
    def ensure_can_access(user: User, lead: Lead) -> None:
        if LeadService.is_scoped_to_assigned_leads(user) and lead.assigned_executive_id != user.id:
            raise ForbiddenException("You do not have permission to access this lead")

    @staticmethod
    async def get_accessible_lead(db: AsyncSession, lead_id: uuid.UUID, user: User) -> Lead:
        lead = await LeadService.get_lead_by_id(db, lead_id)
        LeadService.ensure_can_access(user, lead)
        return lead

    @staticmethod
    def ensure_can_assign(user: User, lead: Lead, new_executive_id: Optional[uuid.UUID]) -> None:
        if new_executive_id is None or new_executive_id == lead.assigned_executive_id:
            return
        if LeadService.is_scoped_to_assigned_leads(user):
            raise ForbiddenException("Only an admin or manager may reassign a lead")

    @staticmethod
    async def get_lead_by_id(db: AsyncSession, lead_id: uuid.UUID, with_sources: bool = False) -> Lead:
        query = select(Lead).where(Lead.id == lead_id)
        if with_sources:
            query = query.options(selectinload(Lead.sources))
        result = await db.execute(query)
        lead = result.scalar_one_or_none()
        if lead is None:
            raise NotFoundException("Lead not found")
        return lead

    @staticmethod
    async def list_leads(
        db: AsyncSession,
        *,
        search: Optional[str] = None,
        source_type: Optional[SourceType] = None,
        lead_status: Optional[LeadStatus] = None,
        assigned_executive_id: Optional[uuid.UUID] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Lead], int, int]:
        base_query = select(Lead)
        count_query = select(func.count(func.distinct(Lead.id))).select_from(Lead)

        if source_type is not None or search:
            base_query = base_query.join(LeadSource, LeadSource.lead_id == Lead.id, isouter=True)
            count_query = count_query.join(LeadSource, LeadSource.lead_id == Lead.id, isouter=True)

        filters = []
        if search:
            like_term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(Lead.full_name).like(like_term),
                    Lead.normalized_phone.ilike(like_term),
                    Lead.normalized_email.ilike(like_term),
                )
            )
        if source_type is not None:
            filters.append(LeadSource.source_type == source_type)
        if lead_status is not None:
            filters.append(Lead.lead_status == lead_status)
        if assigned_executive_id is not None:
            filters.append(Lead.assigned_executive_id == assigned_executive_id)

        for f in filters:
            base_query = base_query.where(f)
            count_query = count_query.where(f)

        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        new_count_result = await db.execute(select(func.count()).select_from(Lead).where(Lead.lead_status == LeadStatus.NEW))
        new_count = new_count_result.scalar_one()

        base_query = (
            base_query.distinct()
            .order_by(Lead.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(base_query)
        leads = list(result.scalars().all())
        return leads, total, new_count

    @staticmethod
    async def get_sources_for_lead(db: AsyncSession, lead_id: uuid.UUID) -> List[LeadSource]:
        await LeadService.get_lead_by_id(db, lead_id)
        result = await db.execute(
            select(LeadSource).where(LeadSource.lead_id == lead_id).order_by(LeadSource.submitted_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_lead(
        db: AsyncSession,
        lead_id: uuid.UUID,
        *,
        full_name: Optional[str],
        preferred_language: Optional[str],
        lead_status: Optional[LeadStatus],
        assigned_executive_id: Optional[uuid.UUID],
        consent_status: Optional[ConsentStatus],
    ) -> Lead:
        lead = await LeadService.get_lead_by_id(db, lead_id)

        if assigned_executive_id is not None:
            exec_result = await db.execute(select(User).where(User.id == assigned_executive_id))
            if exec_result.scalar_one_or_none() is None:
                raise NotFoundException("Assigned executive not found")

        if full_name is not None:
            lead.full_name = full_name
        if preferred_language is not None:
            lead.preferred_language = preferred_language
        if lead_status is not None:
            lead.lead_status = lead_status
        if assigned_executive_id is not None:
            lead.assigned_executive_id = assigned_executive_id
        if consent_status is not None:
            lead.consent_status = consent_status

        await db.commit()
        await db.refresh(lead)
        return lead

    @staticmethod
    async def list_potential_duplicates(
        db: AsyncSession, *, status: Optional[DuplicateReviewStatus] = None, limit: int = 20, offset: int = 0
    ) -> Tuple[List[PotentialDuplicateMatch], int]:
        query = select(PotentialDuplicateMatch).options(
            selectinload(PotentialDuplicateMatch.new_lead), selectinload(PotentialDuplicateMatch.existing_lead)
        )
        count_query = select(func.count()).select_from(PotentialDuplicateMatch)
        if status is not None:
            query = query.where(PotentialDuplicateMatch.status == status)
            count_query = count_query.where(PotentialDuplicateMatch.status == status)

        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(PotentialDuplicateMatch.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all()), total

    @staticmethod
    async def review_potential_duplicate(
        db: AsyncSession, match_id: uuid.UUID, *, status: DuplicateReviewStatus, reviewed_by_id: uuid.UUID
    ) -> PotentialDuplicateMatch:
        result = await db.execute(
            select(PotentialDuplicateMatch).where(PotentialDuplicateMatch.id == match_id)
        )
        match = result.scalar_one_or_none()
        if match is None:
            raise NotFoundException("Potential duplicate match not found")

        match.status = status
        match.reviewed_by_id = reviewed_by_id
        match.reviewed_at = datetime.now(timezone.utc)
        await db.commit()

        reloaded = await db.execute(
            select(PotentialDuplicateMatch)
            .options(selectinload(PotentialDuplicateMatch.new_lead), selectinload(PotentialDuplicateMatch.existing_lead))
            .where(PotentialDuplicateMatch.id == match_id)
        )
        return reloaded.scalar_one()
