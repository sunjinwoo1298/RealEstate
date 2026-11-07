from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.models.conversation import OwnershipStatus
from backend.models.conversation_assignment import AssignmentStatus
from backend.models.handoff import HandoffReason, HandoffStatus
from backend.models.lead_qualification import ConfigurationType, PurchasePurpose
from backend.models.site_visit import SiteVisitStatus


class HandoffPublic(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    lead_id: uuid.UUID
    assigned_executive_id: Optional[uuid.UUID]
    status: HandoffStatus
    reason: HandoffReason
    summary: Optional[str]
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}


class HandoffListItem(HandoffPublic):
    lead_full_name: str = ""
    lead_normalized_phone: Optional[str] = None


class HandoffListResponse(BaseModel):
    items: List[HandoffListItem]
    total: int


class ConversationAssignmentPublic(BaseModel):
    id: uuid.UUID
    executive_id: Optional[uuid.UUID]
    assigned_by: Optional[uuid.UUID]
    status: AssignmentStatus
    assigned_at: datetime
    accepted_at: Optional[datetime]
    ended_at: Optional[datetime]

    model_config = {"from_attributes": True}


class HandoffQualificationSummary(BaseModel):
    project_id: Optional[uuid.UUID]
    configuration: Optional[ConfigurationType]
    budget_min: Optional[float]
    budget_max: Optional[float]
    purchase_purpose: Optional[PurchasePurpose]
    preferred_visit_date: Optional[str]


class HandoffSiteVisitSummary(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    start_time: datetime
    end_time: datetime
    status: SiteVisitStatus
    booking_reference: str


class HandoffDetail(HandoffPublic):
    """
    The full handoff context a sales executive needs per spec section 6:
    buyer requirements, source, escalation reason and booking details --
    assembled from existing Lead/LeadSource/LeadQualification/SiteVisit
    data rather than duplicated storage.
    """

    lead_full_name: str
    lead_normalized_phone: Optional[str]
    lead_normalized_email: Optional[str]
    lead_preferred_language: Optional[str]
    source_types: List[str] = Field(default_factory=list)
    qualification: Optional[HandoffQualificationSummary] = None
    site_visits: List[HandoffSiteVisitSummary] = Field(default_factory=list)
    assignments: List[ConversationAssignmentPublic] = Field(default_factory=list)
    conversation_ownership_status: OwnershipStatus


class HandoffRequestCreate(BaseModel):
    reason: HandoffReason = HandoffReason.BUYER_REQUEST
    summary: Optional[str] = Field(default=None, max_length=2000)


class HandoffReassignRequest(BaseModel):
    executive_id: uuid.UUID


class HandoffRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class OwnershipTransitionRequest(BaseModel):
    ownership_status: OwnershipStatus
