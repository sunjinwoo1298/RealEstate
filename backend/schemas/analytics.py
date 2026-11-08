from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.models.lead import LeadStatus
from backend.models.lead_source import SourceType
from backend.models.site_visit import SiteVisitStatus
from backend.models.visit_reminder import ReminderStatus


class DateRangePreset(str, enum.Enum):
    TODAY = "TODAY"
    LAST_7_DAYS = "LAST_7_DAYS"
    LAST_30_DAYS = "LAST_30_DAYS"
    THIS_MONTH = "THIS_MONTH"
    PREVIOUS_MONTH = "PREVIOUS_MONTH"
    CUSTOM = "CUSTOM"


class VisitDateBasis(str, enum.Enum):
    """Which SiteVisit timestamp a site-visit query is filtered/grouped by."""

    BOOKING = "BOOKING"  # SiteVisit.created_at -- when the booking was made
    VISIT = "VISIT"  # SiteVisit.start_time -- when the visit occurs/occurred


class ReminderDateBasis(str, enum.Enum):
    """Which VisitReminder timestamp a reminder query is filtered/grouped by."""

    CREATED = "CREATED"  # VisitReminder.created_at -- when the reminder row was scheduled
    EXECUTED = "EXECUTED"  # when the worker actually processed it (see AnalyticsService)


class DateRangeEcho(BaseModel):
    """Echoes the resolved UTC window back to the caller so the UI can label charts unambiguously."""

    preset: DateRangePreset
    start_utc: datetime
    end_utc: datetime


class AppliedFilters(BaseModel):
    project_id: Optional[uuid.UUID] = None
    source_type: Optional[SourceType] = None
    executive_id: Optional[uuid.UUID] = None


# --- Overview ---


class OverviewResponse(BaseModel):
    date_range: DateRangeEcho
    filters: AppliedFilters
    total_unique_leads: int
    total_enquiry_records: int
    median_response_time_seconds: Optional[float]
    qualification_rate_percent: Optional[float]
    site_visits_booked: int
    attendance_rate_percent: Optional[float]


# --- Lead acquisition ---


class LeadTrendPoint(BaseModel):
    date: str
    unique_leads: int


class LeadsBySource(BaseModel):
    source_type: SourceType
    enquiry_count: int
    unique_lead_count: int
    percent_of_total_unique_leads: Optional[float]


class LeadsByProject(BaseModel):
    project_id: Optional[uuid.UUID]
    project_name: Optional[str]
    unique_lead_count: int


class LeadAnalyticsResponse(BaseModel):
    date_range: DateRangeEcho
    filters: AppliedFilters
    total_unique_leads: int
    total_enquiry_records: int
    by_source: List[LeadsBySource]
    by_project: List[LeadsByProject]
    trend: List[LeadTrendPoint]


class SourcePerformance(BaseModel):
    source_type: SourceType
    enquiry_count: int
    unique_lead_count: int
    percent_of_total_unique_leads: Optional[float]
    by_project: List[LeadsByProject]


class SourceAnalyticsResponse(BaseModel):
    date_range: DateRangeEcho
    filters: AppliedFilters
    sources: List[SourcePerformance]


# --- Response time ---


class ResponseTimeBucket(BaseModel):
    label: str
    count: int


class ResponseTimeAnalyticsResponse(BaseModel):
    date_range: DateRangeEcho
    filters: AppliedFilters
    leads_evaluated: int
    leads_with_response: int
    leads_without_response: int
    leads_not_responded_within_48h: int
    average_response_time_seconds: Optional[float]
    median_response_time_seconds: Optional[float]
    responded_within_2_minutes_percent: Optional[float]
    responded_within_5_minutes_percent: Optional[float]
    distribution_buckets: List[ResponseTimeBucket]


# --- Qualification ---


class QualificationBreakdownItem(BaseModel):
    label: str
    count: int


class QualificationAnalyticsResponse(BaseModel):
    date_range: DateRangeEcho
    filters: AppliedFilters
    ai_handled_conversations: int
    handed_off_conversations: int
    handoff_rate_percent: Optional[float]
    leads_in_cohort: int
    qualified_leads: int
    qualification_completion_rate_percent: Optional[float]
    by_budget_range: List[QualificationBreakdownItem]
    by_configuration: List[QualificationBreakdownItem]
    by_purchase_purpose: List[QualificationBreakdownItem]
    by_language: List[QualificationBreakdownItem]


# --- Funnel ---


class FunnelStage(BaseModel):
    stage: str
    lead_status_floor: Optional[LeadStatus]
    count: int
    conversion_from_previous_percent: Optional[float]


class FunnelAnalyticsResponse(BaseModel):
    date_range: DateRangeEcho
    filters: AppliedFilters
    cohort_size: int
    stages: List[FunnelStage]
    excluded_lost: int
    excluded_opted_out: int
    note: str


# --- Site visits ---


class VisitTrendPoint(BaseModel):
    date: str
    count: int


class ProjectVisitDistribution(BaseModel):
    project_id: Optional[uuid.UUID]
    project_name: Optional[str]
    count: int


class SiteVisitAnalyticsResponse(BaseModel):
    date_range: DateRangeEcho
    filters: AppliedFilters
    date_basis: VisitDateBasis
    total_booked: int
    confirmed: int
    completed: int
    no_show: int
    cancelled: int
    attendance_rate_percent: Optional[float]
    no_show_rate_percent: Optional[float]
    trend: List[VisitTrendPoint]
    by_project: List[ProjectVisitDistribution]


# --- Executive performance ---


class ExecutivePerformance(BaseModel):
    executive_id: uuid.UUID
    executive_name: str
    assigned_leads_current: int
    leads_contacted: int
    qualified_leads: int
    conversations_assigned_current: int
    conversations_assigned_historical: int
    accepted_handoffs: int
    site_visits_booked: int
    site_visits_completed: int
    no_show_count: int
    attendance_rate_percent: Optional[float]


class ExecutiveAnalyticsResponse(BaseModel):
    date_range: DateRangeEcho
    filters: AppliedFilters
    executives: List[ExecutivePerformance]


# --- Reminders ---


class ReminderStatusBreakdownItem(BaseModel):
    status: ReminderStatus
    count: int


class ReminderTrendPoint(BaseModel):
    date: str
    count: int


class ReminderAnalyticsResponse(BaseModel):
    date_range: DateRangeEcho
    filters: AppliedFilters
    date_basis: ReminderDateBasis
    total_scheduled: int
    sent: int
    simulated: int
    failed: int
    cancelled: int
    skipped: int
    failure_rate_percent: Optional[float]
    status_breakdown: List[ReminderStatusBreakdownItem]
    trend: List[ReminderTrendPoint]
