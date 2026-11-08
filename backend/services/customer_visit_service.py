from __future__ import annotations
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundException, ValidationException
from backend.models.customer_account import CustomerAccount
from backend.models.project import Project, ProjectVisibility
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.services.availability_service import AvailabilityService, Slot
from backend.services.booking_service import BookingService
from backend.services.qualification_service import QualificationService

_NO_LINKED_LEAD_MESSAGE = (
    "Your account is not yet linked to an enquiry. Please contact our support team before booking a site visit."
)


class CustomerVisitService:
    """
    Narrowly scoped customer-facing orchestration over the existing
    availability/booking/reminder infrastructure (Features 05/07) -- never a
    second booking engine. Every method here authorizes solely by
    `SiteVisit.lead_id == CustomerAccount.lead_id` (loaded from the
    authenticated customer, never from a caller-supplied id), and every
    mutation is delegated to `BookingService`, which already owns all
    concurrency/capacity/idempotency guarantees.
    """

    @staticmethod
    async def _get_published_project(db: AsyncSession, project_id: uuid.UUID) -> Project:
        """
        Same visibility filter PublicProjectService applies (Feature 09): a
        draft/archived/nonexistent project is indistinguishable here -- a
        customer can never discover or book against an unpublished project
        by guessing its id, even though the booking transaction itself
        (BookingService) only checks existence, not publication status.
        """
        result = await db.execute(
            select(Project).where(Project.id == project_id, Project.visibility_status == ProjectVisibility.PUBLISHED)
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise NotFoundException("Project not found")
        return project

    @staticmethod
    def _require_linked_lead(customer: CustomerAccount) -> uuid.UUID:
        if customer.lead_id is None:
            raise ValidationException(_NO_LINKED_LEAD_MESSAGE)
        return customer.lead_id

    @staticmethod
    async def get_available_slots(
        db: AsyncSession, *, project_id: uuid.UUID, target_date: date
    ) -> List[Slot]:
        await CustomerVisitService._get_published_project(db, project_id)
        slots = await AvailabilityService.get_available_slots(db, project_id=project_id, target_date=target_date)
        now = datetime.now(timezone.utc)
        # Belt-and-suspenders: AvailabilityService itself doesn't filter out
        # past slots (staff may legitimately query historical dates), but
        # the customer-facing listing must never offer one (spec section 4).
        return [s for s in slots if s.start_time > now]

    @staticmethod
    async def create_booking(
        db: AsyncSession,
        customer: CustomerAccount,
        *,
        project_id: uuid.UUID,
        scheduled_start: datetime,
        scheduled_end: Optional[datetime],
        idempotency_key: Optional[str],
    ) -> SiteVisit:
        lead_id = CustomerVisitService._require_linked_lead(customer)
        project = await CustomerVisitService._get_published_project(db, project_id)

        if scheduled_end is not None:
            capacity_config = await AvailabilityService.get_visit_capacity(db, project_id)
            expected_end = scheduled_start + timedelta(minutes=capacity_config.visit_duration_minutes)
            if scheduled_end != expected_end:
                raise ValidationException(
                    "This slot is no longer available. Please reload available slots and try again."
                )

        visit = await BookingService.book_site_visit(
            db,
            lead_id=lead_id,
            project_id=project.id,
            start_time=scheduled_start,
            idempotency_key=idempotency_key,
            actor_id=None,
        )

        # Per spec section 3: booking a different project than the one
        # currently on file may update qualification, but only through the
        # existing validated service, which merges in project_id without
        # touching any other previously captured field.
        await QualificationService.upsert(db, lead_id, project_id=project.id)

        return visit

    @staticmethod
    async def list_visits(
        db: AsyncSession,
        customer: CustomerAccount,
        *,
        status: Optional[SiteVisitStatus] = None,
        upcoming: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[SiteVisit], int]:
        if customer.lead_id is None:
            return [], 0
        return await BookingService.list_site_visits(
            db, lead_id=customer.lead_id, status=status, upcoming=upcoming, limit=limit, offset=offset
        )

    @staticmethod
    async def get_owned_visit(db: AsyncSession, customer: CustomerAccount, visit_id: uuid.UUID) -> SiteVisit:
        """
        Returns 404 (never 403) for a visit that doesn't exist or belongs to
        another customer's Lead, so a caller can never distinguish "not
        yours" from "doesn't exist" -- same convention as
        CustomerConversationService.get_owned_conversation.
        """
        result = await db.execute(select(SiteVisit).where(SiteVisit.id == visit_id))
        visit = result.scalar_one_or_none()
        if visit is None or customer.lead_id is None or visit.lead_id != customer.lead_id:
            raise NotFoundException("Site visit not found")
        return visit

    @staticmethod
    async def reschedule_visit(
        db: AsyncSession,
        customer: CustomerAccount,
        visit_id: uuid.UUID,
        *,
        scheduled_start: datetime,
        scheduled_end: Optional[datetime],
    ) -> SiteVisit:
        visit = await CustomerVisitService.get_owned_visit(db, customer, visit_id)

        if scheduled_end is not None:
            capacity_config = await AvailabilityService.get_visit_capacity(db, visit.project_id)
            expected_end = scheduled_start + timedelta(minutes=capacity_config.visit_duration_minutes)
            if scheduled_end != expected_end:
                raise ValidationException(
                    "This slot is no longer available. Please reload available slots and try again."
                )

        return await BookingService.reschedule_site_visit(
            db, visit_id, new_start_time=scheduled_start, actor_id=None
        )

    @staticmethod
    async def cancel_visit(db: AsyncSession, customer: CustomerAccount, visit_id: uuid.UUID) -> SiteVisit:
        await CustomerVisitService.get_owned_visit(db, customer, visit_id)
        return await BookingService.cancel_site_visit(db, visit_id, actor_id=None)
