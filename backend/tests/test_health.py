import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.config import settings

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "EstateFlow AI"
    assert data["status"] == "online"
    assert "health" in data


def test_cors_headers():
    response = client.get("/", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_settings_url_transformation():
    raw_postgres = "postgres://user:pass@db.prisma.io:5432/postgres?sslmode=require"
    formatted = settings._format_async_postgres_url(raw_postgres)
    assert formatted.startswith("postgresql+asyncpg://")
    assert "ssl=require" in formatted
    assert "sslmode=" not in formatted


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "EstateFlow AI"
    assert "database" in data
    assert data["database"]["status"] == "healthy"
    assert data["database"]["database"] == "PostgreSQL (Prisma)"
    assert "redis" in data

