"""Test setup.

- Tests run on an in-memory SQLite database. No network, no real keys.
- Test fixtures may create data; the real app always starts empty.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db import init_db

os.environ.setdefault("DATABASE_URL", "sqlite://")
# 32+ bytes dummy secret: PyJWT warns on short HMAC keys (test-only value).
os.environ.setdefault("JWT_SECRET", "test-only-secret-0123456789abcdef")

# Dummy passwords for test fixtures only. Override via env; never real values.
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "FixturePass123")
TEST_NEW_PASSWORD = os.environ.get("TEST_NEW_PASSWORD", "FixturePass456")


@pytest.fixture(name="engine")
def engine_fixture():
    """One shared in-memory SQLite database per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(engine):
    """TestClient wired to the same in-memory DB the session fixture uses."""
    from app.deps import get_db
    from app.main import app

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
