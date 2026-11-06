import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized configuration management using Pydantic Settings.
    Reads environment variables from backend environment and .env.local file.
    """

    APP_NAME: str = Field(default="EstateFlow AI", description="Application Name")
    APP_ENV: str = Field(default="development", description="Application Environment: development, staging, production")
    DEBUG: bool = Field(default=False, description="Debug mode flag")
    
    # Database
    DATABASE_URL: str = Field(
        default="",
        description="Hosted PostgreSQL database connection URL (Prisma Postgres)",
    )
    DIRECT_DATABASE_URL: Optional[str] = Field(
        default=None,
        description="Direct PostgreSQL connection URL for database migrations if pooled",
    )

    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # CORS
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        description="Allowed CORS origins as comma-separated string",
    )

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Application logging level")
    STRUCTURED_LOGS: bool = Field(default=False, description="Whether to output JSON formatted logs")

    # Authentication / JWT
    JWT_SECRET_KEY: str = Field(
        default="",
        description="Secret key used to sign JWT access and refresh tokens. Must be set in production.",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    JWT_ISSUER: str = Field(default="estateflow-ai", description="JWT issuer claim")
    JWT_AUDIENCE: str = Field(default="estateflow-ai-clients", description="JWT audience claim")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, description="Access token lifetime in minutes")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Refresh token lifetime in days")

    # Session cookie
    REFRESH_COOKIE_NAME: str = Field(default="estateflow_refresh_token", description="Refresh token cookie name")
    COOKIE_SECURE: bool = Field(default=True, description="Whether cookies require HTTPS (disable only for local http dev)")
    COOKIE_SAMESITE: str = Field(default="lax", description="SameSite policy for the refresh cookie: lax, strict, or none")
    COOKIE_DOMAIN: Optional[str] = Field(default=None, description="Cookie domain, if cross-subdomain sharing is required")

    # Login rate limiting
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = Field(default=5, description="Max failed login attempts per window")
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=300, description="Login rate limit window in seconds")

    # Admin bootstrap
    INITIAL_ADMIN_EMAIL: Optional[str] = Field(default=None, description="Bootstrap admin email, read from environment")
    INITIAL_ADMIN_PASSWORD: Optional[str] = Field(default=None, description="Bootstrap admin password, read from environment")

    # Lead ingestion / webhooks
    WEBHOOK_SOURCE_SECRETS: str = Field(
        default="WEBSITE:dev-website-secret,PROPERTY_PORTAL:dev-portal-secret,SOCIAL_AD:dev-social-secret,HOARDING:dev-hoarding-secret",
        description="Comma-separated SOURCE_TYPE:secret pairs used to verify inbound webhook HMAC signatures",
    )
    LEAD_NAME_SIMILARITY_THRESHOLD: float = Field(
        default=0.85, description="Minimum name-similarity ratio to flag an ambiguous potential duplicate"
    )
    CSV_IMPORT_MAX_FILE_SIZE_BYTES: int = Field(default=2_000_000, description="Maximum accepted CSV import file size in bytes")
    CSV_IMPORT_MAX_ROWS: int = Field(default=2000, description="Maximum accepted CSV import row count")

    # Buyer chat / conversations
    BUYER_SESSION_COOKIE_NAME: str = Field(default="estateflow_buyer_session", description="Buyer chat session cookie name")
    BUYER_SESSION_EXPIRE_HOURS: int = Field(default=72, description="Buyer chat session lifetime in hours")
    CHAT_MESSAGE_MAX_LENGTH: int = Field(default=4000, description="Maximum accepted buyer/staff chat message length")
    CHAT_SESSION_RATE_LIMIT_MAX_ATTEMPTS: int = Field(default=10, description="Max buyer session-creation attempts per window per IP")
    CHAT_SESSION_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=300, description="Buyer session-creation rate limit window in seconds")
    CHAT_MESSAGE_RATE_LIMIT_MAX_ATTEMPTS: int = Field(default=30, description="Max buyer messages per window per conversation")
    CHAT_MESSAGE_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, description="Buyer message rate limit window in seconds")

    model_config = SettingsConfigDict(
        env_file=(
            ".env.local",
            ".env",
            os.path.join(os.path.dirname(__file__), "..", ".env.local"),
            os.path.join(os.path.dirname(__file__), "..", ".env"),
            os.path.join(os.path.dirname(__file__), "..", "..", ".env.local"),
            os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        """Returns allowed CORS origins as a list."""
        if not self.CORS_ORIGINS:
            return ["http://localhost:3000", "http://127.0.0.1:3000"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    def _format_async_postgres_url(self, raw_url: str) -> str:
        """
        Converts a standard PostgreSQL URL (postgres:// or postgresql://)
        into the format expected by SQLAlchemy + asyncpg (postgresql+asyncpg://)
        and normalizes query parameters (such as sslmode=require to ssl=require).
        """
        if not raw_url:
            return ""
        url = raw_url.strip()
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # asyncpg prefers 'ssl' parameter over 'sslmode'
        if "sslmode=" in url:
            url = url.replace("sslmode=", "ssl=")

        return url

    @property
    def webhook_source_secrets_map(self) -> dict:
        """Parses WEBHOOK_SOURCE_SECRETS into a {source_type: secret} dict."""
        result: dict = {}
        for pair in self.WEBHOOK_SOURCE_SECRETS.split(","):
            if ":" not in pair:
                continue
            source, _, secret = pair.strip().partition(":")
            if source and secret:
                result[source.strip().upper()] = secret.strip()
        return result

    @property
    def async_database_url(self) -> str:
        """Returns the SQLAlchemy asyncpg connection string for runtime database operations."""
        return self._format_async_postgres_url(self.DATABASE_URL)

    @property
    def migration_database_url(self) -> str:
        """
        Returns the database URL for Alembic migrations.
        Prefers DIRECT_DATABASE_URL if available, else falls back to DATABASE_URL.
        """
        target = self.DIRECT_DATABASE_URL or self.DATABASE_URL
        return self._format_async_postgres_url(target)


settings = Settings()

