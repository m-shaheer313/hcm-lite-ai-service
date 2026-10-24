"""Small pieces shared by every AI endpoint: label + rate limit."""

import time

from sqlmodel import Session

from app import logging_db
from app.config import Settings
from app.context import UserContext
from app.errors import RateLimitError

AI_LABEL = "AI-generated"


def enforce_rate_limit(
    session: Session, ctx: UserContext, settings: Settings, *, endpoint: str
) -> None:
    """Shared 20-requests-per-user-per-hour limit, counted from ai_logs.

    The refusal itself is logged, then the caller sees HTTP 429.
    """
    started = time.monotonic()
    if logging_db.count_recent_calls(session, ctx.user_id) < settings.rate_limit_per_hour:
        return
    logging_db.log_call(
        session,
        user_id=ctx.user_id,
        role=ctx.role,
        endpoint=endpoint,
        tool=None,
        status="rate_limited",
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    raise RateLimitError(
        f"You have used your {settings.rate_limit_per_hour} AI requests for this hour. "
        "Please try again later."
    )
