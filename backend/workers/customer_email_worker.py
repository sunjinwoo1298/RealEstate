"""
Customer transactional email worker (Feature 14).

Run locally:
    conda activate minor
    python -m backend.workers.customer_email_worker

Claims committed PENDING customer_notification_deliveries (booking,
reschedule and cancellation emails) with FOR UPDATE SKIP LOCKED and sends
them through the configured provider, outside any database transaction.
24h/2h reminder emails are NOT handled here -- the Feature 07 reminder
worker owns reminders, so the two workers never race on the same row.
Deploy as a separate long-lived worker service next to the API.
"""
import asyncio
import signal

from backend.core.config import settings
from backend.core.database import close_db_connection, get_session_factory
from backend.core.logging import logger, setup_logging
from backend.services.customer_email_provider import get_customer_email_provider
from backend.services.customer_notification_service import CustomerNotificationService

_shutdown_requested = False


def _request_shutdown(*_args) -> None:
    global _shutdown_requested
    _shutdown_requested = True


async def _run_forever() -> None:
    session_factory = get_session_factory()
    provider = get_customer_email_provider()  # validates config; raises on a bad production setup
    logger.info(f"Customer email worker started (provider={settings.EMAIL_PROVIDER}).")

    while not _shutdown_requested:
        try:
            async with session_factory() as db:
                processed = await CustomerNotificationService.run_due_deliveries(db, provider)
                if processed:
                    logger.info(f"Customer email worker processed {processed} delivery(ies).")
        except Exception:
            logger.exception("Customer email worker poll failed; will retry on the next interval.")
        await asyncio.sleep(settings.CUSTOMER_EMAIL_WORKER_POLL_SECONDS)

    logger.info("Customer email worker shutting down.")


def main() -> None:
    setup_logging(level=settings.LOG_LEVEL, structured=settings.STRUCTURED_LOGS)
    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    try:
        asyncio.run(_run_forever())
    finally:
        asyncio.run(close_db_connection())


if __name__ == "__main__":
    main()
