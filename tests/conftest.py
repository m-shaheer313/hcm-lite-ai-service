"""Test setup. Tests run on SQLite with a dummy secret. Never put real keys here."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("JWT_SECRET", "test-only-secret")
