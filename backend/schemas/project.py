from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=255)


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None


class ProjectPublic(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    location: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: List[ProjectPublic]
    total: int
