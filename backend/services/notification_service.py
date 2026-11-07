from __future__ import annotations
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.handoff import Handoff
from backend.models.notification import Notification, NotificationStatus, NotificationType


class NotificationService:
    """
    Internal-only notification mechanism (no WhatsApp/email delivery, per
    spec section 10). "Delivery" here means persisting a SENT row the
    executive's workspace can read; the unique constraint on
    (recipient_id, reference_id, notification_type) makes a retried call
    for the same event a no-op rather than a duplicate.
    """

    @staticmethod
    async def notify_handoff_assigned(db: AsyncSession, recipient_id: uuid.UUID, handoff: Handoff) -> None:
        notification = Notification(
            recipient_id=recipient_id,
            notification_type=NotificationType.HANDOFF_ASSIGNED,
            reference_id=handoff.id,
            status=NotificationStatus.SENT,
            payload={
                "handoff_id": str(handoff.id),
                "conversation_id": str(handoff.conversation_id),
                "lead_id": str(handoff.lead_id),
                "reason": handoff.reason.value,
            },
            attempts=1,
            delivered_at=datetime.now(timezone.utc),
        )
        try:
            # A SAVEPOINT, not the outer transaction: callers (AssignmentService)
            # have already made uncommitted handoff/assignment changes in this
            # same session, and a duplicate-notification race must only roll
            # back this insert, never the assignment it belongs to.
            async with db.begin_nested():
                db.add(notification)
                await db.flush()
        except IntegrityError:
            # Already notified for this exact (recipient, handoff) pair --
            # a retry of the same assignment, not a new event.
            pass
