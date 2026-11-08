from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.models.project import ProjectVisibility


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=255)


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None

    # Public website fields (Feature 09) -- publication/visibility changes
    # are restricted to ADMIN at the endpoint layer, not here.
    visibility_status: Optional[ProjectVisibility] = None
    is_featured: Optional[bool] = None
    configurations: Optional[List[str]] = None
    amenities: Optional[List[str]] = None
    images: Optional[List[str]] = None
    starting_price_label: Optional[str] = Field(default=None, max_length=120)
    price_display_approved: Optional[bool] = None
    rera_number: Optional[str] = Field(default=None, max_length=100)
    floor_plan_url: Optional[str] = Field(default=None, max_length=1000)


class ProjectPublic(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    location: Optional[str]
    is_active: bool
    visibility_status: ProjectVisibility
    is_featured: bool
    configurations: Optional[List[str]] = None
    amenities: Optional[List[str]] = None
    images: Optional[List[str]] = None
    starting_price_label: Optional[str] = None
    price_display_approved: bool
    rera_number: Optional[str] = None
    floor_plan_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: List[ProjectPublic]
    total: int
