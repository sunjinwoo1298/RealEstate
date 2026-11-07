from __future__ import annotations
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    """
    Structured output of the first LLM call: detected language/intent plus
    any buyer requirements mentioned in the latest message. All fields are
    optional/nullable so the orchestrator only ever merges newly-mentioned
    information (never overwrites previously captured fields with null).
    """

    detected_language: Literal["EN", "HI", "GU"] = "EN"
    intent: Literal[
        "GREETING",
        "PROJECT_QUESTION",
        "QUALIFICATION_INFO",
        "PRICING_OR_DISCOUNT_REQUEST",
        "HUMAN_HANDOFF_REQUEST",
        "OTHER",
    ] = "OTHER"
    mentioned_project_name: Optional[str] = Field(
        default=None, description="Project name the buyer mentioned, verbatim, if any"
    )
    configuration: Optional[Literal["BHK_2", "BHK_3"]] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    purchase_purpose: Optional[Literal["SELF_USE", "INVESTMENT"]] = None
    preferred_visit_date: Optional[str] = Field(default=None, description="ISO 8601 date (YYYY-MM-DD) if mentioned")
    wants_human_handoff: bool = False


class OrchestratorReply(BaseModel):
    """Structured output of the final response-generation LLM call."""

    reply_text: str
    language: Literal["EN", "HI", "GU"] = "EN"
