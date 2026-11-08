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


def normalize_phone_optional(raw_phone: Optional[str], region: str = DEFAULT_REGION) -> Optional[str]:
    """
    Same validation/normalization as normalize_phone, but returns None instead
    of raising when no phone was supplied at all. For flows where a phone
    number is genuinely optional (e.g. customer registration) -- a phone that
    IS supplied is still validated with the same strictness as every other
    ingestion channel.
    """
    if raw_phone is None or not raw_phone.strip():
        return None
    return normalize_phone(raw_phone, region)


def normalize_email(raw_email: Optional[str]) -> Optional[str]:
    """Normalizes an email address by trimming whitespace and lowercasing it."""
    if raw_email is None:
        return None
    normalized = raw_email.strip().lower()
    return normalized or None
