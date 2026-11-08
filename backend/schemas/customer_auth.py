from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from backend.models.customer_account import CustomerAccountStatus


class CustomerRegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    password_confirmation: str = Field(min_length=8, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=32)
    accepted_privacy_policy: bool
    marketing_consent: bool = False

    @field_validator("accepted_privacy_policy")
    @classmethod
    def must_accept_privacy_policy(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must accept the privacy policy and terms to create an account")
        return value

    @model_validator(mode="after")
    def passwords_must_match(self) -> "CustomerRegisterRequest":
        if self.password != self.password_confirmation:
            raise ValueError("Password and password confirmation do not match")
        return self


class CustomerRegisterResponse(BaseModel):
    message: str
    email: EmailStr


class GenericMessageResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class CustomerLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class CustomerPublic(BaseModel):
    id: uuid.UUID
    full_name: str
    email: EmailStr
    email_verified: bool
    phone: Optional[str]
    status: CustomerAccountStatus
    lead_linked: bool
    created_at: datetime


class CustomerLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    customer: CustomerPublic


class CustomerRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirmation: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_must_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.new_password_confirmation:
            raise ValueError("New password and confirmation do not match")
        return self
