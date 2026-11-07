from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator

from backend.models.site_visit import SiteVisitStatus
from backend.models.visit_event import VisitEventType


class SiteVisitPublic(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    project_id: uuid.UUID
    executive_id: Optional[uuid.UUID]
    start_time: datetime
    end_time: datetime
    status: SiteVisitStatus
    booking_reference: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SiteVisitListResponse(BaseModel):
    items: List[SiteVisitPublic]
    total: int


class VisitEventPublic(BaseModel):
    id: uuid.UUID
    site_visit_id: uuid.UUID
    event_type: VisitEventType
    actor_id: Optional[uuid.UUID]
    extra_metadata: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingCreateRequest(BaseModel):
    lead_id: uuid.UUID
    project_id: uuid.UUID
    start_time: datetime


class BookingRescheduleRequest(BaseModel):
    start_time: datetime


class AttendanceUpdateRequest(BaseModel):
    status: SiteVisitStatus

    @field_validator("status")
    @classmethod
    def status_must_be_an_attendance_outcome(cls, value: SiteVisitStatus) -> SiteVisitStatus:
        if value not in (SiteVisitStatus.COMPLETED, SiteVisitStatus.NO_SHOW):
            raise ValueError("Attendance status must be COMPLETED or NO_SHOW")
        return value
