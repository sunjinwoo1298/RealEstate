from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from backend.models.lead import ConsentStatus, LeadStatus
from backend.models.lead_source import SourceType
from backend.models.potential_duplicate import DuplicateReviewStatus


class LeadSourcePublic(BaseModel):
    """
    Public representation of an enquiry/source record. Raw webhook payloads
    are intentionally never exposed through the API.
    """

    id: uuid.UUID
    source_type: SourceType
    external_lead_id: Optional[str]
    campaign_name: Optional[str]
    submitted_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadPublic(BaseModel):
    id: uuid.UUID
    full_name: str
    normalized_phone: Optional[str]
    normalized_email: Optional[str]
    preferred_language: Optional[str]
    lead_status: LeadStatus
    assigned_executive_id: Optional[uuid.UUID]
    consent_status: ConsentStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadListItem(LeadPublic):
    source_count: int = 0
    latest_source_type: Optional[SourceType] = None


class LeadListResponse(BaseModel):
    items: List[LeadListItem]
    total: int
    new_count: int


class LeadDetailResponse(LeadPublic):
    sources: List[LeadSourcePublic] = Field(default_factory=list)


class ManualLeadCreateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=6, max_length=20)
    email: Optional[EmailStr] = None
    preferred_language: Optional[str] = Field(default=None, max_length=10)
    campaign_name: Optional[str] = Field(default=None, max_length=255)
    consent_status: ConsentStatus = ConsentStatus.NOT_RECORDED
    notes: Optional[str] = Field(default=None, max_length=2000)


class WebhookLeadPayload(BaseModel):
    """Generic enquiry payload accepted from verified external sources/website forms."""

    full_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=6, max_length=20)
    email: Optional[EmailStr] = None
    preferred_language: Optional[str] = Field(default=None, max_length=10)
    external_lead_id: Optional[str] = Field(default=None, max_length=255)
    campaign_name: Optional[str] = Field(default=None, max_length=255)
    submitted_at: Optional[datetime] = None
    consent_status: ConsentStatus = ConsentStatus.NOT_RECORDED
    extra: Dict[str, Any] = Field(default_factory=dict)


class LeadUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    preferred_language: Optional[str] = Field(default=None, max_length=10)
    lead_status: Optional[LeadStatus] = None
    assigned_executive_id: Optional[uuid.UUID] = None
    consent_status: Optional[ConsentStatus] = None


class IngestionResponse(BaseModel):
    lead_id: uuid.UUID
    lead_source_id: uuid.UUID
    created_new_lead: bool
    match_reason: str
    idempotent_replay: bool = False


class CsvImportRowResult(BaseModel):
    row_number: int
    status: str
    message: Optional[str] = None
    lead_id: Optional[uuid.UUID] = None


class CsvImportResponse(BaseModel):
    total_rows: int
    created: int
    matched: int
    failed: int
    results: List[CsvImportRowResult]


class PotentialDuplicatePublic(BaseModel):
    id: uuid.UUID
    new_lead_id: uuid.UUID
    existing_lead_id: uuid.UUID
    match_reason: str
    similarity_score: Optional[float]
    status: DuplicateReviewStatus
    reviewed_by_id: Optional[uuid.UUID]
    reviewed_at: Optional[datetime]
    created_at: datetime
    new_lead: Optional[LeadPublic] = None
    existing_lead: Optional[LeadPublic] = None

    model_config = {"from_attributes": True}


class PotentialDuplicateListResponse(BaseModel):
    items: List[PotentialDuplicatePublic]
    total: int


class DuplicateReviewRequest(BaseModel):
    status: DuplicateReviewStatus

    @field_validator("status")
    @classmethod
    def disallow_pending(cls, value: DuplicateReviewStatus) -> DuplicateReviewStatus:
        if value == DuplicateReviewStatus.PENDING_REVIEW:
            raise ValueError("Review decision must be CONFIRMED_DUPLICATE or REJECTED")
        return value
