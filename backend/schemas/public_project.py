from __future__ import annotations
import uuid
from typing import List, Optional

from pydantic import BaseModel


class PublicProjectCard(BaseModel):
    """
    Controlled public representation of a project for listing/homepage
    display. Deliberately separate from `ProjectPublic` (the internal admin
    schema) so a future internal-only field never leaks through this path
    by accident -- callers must opt a field into this schema explicitly.
    """

    id: uuid.UUID
    name: str
    location: Optional[str] = None
    description: Optional[str] = None
    configurations: List[str] = []
    primary_image: Optional[str] = None
    starting_price_label: Optional[str] = None
    is_featured: bool = False


class PublicProjectDetail(PublicProjectCard):
    amenities: List[str] = []
    images: List[str] = []
    rera_number: Optional[str] = None
    floor_plan_url: Optional[str] = None


class PublicProjectListResponse(BaseModel):
    items: List[PublicProjectCard]
    total: int
