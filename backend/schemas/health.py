from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    status: str = Field(..., description="'healthy' or 'unhealthy'")
    database: str = Field(default="PostgreSQL (Prisma)", description="Database engine")
    latency_ms: Optional[float] = Field(None, description="Roundtrip query latency in ms")
    error: Optional[str] = Field(None, description="Error message if unhealthy")


class RedisHealth(BaseModel):
    status: str = Field(..., description="'connected', 'disconnected', or 'degraded'")
    message: str = Field(..., description="Status description")
    url: Optional[str] = Field(None, description="Sanitized redis host/port")


class HealthResponse(BaseModel):
    status: str = Field(..., description="Overall health: 'healthy', 'degraded', or 'unhealthy'")
    timestamp: datetime = Field(..., description="Server timestamp in UTC")
    app_name: str = Field(..., description="Application name")
    environment: str = Field(..., description="Runtime environment")
    version: str = Field(default="1.0.0", description="API version")
    database: DatabaseHealth = Field(..., description="Database connectivity status")
    redis: RedisHealth = Field(..., description="Redis connectivity status")

