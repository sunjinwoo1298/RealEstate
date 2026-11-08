from __future__ import annotations
import uuid
from typing import Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer_account import CustomerAccount
from backend.models.lead import Lead, LeadStatus
from backend.models.lead_qualification import ConfigurationType, LeadQualification
from backend.models.lead_source import LeadSource
from backend.models.project import Project, ProjectVisibility
from backend.schemas.customer_profile import CustomerEnquirySummary

# Explicit internal-status -> customer-facing label mapping, per spec
# section 4 ("do not expose internal Lead status enums directly... define
# an explicit mapping to customer-facing labels"). Deliberately coarser
# than the internal state machine -- AI_CONTACTED/QUALIFIED both read as
# "In Progress" to a customer, since neither is a customer-actionable
# distinction.
_CUSTOMER_STATUS_LABELS: Dict[LeadStatus, str] = {
    LeadStatus.NEW: "Enquiry Received",
    LeadStatus.AI_CONTACTED: "In Progress",
    LeadStatus.QUALIFIED: "In Progress",
    LeadStatus.VISIT_REQUESTED: "Site Visit Requested",
    LeadStatus.VISIT_BOOKED: "Site Visit Scheduled",
    LeadStatus.VISIT_COMPLETED: "Site Visit Completed",
    LeadStatus.CONVERTED: "Converted",
    LeadStatus.LOST: "Closed",
    LeadStatus.OPTED_OUT: "Closed",
}

_CONFIGURATION_LABELS: Dict[ConfigurationType, str] = {
    ConfigurationType.BHK_2: "2 BHK",
    ConfigurationType.BHK_3: "3 BHK",
}


class CustomerEnquiryService:
    """
    Read-only, sanitized view of the authenticated customer's own linked
    Lead. The Lead is resolved exclusively from `CustomerAccount.lead_id` --
    never from a caller-supplied id -- so an unlinked (or wrongly-scoped)
    customer can never enumerate or reach another buyer's Lead. Never
    returns the raw `Lead`/`LeadQualification` model or any internal-only
    field (assigned_executive_id, consent_status, raw lead_status, etc.).
    """

    @staticmethod
    async def get_enquiry_summary(db: AsyncSession, customer: CustomerAccount) -> CustomerEnquirySummary:
        if customer.lead_id is None:
            return CustomerEnquirySummary(has_enquiry=False)

        result = await db.execute(select(Lead).where(Lead.id == customer.lead_id))
        lead = result.scalar_one_or_none()
        if lead is None:
            # Defensive only -- customer_accounts.lead_id is ON DELETE SET
            # NULL, so this branch shouldn't be reachable in practice.
            return CustomerEnquirySummary(has_enquiry=False)

        qualification_result = await db.execute(
            select(LeadQualification).where(LeadQualification.lead_id == lead.id)
        )
        qualification = qualification_result.scalar_one_or_none()

        earliest_submitted = await db.execute(
            select(func.min(LeadSource.submitted_at)).where(LeadSource.lead_id == lead.id)
        )
        enquiry_date = earliest_submitted.scalar_one_or_none() or lead.created_at

        project_id: Optional[uuid.UUID] = None
        project_name: Optional[str] = None
        if qualification is not None and qualification.project_id is not None:
            project_result = await db.execute(select(Project).where(Project.id == qualification.project_id))
            project = project_result.scalar_one_or_none()
            if project is not None and project.visibility_status == ProjectVisibility.PUBLISHED:
                project_id = project.id
                project_name = project.name
            # else: draft/archived/deleted project -- leave both None. This
            # is the safe "unavailable project" representation the spec
            # asks for, rather than leaking draft/archived project details.

        configuration: Optional[str] = None
        if qualification is not None and qualification.configuration is not None:
            configuration = _CONFIGURATION_LABELS.get(
                qualification.configuration, qualification.configuration.value
            )

        return CustomerEnquirySummary(
            has_enquiry=True,
            enquiry_reference=f"ENQ-{str(lead.id)[:8].upper()}",
            project_id=project_id,
            project_name=project_name,
            configuration=configuration,
            enquiry_date=enquiry_date,
            customer_status=_CUSTOMER_STATUS_LABELS.get(lead.lead_status, "In Progress"),
        )
