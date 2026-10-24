"""FastAPI entry point. Starts the app and serves /health.

Business layers (added in later tasks): routes -> services -> repositories.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast: the app will not start if a required env var is missing.
    app.state.settings = Settings()
    yield


app = FastAPI(title="HCM Lite AI Service", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Small check that the service is up. Used by Render and by me."""
    return HealthResponse(status="ok")
