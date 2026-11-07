from __future__ import annotations
import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from backend.models.conversation import ConversationLanguage
from backend.models.lead_qualification import ConfigurationType, PurchasePurpose


class LeadQualificationPublic(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    configuration: Optional[ConfigurationType]
    budget_min: Optional[float]
    budget_max: Optional[float]
    purchase_purpose: Optional[PurchasePurpose]
    preferred_language: Optional[ConversationLanguage]
    preferred_visit_date: Optional[date]
    updated_at: datetime

    model_config = {"from_attributes": True}
