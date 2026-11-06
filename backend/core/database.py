from __future__ import annotations
import asyncio
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.core.config import settings
from backend.core.logging import logger


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base class for all application models.
    """
    pass


_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_engine_loop: Optional[asyncio.AbstractEventLoop] = None


def get_engine() -> AsyncEngine:
    """
    Initializes and returns the shared SQLAlchemy AsyncEngine singleton.

    Recreates the engine if the running event loop has changed since it was
    created (e.g. across test-runner event loops), since asyncpg connections
    are bound to the loop that created them and cannot be reused across loops.
    """
    global _engine, _session_factory, _engine_loop

    try:
        current_loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _engine is not None and current_loop is not None and _engine_loop is not current_loop:
        logger.warning("Event loop changed; discarding stale AsyncEngine and recreating.")
        _engine = None
        _session_factory = None
        _engine_loop = None

    if _engine is None:
        db_url = settings.async_database_url
        if not db_url:
            logger.warning("DATABASE_URL is not configured. Database operations will fail.")
            raise ValueError("DATABASE_URL is required but not configured.")

        # SSL handling: if Prisma URL has ssl=require or sslmode=require,
        # create_async_engine passes parameters cleanly to asyncpg.
        connect_args = {}
        if "ssl=" in db_url or "sslmode=" in db_url:
            # asyncpg accepts ssl='require' or True
            connect_args["ssl"] = "require"

        _engine = create_async_engine(
            db_url,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            connect_args=connect_args,
        )
        _engine_loop = current_loop
        logger.info("Initialized SQLAlchemy AsyncEngine for Prisma Postgres.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Returns the shared async sessionmaker.
    """
    global _session_factory
    engine = get_engine()  # also discards a stale factory if the event loop has changed
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an asynchronous SQLAlchemy database session.
    Automatically handles rollback on error and ensures cleanup.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db_connection() -> None:
    """
    Gracefully disposes the database engine during application shutdown.
    """
    global _engine, _session_factory
    if _engine is not None:
        logger.info("Disposing SQLAlchemy AsyncEngine...")
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection disposed successfully.")
