from __future__ import annotations
import uuid
from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class AvailabilityRulePublic(BaseModel):
    id: uuid.UUID
    executive_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    day_of_week: int
    start_time: time
    end_time: time
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AvailabilityRuleListResponse(BaseModel):
    items: List[AvailabilityRulePublic]
    total: int


class AvailabilityRuleCreateRequest(BaseModel):
    executive_id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    is_active: bool = True

    @model_validator(mode="after")
    def check_times(self) -> "AvailabilityRuleCreateRequest":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AvailabilityRuleUpdateRequest(BaseModel):
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    is_active: Optional[bool] = None


class BlockedPeriodPublic(BaseModel):
    id: uuid.UUID
    executive_id: uuid.UUID
    start_time: datetime
    end_time: datetime
    reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class BlockedPeriodCreateRequest(BaseModel):
    executive_id: uuid.UUID
    start_time: datetime
    end_time: datetime
    reason: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def check_times(self) -> "BlockedPeriodCreateRequest":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class ProjectVisitCapacityPublic(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    capacity: int
    visit_duration_minutes: int
    buffer_minutes: int

    model_config = {"from_attributes": True}


class ProjectVisitCapacityUpsertRequest(BaseModel):
    project_id: uuid.UUID
    capacity: int = Field(gt=0)
    visit_duration_minutes: int = Field(gt=0, default=30)
    buffer_minutes: int = Field(ge=0, default=0)


class AvailableSlotPublic(BaseModel):
    start_time: datetime
    end_time: datetime
    available_executive_count: int


class AvailableSlotsResponse(BaseModel):
    project_id: uuid.UUID
    date: date
    slots: List[AvailableSlotPublic]
