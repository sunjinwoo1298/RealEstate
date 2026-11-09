from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from backend.models.customer_notification_delivery import (
    CustomerDeliveryStatus,
    CustomerNotificationChannel,
    CustomerNotificationEvent,
)

CustomerNotificationStatus = Literal["PENDING", "SENT", "SIMULATED", "FAILED", "NOT_SENT"]


class CustomerNotificationPublic(BaseModel):
    """
    Customer-safe view. Deliberately omits the recipient snapshot, provider
    message id/errors, payload JSON, attempt counters and every account/lead
    identifier.
    """

    id: uuid.UUID
    event_type: CustomerNotificationEvent
    channel: CustomerNotificationChannel
    status: CustomerNotificationStatus
    project_name: Optional[str]
    visit_id: Optional[uuid.UUID]
    visit_start_time: Optional[datetime]
    created_at: datetime
    sent_at: Optional[datetime]


class CustomerNotificationListResponse(BaseModel):
    items: List[CustomerNotificationPublic]
    total: int
    limit: int
    offset: int


class NotificationPreferences(BaseModel):
    transactional_email_enabled: bool
    # Read-only mirror of the account's marketing consent. No marketing email
    # exists in this release, so it is informational and never patchable here.
    marketing_email_enabled: bool
    email_verified: bool


class NotificationPreferencesUpdate(BaseModel):
    """Only the customer-controllable field; extra fields are ignored by Pydantic."""

    transactional_email_enabled: bool


class StaffDeliveryDiagnostic(BaseModel):
    """Safe diagnostics: no recipient address, payload or provider message id."""

    id: uuid.UUID
    event_type: CustomerNotificationEvent
    status: CustomerDeliveryStatus
    site_visit_id: Optional[uuid.UUID]
    visit_reminder_id: Optional[uuid.UUID]
    project_name: Optional[str]
    attempt_count: int
    last_attempt_at: Optional[datetime]
    next_attempt_at: datetime
    last_error: Optional[str]
    created_at: datetime
    sent_at: Optional[datetime]


class StaffDeliveryListResponse(BaseModel):
    items: List[StaffDeliveryDiagnostic]
    total: int
