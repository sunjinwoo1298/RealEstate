from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db_session, verify_same_origin
from backend.core.config import settings
from backend.core.exceptions import UnauthorizedException
from backend.core.rate_limit import enforce_login_rate_limit
from backend.models.user import User
from backend.schemas.auth import LoginRequest, LoginResponse, RefreshResponse
from backend.schemas.user import UserPublic
from backend.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/api/v1/auth",
    )


@router.post("/login", response_model=LoginResponse, summary="Staff login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{payload.email.strip().lower()}"
    await enforce_login_rate_limit(rate_limit_key)

    user = await AuthService.authenticate(db, payload.email, payload.password)
    access_token, raw_refresh_token, expires_in = await AuthService.issue_session(db, user)

    _set_refresh_cookie(response, raw_refresh_token)

    return LoginResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserPublic.model_validate(user),
    )


@router.post("/refresh", response_model=RefreshResponse, summary="Refresh access token")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    _origin_ok: None = Depends(verify_same_origin),
) -> RefreshResponse:
    raw_refresh_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw_refresh_token:
        raise UnauthorizedException("No active session")

    access_token, new_raw_refresh_token, expires_in = await AuthService.rotate_refresh_token(
        db, raw_refresh_token
    )

    _set_refresh_cookie(response, new_raw_refresh_token)

    return RefreshResponse(access_token=access_token, expires_in=expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke current session")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    _origin_ok: None = Depends(verify_same_origin),
) -> None:
    raw_refresh_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if raw_refresh_token:
        await AuthService.revoke_refresh_token(db, raw_refresh_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserPublic, summary="Get authenticated user")
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)
