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

    # Idempotent refresh recovery (BUG-18): lets the *immediately previous*
    # refresh token be retried for a short window and return the same
    # successor, so a response lost to a reload/navigation is not mistaken
    # for token theft. The successor is stored only AES-256-GCM encrypted.
    REFRESH_RECOVERY_KEY: str = Field(
        default="",
        description="Dedicated base64url-encoded 32-byte key for refresh-token recovery. Empty disables recovery "
        "(strict reuse detection only). Generate with: python -c \"import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())\"",
    )
    REFRESH_RECOVERY_GRACE_SECONDS: int = Field(
        default=20, ge=0, le=120, description="Grace period (seconds) in which the previous refresh token can be retried; 0 disables"
    )

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

    # AI qualification / knowledge (RAG)
    GROQ_API_KEY: str = Field(default="", description="Groq API key used for all LLM orchestration calls")
    GROQ_MODEL: str = Field(default="openai/gpt-oss-20b", description="Groq chat-completion model id")
    AI_RESPONSE_TIMEOUT_SECONDS: float = Field(default=20.0, description="Max time allowed for the full AI reply pipeline")
    HF_TOKEN: str = Field(default="", description="Hugging Face API token for remote inference embedding generation")
    HF_API_URL: Optional[str] = Field(default=None, description="Optional custom Hugging Face inference endpoint URL")
    HF_EMBEDDING_TIMEOUT_SECONDS: float = Field(default=30.0, description="Timeout in seconds for Hugging Face embedding API requests")
    EMBEDDING_MODEL_NAME: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        description="Sentence-transformers model used for knowledge chunk and query embeddings (multilingual, offline)",
    )
    EMBEDDING_DIMENSION: int = Field(default=384, description="Embedding vector dimension produced by EMBEDDING_MODEL_NAME")
    KNOWLEDGE_CHUNK_SIZE_CHARS: int = Field(default=900, description="Target character length per knowledge chunk")
    KNOWLEDGE_CHUNK_OVERLAP_CHARS: int = Field(default=150, description="Character overlap between consecutive chunks")
    RAG_TOP_K: int = Field(default=4, description="Number of semantic chunks retrieved per knowledge query")
    AI_PROCESSING_LOCK_TTL_SECONDS: int = Field(
        default=30, description="TTL for the per-conversation AI-processing lock that prevents duplicate AI replies on retry"
    )

    # Customer authentication & identity (Feature 10)
    FRONTEND_BASE_URL: str = Field(
        default="http://localhost:3000", description="Frontend base URL used to build links in transactional emails"
    )
    CUSTOMER_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, description="Customer access token lifetime in minutes")
    CUSTOMER_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, description="Customer refresh token lifetime in days")
    CUSTOMER_REFRESH_COOKIE_NAME: str = Field(
        default="estateflow_customer_refresh_token", description="Customer refresh token cookie name"
    )
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = Field(
        default=24, description="Customer email-verification token lifetime in hours"
    )
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="Customer password-reset token lifetime in minutes"
    )
    CUSTOMER_REGISTRATION_RATE_LIMIT_MAX_ATTEMPTS: int = Field(
        default=5, description="Max customer registration attempts per window per IP"
    )
    CUSTOMER_REGISTRATION_RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=3600, description="Customer registration rate limit window in seconds"
    )
    CUSTOMER_LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = Field(
        default=5, description="Max failed customer login attempts per window"
    )
    CUSTOMER_LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=300, description="Customer login rate limit window in seconds"
    )
    CUSTOMER_VERIFICATION_RATE_LIMIT_MAX_ATTEMPTS: int = Field(
        default=5, description="Max email verification/resend requests per window per identifier"
    )
    CUSTOMER_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=3600, description="Customer email verification rate limit window in seconds"
    )
    CUSTOMER_PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS: int = Field(
        default=5, description="Max password-reset requests per window per identifier"
    )
    CUSTOMER_PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=3600, description="Customer password-reset rate limit window in seconds"
    )

    # Customer chat (Feature 12) -- rate limits keyed per authenticated
    # customer, distinct from the anonymous buyer-chat limiters above.
    CUSTOMER_CONVERSATION_RATE_LIMIT_MAX_ATTEMPTS: int = Field(
        default=10, description="Max customer conversation-creation attempts per window per customer"
    )
    CUSTOMER_CONVERSATION_RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=300, description="Customer conversation-creation rate limit window in seconds"
    )
    CUSTOMER_CHAT_MESSAGE_RATE_LIMIT_MAX_ATTEMPTS: int = Field(
        default=30, description="Max customer chat messages per window per conversation"
    )
    CUSTOMER_CHAT_MESSAGE_RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=60, description="Customer chat message rate limit window in seconds"
    )
    CUSTOMER_HANDOFF_RATE_LIMIT_MAX_ATTEMPTS: int = Field(
        default=5, description="Max customer handoff requests per window per customer"
    )
    CUSTOMER_HANDOFF_RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=300, description="Customer handoff-request rate limit window in seconds"
    )

    # Site-visit reminders (Feature 07)
    REMINDER_WORKER_POLL_INTERVAL_SECONDS: int = Field(
        default=30, description="How often the reminder worker polls for due reminders"
    )
    REMINDER_WORKER_BATCH_SIZE: int = Field(
        default=50, description="Max due reminders claimed by one worker poll"
    )
    REMINDER_MAX_ATTEMPTS: int = Field(
        default=5, description="Max delivery attempts before a reminder is marked permanently FAILED"
    )
    REMINDER_RETRY_BASE_SECONDS: int = Field(
        default=60, description="Base delay for exponential backoff between reminder delivery retries"
    )
    REMINDER_RETRY_MAX_SECONDS: int = Field(
        default=1800, description="Maximum backoff delay between reminder delivery retries"
    )

    # Customer transactional email (Feature 14). EMAIL_PROVIDER=log is the
    # safe development/test default: nothing is ever sent for real.
    EMAIL_PROVIDER: str = Field(default="log", description="Customer email provider: 'log' (simulated) or 'resend'")
    EMAIL_API_KEY: str = Field(default="", description="Email provider API key (secret; never exposed to the frontend)")
    EMAIL_FROM_ADDRESS: str = Field(default="", description="Verified sender address for customer email")
    EMAIL_FROM_NAME: str = Field(default="EstateFlow", description="Sender display name for customer email")
    EMAIL_REPLY_TO: str = Field(default="", description="Optional reply-to address")
    EMAIL_SUPPORT_CONTACT: str = Field(
        default="", description="Optional verified support contact line shown in emails; omitted when empty"
    )
    EMAIL_PROVIDER_TIMEOUT_SECONDS: float = Field(default=10.0, description="HTTP timeout for the email provider")
    CUSTOMER_PORTAL_BASE_URL: str = Field(
        default="", description="Public customer-portal base URL used in email links; falls back to FRONTEND_BASE_URL"
    )
    CUSTOMER_EMAIL_WORKER_POLL_SECONDS: int = Field(default=5, description="Customer email worker poll interval")
    CUSTOMER_EMAIL_WORKER_BATCH_SIZE: int = Field(default=25, description="Max deliveries claimed per poll")
    CUSTOMER_EMAIL_MAX_ATTEMPTS: int = Field(default=5, description="Max attempts before a delivery is FAILED")
    CUSTOMER_EMAIL_RETRY_BASE_SECONDS: int = Field(default=30, description="Base exponential-backoff delay")
    CUSTOMER_EMAIL_RETRY_MAX_SECONDS: int = Field(default=1800, description="Maximum backoff delay")
    CUSTOMER_EMAIL_PROCESSING_LEASE_SECONDS: int = Field(
        default=300, description="A PROCESSING delivery older than this is considered orphaned by a crashed worker"
    )
    CUSTOMER_DELIVERY_RETRY_RATE_LIMIT_MAX_ATTEMPTS: int = Field(
        default=20, description="Max admin delivery-retry actions per window per admin"
    )
    CUSTOMER_DELIVERY_RETRY_RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=300, description="Admin delivery-retry rate limit window in seconds"
    )

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
        return [origin.strip().rstrip("/") for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

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
    def customer_portal_base_url(self) -> str:
        return (self.CUSTOMER_PORTAL_BASE_URL or self.FRONTEND_BASE_URL).rstrip("/")

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

