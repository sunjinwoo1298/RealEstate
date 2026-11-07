from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from backend.models.visit_reminder import ReminderStatus, ReminderType


class VisitReminderPublic(BaseModel):
    id: uuid.UUID
    site_visit_id: uuid.UUID
    reminder_type: ReminderType
    scheduled_at: datetime
    status: ReminderStatus
    attempt_count: int
    last_attempt_at: Optional[datetime]
    sent_at: Optional[datetime]
    failure_reason: Optional[str]
    booking_version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VisitReminderListResponse(BaseModel):
    items: List[VisitReminderPublic]
    total: int
