from __future__ import annotations
from typing import Protocol

from backend.core.logging import logger


class EmailDeliveryProvider(Protocol):
    """
    Email delivery abstraction. The AI/business logic never depends on a
    specific email provider -- only on this interface -- so a real provider
    (SES/SendGrid/etc.) can be swapped in later without touching any caller.
    """

    async def send(self, *, to_email: str, subject: str, body: str) -> bool:
        ...


class LoggingEmailDeliveryProvider:
    """
    Development-only provider: no real email provider is configured anywhere
    in this codebase (no SMTP/SES/SendGrid dependency exists), so this is the
    only implementation for now. It logs the full simulated email -- including
    its verification/reset link -- which is the deliberate, documented way to
    retrieve a token in local development (see Feature 10 completion report /
    PROGRESS_TRACKER.md for the exact flow). This is the one sanctioned place
    a raw token is ever written anywhere in the system; no other log line in
    the customer-auth flow includes a raw verification or reset token.
    It always reports a SIMULATED send, never a real delivery confirmation.
    """

    async def send(self, *, to_email: str, subject: str, body: str) -> bool:
        logger.info(
            "[DEV EMAIL SIMULATED] This is not a real email delivery -- no provider is configured.\n"
            f"To: {to_email}\nSubject: {subject}\n{body}"
        )
        return True


def get_email_provider() -> EmailDeliveryProvider:
    """Returns the active email delivery provider. Only a logging provider exists at this time."""
    return LoggingEmailDeliveryProvider()
