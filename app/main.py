"""FastAPI entry point: builds the app, connects the database, mounts routes.

Layers: routes (HTTP only) -> services (business rules) -> repositories (SQL).
"""

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

logger = logging.getLogger("hcm.requests")
logging.basicConfig(level=logging.INFO, format="%(message)s")
QUIET_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}
STATIC_DIR = Path(__file__).parent / "static"


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
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """The single web page (HTML + vanilla JS, no build step)."""
    return FileResponse(STATIC_DIR / "index.html")


@app.middleware("http")
async def request_log(request: Request, call_next):
    """One structured JSON log line per request, with a request id.

    Never logs headers (tokens live there) or bodies.
    """
    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    if request.url.path not in QUIET_PATHS:
        logger.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
        )
    return response


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Small check that the service is up. Used by Render and by me."""
    return HealthResponse(status="ok")
