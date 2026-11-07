from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.conversation import Conversation, ConversationLanguage
from backend.models.handoff import Handoff, HandoffReason
from backend.models.lead import Lead
from backend.models.lead_qualification import ConfigurationType, LeadQualification, PurchasePurpose
from backend.models.site_visit import SiteVisit
from backend.services.assignment_service import AssignmentService
from backend.services.availability_service import AvailabilityService, Slot
from backend.services.booking_service import BookingService
from backend.services.handoff_service import HandoffService
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
    The only operations the AI orchestrator is permitted to invoke. Every
    call is server-side validated and routed through an existing domain
    service — the LLM never touches the database directly. The three
    qualification/knowledge tools are from Feature 04; get_available_slots,
    book_site_visit, reschedule_site_visit and cancel_site_visit are from
    Feature 05 (Availability & Booking Engine).
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

    async def get_available_slots(self, project_id: uuid.UUID, target_date: date) -> List[Slot]:
        slots = await AvailabilityService.get_available_slots(self._db, project_id=project_id, target_date=target_date)
        self._log.record(
            "get_available_slots",
            {"project_id": str(project_id), "date": target_date.isoformat()},
            f"{len(slots)} slot(s) available",
        )
        return slots

    async def book_site_visit(
        self, lead_id: uuid.UUID, project_id: uuid.UUID, start_time: datetime
    ) -> SiteVisit:
        visit = await BookingService.book_site_visit(
            self._db, lead_id=lead_id, project_id=project_id, start_time=start_time
        )
        self._log.record(
            "book_site_visit",
            {"lead_id": str(lead_id), "project_id": str(project_id), "start_time": start_time.isoformat()},
            f"booked {visit.booking_reference}",
        )
        return visit

    async def reschedule_site_visit(self, site_visit_id: uuid.UUID, new_start_time: datetime) -> SiteVisit:
        visit = await BookingService.reschedule_site_visit(self._db, site_visit_id, new_start_time=new_start_time)
        self._log.record(
            "reschedule_site_visit",
            {"site_visit_id": str(site_visit_id), "new_start_time": new_start_time.isoformat()},
            f"rescheduled {visit.booking_reference}",
        )
        return visit

    async def cancel_site_visit(self, site_visit_id: uuid.UUID) -> SiteVisit:
        visit = await BookingService.cancel_site_visit(self._db, site_visit_id)
        self._log.record(
            "cancel_site_visit",
            {"site_visit_id": str(site_visit_id)},
            f"cancelled {visit.booking_reference}",
        )
        return visit

    async def request_human_handoff(
        self, conversation: Conversation, lead: Lead, *, reason: HandoffReason, summary: Optional[str]
    ) -> Handoff:
        """
        The only way the AI orchestrator may escalate a conversation. Creates
        (or, on a retry, reuses) the active Handoff and auto-assigns an
        eligible executive -- the LLM only ever decides *that* a handoff is
        needed and *why*; HandoffService/AssignmentService decide everything
        else (ownership transition, who gets assigned, notification).
        """
        handoff = await HandoffService.create_handoff(self._db, conversation, lead, reason=reason, summary=summary)
        await AssignmentService.auto_assign_if_unassigned(self._db, handoff)
        self._log.record(
            "request_human_handoff",
            {"conversation_id": str(conversation.id), "reason": reason.value},
            f"handoff {handoff.id} status={handoff.status.value}",
        )
        return handoff
