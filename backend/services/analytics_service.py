from __future__ import annotations
import statistics
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ValidationException
from backend.models.conversation import Conversation
from backend.models.conversation_assignment import AssignmentStatus, ConversationAssignment
from backend.models.handoff import Handoff
from backend.models.lead import Lead, LeadStatus
from backend.models.lead_qualification import LeadQualification
from backend.models.lead_source import LeadSource, SourceType
from backend.models.message import MessageType, SenderType, Message
from backend.models.project import Project
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.models.user import User, UserRole
from backend.models.visit_reminder import ReminderStatus, VisitReminder
from backend.schemas.analytics import (
    AppliedFilters,
    DateRangeEcho,
    DateRangePreset,
    ExecutivePerformance,
    LeadsByProject,
    LeadsBySource,
    LeadTrendPoint,
    ProjectVisitDistribution,
    QualificationBreakdownItem,
    ReminderDateBasis,
    ReminderStatusBreakdownItem,
    ReminderTrendPoint,
    ResponseTimeBucket,
    SourcePerformance,
    VisitDateBasis,
    VisitTrendPoint,
)
from backend.services.qualification_service import QualificationService

IST = ZoneInfo("Asia/Kolkata")

# Sender types that count as a qualifying, buyer-facing first response.
# BUYER (not a response to themselves) and SYSTEM (internal/automated
# notices, never a human-or-AI reply) are intentionally excluded.
QUALIFYING_RESPONSE_SENDER_TYPES = (SenderType.AI, SenderType.STAFF)

# Forward-only funnel ladder used for stage-floor counting (see get_funnel).
# LOST/OPTED_OUT are terminal exits, not forward progress, and are reported
# separately rather than forced into this ordering.
FUNNEL_LADDER: List[Tuple[str, Optional[LeadStatus]]] = [
    ("New Leads", None),
    ("Contacted", LeadStatus.AI_CONTACTED),
    ("Qualified", LeadStatus.QUALIFIED),
    ("Site Visit Booked", LeadStatus.VISIT_BOOKED),
    ("Site Visit Completed", LeadStatus.VISIT_COMPLETED),
    ("Converted", LeadStatus.CONVERTED),
]

# Ordinal rank for "has this lead reached at least this stage" comparisons.
# VISIT_REQUESTED sits between QUALIFIED and VISIT_BOOKED in the lead
# lifecycle (CLAUDE.md section 5) but has no dedicated funnel stage in the
# spec's suggested list, so it is folded into "Qualified" for floor
# comparisons (a lead that only requested a visit has not yet reached
# VISIT_BOOKED and must not be miscounted as unqualified either).
_STATUS_RANK = {
    LeadStatus.NEW: 0,
    LeadStatus.AI_CONTACTED: 1,
    LeadStatus.QUALIFIED: 2,
    LeadStatus.VISIT_REQUESTED: 2,
    LeadStatus.VISIT_BOOKED: 3,
    LeadStatus.VISIT_COMPLETED: 4,
    LeadStatus.CONVERTED: 5,
}
_STAGE_RANK = {None: 0, LeadStatus.AI_CONTACTED: 1, LeadStatus.QUALIFIED: 2, LeadStatus.VISIT_BOOKED: 3, LeadStatus.VISIT_COMPLETED: 4, LeadStatus.CONVERTED: 5}

# Fixed budget bands (INR) used only for the qualification budget-range
# breakdown. Bucketing is display-only; no stored field is derived from it.
_BUDGET_BANDS = [
    ("< 50L", 0, 5_000_000),
    ("50L - 75L", 5_000_000, 7_500_000),
    ("75L - 1Cr", 7_500_000, 10_000_000),
    ("> 1Cr", 10_000_000, None),
]


@dataclass
class AnalyticsFilters:
    """
    Resolved, role-enforced filter set shared by every analytics endpoint.
    `executive_id` is forced to the caller's own id for SALES_EXECUTIVE by
    the API layer before this object is constructed -- this service never
    re-derives role scoping itself, so every endpoint must build filters via
    `AnalyticsService.build_filters`.
    """

    start_utc: datetime
    end_utc: datetime
    preset: DateRangePreset
    project_id: Optional[uuid.UUID]
    source_type: Optional[SourceType]
    executive_id: Optional[uuid.UUID]

    @property
    def date_range_echo(self) -> DateRangeEcho:
        return DateRangeEcho(preset=self.preset, start_utc=self.start_utc, end_utc=self.end_utc)

    @property
    def applied_filters(self) -> AppliedFilters:
        return AppliedFilters(project_id=self.project_id, source_type=self.source_type, executive_id=self.executive_id)


def _percent(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 2)


class AnalyticsService:
    """
    All analytics calculations for Feature 08. Every metric reads only
    already-persisted models (Lead, LeadSource, Conversation, Message,
    LeadQualification, SiteVisit, VisitReminder, Handoff,
    ConversationAssignment) -- nothing here invents or infers an event that
    was not actually recorded. See context/ANALYTICS_METRICS.md for the
    definition (source table, timestamp, duplicate handling, current-state
    vs. period-based) of every metric returned by this module.
    """

    # --- Date range resolution -------------------------------------------------

    @staticmethod
    def resolve_date_range(
        preset: DateRangePreset, date_from: Optional[date], date_to: Optional[date]
    ) -> Tuple[datetime, datetime]:
        """
        Resolves a business-facing (Asia/Kolkata) calendar date range into a
        UTC [start, end] window for querying UTC-stored timestamps. "Today"
        and the rolling windows are anchored to the current IST date, not UTC,
        so a dashboard viewed late at night IST doesn't silently roll back a day.
        """
        today_ist = datetime.now(IST).date()

        if preset == DateRangePreset.TODAY:
            start_date, end_date = today_ist, today_ist
        elif preset == DateRangePreset.LAST_7_DAYS:
            start_date, end_date = today_ist - timedelta(days=6), today_ist
        elif preset == DateRangePreset.LAST_30_DAYS:
            start_date, end_date = today_ist - timedelta(days=29), today_ist
        elif preset == DateRangePreset.THIS_MONTH:
            start_date, end_date = today_ist.replace(day=1), today_ist
        elif preset == DateRangePreset.PREVIOUS_MONTH:
            first_of_this_month = today_ist.replace(day=1)
            end_date = first_of_this_month - timedelta(days=1)
            start_date = end_date.replace(day=1)
        elif preset == DateRangePreset.CUSTOM:
            if date_from is None or date_to is None:
                raise ValidationException("date_from and date_to are both required for a CUSTOM date range")
            if date_from > date_to:
                raise ValidationException("date_from must not be after date_to")
            start_date, end_date = date_from, date_to
        else:
            raise ValidationException(f"Unsupported date range preset: {preset}")

        start_utc = datetime.combine(start_date, time.min, tzinfo=IST).astimezone(timezone.utc)
        end_utc = datetime.combine(end_date, time.max, tzinfo=IST).astimezone(timezone.utc)
        return start_utc, end_utc

    @staticmethod
    def build_filters(
        *,
        preset: DateRangePreset,
        date_from: Optional[date],
        date_to: Optional[date],
        project_id: Optional[uuid.UUID],
        source_type: Optional[SourceType],
        executive_id: Optional[uuid.UUID],
        current_user: User,
    ) -> AnalyticsFilters:
        if current_user.role == UserRole.SALES_EXECUTIVE:
            # A sales executive may only ever see their own scope (spec
            # section 3) -- a caller-supplied executive_id is never trusted.
            executive_id = current_user.id
        start_utc, end_utc = AnalyticsService.resolve_date_range(preset, date_from, date_to)
        return AnalyticsFilters(
            start_utc=start_utc,
            end_utc=end_utc,
            preset=preset,
            project_id=project_id,
            source_type=source_type,
            executive_id=executive_id,
        )

    # --- Shared cohort helper ---------------------------------------------------

    @staticmethod
    def _lead_cohort_query(filters: AnalyticsFilters):
        """
        The canonical "unique leads created in period" cohort query, used by
        every metric that counts leads once per canonical buyer. Lead.created_at
        is used as the single creation timestamp (set once, never touched by
        later enquiries/merges), which is what prevents a buyer with multiple
        LeadSource rows from being counted more than once.
        """
        query = select(Lead).where(Lead.created_at >= filters.start_utc, Lead.created_at <= filters.end_utc)
        if filters.executive_id is not None:
            query = query.where(Lead.assigned_executive_id == filters.executive_id)
        if filters.source_type is not None:
            query = query.where(
                Lead.id.in_(select(LeadSource.lead_id).where(LeadSource.source_type == filters.source_type))
            )
        if filters.project_id is not None:
            query = query.where(
                Lead.id.in_(select(LeadQualification.lead_id).where(LeadQualification.project_id == filters.project_id))
            )
        return query

    # --- 1. Overview -------------------------------------------------------------

    @staticmethod
    async def get_overview(db: AsyncSession, filters: AnalyticsFilters) -> dict:
        leads = (await db.execute(AnalyticsService._lead_cohort_query(filters))).scalars().all()
        total_unique_leads = len(leads)

        enquiry_count_query = select(func.count(LeadSource.id)).where(
            LeadSource.submitted_at >= filters.start_utc, LeadSource.submitted_at <= filters.end_utc
        )
        if filters.source_type is not None:
            enquiry_count_query = enquiry_count_query.where(LeadSource.source_type == filters.source_type)
        if filters.project_id is not None or filters.executive_id is not None:
            lead_subquery = select(Lead.id)
            if filters.executive_id is not None:
                lead_subquery = lead_subquery.where(Lead.assigned_executive_id == filters.executive_id)
            if filters.project_id is not None:
                lead_subquery = lead_subquery.where(
                    Lead.id.in_(select(LeadQualification.lead_id).where(LeadQualification.project_id == filters.project_id))
                )
            enquiry_count_query = enquiry_count_query.where(LeadSource.lead_id.in_(lead_subquery))
        total_enquiry_records = (await db.execute(enquiry_count_query)).scalar_one()

        response_stats = await AnalyticsService._compute_response_times(db, filters, leads)
        qualified_count = await AnalyticsService._count_qualified(db, leads)

        visit_stats = await AnalyticsService._visit_counts(db, filters, VisitDateBasis.BOOKING)

        return {
            "date_range": filters.date_range_echo,
            "filters": filters.applied_filters,
            "total_unique_leads": total_unique_leads,
            "total_enquiry_records": total_enquiry_records,
            "median_response_time_seconds": response_stats["median"],
            "qualification_rate_percent": _percent(qualified_count, total_unique_leads),
            "site_visits_booked": visit_stats["total_booked"],
            "attendance_rate_percent": _percent(
                visit_stats["completed"], visit_stats["completed"] + visit_stats["no_show"]
            ),
        }

    # --- 2. Lead acquisition ------------------------------------------------------

    @staticmethod
    async def get_leads(db: AsyncSession, filters: AnalyticsFilters) -> dict:
        leads = (await db.execute(AnalyticsService._lead_cohort_query(filters))).scalars().all()
        total_unique_leads = len(leads)
        lead_ids = [lead.id for lead in leads]

        total_enquiry_records = 0
        by_source: List[LeadsBySource] = []
        if lead_ids:
            enquiry_total_query = select(func.count(LeadSource.id)).where(LeadSource.lead_id.in_(lead_ids))
            total_enquiry_records = (await db.execute(enquiry_total_query)).scalar_one()

            source_rows = (
                await db.execute(
                    select(
                        LeadSource.source_type,
                        func.count(LeadSource.id),
                        func.count(func.distinct(LeadSource.lead_id)),
                    )
                    .where(LeadSource.lead_id.in_(lead_ids))
                    .group_by(LeadSource.source_type)
                )
            ).all()
            for source_type, enquiry_count, unique_lead_count in source_rows:
                by_source.append(
                    LeadsBySource(
                        source_type=source_type,
                        enquiry_count=enquiry_count,
                        unique_lead_count=unique_lead_count,
                        percent_of_total_unique_leads=_percent(unique_lead_count, total_unique_leads),
                    )
                )

        by_project = await AnalyticsService._leads_by_project(db, lead_ids)
        trend = AnalyticsService._lead_trend(leads)

        return {
            "date_range": filters.date_range_echo,
            "filters": filters.applied_filters,
            "total_unique_leads": total_unique_leads,
            "total_enquiry_records": total_enquiry_records,
            "by_source": by_source,
            "by_project": by_project,
            "trend": trend,
        }

    @staticmethod
    async def _leads_by_project(db: AsyncSession, lead_ids: Sequence[uuid.UUID]) -> List[LeadsByProject]:
        """
        Project attribution for a Lead comes from its current LeadQualification
        snapshot (the project the buyer is actually interested in, captured by
        AI extraction) -- Lead and LeadSource carry no project field of their
        own. A lead with no qualification yet is reported under a null/
        "Unspecified" bucket rather than silently dropped or guessed.
        """
        if not lead_ids:
            return []
        rows = (
            await db.execute(
                select(LeadQualification.project_id, Project.name, func.count(func.distinct(LeadQualification.lead_id)))
                .outerjoin(Project, Project.id == LeadQualification.project_id)
                .where(LeadQualification.lead_id.in_(lead_ids), LeadQualification.project_id.isnot(None))
                .group_by(LeadQualification.project_id, Project.name)
            )
        ).all()
        result = [
            LeadsByProject(project_id=project_id, project_name=project_name, unique_lead_count=count)
            for project_id, project_name, count in rows
        ]
        attributed = sum(r.unique_lead_count for r in result)
        unattributed = len(lead_ids) - attributed
        if unattributed > 0:
            result.append(LeadsByProject(project_id=None, project_name="Unspecified", unique_lead_count=unattributed))
        return result

    @staticmethod
    def _lead_trend(leads: Sequence[Lead]) -> List[LeadTrendPoint]:
        counts: dict = {}
        for lead in leads:
            day_key = lead.created_at.astimezone(IST).date().isoformat()
            counts[day_key] = counts.get(day_key, 0) + 1
        return [LeadTrendPoint(date=day, unique_leads=count) for day, count in sorted(counts.items())]

    # --- 3. Source performance ----------------------------------------------------

    @staticmethod
    async def get_sources(db: AsyncSession, filters: AnalyticsFilters) -> dict:
        leads_result = await AnalyticsService.get_leads(db, filters)
        total_unique_leads = leads_result["total_unique_leads"]
        lead_ids_by_source: dict = {}
        if total_unique_leads:
            leads = (await db.execute(AnalyticsService._lead_cohort_query(filters))).scalars().all()
            lead_ids = [lead.id for lead in leads]
            if lead_ids:
                rows = (
                    await db.execute(
                        select(LeadSource.source_type, LeadSource.lead_id).where(LeadSource.lead_id.in_(lead_ids))
                    )
                ).all()
                for source_type, lead_id in rows:
                    lead_ids_by_source.setdefault(source_type, set()).add(lead_id)

        sources: List[SourcePerformance] = []
        for item in leads_result["by_source"]:
            by_project = await AnalyticsService._leads_by_project(db, list(lead_ids_by_source.get(item.source_type, [])))
            sources.append(
                SourcePerformance(
                    source_type=item.source_type,
                    enquiry_count=item.enquiry_count,
                    unique_lead_count=item.unique_lead_count,
                    percent_of_total_unique_leads=item.percent_of_total_unique_leads,
                    by_project=by_project,
                )
            )

        return {"date_range": filters.date_range_echo, "filters": filters.applied_filters, "sources": sources}

    # --- 4. Response time ----------------------------------------------------------

    @staticmethod
    async def _compute_response_times(db: AsyncSession, filters: AnalyticsFilters, leads: Sequence[Lead]) -> dict:
        """
        For each lead in the cohort, the start timestamp is Lead.created_at
        (when the enquiry/lead was received) and the end timestamp is the
        earliest AI- or STAFF-sent, non-system message across any of that
        lead's conversations -- the first actual buyer-facing response, never
        the latest message. A lead with multiple conversations/enquiries is
        still only ever represented once, by its single earliest qualifying
        reply. Leads with no qualifying response are excluded from
        average/median/percentile calculations (never assigned an artificial
        response time) and reported separately as leads_without_response.
        """
        lead_ids = [lead.id for lead in leads]
        first_response_at_by_lead: dict = {}
        if lead_ids:
            rows = (
                await db.execute(
                    select(Conversation.lead_id, func.min(Message.created_at))
                    .join(Message, Message.conversation_id == Conversation.id)
                    .where(
                        Conversation.lead_id.in_(lead_ids),
                        Message.sender_type.in_(QUALIFYING_RESPONSE_SENDER_TYPES),
                        Message.message_type != MessageType.SYSTEM_EVENT,
                    )
                    .group_by(Conversation.lead_id)
                )
            ).all()
            first_response_at_by_lead = dict(rows)

        now = datetime.now(timezone.utc)
        response_seconds: List[float] = []
        not_responded_48h = 0
        with_response = 0
        for lead in leads:
            first_response_at = first_response_at_by_lead.get(lead.id)
            if first_response_at is None:
                if now - lead.created_at >= timedelta(hours=48):
                    not_responded_48h += 1
                continue
            with_response += 1
            delta_seconds = (first_response_at - lead.created_at).total_seconds()
            response_seconds.append(max(delta_seconds, 0.0))
            if delta_seconds > timedelta(hours=48).total_seconds():
                not_responded_48h += 1

        average = round(statistics.fmean(response_seconds), 2) if response_seconds else None
        median = round(statistics.median(response_seconds), 2) if response_seconds else None
        within_2min = sum(1 for s in response_seconds if s <= 120)
        within_5min = sum(1 for s in response_seconds if s <= 300)

        return {
            "leads_evaluated": len(leads),
            "with_response": with_response,
            "without_response": len(leads) - with_response,
            "not_responded_48h": not_responded_48h,
            "average": average,
            "median": median,
            "within_2min_percent": _percent(within_2min, len(response_seconds)),
            "within_5min_percent": _percent(within_5min, len(response_seconds)),
            "response_seconds": response_seconds,
        }

    @staticmethod
    def _bucket_response_times(response_seconds: Sequence[float]) -> List[ResponseTimeBucket]:
        bucket_bounds = [
            ("< 2 min", 0, 120),
            ("2 - 5 min", 120, 300),
            ("5 - 30 min", 300, 1800),
            ("30 min - 2 hr", 1800, 7200),
            ("2 - 24 hr", 7200, 86400),
            ("> 24 hr", 86400, None),
        ]
        buckets = []
        for label, lower, upper in bucket_bounds:
            if upper is None:
                count = sum(1 for s in response_seconds if s >= lower)
            else:
                count = sum(1 for s in response_seconds if lower <= s < upper)
            buckets.append(ResponseTimeBucket(label=label, count=count))
        return buckets

    @staticmethod
    async def get_response_times(db: AsyncSession, filters: AnalyticsFilters) -> dict:
        leads = (await db.execute(AnalyticsService._lead_cohort_query(filters))).scalars().all()
        stats = await AnalyticsService._compute_response_times(db, filters, leads)
        return {
            "date_range": filters.date_range_echo,
            "filters": filters.applied_filters,
            "leads_evaluated": stats["leads_evaluated"],
            "leads_with_response": stats["with_response"],
            "leads_without_response": stats["without_response"],
            "leads_not_responded_within_48h": stats["not_responded_48h"],
            "average_response_time_seconds": stats["average"],
            "median_response_time_seconds": stats["median"],
            "responded_within_2_minutes_percent": stats["within_2min_percent"],
            "responded_within_5_minutes_percent": stats["within_5min_percent"],
            "distribution_buckets": AnalyticsService._bucket_response_times(stats["response_seconds"]),
        }

    # --- 5. Qualification -----------------------------------------------------------

    @staticmethod
    async def _count_qualified(db: AsyncSession, leads: Sequence[Lead]) -> int:
        """
        Current-state count: how many leads in the cohort are, right now,
        fully qualified, using the exact completion criteria from Feature 04
        (QualificationService.is_fully_qualified) -- no new threshold invented.
        """
        lead_ids = [lead.id for lead in leads]
        if not lead_ids:
            return 0
        qualifications = (
            await db.execute(select(LeadQualification).where(LeadQualification.lead_id.in_(lead_ids)))
        ).scalars().all()
        return sum(1 for q in qualifications if QualificationService.is_fully_qualified(q))

    @staticmethod
    async def get_qualification(db: AsyncSession, filters: AnalyticsFilters) -> dict:
        leads = (await db.execute(AnalyticsService._lead_cohort_query(filters))).scalars().all()
        lead_ids = [lead.id for lead in leads]

        qualifications = []
        if lead_ids:
            qualifications = (
                await db.execute(select(LeadQualification).where(LeadQualification.lead_id.in_(lead_ids)))
            ).scalars().all()
        qualified_count = sum(1 for q in qualifications if QualificationService.is_fully_qualified(q))

        conversation_rows = []
        if lead_ids:
            conversation_rows = (
                await db.execute(select(Conversation.id, Conversation.lead_id).where(Conversation.lead_id.in_(lead_ids)))
            ).all()
        conversation_ids = [row[0] for row in conversation_rows]

        ai_handled = 0
        if conversation_ids:
            ai_handled_rows = (
                await db.execute(
                    select(func.count(func.distinct(Message.conversation_id))).where(
                        Message.conversation_id.in_(conversation_ids),
                        Message.sender_type == SenderType.AI,
                        Message.message_type != MessageType.SYSTEM_EVENT,
                    )
                )
            ).scalar_one()
            ai_handled = ai_handled_rows

        handed_off = 0
        if conversation_ids:
            handed_off = (
                await db.execute(
                    select(func.count(func.distinct(Handoff.conversation_id))).where(
                        Handoff.conversation_id.in_(conversation_ids)
                    )
                )
            ).scalar_one()

        by_budget = AnalyticsService._bucket_budgets(qualifications)
        by_configuration = AnalyticsService._count_enum_field(qualifications, "configuration")
        by_purpose = AnalyticsService._count_enum_field(qualifications, "purchase_purpose")
        by_language = AnalyticsService._count_enum_field(qualifications, "preferred_language")

        return {
            "date_range": filters.date_range_echo,
            "filters": filters.applied_filters,
            "ai_handled_conversations": ai_handled,
            "handed_off_conversations": handed_off,
            "handoff_rate_percent": _percent(handed_off, ai_handled),
            "leads_in_cohort": len(leads),
            "qualified_leads": qualified_count,
            "qualification_completion_rate_percent": _percent(qualified_count, len(leads)),
            "by_budget_range": by_budget,
            "by_configuration": by_configuration,
            "by_purchase_purpose": by_purpose,
            "by_language": by_language,
        }

    @staticmethod
    def _count_enum_field(qualifications: Sequence[LeadQualification], field: str) -> List[QualificationBreakdownItem]:
        counts: dict = {}
        for q in qualifications:
            value = getattr(q, field)
            label = value.value if value is not None else "Unspecified"
            counts[label] = counts.get(label, 0) + 1
        return [QualificationBreakdownItem(label=label, count=count) for label, count in sorted(counts.items())]

    @staticmethod
    def _bucket_budgets(qualifications: Sequence[LeadQualification]) -> List[QualificationBreakdownItem]:
        counts = {label: 0 for label, _, _ in _BUDGET_BANDS}
        counts["Unspecified"] = 0
        for q in qualifications:
            value = q.budget_max if q.budget_max is not None else q.budget_min
            if value is None:
                counts["Unspecified"] += 1
                continue
            value = float(value)
            for label, lower, upper in _BUDGET_BANDS:
                if value >= lower and (upper is None or value < upper):
                    counts[label] += 1
                    break
        return [QualificationBreakdownItem(label=label, count=count) for label, count in counts.items()]

    # --- 6. Sales funnel -------------------------------------------------------------

    @staticmethod
    async def get_funnel(db: AsyncSession, filters: AnalyticsFilters) -> dict:
        """
        Current-state funnel: for the cohort of leads created in the selected
        period, how many have reached at least each stage right now (not how
        many *transitioned* into a stage during the period -- Lead.lead_status
        is a single current value with no persisted history of when it
        changed, so a period-based transition count is not available).
        LOST/OPTED_OUT leads exit the forward ladder entirely and are reported
        as separate counts rather than forced into a stage. "Converted" uses
        Lead.lead_status == CONVERTED, which is only ever set by an explicit
        staff action (PATCH /leads/{id}) -- never inferred from a completed
        site visit, per spec section 8/14.
        """
        leads = (await db.execute(AnalyticsService._lead_cohort_query(filters))).scalars().all()
        cohort_size = len(leads)
        excluded_lost = sum(1 for lead in leads if lead.lead_status == LeadStatus.LOST)
        excluded_opted_out = sum(1 for lead in leads if lead.lead_status == LeadStatus.OPTED_OUT)
        ladder_leads = [lead for lead in leads if lead.lead_status not in (LeadStatus.LOST, LeadStatus.OPTED_OUT)]

        stages = []
        previous_count: Optional[int] = None
        for stage_name, floor_status in FUNNEL_LADDER:
            floor_rank = _STAGE_RANK[floor_status]
            count = sum(1 for lead in ladder_leads if _STATUS_RANK[lead.lead_status] >= floor_rank)
            conversion = _percent(count, previous_count) if previous_count is not None else None
            stages.append(
                {
                    "stage": stage_name,
                    "lead_status_floor": floor_status,
                    "count": count,
                    "conversion_from_previous_percent": conversion,
                }
            )
            previous_count = count

        return {
            "date_range": filters.date_range_echo,
            "filters": filters.applied_filters,
            "cohort_size": cohort_size,
            "stages": stages,
            "excluded_lost": excluded_lost,
            "excluded_opted_out": excluded_opted_out,
            "note": (
                "Stage counts are current-state (how many cohort leads have reached at least this "
                "stage right now), not period-based transition counts -- lead_status has no "
                "persisted change history to derive the latter from."
            ),
        }

    # --- 7. Site visits & attendance --------------------------------------------------

    @staticmethod
    def _visit_date_column(date_basis: VisitDateBasis):
        return SiteVisit.created_at if date_basis == VisitDateBasis.BOOKING else SiteVisit.start_time

    @staticmethod
    async def _visit_counts(db: AsyncSession, filters: AnalyticsFilters, date_basis: VisitDateBasis) -> dict:
        date_column = AnalyticsService._visit_date_column(date_basis)
        query = select(SiteVisit).where(date_column >= filters.start_utc, date_column <= filters.end_utc)
        if filters.project_id is not None:
            query = query.where(SiteVisit.project_id == filters.project_id)
        if filters.executive_id is not None:
            query = query.where(SiteVisit.executive_id == filters.executive_id)
        if filters.source_type is not None:
            query = query.where(
                SiteVisit.lead_id.in_(select(LeadSource.lead_id).where(LeadSource.source_type == filters.source_type))
            )
        visits = (await db.execute(query)).scalars().all()

        completed = sum(1 for v in visits if v.status == SiteVisitStatus.COMPLETED)
        no_show = sum(1 for v in visits if v.status == SiteVisitStatus.NO_SHOW)
        return {
            "visits": visits,
            "total_booked": len(visits),
            "confirmed": sum(1 for v in visits if v.status == SiteVisitStatus.CONFIRMED),
            "completed": completed,
            "no_show": no_show,
            "cancelled": sum(1 for v in visits if v.status == SiteVisitStatus.CANCELLED),
        }

    @staticmethod
    async def get_site_visits(db: AsyncSession, filters: AnalyticsFilters, date_basis: VisitDateBasis) -> dict:
        stats = await AnalyticsService._visit_counts(db, filters, date_basis)
        visits = stats["visits"]
        date_column_attr = "created_at" if date_basis == VisitDateBasis.BOOKING else "start_time"

        trend_counts: dict = {}
        project_counts: dict = {}
        project_ids = {v.project_id for v in visits}
        project_names: dict = {}
        if project_ids:
            rows = (await db.execute(select(Project.id, Project.name).where(Project.id.in_(project_ids)))).all()
            project_names = dict(rows)

        for visit in visits:
            ts = getattr(visit, date_column_attr)
            day_key = ts.astimezone(IST).date().isoformat()
            trend_counts[day_key] = trend_counts.get(day_key, 0) + 1
            project_counts[visit.project_id] = project_counts.get(visit.project_id, 0) + 1

        trend = [VisitTrendPoint(date=day, count=count) for day, count in sorted(trend_counts.items())]
        by_project = [
            ProjectVisitDistribution(project_id=pid, project_name=project_names.get(pid), count=count)
            for pid, count in sorted(project_counts.items(), key=lambda kv: -kv[1])
        ]

        denom = stats["completed"] + stats["no_show"]
        return {
            "date_range": filters.date_range_echo,
            "filters": filters.applied_filters,
            "date_basis": date_basis,
            "total_booked": stats["total_booked"],
            "confirmed": stats["confirmed"],
            "completed": stats["completed"],
            "no_show": stats["no_show"],
            "cancelled": stats["cancelled"],
            "attendance_rate_percent": _percent(stats["completed"], denom),
            "no_show_rate_percent": _percent(stats["no_show"], denom),
            "trend": trend,
            "by_project": by_project,
        }

    # --- 8. Executive performance -----------------------------------------------------

    @staticmethod
    async def get_executives(db: AsyncSession, filters: AnalyticsFilters) -> dict:
        exec_query = select(User).where(User.role == UserRole.SALES_EXECUTIVE)
        if filters.executive_id is not None:
            exec_query = exec_query.where(User.id == filters.executive_id)
        executives = (await db.execute(exec_query.order_by(User.full_name))).scalars().all()

        results: List[ExecutivePerformance] = []
        for executive in executives:
            # Current assignment: leads whose assigned_executive_id is this
            # executive right now, within the cohort window.
            assigned_leads_query = AnalyticsService._lead_cohort_query(
                AnalyticsFilters(
                    start_utc=filters.start_utc,
                    end_utc=filters.end_utc,
                    preset=filters.preset,
                    project_id=filters.project_id,
                    source_type=filters.source_type,
                    executive_id=executive.id,
                )
            )
            assigned_leads = (await db.execute(assigned_leads_query)).scalars().all()
            leads_contacted = sum(1 for lead in assigned_leads if lead.lead_status != LeadStatus.NEW)
            qualified_leads = await AnalyticsService._count_qualified(db, assigned_leads)

            # Historical: every ConversationAssignment ever created for this
            # executive, vs. current: still ASSIGNED/ACCEPTED right now.
            assignment_rows = (
                await db.execute(
                    select(ConversationAssignment).where(
                        ConversationAssignment.executive_id == executive.id,
                        ConversationAssignment.created_at >= filters.start_utc,
                        ConversationAssignment.created_at <= filters.end_utc,
                    )
                )
            ).scalars().all()
            conversations_assigned_historical = len({a.conversation_id for a in assignment_rows})
            conversations_assigned_current = len(
                {
                    a.conversation_id
                    for a in assignment_rows
                    if a.status in (AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED)
                }
            )
            accepted_handoffs = len({a.conversation_id for a in assignment_rows if a.accepted_at is not None})

            visit_filters = AnalyticsFilters(
                start_utc=filters.start_utc,
                end_utc=filters.end_utc,
                preset=filters.preset,
                project_id=filters.project_id,
                source_type=filters.source_type,
                executive_id=executive.id,
            )
            visit_stats = await AnalyticsService._visit_counts(db, visit_filters, VisitDateBasis.BOOKING)
            denom = visit_stats["completed"] + visit_stats["no_show"]

            results.append(
                ExecutivePerformance(
                    executive_id=executive.id,
                    executive_name=executive.full_name,
                    assigned_leads_current=len(assigned_leads),
                    leads_contacted=leads_contacted,
                    qualified_leads=qualified_leads,
                    conversations_assigned_current=conversations_assigned_current,
                    conversations_assigned_historical=conversations_assigned_historical,
                    accepted_handoffs=accepted_handoffs,
                    site_visits_booked=visit_stats["total_booked"],
                    site_visits_completed=visit_stats["completed"],
                    no_show_count=visit_stats["no_show"],
                    attendance_rate_percent=_percent(visit_stats["completed"], denom),
                )
            )

        return {"date_range": filters.date_range_echo, "filters": filters.applied_filters, "executives": results}

    # --- 9. Reminders ------------------------------------------------------------------

    @staticmethod
    def _reminder_date_column(date_basis: ReminderDateBasis):
        if date_basis == ReminderDateBasis.CREATED:
            return VisitReminder.created_at
        # "Executed" = when the worker actually finished processing this
        # reminder. sent_at is set for SENT/SIMULATED; a FAILED/SKIPPED/
        # CANCELLED reminder has no sent_at, so fall back to the row's own
        # updated_at (TimestampMixin), which is bumped on every status change.
        return func.coalesce(VisitReminder.sent_at, VisitReminder.updated_at)

    @staticmethod
    async def get_reminders(db: AsyncSession, filters: AnalyticsFilters, date_basis: ReminderDateBasis) -> dict:
        date_column = AnalyticsService._reminder_date_column(date_basis)
        query = select(VisitReminder).where(date_column >= filters.start_utc, date_column <= filters.end_utc)
        if filters.executive_id is not None or filters.project_id is not None or filters.source_type is not None:
            visit_subquery = select(SiteVisit.id)
            if filters.executive_id is not None:
                visit_subquery = visit_subquery.where(SiteVisit.executive_id == filters.executive_id)
            if filters.project_id is not None:
                visit_subquery = visit_subquery.where(SiteVisit.project_id == filters.project_id)
            if filters.source_type is not None:
                visit_subquery = visit_subquery.where(
                    SiteVisit.lead_id.in_(select(LeadSource.lead_id).where(LeadSource.source_type == filters.source_type))
                )
            query = query.where(VisitReminder.site_visit_id.in_(visit_subquery))

        reminders = (await db.execute(query)).scalars().all()

        status_counts: dict = {status: 0 for status in ReminderStatus}
        for reminder in reminders:
            status_counts[reminder.status] += 1

        sent = status_counts[ReminderStatus.SENT]
        simulated = status_counts[ReminderStatus.SIMULATED]
        failed = status_counts[ReminderStatus.FAILED]
        cancelled = status_counts[ReminderStatus.CANCELLED]
        skipped = status_counts[ReminderStatus.SKIPPED]
        # Failure rate denominator is attempted-delivery outcomes only
        # (sent + simulated + failed); cancelled and skipped reminders never
        # reached a delivery attempt and are excluded, per spec section 11's
        # instruction to never blend SIMULATED into a single "success" figure
        # and to keep each outcome distinguishable.
        attempted = sent + simulated + failed

        date_attr = "created_at" if date_basis == ReminderDateBasis.CREATED else None
        trend_counts: dict = {}
        for reminder in reminders:
            if date_attr is not None:
                ts = reminder.created_at
            else:
                ts = reminder.sent_at or reminder.updated_at
            trend_counts.setdefault(ts.astimezone(IST).date().isoformat(), 0)
            trend_counts[ts.astimezone(IST).date().isoformat()] += 1

        return {
            "date_range": filters.date_range_echo,
            "filters": filters.applied_filters,
            "date_basis": date_basis,
            "total_scheduled": len(reminders),
            "sent": sent,
            "simulated": simulated,
            "failed": failed,
            "cancelled": cancelled,
            "skipped": skipped,
            "failure_rate_percent": _percent(failed, attempted),
            "status_breakdown": [
                ReminderStatusBreakdownItem(status=status, count=count) for status, count in status_counts.items()
            ],
            "trend": [ReminderTrendPoint(date=day, count=count) for day, count in sorted(trend_counts.items())],
        }
