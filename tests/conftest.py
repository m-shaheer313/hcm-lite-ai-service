"""Test setup.

- Tests run on an in-memory SQLite database. No network, no real keys.
- Test fixtures may create data; the real app always starts empty.
"""

import os

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db import init_db

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("JWT_SECRET", "test-only-secret")


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
