from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import logger
from backend.models.customer_account import CustomerAccount
from backend.models.lead import ConsentStatus, Lead
from backend.models.lead_source import SourceType
from backend.services.lead_ingestion_service import LeadIngestionService

CUSTOMER_REGISTRATION_CAMPAIGN = "Customer Registration"


@dataclass
class LinkingOutcome:
    linked_lead_id: Optional[str]
    reason: str


class CustomerLeadLinkingService:
    """
    Resolves a just-verified customer's identity against the canonical Lead
    table (Feature 02's `leads`/`lead_sources`), per the Feature 10 spec's
    "Customer-to-Lead Identity Linking" rules. Only ever runs after the
    customer's email has been verified -- an unverified email must never
    drive this decision.
    """

    @staticmethod
    async def _find_eligible_leads_by_email(db: AsyncSession, normalized_email: str) -> List[Lead]:
        """
        Leads whose normalized_email matches, excluding any Lead already
        linked to a *different* CustomerAccount (never seize another
        customer's claimed identity).
        """
        result = await db.execute(select(Lead).where(Lead.normalized_email == normalized_email))
        candidates = list(result.scalars().all())
        if not candidates:
            return []

        lead_ids = [lead.id for lead in candidates]
        linked_result = await db.execute(
            select(CustomerAccount.lead_id).where(CustomerAccount.lead_id.in_(lead_ids))
        )
        already_linked_ids = {row[0] for row in linked_result.all()}
        return [lead for lead in candidates if lead.id not in already_linked_ids]

    @staticmethod
    async def _is_lead_claimed_by_another_customer(
        db: AsyncSession, lead_id, customer_account_id
    ) -> bool:
        result = await db.execute(
            select(CustomerAccount.id).where(
                CustomerAccount.lead_id == lead_id, CustomerAccount.id != customer_account_id
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def link_or_create_for_verified_customer(
        db: AsyncSession, customer: CustomerAccount
    ) -> LinkingOutcome:
        """
        Must only be called immediately after the customer's email has just
        been verified. Never called on phone alone (no phone-verification
        mechanism exists yet, per spec).
        """
        if customer.lead_id is not None:
            # Idempotency guard: a repeated/retried invocation for an
            # already-linked customer must never create or link a second
            # Lead.
            return LinkingOutcome(linked_lead_id=str(customer.lead_id), reason="ALREADY_LINKED")

        eligible_leads = await CustomerLeadLinkingService._find_eligible_leads_by_email(
            db, customer.normalized_email
        )

        if len(eligible_leads) > 1:
            # Ambiguous: multiple canonical Leads share this email. Never
            # auto-link or auto-merge -- leave unresolved for manual review.
            logger.warning(
                f"Ambiguous customer-to-lead match for customer_account_id={customer.id}: "
                f"{len(eligible_leads)} candidate leads share normalized_email"
            )
            return LinkingOutcome(linked_lead_id=None, reason="AMBIGUOUS_MATCH_UNRESOLVED")

        if len(eligible_leads) == 1:
            lead = eligible_leads[0]
            try:
                customer.lead_id = lead.id
                await db.flush()
            except IntegrityError:
                # Lost a race to another verification linking the same Lead
                # concurrently. Roll back and leave this customer unlinked
                # rather than retry blindly -- the other party already won.
                await db.rollback()
                await db.refresh(customer)
                logger.warning(
                    f"Concurrent customer-to-lead link race lost for lead_id={lead.id}; leaving unlinked"
                )
                return LinkingOutcome(linked_lead_id=None, reason="CONCURRENT_LINK_LOST")
            return LinkingOutcome(linked_lead_id=str(lead.id), reason="EXACT_EMAIL_MATCH")

        # No existing Lead for this email: create one through the existing
        # Lead domain service, exactly as every other ingestion channel does.
        ingestion = await LeadIngestionService.ingest(
            db,
            full_name=customer.full_name,
            raw_phone=customer.phone,
            raw_email=customer.email,
            preferred_language=None,
            source_type=SourceType.WEBSITE,
            external_lead_id=None,
            campaign_name=CUSTOMER_REGISTRATION_CAMPAIGN,
            raw_payload={"channel": "CUSTOMER_REGISTRATION", "customer_account_id": str(customer.id)},
            consent_status=ConsentStatus.GRANTED,
        )

        new_lead = ingestion.lead
        # The ingestion service's own identity resolution may have matched an
        # existing Lead by phone (an established, pre-existing system
        # behavior -- exact phone match has always been a trusted identity
        # signal here). Before claiming it for this customer, re-check that
        # it isn't already claimed by a *different* customer account.
        if await CustomerLeadLinkingService._is_lead_claimed_by_another_customer(db, new_lead.id, customer.id):
            logger.warning(
                f"Lead {new_lead.id} resolved during customer registration is already linked to "
                f"another customer account; leaving customer_account_id={customer.id} unlinked"
            )
            return LinkingOutcome(linked_lead_id=None, reason="RESOLVED_LEAD_ALREADY_CLAIMED")

        try:
            customer.lead_id = new_lead.id
            await db.flush()
        except IntegrityError:
            await db.rollback()
            await db.refresh(customer)
            logger.warning(
                f"Concurrent customer-to-lead link race lost for lead_id={new_lead.id}; leaving unlinked"
            )
            return LinkingOutcome(linked_lead_id=None, reason="CONCURRENT_LINK_LOST")

        reason = "NEW_LEAD_CREATED" if ingestion.created_new_lead else "RESOLVED_VIA_INGESTION"
        return LinkingOutcome(linked_lead_id=str(new_lead.id), reason=reason)
