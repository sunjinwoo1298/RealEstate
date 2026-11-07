from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List

# Currency figures ("Rs 50 lakh", "₹1.2 Cr", "$500,000") and discount/offer
# language. Deliberately broad/over-inclusive: a false positive just swaps in
# the safe fallback, which is always an acceptable answer to a pricing question.
_PRICE_PATTERNS = [
    re.compile(r"(?:rs\.?|inr|₹|\$)\s?[\d,]+(?:\.\d+)?\s?(?:lakh|lac|crore|cr|k|thousand)?", re.IGNORECASE),
    re.compile(r"\b\d[\d,]*(?:\.\d+)?\s?(?:lakh|lac|crore)\b", re.IGNORECASE),
]
_DISCOUNT_PATTERNS = [
    re.compile(r"\b\d{1,2}\s?%\s?(?:off|discount)\b", re.IGNORECASE),
    re.compile(r"\bdiscount of\b", re.IGNORECASE),
]

_HANDOFF_PHRASES = [
    "talk to a human",
    "talk to someone",
    "speak to a human",
    "speak to a person",
    "speak with a salesperson",
    "connect me to",
    "real person",
    "human agent",
    "call me",
    "stop the bot",
]

_COMPLAINT_PHRASES = [
    "complaint",
    "unhappy",
    "disappointed",
    "this is unacceptable",
    "refund",
    "cheated",
    "scam",
    "fraud",
    "legal action",
    "consumer court",
    "worst experience",
]

_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore (all|previous|above) instructions", re.IGNORECASE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
    re.compile(r"reveal your (instructions|prompt)", re.IGNORECASE),
    re.compile(r"pretend (you|to) ", re.IGNORECASE),
    re.compile(r"act as (an? )?(?!real estate|sales)", re.IGNORECASE),
]

SAFE_PRICING_FALLBACK = {
    "EN": "I'm not able to share final pricing or discount details here — one of our sales executives will confirm the exact numbers with you.",
    "HI": "Main yahan final price ya discount ki details share nahi kar sakta — hamari sales team aapko exact numbers confirm karegi.",
    "GU": "Hun ahiya final price ke discount ni vigat aapi shaktho nathi — amara sales executive tamne exact numbers confirm karshe.",
}


@dataclass
class GuardrailFlags:
    prompt_injection_detected: bool = False
    pricing_or_discount_requested: bool = False
    handoff_requested: bool = False
    complaint_detected: bool = False
    reply_price_violation_blocked: bool = False
    notes: List[str] = field(default_factory=list)


def detect_prompt_injection(text: str) -> bool:
    return any(p.search(text) for p in _PROMPT_INJECTION_PATTERNS)


def detect_handoff_request(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _HANDOFF_PHRASES)


def detect_pricing_or_discount_request(text: str) -> bool:
    lowered = text.lower()
    return "price" in lowered or "pricing" in lowered or "cost" in lowered or "discount" in lowered or "offer" in lowered


def detect_complaint_request(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _COMPLAINT_PHRASES)


def contains_price_or_discount_claim(text: str) -> bool:
    return any(p.search(text) for p in _PRICE_PATTERNS) or any(p.search(text) for p in _DISCOUNT_PATTERNS)


def enforce_reply_guardrails(reply_text: str, *, language: str, flags: GuardrailFlags) -> str:
    """
    Final, authoritative safety net applied to the generated reply text
    regardless of what the LLM produced. If the reply still names a price or
    discount figure, it is replaced outright with a safe fallback — the
    backend never trusts the LLM alone to honor the "never quote prices" rule.
    """
    if contains_price_or_discount_claim(reply_text):
        flags.reply_price_violation_blocked = True
        flags.notes.append("Blocked a generated reply that contained a price/discount figure")
        return SAFE_PRICING_FALLBACK.get(language, SAFE_PRICING_FALLBACK["EN"])
    return reply_text
