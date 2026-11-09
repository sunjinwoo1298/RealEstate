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



def test_validation_errors_never_echo_submitted_values(monkeypatch):
    """
    Regression (E2E BUG-2): the 422 handler logged and returned Pydantic's
    `input` value -- for a missing field that is the whole request body, so
    reset tokens and plaintext passwords were written to the server log.
    """
    from backend.core import exceptions as exc_module

    logged = []
    monkeypatch.setattr(exc_module.logger, "warning", lambda msg, *a, **k: logged.append(str(msg)))

    secret_token = "SECRET-RESET-TOKEN-CANARY"
    secret_password = "Canary!Password123"
    response = client.post(
        "/api/v1/customer-auth/reset-password",
        json={"token": secret_token, "password": secret_password},
    )
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details and all("input" not in d for d in details)
    assert {tuple(d["loc"]) for d in details} >= {("body", "new_password")}
    for text in [response.text, *logged]:
        assert secret_token not in text
        assert secret_password not in text
