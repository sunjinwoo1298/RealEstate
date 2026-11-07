from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from backend.models.knowledge_document import ApprovalStatus


class KnowledgeDocumentPublic(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    version: int
    approval_status: ApprovalStatus
    source_filename: Optional[str]
    uploaded_by: Optional[uuid.UUID]
    approved_by: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    chunk_count: int = 0

    model_config = {"from_attributes": True}


class KnowledgeDocumentListResponse(BaseModel):
    items: List[KnowledgeDocumentPublic]
    total: int


class KnowledgeChunkPreview(BaseModel):
    id: uuid.UUID
    chunk_index: int
    content: str


class KnowledgeRetrievalReference(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    document_version: int
    content: str
    similarity: float
