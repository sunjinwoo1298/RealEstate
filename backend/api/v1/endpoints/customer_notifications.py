from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_customer, get_current_user, get_db_session, verify_same_origin
from backend.core.exceptions import ForbiddenException
from backend.core.rate_limit import enforce_customer_delivery_retry_rate_limit
from backend.models.customer_account import CustomerAccount
from backend.models.customer_notification_delivery import (
    CustomerDeliveryStatus,
    CustomerNotificationDelivery,
    CustomerNotificationEvent,
)
from backend.models.user import User, UserRole
from backend.schemas.customer_notification import (
    CustomerNotificationListResponse,
    CustomerNotificationPublic,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    StaffDeliveryDiagnostic,
    StaffDeliveryListResponse,
)
from backend.services.customer_notification_service import CustomerNotificationService

customer_router = APIRouter(prefix="/customer", tags=["Customer Notifications"])
staff_router = APIRouter(prefix="/admin/customer-notifications", tags=["Customer Notification Operations"])


def _to_public(delivery: CustomerNotificationDelivery) -> CustomerNotificationPublic:
    payload = delivery.payload or {}
    start_raw: Optional[str] = payload.get("start_time")
    return CustomerNotificationPublic(
        id=delivery.id,
        event_type=delivery.event_type,
        channel=delivery.channel,
        status=CustomerNotificationService.customer_status(delivery),  # type: ignore[arg-type]
        project_name=payload.get("project_name"),
        visit_id=delivery.site_visit_id,
        visit_start_time=datetime.fromisoformat(start_raw) if start_raw else None,
        created_at=delivery.created_at,
        sent_at=delivery.sent_at,
    )


def _preferences(customer: CustomerAccount) -> NotificationPreferences:
    return NotificationPreferences(
        transactional_email_enabled=customer.transactional_email_enabled,
        marketing_email_enabled=customer.marketing_consent,
        email_verified=customer.email_verified_at is not None,
    )


# Static paths are declared before "/notifications/{notification_id}".
@customer_router.get("/notification-preferences", response_model=NotificationPreferences)
async def get_notification_preferences(
    current_customer: CustomerAccount = Depends(get_current_customer),
) -> NotificationPreferences:
    return _preferences(current_customer)


@customer_router.patch("/notification-preferences", response_model=NotificationPreferences)
async def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> NotificationPreferences:
    customer = await CustomerNotificationService.update_preferences(
        db, current_customer, transactional_email_enabled=payload.transactional_email_enabled
    )
    return _preferences(customer)


@customer_router.get(
    "/notifications", response_model=CustomerNotificationListResponse, summary="The customer's own notification history"
)
async def list_my_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerNotificationListResponse:
    rows, total = await CustomerNotificationService.list_for_customer(db, current_customer, limit=limit, offset=offset)
    return CustomerNotificationListResponse(items=[_to_public(r) for r in rows], total=total, limit=limit, offset=offset)


@customer_router.get("/notifications/{notification_id}", response_model=CustomerNotificationPublic)
async def get_my_notification(
    notification_id: uuid.UUID,
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerNotificationPublic:
    return _to_public(await CustomerNotificationService.get_owned(db, current_customer, notification_id))


# ----- staff / admin -----------------------------------------------------------


def _to_diagnostic(delivery: CustomerNotificationDelivery) -> StaffDeliveryDiagnostic:
    return StaffDeliveryDiagnostic(
        id=delivery.id,
        event_type=delivery.event_type,
        status=delivery.status,
        site_visit_id=delivery.site_visit_id,
        visit_reminder_id=delivery.visit_reminder_id,
        project_name=(delivery.payload or {}).get("project_name"),
        attempt_count=delivery.attempt_count,
        last_attempt_at=delivery.last_attempt_at,
        next_attempt_at=delivery.next_attempt_at,
        last_error=delivery.last_error,
        created_at=delivery.created_at,
        sent_at=delivery.sent_at,
    )


@staff_router.get("", response_model=StaffDeliveryListResponse, summary="List customer deliveries (admin/manager)")
async def list_customer_deliveries(
    delivery_status: Optional[CustomerDeliveryStatus] = Query(default=None, alias="status"),
    event_type: Optional[CustomerNotificationEvent] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> StaffDeliveryListResponse:
    # Sales executives get no access: delivery rows concern other customers
    # and carry no per-executive scoping that would make them safe to share.
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise ForbiddenException("Only an admin or manager may view customer notification deliveries")
    rows, total = await CustomerNotificationService.list_for_staff(
        db, status=delivery_status, event_type=event_type, limit=limit, offset=offset
    )
    return StaffDeliveryListResponse(items=[_to_diagnostic(r) for r in rows], total=total)


@staff_router.post("/{delivery_id}/retry", response_model=StaffDeliveryDiagnostic, summary="Retry a failed delivery (admin)")
async def retry_customer_delivery(
    delivery_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    _origin_ok: None = Depends(verify_same_origin),
) -> StaffDeliveryDiagnostic:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException("Only an admin may retry a customer notification delivery")
    await enforce_customer_delivery_retry_rate_limit(str(current_user.id))
    delivery = await CustomerNotificationService.retry_failed(db, delivery_id, actor_id=current_user.id)
    return _to_diagnostic(delivery)
