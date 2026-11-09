from __future__ import annotations
import random
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import ConflictException, NotFoundException
from backend.core.logging import logger
from backend.models.customer_account import CustomerAccount, CustomerAccountStatus
from backend.models.customer_notification_delivery import (
    CustomerDeliveryStatus,
    CustomerNotificationChannel,
    CustomerNotificationDelivery,
    CustomerNotificationEvent,
)
from backend.models.project import Project
from backend.models.site_visit import SiteVisit, SiteVisitStatus
from backend.models.user import User
from backend.models.visit_reminder import ReminderStatus, ReminderType, VisitReminder
from backend.services.customer_email_provider import (
    CustomerEmailProvider,
    EmailPermanentError,
    EmailTransientError,
    OutgoingEmail,
)
from backend.services.customer_email_templates import TEMPLATE_KEYS, render_email

_Status = CustomerDeliveryStatus
_Event = CustomerNotificationEvent

_EVENT_KEY_SUFFIX = {
    _Event.SITE_VISIT_BOOKED: "booked",
    _Event.SITE_VISIT_RESCHEDULED: "rescheduled",
    _Event.SITE_VISIT_CANCELLED: "cancelled",
}
_REMINDER_EVENT = {
    ReminderType.H24: _Event.SITE_VISIT_REMINDER_24H,
    ReminderType.H2: _Event.SITE_VISIT_REMINDER_2H,
}
_IN_FLIGHT = (_Status.PENDING, _Status.PROCESSING)

# Customer-safe vocabulary (never the raw internal state machine).
_CUSTOMER_STATUS = {
    _Status.PENDING: "PENDING",
    _Status.PROCESSING: "PENDING",
    _Status.SENT: "SENT",
    _Status.SIMULATED: "SIMULATED",
    _Status.FAILED: "FAILED",
    _Status.SKIPPED: "NOT_SENT",
    _Status.CANCELLED: "NOT_SENT",
}

_EMAIL_IN_TEXT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def sanitize_error(message: str) -> str:
    """Strips anything resembling a secret or an email address and bounds length."""
    cleaned = message or ""
    if settings.EMAIL_API_KEY:
        cleaned = cleaned.replace(settings.EMAIL_API_KEY, "[redacted]")
    cleaned = _EMAIL_IN_TEXT.sub("[email]", cleaned)
    cleaned = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", cleaned)
    return cleaned[:300]


def describe_exception(exc: Exception) -> str:
    """Typed provider errors carry pre-sanitized messages; anything else is logged by class only."""
    if isinstance(exc, (EmailTransientError, EmailPermanentError)):
        return sanitize_error(f"{type(exc).__name__}: {exc}")
    return f"{type(exc).__name__}: unexpected delivery error"


def compute_backoff_seconds(
    attempt_count: int,
    *,
    retry_after: Optional[float] = None,
    base: Optional[float] = None,
    max_seconds: Optional[float] = None,
    rand: Callable[[], float] = random.random,
) -> float:
    """
    Bounded exponential backoff with equal jitter: the delay lies in
    [exp/2, exp], where exp = min(base * 2^(attempt-1), max). A provider
    Retry-After is honoured as a floor (capped at one hour).
    """
    base = settings.CUSTOMER_EMAIL_RETRY_BASE_SECONDS if base is None else base
    max_seconds = settings.CUSTOMER_EMAIL_RETRY_MAX_SECONDS if max_seconds is None else max_seconds
    exp = min(base * (2 ** max(attempt_count - 1, 0)), max_seconds)
    delay = exp / 2 + rand() * exp / 2
    if retry_after:
        delay = max(delay, min(retry_after, 3600.0))
    return delay


def ineligibility_reason(account: Optional[CustomerAccount]) -> Optional[str]:
    """Returns a clear non-delivery reason, or None when email may be attempted."""
    if account is None:
        return "NO_CUSTOMER_ACCOUNT"
    if account.status != CustomerAccountStatus.ACTIVE:
        return "ACCOUNT_NOT_ACTIVE"
    if account.email_verified_at is None:
        return "EMAIL_NOT_VERIFIED"
    if not account.transactional_email_enabled:
        return "TRANSACTIONAL_EMAIL_DISABLED_BY_CUSTOMER"
    return None


@dataclass
class ReminderEmailOutcome:
    simulated: bool = False
    skipped_reason: Optional[str] = None


class CustomerNotificationService:
    """
    Customer transactional notifications (Feature 14). Creation methods only
    add rows to the caller's session and never commit -- BookingService
    commits them atomically with the booking change. Sending always happens
    outside any open transaction.
    """

    # ----- outbox creation (inside the domain transaction) -----------------

    @staticmethod
    async def _account_for_lead(db: AsyncSession, lead_id: uuid.UUID) -> Optional[CustomerAccount]:
        result = await db.execute(select(CustomerAccount).where(CustomerAccount.lead_id == lead_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def _build_payload(
        db: AsyncSession, account: CustomerAccount, visit: SiteVisit, *, include_executive: bool = True
    ) -> Dict[str, Any]:
        project = (await db.execute(select(Project).where(Project.id == visit.project_id))).scalar_one_or_none()
        executive_name = None
        if include_executive and visit.executive_id is not None:
            executive_name = (
                await db.execute(select(User.full_name).where(User.id == visit.executive_id))
            ).scalar_one_or_none()
        full_name = (account.full_name or "").strip()
        payload: Dict[str, Any] = {
            "first_name": full_name.split()[0] if full_name else None,
            "project_name": project.name if project else None,
            "project_location": project.location if project else None,
            "project_rera_number": project.rera_number if project else None,
            "start_time": visit.start_time.isoformat(),
            "visit_id": str(visit.id),
        }
        if executive_name:
            payload["executive_name"] = executive_name
        return payload

    @staticmethod
    async def _insert_if_absent(db: AsyncSession, values: Dict[str, Any]) -> None:
        # ON CONFLICT DO NOTHING keeps a duplicate event from creating a
        # second row *and* from aborting the surrounding booking transaction.
        await db.execute(
            pg_insert(CustomerNotificationDelivery)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
        )

    @staticmethod
    def _base_values(
        account: CustomerAccount, event: CustomerNotificationEvent, payload: Dict[str, Any], key: str
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "id": uuid.uuid4(),
            "customer_account_id": account.id,
            "channel": CustomerNotificationChannel.EMAIL,
            "event_type": event,
            "recipient": account.email,
            "template_key": TEMPLATE_KEYS[event],
            "payload": payload,
            "idempotency_key": key,
            "status": _Status.PENDING,
            "attempt_count": 0,
            "next_attempt_at": now,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    async def enqueue_visit_event(
        db: AsyncSession,
        visit: SiteVisit,
        event: CustomerNotificationEvent,
        *,
        previous_start_time: Optional[datetime] = None,
    ) -> bool:
        """
        Adds a PENDING delivery for a booked/rescheduled/cancelled visit to
        the current (uncommitted) transaction. Returns False when the visit's
        lead has no customer account (nothing to notify). Never raises for a
        missing/unverified email -- that is decided at send time, so the
        booking is never blocked by email availability.
        """
        account = await CustomerNotificationService._account_for_lead(db, visit.lead_id)
        if account is None:
            return False

        payload = await CustomerNotificationService._build_payload(
            db, account, visit, include_executive=event != _Event.SITE_VISIT_CANCELLED
        )
        if previous_start_time is not None:
            payload["previous_start_time"] = previous_start_time.isoformat()

        key = f"visit:{visit.id}:{_EVENT_KEY_SUFFIX[event]}:v{visit.booking_version}"
        values = CustomerNotificationService._base_values(account, event, payload, key)
        values.update(lead_id=visit.lead_id, site_visit_id=visit.id, booking_version=visit.booking_version)

        if event in (_Event.SITE_VISIT_RESCHEDULED, _Event.SITE_VISIT_CANCELLED):
            # An unsent older booked/rescheduled email is superseded. A
            # reschedule bumps the version (older = strictly lower); a
            # cancellation keeps it (older = lower or equal).
            version_col = CustomerNotificationDelivery.booking_version
            older = (
                version_col < visit.booking_version
                if event == _Event.SITE_VISIT_RESCHEDULED
                else version_col <= visit.booking_version
            )
            await db.execute(
                update(CustomerNotificationDelivery)
                .where(
                    CustomerNotificationDelivery.site_visit_id == visit.id,
                    CustomerNotificationDelivery.status == _Status.PENDING,
                    CustomerNotificationDelivery.event_type.in_([_Event.SITE_VISIT_BOOKED, _Event.SITE_VISIT_RESCHEDULED]),
                    older,
                )
                .values(status=_Status.CANCELLED, last_error="SUPERSEDED")
            )
        await CustomerNotificationService._insert_if_absent(db, values)
        return True

    @staticmethod
    async def cancel_deliveries_for_reminders(db: AsyncSession, reminder_ids: List[uuid.UUID]) -> None:
        """Called by ReminderService when it cancels reminders (reschedule/cancel/attendance)."""
        if not reminder_ids:
            return
        await db.execute(
            update(CustomerNotificationDelivery)
            .where(
                CustomerNotificationDelivery.visit_reminder_id.in_(reminder_ids),
                CustomerNotificationDelivery.status.in_(_IN_FLIGHT),
            )
            .values(status=_Status.CANCELLED, last_error="SUPERSEDED")
        )

    # ----- worker: transactional events -------------------------------------

    @staticmethod
    async def claim_due(
        db: AsyncSession, *, limit: Optional[int] = None, site_visit_ids: Optional[List[uuid.UUID]] = None
    ) -> List[uuid.UUID]:
        """
        Claims due non-reminder deliveries with FOR UPDATE SKIP LOCKED. A
        PROCESSING row whose lease expired (worker crashed mid-send) is
        reclaimed, so a crash never silently loses a pending delivery.
        `site_visit_ids` optionally narrows the claim to those visits (used by
        tests against a shared database; the worker never passes it).
        """
        now = datetime.now(timezone.utc)
        lease_cutoff = now - timedelta(seconds=settings.CUSTOMER_EMAIL_PROCESSING_LEASE_SECONDS)
        batch = limit or settings.CUSTOMER_EMAIL_WORKER_BATCH_SIZE
        scope = []
        if site_visit_ids is not None:
            scope.append(CustomerNotificationDelivery.site_visit_id.in_(site_visit_ids))
        result = await db.execute(
            select(CustomerNotificationDelivery)
            .where(
                CustomerNotificationDelivery.visit_reminder_id.is_(None),
                *scope,
                or_(
                    and_(
                        CustomerNotificationDelivery.status == _Status.PENDING,
                        CustomerNotificationDelivery.next_attempt_at <= now,
                    ),
                    and_(
                        CustomerNotificationDelivery.status == _Status.PROCESSING,
                        CustomerNotificationDelivery.last_attempt_at < lease_cutoff,
                    ),
                ),
            )
            .order_by(CustomerNotificationDelivery.next_attempt_at)
            .limit(batch)
            .with_for_update(skip_locked=True)
        )
        claimed: List[uuid.UUID] = []
        for delivery in result.scalars().all():
            if delivery.attempt_count >= settings.CUSTOMER_EMAIL_MAX_ATTEMPTS:
                delivery.status = _Status.FAILED
                delivery.last_error = "Worker interrupted after the final attempt; outcome unknown"
                continue
            delivery.status = _Status.PROCESSING
            delivery.attempt_count += 1
            delivery.last_attempt_at = now
            claimed.append(delivery.id)
        await db.commit()
        return claimed

    @staticmethod
    async def process_delivery(db: AsyncSession, delivery_id: uuid.UUID, provider: CustomerEmailProvider) -> None:
        delivery = (
            await db.execute(select(CustomerNotificationDelivery).where(CustomerNotificationDelivery.id == delivery_id))
        ).scalar_one_or_none()
        if delivery is None or delivery.status != _Status.PROCESSING:
            return

        visit = None
        if delivery.site_visit_id is not None:
            visit = (await db.execute(select(SiteVisit).where(SiteVisit.id == delivery.site_visit_id))).scalar_one_or_none()
        account = (
            await db.execute(select(CustomerAccount).where(CustomerAccount.id == delivery.customer_account_id))
        ).scalar_one_or_none()

        if CustomerNotificationService._is_stale(delivery, visit):
            delivery.status = _Status.CANCELLED
            delivery.last_error = "SUPERSEDED"
            await db.commit()
            return

        reason = ineligibility_reason(account)
        if reason is not None:
            delivery.status = _Status.SKIPPED
            delivery.last_error = reason
            await db.commit()
            return

        assert account is not None
        delivery.recipient = account.email
        message = CustomerNotificationService._render(delivery)
        # Release the transaction before the external call.
        await db.commit()

        try:
            result = await provider.send(message)
        except Exception as exc:  # noqa: BLE001 -- classified below; never crashes the worker
            CustomerNotificationService._apply_failure(delivery, exc)
            logger.warning(
                f"Customer email delivery {delivery.id} attempt {delivery.attempt_count} failed: {type(exc).__name__}"
            )
        else:
            CustomerNotificationService._apply_success(delivery, simulated=result.simulated, message_id=result.provider_message_id)
        await db.commit()

    @staticmethod
    def _is_stale(delivery: CustomerNotificationDelivery, visit: Optional[SiteVisit]) -> bool:
        if delivery.event_type in (_Event.SITE_VISIT_BOOKED, _Event.SITE_VISIT_RESCHEDULED):
            return (
                visit is None
                or visit.status != SiteVisitStatus.CONFIRMED
                or visit.booking_version != delivery.booking_version
            )
        return False

    @staticmethod
    def _render(delivery: CustomerNotificationDelivery) -> OutgoingEmail:
        rendered = render_email(delivery.template_key, delivery.payload)
        return OutgoingEmail(
            to_email=delivery.recipient,
            subject=rendered.subject,
            text_body=rendered.text_body,
            html_body=rendered.html_body,
            delivery_id=str(delivery.id),
        )

    @staticmethod
    def _apply_success(delivery: CustomerNotificationDelivery, *, simulated: bool, message_id: Optional[str]) -> None:
        delivery.status = _Status.SIMULATED if simulated else _Status.SENT
        delivery.sent_at = datetime.now(timezone.utc)
        delivery.provider_message_id = message_id
        delivery.last_error = None

    @staticmethod
    def _apply_failure(delivery: CustomerNotificationDelivery, exc: Exception) -> None:
        delivery.last_error = describe_exception(exc)
        permanent = isinstance(exc, EmailPermanentError)
        if permanent or delivery.attempt_count >= settings.CUSTOMER_EMAIL_MAX_ATTEMPTS:
            delivery.status = _Status.FAILED
            return
        retry_after = getattr(exc, "retry_after_seconds", None)
        delivery.status = _Status.PENDING
        delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(
            seconds=compute_backoff_seconds(delivery.attempt_count, retry_after=retry_after)
        )

    @staticmethod
    async def run_due_deliveries(
        db: AsyncSession,
        provider: CustomerEmailProvider,
        *,
        limit: Optional[int] = None,
        site_visit_ids: Optional[List[uuid.UUID]] = None,
    ) -> int:
        ids = await CustomerNotificationService.claim_due(db, limit=limit, site_visit_ids=site_visit_ids)
        for delivery_id in ids:
            await CustomerNotificationService.process_delivery(db, delivery_id, provider)
        return len(ids)

    # ----- reminder integration (called by the Feature 07 reminder worker) ---

    @staticmethod
    async def deliver_reminder(
        db: AsyncSession,
        reminder: VisitReminder,
        visit: SiteVisit,
        project: Project,
        provider: CustomerEmailProvider,
    ) -> Optional[ReminderEmailOutcome]:
        """
        Sends the customer email for a reminder the reminder worker already
        owns (status PROCESSING). Returns None when the visit's lead has no
        customer account (caller keeps the legacy reminder behaviour). Raises
        the provider error on failure so the existing Feature 07 retry/backoff
        policy applies; one delivery row exists per reminder id.
        """
        account = await CustomerNotificationService._account_for_lead(db, visit.lead_id)
        if account is None:
            return None

        key = f"visit-reminder:{reminder.id}"
        delivery = await CustomerNotificationService._get_by_key(db, key)
        if delivery is None:
            payload = await CustomerNotificationService._build_payload(db, account, visit)
            event = _REMINDER_EVENT[reminder.reminder_type]
            values = CustomerNotificationService._base_values(account, event, payload, key)
            values.update(
                lead_id=visit.lead_id,
                site_visit_id=visit.id,
                visit_reminder_id=reminder.id,
                booking_version=reminder.booking_version,
            )
            await CustomerNotificationService._insert_if_absent(db, values)
            delivery = await CustomerNotificationService._get_by_key(db, key)
            assert delivery is not None

        if delivery.status in (_Status.SENT, _Status.SIMULATED):
            return ReminderEmailOutcome(simulated=delivery.status == _Status.SIMULATED)

        reason = ineligibility_reason(account)
        if reason is not None:
            delivery.status = _Status.SKIPPED
            delivery.last_error = reason
            await db.commit()
            return ReminderEmailOutcome(skipped_reason=reason)

        delivery.status = _Status.PROCESSING
        delivery.attempt_count += 1
        delivery.last_attempt_at = datetime.now(timezone.utc)
        delivery.recipient = account.email
        message = CustomerNotificationService._render(delivery)
        await db.commit()

        try:
            result = await provider.send(message)
        except Exception as exc:  # noqa: BLE001
            delivery.last_error = describe_exception(exc)
            # The reminder row owns retry/backoff; the delivery stays PENDING
            # until the reminder worker decides (see mark_reminder_delivery_failed).
            delivery.status = _Status.PENDING
            await db.commit()
            raise
        CustomerNotificationService._apply_success(delivery, simulated=result.simulated, message_id=result.provider_message_id)
        await db.commit()
        return ReminderEmailOutcome(simulated=result.simulated)

    @staticmethod
    async def mark_reminder_delivery_failed(db: AsyncSession, reminder_id: uuid.UUID) -> None:
        """Called (no commit) when the reminder worker gives up on a reminder."""
        await db.execute(
            update(CustomerNotificationDelivery)
            .where(
                CustomerNotificationDelivery.visit_reminder_id == reminder_id,
                CustomerNotificationDelivery.status.in_(_IN_FLIGHT),
            )
            .values(status=_Status.FAILED)
        )

    @staticmethod
    async def _get_by_key(db: AsyncSession, key: str) -> Optional[CustomerNotificationDelivery]:
        result = await db.execute(
            select(CustomerNotificationDelivery)
            .where(CustomerNotificationDelivery.idempotency_key == key)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    # ----- customer history & preferences ----------------------------------

    @staticmethod
    def customer_status(delivery: CustomerNotificationDelivery) -> str:
        return _CUSTOMER_STATUS[delivery.status]

    @staticmethod
    async def list_for_customer(
        db: AsyncSession, customer: CustomerAccount, *, limit: int = 20, offset: int = 0
    ) -> Tuple[List[CustomerNotificationDelivery], int]:
        # Superseded (CANCELLED) rows are internal bookkeeping, not history.
        cond = [
            CustomerNotificationDelivery.customer_account_id == customer.id,
            CustomerNotificationDelivery.status != _Status.CANCELLED,
        ]
        total = (
            await db.execute(select(func.count()).select_from(CustomerNotificationDelivery).where(*cond))
        ).scalar_one()
        rows = (
            await db.execute(
                select(CustomerNotificationDelivery)
                .where(*cond)
                .order_by(CustomerNotificationDelivery.created_at.desc(), CustomerNotificationDelivery.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(rows), total

    @staticmethod
    async def get_owned(db: AsyncSession, customer: CustomerAccount, notification_id: uuid.UUID) -> CustomerNotificationDelivery:
        """404 (never 403) for another customer's record, mirroring the other customer APIs."""
        result = await db.execute(
            select(CustomerNotificationDelivery).where(
                CustomerNotificationDelivery.id == notification_id,
                CustomerNotificationDelivery.customer_account_id == customer.id,
                CustomerNotificationDelivery.status != _Status.CANCELLED,
            )
        )
        delivery = result.scalar_one_or_none()
        if delivery is None:
            raise NotFoundException("Notification not found")
        return delivery

    @staticmethod
    async def update_preferences(
        db: AsyncSession, customer: CustomerAccount, *, transactional_email_enabled: bool
    ) -> CustomerAccount:
        changed = customer.transactional_email_enabled != transactional_email_enabled
        customer.transactional_email_enabled = transactional_email_enabled
        customer.notification_preferences_updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(customer)
        if changed:
            logger.info(
                f"[AUDIT] customer_notification_preference_changed customer={customer.id} "
                f"transactional_email_enabled={transactional_email_enabled}"
            )
        return customer

    # ----- staff / admin ------------------------------------------------------

    @staticmethod
    async def list_for_staff(
        db: AsyncSession,
        *,
        status: Optional[CustomerDeliveryStatus] = None,
        event_type: Optional[CustomerNotificationEvent] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[CustomerNotificationDelivery], int]:
        cond = []
        if status is not None:
            cond.append(CustomerNotificationDelivery.status == status)
        if event_type is not None:
            cond.append(CustomerNotificationDelivery.event_type == event_type)
        total = (
            await db.execute(select(func.count()).select_from(CustomerNotificationDelivery).where(*cond))
        ).scalar_one()
        rows = (
            await db.execute(
                select(CustomerNotificationDelivery)
                .where(*cond)
                .order_by(CustomerNotificationDelivery.created_at.desc(), CustomerNotificationDelivery.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(rows), total

    @staticmethod
    async def retry_failed(db: AsyncSession, delivery_id: uuid.UUID, *, actor_id: uuid.UUID) -> CustomerNotificationDelivery:
        """
        Idempotent admin retry: only a FAILED delivery is reset; any other
        state is returned unchanged. Reminder-linked deliveries are re-driven
        through their existing reminder row (no new schedule is created).
        """
        delivery = (
            await db.execute(
                select(CustomerNotificationDelivery)
                .where(CustomerNotificationDelivery.id == delivery_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if delivery is None:
            raise NotFoundException("Delivery not found")
        if delivery.status != _Status.FAILED:
            return delivery

        visit = None
        if delivery.site_visit_id is not None:
            visit = (await db.execute(select(SiteVisit).where(SiteVisit.id == delivery.site_visit_id))).scalar_one_or_none()

        if delivery.visit_reminder_id is not None:
            reminder = (
                await db.execute(select(VisitReminder).where(VisitReminder.id == delivery.visit_reminder_id).with_for_update())
            ).scalar_one_or_none()
            if (
                reminder is None
                or visit is None
                or visit.status != SiteVisitStatus.CONFIRMED
                or visit.booking_version != reminder.booking_version
            ):
                raise ConflictException("This reminder's booking has since changed and can no longer be retried")
            reminder.status = ReminderStatus.SCHEDULED
            reminder.attempt_count = 0
            reminder.failure_reason = None
            reminder.scheduled_at = datetime.now(timezone.utc)
        elif CustomerNotificationService._is_stale(delivery, visit):
            raise ConflictException("This notification's booking has since changed and can no longer be retried")

        delivery.status = _Status.PENDING
        delivery.attempt_count = 0
        delivery.last_error = None
        delivery.next_attempt_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(delivery)
        logger.info(f"[AUDIT] customer_delivery_retry delivery={delivery.id} actor={actor_id}")
        return delivery
