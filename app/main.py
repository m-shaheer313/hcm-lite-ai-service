"""FastAPI entry point: builds the app, connects the database, mounts routes.

Layers: routes (HTTP only) -> services (business rules) -> repositories (SQL).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings
from app.db import init_db, make_engine
from app.errors import install_error_handlers
from app.routes import ai as ai_routes
from app.routes import analytics as analytics_routes
from app.routes import attendance as attendance_routes
from app.routes import auth as auth_routes
from app.routes import leaves as leaves_routes
from app.routes import org as org_routes
from app.routes import payroll as payroll_routes
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast if required env vars are missing; create tables on startup.
    settings = Settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    app.state.settings = settings
    app.state.engine = engine
    yield
    engine.dispose()


app = FastAPI(title="HCM Lite AI Service", lifespan=lifespan)
install_error_handlers(app)
app.include_router(auth_routes.router)
app.include_router(org_routes.router)
app.include_router(attendance_routes.router)
app.include_router(leaves_routes.router)
app.include_router(payroll_routes.router)
app.include_router(analytics_routes.router)
app.include_router(ai_routes.router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Small check that the service is up. Used by Render and by me."""
    return HealthResponse(status="ok")
