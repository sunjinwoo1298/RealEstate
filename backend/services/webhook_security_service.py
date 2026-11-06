from __future__ import annotations
import hashlib
import hmac

from backend.core.config import settings
from backend.core.exceptions import UnauthorizedException

SIGNATURE_HEADER = "X-Webhook-Signature"


def verify_webhook_signature(source_type: str, raw_body: bytes, signature_header: str | None) -> None:
    """
    Verifies an inbound webhook's HMAC-SHA256 signature against the secret
    configured for its source (WEBHOOK_SOURCE_SECRETS). An unconfigured
    source or a missing/invalid signature is always rejected as unauthorized.
    """
    secret = settings.webhook_source_secrets_map.get(source_type.upper())
    if not secret:
        raise UnauthorizedException("Unknown or unconfigured webhook source")

    if not signature_header:
        raise UnauthorizedException("Missing webhook signature")

    expected_signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature_header.strip()):
        raise UnauthorizedException("Invalid webhook signature")
