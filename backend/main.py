from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1.router import api_v1_router
from backend.core.config import settings
from backend.core.database import close_db_connection, get_engine
from backend.core.exceptions import register_exception_handlers
from backend.core.logging import logger, setup_logging
from backend.core.redis import close_redis_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown lifecycle.
    """
    setup_logging(level=settings.LOG_LEVEL, structured=settings.STRUCTURED_LOGS)
    logger.info(f"Starting {settings.APP_NAME} in [{settings.APP_ENV}] mode...")

    if not settings.JWT_SECRET_KEY:
        logger.warning(
            "JWT_SECRET_KEY is not configured. Authentication tokens cannot be issued or validated."
        )

    # Initialize database engine
    try:
        get_engine()
        logger.info("Database engine initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database engine: {e}")

    yield

    # Clean shutdown
    logger.info(f"Shutting down {settings.APP_NAME}...")
    await close_db_connection()
    await close_redis_connection()
    logger.info("Application shutdown completed.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Real Estate Lead Management and Sales Automation Platform API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Centralized Exception Handlers
register_exception_handlers(app)

# Include API Routers
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    return {
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "status": "online",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/health", tags=["Root"])
async def root_health():
    """Top-level health redirect/proxy to /api/v1/health."""
    from backend.api.deps import get_db_session
    from backend.services.health_service import HealthService
    async for db in get_db_session():
        return await HealthService.get_health_status(db)

