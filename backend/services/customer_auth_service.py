from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import ConflictException, UnauthorizedException, ValidationException
from backend.core.logging import logger
from backend.core.security import (
    create_customer_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    validate_password_strength,
    verify_password,
)
from backend.models.customer_account import CustomerAccount, CustomerAccountStatus
from backend.models.customer_session import CustomerSession
from backend.models.customer_verification_token import TokenPurpose
from backend.services.customer_lead_linking_service import CustomerLeadLinkingService
from backend.services.customer_verification_service import CustomerVerificationService
from backend.services.normalization_service import normalize_email, normalize_phone_optional

INVALID_CREDENTIALS_MESSAGE = "Invalid email or password"
# Argon2 hash of an arbitrary value, used purely to keep verify-password timing
# similar whether or not the account exists (mirrors AuthService.authenticate).
_DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$ZHVtbXloYXNo"


class CustomerAuthService:
    """Coordinates customer registration, login, refresh rotation and password recovery."""

    @staticmethod
    async def register(
        db: AsyncSession,
        *,
        full_name: str,
        email: str,
        password: str,
        phone: Optional[str],
        accepted_privacy_policy: bool,
        marketing_consent: bool,
    ) -> Tuple[CustomerAccount, str]:
        if not accepted_privacy_policy:
            raise ValidationException("You must accept the privacy policy and terms to create an account")

        normalized_email = normalize_email(email)
        validate_password_strength(password)
        normalized_phone = normalize_phone_optional(phone)

        existing = await db.execute(
            select(CustomerAccount).where(CustomerAccount.normalized_email == normalized_email)
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictException("An account with this email already exists")

        now = datetime.now(timezone.utc)
        customer = CustomerAccount(
            email=email.strip(),
            normalized_email=normalized_email,
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            phone=normalized_phone,
            status=CustomerAccountStatus.PENDING_VERIFICATION,
            privacy_policy_accepted_at=now,
            marketing_consent=marketing_consent,
            marketing_consent_updated_at=now if marketing_consent else None,
        )
        db.add(customer)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise ConflictException("An account with this email already exists")

        _, raw_token = await CustomerVerificationService.issue_token(
            db, customer.id, TokenPurpose.EMAIL_VERIFICATION
        )
        await db.commit()
        await db.refresh(customer)
        return customer, raw_token

    @staticmethod
    async def resend_verification(db: AsyncSession, email: str) -> Optional[str]:
        """
        Returns a fresh raw verification token if an eligible PENDING_VERIFICATION
        account exists for this email, else None. Always returns a generic
        acknowledgement to the caller regardless of outcome -- the caller must
        not branch the HTTP response on this return value's truthiness.
        """
        normalized_email = normalize_email(email)
        result = await db.execute(
            select(CustomerAccount).where(CustomerAccount.normalized_email == normalized_email)
        )
        customer = result.scalar_one_or_none()
        if customer is None or customer.status != CustomerAccountStatus.PENDING_VERIFICATION:
            return None

        _, raw_token = await CustomerVerificationService.issue_token(
            db, customer.id, TokenPurpose.EMAIL_VERIFICATION
        )
        await db.commit()
        return raw_token

    @staticmethod
    async def verify_email(db: AsyncSession, raw_token: str) -> CustomerAccount:
        """
        Activates the account for a valid, unexpired, unused email-verification
        token, then runs the customer-to-Lead linking workflow. Raises
        ValidationException for any invalid/expired/already-used token.
        """
        token = await CustomerVerificationService.consume_token(db, raw_token, TokenPurpose.EMAIL_VERIFICATION)
        if token is None:
            raise ValidationException("This verification link is invalid, expired, or has already been used")

        result = await db.execute(select(CustomerAccount).where(CustomerAccount.id == token.customer_account_id))
        customer = result.scalar_one_or_none()
        if customer is None:
            raise ValidationException("This verification link is invalid, expired, or has already been used")

        now = datetime.now(timezone.utc)
        customer.email_verified_at = now
        if customer.status == CustomerAccountStatus.PENDING_VERIFICATION:
            customer.status = CustomerAccountStatus.ACTIVE
        await db.flush()

        await CustomerLeadLinkingService.link_or_create_for_verified_customer(db, customer)

        await db.commit()
        await db.refresh(customer)
        return customer

    @staticmethod
    async def authenticate(db: AsyncSession, email: str, password: str) -> CustomerAccount:
        """
        Validates customer credentials. Raises UnauthorizedException for any
        failure case with an identical message, so login failures never
        reveal whether an email exists or why authentication failed.
        """
        normalized_email = normalize_email(email)
        result = await db.execute(
            select(CustomerAccount).where(CustomerAccount.normalized_email == normalized_email)
        )
        customer = result.scalar_one_or_none()

        if customer is None:
            verify_password(password, _DUMMY_HASH)
            raise UnauthorizedException(INVALID_CREDENTIALS_MESSAGE)

        if not verify_password(password, customer.password_hash):
            raise UnauthorizedException(INVALID_CREDENTIALS_MESSAGE)

        if customer.status != CustomerAccountStatus.ACTIVE:
            # Deliberately the same generic message for PENDING_VERIFICATION,
            # SUSPENDED, and DEACTIVATED -- never reveal account state to an
            # unauthenticated caller.
            raise UnauthorizedException(INVALID_CREDENTIALS_MESSAGE)

        return customer

    @staticmethod
    async def issue_session(db: AsyncSession, customer: CustomerAccount) -> Tuple[str, str, int]:
        access_token = create_customer_access_token(str(customer.id))
        raw_refresh_token = generate_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.CUSTOMER_REFRESH_TOKEN_EXPIRE_DAYS)

        session = CustomerSession(
            customer_account_id=customer.id,
            refresh_token_hash=hash_refresh_token(raw_refresh_token),
            expires_at=expires_at,
        )
        db.add(session)
        customer.last_login_at = datetime.now(timezone.utc)
        await db.commit()

        return access_token, raw_refresh_token, settings.CUSTOMER_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @staticmethod
    async def rotate_refresh_token(db: AsyncSession, raw_refresh_token: str) -> Tuple[str, str, int]:
        """
        Validates and rotates a customer refresh token. Reuse of an
        already-revoked/rotated token revokes the entire session chain for
        that customer, same precaution as the staff auth flow.
        """
        token_hash = hash_refresh_token(raw_refresh_token)
        result = await db.execute(select(CustomerSession).where(CustomerSession.refresh_token_hash == token_hash))
        session = result.scalar_one_or_none()

        if session is None:
            raise UnauthorizedException("Invalid refresh token")

        now = datetime.now(timezone.utc)
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if session.revoked_at is not None:
            logger.warning(f"Customer refresh token reuse detected for customer_account_id={session.customer_account_id}")
            await CustomerAuthService._revoke_all_sessions(db, session.customer_account_id)
            raise UnauthorizedException("Refresh token has been revoked")

        if expires_at < now:
            raise UnauthorizedException("Refresh token has expired")

        result = await db.execute(select(CustomerAccount).where(CustomerAccount.id == session.customer_account_id))
        customer = result.scalar_one_or_none()
        if customer is None or customer.status != CustomerAccountStatus.ACTIVE:
            raise UnauthorizedException("Account is not available")

        access_token = create_customer_access_token(str(customer.id))
        new_raw_refresh_token = generate_refresh_token()
        new_expires_at = now + timedelta(days=settings.CUSTOMER_REFRESH_TOKEN_EXPIRE_DAYS)

        new_session = CustomerSession(
            customer_account_id=customer.id,
            refresh_token_hash=hash_refresh_token(new_raw_refresh_token),
            expires_at=new_expires_at,
        )
        db.add(new_session)
        await db.flush()

        session.revoked_at = now
        session.last_used_at = now
        session.replaced_by_id = new_session.id
        await db.commit()

        return access_token, new_raw_refresh_token, settings.CUSTOMER_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @staticmethod
    async def revoke_refresh_token(db: AsyncSession, raw_refresh_token: str) -> None:
        token_hash = hash_refresh_token(raw_refresh_token)
        result = await db.execute(select(CustomerSession).where(CustomerSession.refresh_token_hash == token_hash))
        session = result.scalar_one_or_none()
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            await db.commit()

    @staticmethod
    async def _revoke_all_sessions(db: AsyncSession, customer_account_id: uuid.UUID) -> None:
        now = datetime.now(timezone.utc)
        await db.execute(
            update(CustomerSession)
            .where(CustomerSession.customer_account_id == customer_account_id, CustomerSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()

    @staticmethod
    async def forgot_password(db: AsyncSession, email: str) -> Optional[str]:
        """
        Returns a fresh raw password-reset token if an eligible account
        exists, else None. The caller must always return a generic
        acknowledgement regardless of this return value, to prevent account
        enumeration.
        """
        normalized_email = normalize_email(email)
        result = await db.execute(
            select(CustomerAccount).where(CustomerAccount.normalized_email == normalized_email)
        )
        customer = result.scalar_one_or_none()
        if customer is None or customer.status == CustomerAccountStatus.DEACTIVATED:
            return None

        _, raw_token = await CustomerVerificationService.issue_token(db, customer.id, TokenPurpose.PASSWORD_RESET)
        await db.commit()
        return raw_token

    @staticmethod
    async def reset_password(db: AsyncSession, raw_token: str, new_password: str) -> CustomerAccount:
        validate_password_strength(new_password)

        token = await CustomerVerificationService.consume_token(db, raw_token, TokenPurpose.PASSWORD_RESET)
        if token is None:
            raise ValidationException("This password reset link is invalid, expired, or has already been used")

        result = await db.execute(select(CustomerAccount).where(CustomerAccount.id == token.customer_account_id))
        customer = result.scalar_one_or_none()
        if customer is None:
            raise ValidationException("This password reset link is invalid, expired, or has already been used")

        customer.password_hash = hash_password(new_password)
        await db.flush()

        # Invalidate every other outstanding reset token and revoke every
        # existing session -- a password reset must not leave old credentials
        # or old sessions usable. Lead association is untouched by design.
        await CustomerVerificationService.invalidate_active_tokens(db, customer.id, TokenPurpose.PASSWORD_RESET)
        await CustomerAuthService._revoke_all_sessions(db, customer.id)

        await db.commit()
        await db.refresh(customer)
        return customer

    @staticmethod
    async def change_password(
        db: AsyncSession, customer: CustomerAccount, *, current_password: str, new_password: str
    ) -> None:
        """
        Changes the authenticated customer's own password after verifying
        their current one. Revokes every existing `CustomerSession` (refresh
        token) afterward -- the same precaution `reset_password` already
        takes -- so a stolen/still-open session elsewhere cannot keep using
        the old password's session; the caller must sign in again. Never
        touches `CustomerAccount.lead_id` or any Lead data, and never
        affects staff `AuthSession` rows (an entirely separate table).
        """
        if not verify_password(current_password, customer.password_hash):
            raise ValidationException("Current password is incorrect")

        validate_password_strength(new_password)

        customer.password_hash = hash_password(new_password)
        await db.flush()

        await CustomerAuthService._revoke_all_sessions(db, customer.id)
        await db.commit()

    @staticmethod
    def to_public(customer: CustomerAccount):
        from backend.schemas.customer_auth import CustomerPublic

        return CustomerPublic(
            id=customer.id,
            full_name=customer.full_name,
            email=customer.email,
            email_verified=customer.email_verified_at is not None,
            phone=customer.phone,
            status=customer.status,
            lead_linked=customer.lead_id is not None,
            created_at=customer.created_at,
        )
