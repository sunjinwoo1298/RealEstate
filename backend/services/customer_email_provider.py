from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional, Protocol

import httpx

from backend.core.config import settings
from backend.core.logging import logger

_EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
_RESEND_URL = "https://api.resend.com/emails"


class EmailProviderError(Exception):
    """Base class. Messages are sanitized -- never contain keys or response bodies."""


class EmailTransientError(EmailProviderError):
    """Network error, timeout, rate limit, or provider 5xx -- safe to retry."""

    def __init__(self, message: str, *, retry_after_seconds: Optional[float] = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class EmailPermanentError(EmailProviderError):
    """Invalid recipient, bad credentials/config, or other non-retryable 4xx."""


class EmailConfigurationError(EmailProviderError):
    """Raised at startup when production email configuration is invalid."""


@dataclass(frozen=True)
class OutgoingEmail:
    to_email: str
    subject: str
    text_body: str
    html_body: str
    # Stable identifier (the delivery row id) -- used as the provider
    # idempotency key where supported.
    delivery_id: str


@dataclass(frozen=True)
class EmailSendResult:
    # simulated=True means no real email left the system. Callers must record
    # SIMULATED, never SENT.
    simulated: bool
    provider_message_id: Optional[str] = None


class CustomerEmailProvider(Protocol):
    async def send(self, message: OutgoingEmail) -> EmailSendResult: ...


class LoggingCustomerEmailProvider:
    """
    Development/test provider. Logs only metadata (never the body or the
    recipient address) and always reports simulated=True.
    """

    async def send(self, message: OutgoingEmail) -> EmailSendResult:
        logger.info(
            f"[SIMULATED CUSTOMER EMAIL] delivery={message.delivery_id} "
            f"subject_len={len(message.subject)} -- not a real email send"
        )
        return EmailSendResult(simulated=True, provider_message_id=None)


class ResendEmailProvider:
    """
    Production adapter for the Resend HTTP API. Provider specifics (URL, JSON
    shape, status codes) never leave this class. The delivery id is sent as
    Resend's Idempotency-Key so a retry after an ambiguous timeout is not
    delivered twice by the provider (within its idempotency window).
    """

    def __init__(self, *, api_key: str, from_address: str, from_name: str, reply_to: str, timeout: float):
        self._api_key = api_key
        self._from = f"{from_name} <{from_address}>" if from_name else from_address
        self._reply_to = reply_to
        self._timeout = timeout

    async def send(self, message: OutgoingEmail) -> EmailSendResult:
        body = {
            "from": self._from,
            "to": [message.to_email],
            "subject": message.subject,
            "text": message.text_body,
            "html": message.html_body,
        }
        if self._reply_to:
            body["reply_to"] = self._reply_to
        headers = {"Authorization": f"Bearer {self._api_key}", "Idempotency-Key": message.delivery_id}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(_RESEND_URL, json=body, headers=headers)
        except httpx.TimeoutException:
            raise EmailTransientError("Provider request timed out (delivery outcome uncertain)")
        except httpx.HTTPError as exc:
            raise EmailTransientError(f"Provider network error: {type(exc).__name__}")

        status = response.status_code
        if 200 <= status < 300:
            try:
                message_id = response.json().get("id")
            except ValueError:
                message_id = None
            return EmailSendResult(simulated=False, provider_message_id=str(message_id) if message_id else None)
        if status == 429:
            raise EmailTransientError("Provider rate limit", retry_after_seconds=_parse_retry_after(response))
        if status >= 500 or status in (408, 409):
            raise EmailTransientError(f"Provider error {status}", retry_after_seconds=_parse_retry_after(response))
        raise EmailPermanentError(f"Provider rejected the message ({status})")


def _parse_retry_after(response: httpx.Response) -> Optional[float]:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def validate_email_configuration() -> None:
    """
    Fails fast (worker/app startup) on invalid configuration. 'log' needs
    nothing. 'resend' requires an API key, a valid sender and an https portal
    URL (outside local development).
    """
    provider = settings.EMAIL_PROVIDER.strip().lower()
    if provider == "log":
        return
    if provider != "resend":
        raise EmailConfigurationError(f"Unsupported EMAIL_PROVIDER '{settings.EMAIL_PROVIDER}'")
    if not settings.EMAIL_API_KEY:
        raise EmailConfigurationError("EMAIL_API_KEY is required when EMAIL_PROVIDER=resend")
    if not _EMAIL_RE.match(settings.EMAIL_FROM_ADDRESS or ""):
        raise EmailConfigurationError("EMAIL_FROM_ADDRESS must be a valid email address")
    if settings.EMAIL_REPLY_TO and not _EMAIL_RE.match(settings.EMAIL_REPLY_TO):
        raise EmailConfigurationError("EMAIL_REPLY_TO must be a valid email address")
    portal = settings.customer_portal_base_url
    if not portal.startswith(("https://", "http://")):
        raise EmailConfigurationError("CUSTOMER_PORTAL_BASE_URL must be an absolute http(s) URL")
    if settings.APP_ENV.lower() == "production" and not portal.startswith("https://"):
        raise EmailConfigurationError("CUSTOMER_PORTAL_BASE_URL must use https in production")


def get_customer_email_provider() -> CustomerEmailProvider:
    validate_email_configuration()
    if settings.EMAIL_PROVIDER.strip().lower() == "resend":
        return ResendEmailProvider(
            api_key=settings.EMAIL_API_KEY,
            from_address=settings.EMAIL_FROM_ADDRESS,
            from_name=settings.EMAIL_FROM_NAME,
            reply_to=settings.EMAIL_REPLY_TO,
            timeout=settings.EMAIL_PROVIDER_TIMEOUT_SECONDS,
        )
    return LoggingCustomerEmailProvider()
