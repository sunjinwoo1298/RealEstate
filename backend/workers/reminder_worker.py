"""
Persistent site-visit reminder worker.

Run locally:
    conda activate minor
    python -m backend.workers.reminder_worker

Deployment (Railway/Render): run this module as a separate long-lived
worker process/service alongside the FastAPI app (not inside a web
request), e.g. a Railway "worker" service with start command
`python -m backend.workers.reminder_worker`.

The worker polls the visit_reminders table every
REMINDER_WORKER_POLL_INTERVAL_SECONDS for due reminders, claims a batch
with `SELECT ... FOR UPDATE SKIP LOCKED` (safe across multiple worker
instances), and executes each one through the configured delivery
provider. All state lives in PostgreSQL, so a restart never loses track of
pending reminders.
"""
import asyncio
import signal

from backend.core.config import settings
from backend.core.database import close_db_connection, get_session_factory
from backend.core.logging import logger, setup_logging
from backend.services.reminder_delivery import LoggingReminderDeliveryProvider
from backend.services.reminder_worker_service import ReminderWorkerService

_shutdown_requested = False


def _request_shutdown(*_args) -> None:
    global _shutdown_requested
    _shutdown_requested = True


async def _run_forever() -> None:
    session_factory = get_session_factory()
    provider = LoggingReminderDeliveryProvider()
    logger.info("Reminder worker started.")

    while not _shutdown_requested:
        try:
            async with session_factory() as db:
                claimed = await ReminderWorkerService.run_due_reminders(db, delivery_provider=provider)
                if claimed:
                    logger.info(f"Reminder worker processed {claimed} due reminder(s).")
        except Exception:
            logger.exception("Reminder worker poll failed; will retry on the next interval.")

        await asyncio.sleep(settings.REMINDER_WORKER_POLL_INTERVAL_SECONDS)

    logger.info("Reminder worker shutting down.")


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
