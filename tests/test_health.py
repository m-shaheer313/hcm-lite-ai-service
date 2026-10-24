"""Tests for GET /health and startup settings."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_required_env_var_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app must refuse to start without DATABASE_URL and JWT_SECRET."""
    from app import config

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(ValidationError):
        config.Settings(_env_file=None)
