from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_customer, get_db_session, verify_same_origin
from backend.core.config import settings
from backend.core.exceptions import UnauthorizedException
from backend.core.rate_limit import (
    enforce_customer_login_rate_limit,
    enforce_customer_password_reset_rate_limit,
    enforce_customer_registration_rate_limit,
    enforce_customer_verification_rate_limit,
)
from backend.models.customer_account import CustomerAccount
from backend.schemas.customer_auth import (
    CustomerLoginRequest,
    CustomerLoginResponse,
    CustomerPublic,
    CustomerRefreshResponse,
    CustomerRegisterRequest,
    CustomerRegisterResponse,
    ForgotPasswordRequest,
    GenericMessageResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from backend.services.customer_auth_service import CustomerAuthService
from backend.services.email_delivery_service import get_email_provider

router = APIRouter(prefix="/customer-auth", tags=["Customer Authentication"])

# Scoped to the customer-auth prefix only, for this feature. A future feature
# that adds customer-authenticated conversation/booking endpoints outside
# this prefix will need to broaden this path, the same way Feature 05
# broadened the buyer-session cookie's path beyond /chat.
_CUSTOMER_REFRESH_COOKIE_PATH = "/api/v1/customer-auth"

_GENERIC_VERIFICATION_SENT_MESSAGE = (
    "If an account with this email exists and is pending verification, a verification email has been sent."
)
_GENERIC_PASSWORD_RESET_MESSAGE = (
    "If an account with this email exists, a password reset email has been sent."
)


def _set_customer_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
    response.set_cookie(
        key=settings.CUSTOMER_REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        max_age=settings.CUSTOMER_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path=_CUSTOMER_REFRESH_COOKIE_PATH,
    )


def _clear_customer_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.CUSTOMER_REFRESH_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path=_CUSTOMER_REFRESH_COOKIE_PATH,
    )


async def _send_verification_email(to_email: str, raw_token: str) -> None:
    link = f"{settings.FRONTEND_BASE_URL}/customer/verify-email?token={raw_token}"
    await get_email_provider().send(
        to_email=to_email,
        subject="Verify your EstateFlow AI account",
        body=f"Please verify your email address by visiting: {link}\n\nThis link expires in "
        f"{settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.",
    )


async def _send_password_reset_email(to_email: str, raw_token: str) -> None:
    link = f"{settings.FRONTEND_BASE_URL}/customer/reset-password?token={raw_token}"
    await get_email_provider().send(
        to_email=to_email,
        subject="Reset your EstateFlow AI password",
        body=f"Reset your password by visiting: {link}\n\nThis link expires in "
        f"{settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes. If you did not request this, "
        "you can safely ignore this email.",
    )


@router.post(
    "/register",
    response_model=CustomerRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer account",
)
async def register(
    payload: CustomerRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> CustomerRegisterResponse:
    client_ip = request.client.host if request.client else "unknown"
    await enforce_customer_registration_rate_limit(client_ip)

    customer, raw_token = await CustomerAuthService.register(
        db,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        phone=payload.phone,
        accepted_privacy_policy=payload.accepted_privacy_policy,
        marketing_consent=payload.marketing_consent,
    )
    await _send_verification_email(customer.email, raw_token)

    return CustomerRegisterResponse(
        message="Account created. Please check your email to verify your address before signing in.",
        email=customer.email,
    )


@router.post("/verify-email", response_model=CustomerPublic, summary="Verify a customer's email address")
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> CustomerPublic:
    client_ip = request.client.host if request.client else "unknown"
    await enforce_customer_verification_rate_limit(client_ip)

    customer = await CustomerAuthService.verify_email(db, payload.token)
    return CustomerAuthService.to_public(customer)


@router.post(
    "/resend-verification",
    response_model=GenericMessageResponse,
    summary="Resend the email-verification link",
)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> GenericMessageResponse:
    client_ip = request.client.host if request.client else "unknown"
    await enforce_customer_verification_rate_limit(f"{client_ip}:{payload.email.strip().lower()}")

    raw_token = await CustomerAuthService.resend_verification(db, payload.email)
    if raw_token is not None:
        await _send_verification_email(payload.email, raw_token)

    return GenericMessageResponse(message=_GENERIC_VERIFICATION_SENT_MESSAGE)


@router.post("/login", response_model=CustomerLoginResponse, summary="Customer login")
async def login(
    payload: CustomerLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> CustomerLoginResponse:
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{payload.email.strip().lower()}"
    await enforce_customer_login_rate_limit(rate_limit_key)

    customer = await CustomerAuthService.authenticate(db, payload.email, payload.password)
    access_token, raw_refresh_token, expires_in = await CustomerAuthService.issue_session(db, customer)

    _set_customer_refresh_cookie(response, raw_refresh_token)

    return CustomerLoginResponse(
        access_token=access_token,
        expires_in=expires_in,
        customer=CustomerAuthService.to_public(customer),
    )


@router.post("/refresh", response_model=CustomerRefreshResponse, summary="Refresh customer access token")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    _origin_ok: None = Depends(verify_same_origin),
) -> CustomerRefreshResponse:
    raw_refresh_token = request.cookies.get(settings.CUSTOMER_REFRESH_COOKIE_NAME)
    if not raw_refresh_token:
        raise UnauthorizedException("No active session")

    access_token, new_raw_refresh_token, expires_in = await CustomerAuthService.rotate_refresh_token(
        db, raw_refresh_token
    )

    _set_customer_refresh_cookie(response, new_raw_refresh_token)

    return CustomerRefreshResponse(access_token=access_token, expires_in=expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke current customer session")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    _origin_ok: None = Depends(verify_same_origin),
) -> None:
    raw_refresh_token = request.cookies.get(settings.CUSTOMER_REFRESH_COOKIE_NAME)
    if raw_refresh_token:
        await CustomerAuthService.revoke_refresh_token(db, raw_refresh_token)
    _clear_customer_refresh_cookie(response)


@router.get("/me", response_model=CustomerPublic, summary="Get authenticated customer")
async def me(current_customer: CustomerAccount = Depends(get_current_customer)) -> CustomerPublic:
    return CustomerAuthService.to_public(current_customer)


@router.post("/forgot-password", response_model=GenericMessageResponse, summary="Request a password reset")
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> GenericMessageResponse:
    client_ip = request.client.host if request.client else "unknown"
    await enforce_customer_password_reset_rate_limit(f"{client_ip}:{payload.email.strip().lower()}")

    raw_token = await CustomerAuthService.forgot_password(db, payload.email)
    if raw_token is not None:
        await _send_password_reset_email(payload.email, raw_token)

    return GenericMessageResponse(message=_GENERIC_PASSWORD_RESET_MESSAGE)


@router.post("/reset-password", response_model=GenericMessageResponse, summary="Reset password using a reset token")
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> GenericMessageResponse:
    client_ip = request.client.host if request.client else "unknown"
    await enforce_customer_password_reset_rate_limit(client_ip)

    await CustomerAuthService.reset_password(db, payload.token, payload.new_password)
    return GenericMessageResponse(message="Your password has been reset. You can now sign in.")
