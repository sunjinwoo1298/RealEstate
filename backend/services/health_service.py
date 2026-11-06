import time
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.redis import check_redis_connectivity
from backend.schemas.health import DatabaseHealth, HealthResponse, RedisHealth


class HealthService:
    """
    Coordinates health checks for core application dependencies.
    """

    @staticmethod
    async def check_database(session: AsyncSession) -> DatabaseHealth:
        start_time = time.perf_counter()
        try:
            result = await session.execute(text("SELECT 1;"))
            val = result.scalar()
            latency = round((time.perf_counter() - start_time) * 1000, 2)
            if val == 1:
                return DatabaseHealth(
                    status="healthy",
                    database="PostgreSQL (Prisma)",
                    latency_ms=latency,
                )
            return DatabaseHealth(
                status="unhealthy",
                database="PostgreSQL (Prisma)",
                latency_ms=latency,
                error="Unexpected query result",
            )
        except Exception as e:
            latency = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(f"Database health check failed: {str(e)}")
            return DatabaseHealth(
                status="unhealthy",
                database="PostgreSQL (Prisma)",
                latency_ms=latency,
                error=str(e),
            )

    @classmethod
    async def get_health_status(cls, session: AsyncSession) -> HealthResponse:
        db_health = await cls.check_database(session)
        redis_raw = await check_redis_connectivity()

        redis_health = RedisHealth(
            status=redis_raw.get("status", "disconnected"),
            message=redis_raw.get("message", "Unknown"),
            url=redis_raw.get("url"),
        )

        overall_status = "healthy"
        if db_health.status != "healthy":
            overall_status = "unhealthy"
        elif redis_health.status != "connected":
            # Redis is currently optional for foundation
            overall_status = "degraded"

        return HealthResponse(
            status=overall_status,
            timestamp=datetime.now(timezone.utc),
            app_name=settings.APP_NAME,
            environment=settings.APP_ENV,
            version="1.0.0",
            database=db_health,
            redis=redis_health,
        )

