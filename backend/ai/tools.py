from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.conversation import ConversationLanguage
from backend.models.lead_qualification import ConfigurationType, LeadQualification, PurchasePurpose
from backend.services.qualification_service import QualificationService
from backend.services.retrieval_service import RetrievalService


@dataclass
class ToolCallRecord:
    tool_name: str
    arguments: dict
    result_summary: str


@dataclass
class ToolCallLog:
    calls: List[ToolCallRecord] = field(default_factory=list)

    def record(self, tool_name: str, arguments: dict, result_summary: str) -> None:
        self.calls.append(ToolCallRecord(tool_name=tool_name, arguments=arguments, result_summary=result_summary))

    def as_metadata(self) -> List[dict]:
        return [{"tool": c.tool_name, "arguments": c.arguments, "result": c.result_summary} for c in self.calls]


class AITools:
    """
    The only three operations the AI orchestrator is permitted to invoke for
    this feature. Every call is server-side validated and routed through an
    existing domain service — the LLM never touches the database directly.
    """

    def __init__(self, db: AsyncSession, log: ToolCallLog):
        self._db = db
        self._log = log

    async def get_project_information(self, project_id: uuid.UUID) -> Optional[dict]:
        info = await RetrievalService.get_project_information(self._db, project_id)
        self._log.record(
            "get_project_information",
            {"project_id": str(project_id)},
            "found" if info else "not_found",
        )
        return info

    async def search_project_knowledge(self, project_id: uuid.UUID, query_text: str):
        chunks = await RetrievalService.search_project_knowledge(self._db, project_id=project_id, query_text=query_text)
        self._log.record(
            "search_project_knowledge",
            {"project_id": str(project_id), "query": query_text},
            f"{len(chunks)} chunk(s) retrieved",
        )
        return chunks

    async def update_buyer_qualification(
        self,
        lead_id: uuid.UUID,
        *,
        project_id: Optional[uuid.UUID] = None,
        configuration: Optional[ConfigurationType] = None,
        budget_min: Optional[float] = None,
        budget_max: Optional[float] = None,
        purchase_purpose: Optional[PurchasePurpose] = None,
        preferred_language: Optional[ConversationLanguage] = None,
        preferred_visit_date: Optional[date] = None,
    ) -> LeadQualification:
        qualification = await QualificationService.upsert(
            self._db,
            lead_id,
            project_id=project_id,
            configuration=configuration,
            budget_min=budget_min,
            budget_max=budget_max,
            purchase_purpose=purchase_purpose,
            preferred_language=preferred_language,
            preferred_visit_date=preferred_visit_date,
        )
        self._log.record(
            "update_buyer_qualification",
            {
                "lead_id": str(lead_id),
                "project_id": str(project_id) if project_id else None,
                "configuration": configuration.value if configuration else None,
                "purchase_purpose": purchase_purpose.value if purchase_purpose else None,
            },
            "updated",
        )
        return qualification
