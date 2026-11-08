from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from backend.models.customer_account import CustomerAccountStatus


class CustomerProfile(BaseModel):
    """
    Dedicated customer-facing profile representation -- never the raw
    SQLAlchemy `CustomerAccount` model, so a future internal-only column
    (password_hash, etc.) can never leak through this response by accident.
    """

    id: uuid.UUID
    full_name: str
    email: str
    email_verified: bool
    phone: Optional[str] = None
    phone_verified: bool
    status: CustomerAccountStatus
    lead_linked: bool
    created_at: datetime
    profile_completeness: int = Field(ge=0, le=100)


class CustomerProfileUpdateRequest(BaseModel):
    """
    Only full_name/phone are updatable here. Email is deliberately absent --
    email changes require a separate verified email-change workflow, not a
    normal profile update (not implemented in this feature).
    """

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=32)


class CustomerEnquirySummary(BaseModel):
    has_enquiry: bool
    enquiry_reference: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    project_name: Optional[str] = None
    configuration: Optional[str] = None
    enquiry_date: Optional[datetime] = None
    customer_status: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_new_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_must_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_new_password:
            raise ValueError("New password and confirmation do not match")
        return self
