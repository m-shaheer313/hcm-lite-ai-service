"""Database engine and session helpers.

- Postgres (Neon) in production via DATABASE_URL.
- SQLite for local dev and tests.
- No Alembic: create_all builds the schema (fine for a hackathon).
"""

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (importing registers all tables)


def make_engine(database_url: str):
    """Create an engine. SQLite gets one extra argument for FastAPI's threads."""
    if database_url.startswith("sqlite"):
        return create_engine(database_url, connect_args={"check_same_thread": False})
    return create_engine(database_url, pool_pre_ping=True)


def init_db(engine) -> None:
    """Create all tables that do not exist yet."""
    SQLModel.metadata.create_all(engine)


def get_session(engine):
    """FastAPI dependency: one database session per request."""

    def _get_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return _get_session
