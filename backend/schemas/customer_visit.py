from __future__ import annotations
import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from backend.models.site_visit import SiteVisitStatus
from backend.models.visit_reminder import ReminderType

DISPLAY_TIMEZONE = "Asia/Kolkata"


class CustomerAvailableSlotPublic(BaseModel):
    """
    Customer-safe slot representation -- deliberately omits
    available_executive_count (an internal capacity figure) and any staff
    identifier, per spec section 4's "do not expose internal capacity
    calculations or staff scheduling details."
    """

    start_time: datetime
    end_time: datetime


class CustomerAvailableSlotsResponse(BaseModel):
    project_id: uuid.UUID
    date: date
    display_timezone: str = DISPLAY_TIMEZONE
    slots: List[CustomerAvailableSlotPublic]


class CustomerVisitCreateRequest(BaseModel):
    """
    Deliberately accepts only project_id/scheduled_start(/scheduled_end) --
    customer_id, lead_id, executive_id, attendance_status, reminder status
    and booking status have no field here at all, so Pydantic's default
    extra="ignore" silently drops any such field a caller sends (same
    convention already used by CustomerProfileUpdateRequest).
    """

    project_id: uuid.UUID
    scheduled_start: datetime
    # Optional, per the spec's suggested request shape -- the actual end
    # time is always authoritatively derived from the project's configured
    # visit duration inside BookingService; if provided, this is only
    # cross-checked against that derived value so a stale frontend slot
    # can be rejected with a clear message rather than silently booking a
    # different time range than what the customer saw.
    scheduled_end: Optional[datetime] = None


class CustomerVisitRescheduleRequest(BaseModel):
    scheduled_start: datetime
    scheduled_end: Optional[datetime] = None


class CustomerReminderPublic(BaseModel):
    """
    Minimal customer-safe reminder representation: type + a coarse status
    only. Never exposes attempt_count, failure_reason, provider error
    details, or the reminder's own internal id.
    """

    reminder_type: ReminderType
    status: str


class CustomerSiteVisitPublic(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    project_location: Optional[str] = None
    project_rera_number: Optional[str] = None
    map_url: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: datetime
    display_timezone: str = DISPLAY_TIMEZONE
    status: SiteVisitStatus
    booking_reference: str
    executive_full_name: Optional[str] = None
    reminder_24h: Optional[CustomerReminderPublic] = None
    reminder_2h: Optional[CustomerReminderPublic] = None
    created_at: datetime
    updated_at: datetime


class CustomerSiteVisitListResponse(BaseModel):
    items: List[CustomerSiteVisitPublic]
    total: int
