from __future__ import annotations
from typing import Optional

import phonenumbers
from phonenumbers import NumberParseException

from backend.core.exceptions import ValidationException

DEFAULT_REGION = "IN"


def normalize_phone(raw_phone: str, region: str = DEFAULT_REGION) -> str:
    """
    Normalizes a phone number to E.164 format using the phonenumbers library,
    defaulting to the Indian region when no country code is present.
    Raises ValidationException for unparsable or invalid numbers.
    """
    if not raw_phone or not raw_phone.strip():
        raise ValidationException("Phone number is required")

    try:
        parsed = phonenumbers.parse(raw_phone.strip(), region)
    except NumberParseException as exc:
        raise ValidationException(f"Invalid phone number: {raw_phone}") from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValidationException(f"Invalid phone number: {raw_phone}")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_email(raw_email: Optional[str]) -> Optional[str]:
    """Normalizes an email address by trimming whitespace and lowercasing it."""
    if raw_email is None:
        return None
    normalized = raw_email.strip().lower()
    return normalized or None
