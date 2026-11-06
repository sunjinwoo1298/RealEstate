from typing import AsyncGenerator, Callable, Optional
import uuid

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db
from backend.core.exceptions import ForbiddenException, UnauthorizedException
from backend.core.security import decode_access_token
from backend.models.conversation import Conversation
from backend.models.user import User, UserRole
from backend.services.buyer_session_service import BuyerSessionService
from backend.services.conversation_service import ConversationService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Reusable FastAPI dependency providing an AsyncSession.
    """
    async for session in get_db():
        yield session


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """
    Resolves the authenticated staff principal from the bearer access token.
    Raises 401 for any missing, invalid, expired or stale-user token.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedException("Authentication required")

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise UnauthorizedException("Access token has expired")
    except jwt.PyJWTError:
        raise UnauthorizedException("Invalid access token")

    try:
        user_id = uuid.UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        raise UnauthorizedException("Invalid access token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise UnauthorizedException("Account is not available")

    return user


def require_roles(*allowed_roles: UserRole) -> Callable:
    """
    Dependency factory enforcing that the current user holds one of the given roles.
    Returns 403 for authenticated-but-unauthorized requests.
    """

    async def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenException("You do not have permission to perform this action")
        return current_user

    return _dependency


async def get_buyer_conversation(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Conversation:
    """
    Resolves the authorized buyer conversation from the buyer session cookie.
    Never trusts a caller-supplied lead or conversation id for authorization;
    the session cookie is the sole source of buyer identity and must match
    the conversation being accessed (enforced by callers via conversation.id).
    """
    raw_token = request.cookies.get(settings.BUYER_SESSION_COOKIE_NAME)
    if not raw_token:
        raise UnauthorizedException("No active chat session")

    session = await BuyerSessionService.validate_session(db, raw_token)
    return await ConversationService.get_conversation_by_id(db, session.conversation_id)


def verify_same_origin(request: Request) -> None:
    """
    Defense-in-depth CSRF check for cookie-authenticated endpoints (refresh/logout).
    Rejects cross-origin requests whose Origin header is not an allowed CORS origin,
    in addition to the primary SameSite cookie defense.
    """
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins_list:
        raise ForbiddenException("Cross-origin request rejected")
