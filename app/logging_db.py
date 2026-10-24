"""ai_logs: one row per AI call, and the rate-limit counter.

The log NEVER stores tokens, keys, full prompts, or salary values — only the
facts needed to debug and to count usage.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, func, select

from app.models import AiLog

logger = logging.getLogger("hcm.ai_logs")


def log_call(
    session: Session,
    *,
    user_id: int,
    role: str,
    endpoint: str,
    tool: str | None,
    status: str,
    latency_ms: int,
    error: str | None = None,
) -> None:
    """Write one ai_logs row. If the database is down, log to stdout instead —
    an AI call must never fail because logging failed."""
    row = AiLog(
        user_id=user_id,
        role=role,
        endpoint=endpoint,
        tool=tool,
        status=status,
        latency_ms=latency_ms,
        error=error[:500] if error else None,
    )
    try:
        session.add(row)
        session.commit()
    except Exception:  # noqa: BLE001 — deliberate: a logging failure must never break the user's request
        session.rollback()
        logger.warning(
            "ai_logs write failed; printing instead: user=%s endpoint=%s status=%s",
            user_id,
            endpoint,
            status,
        )


def count_recent_calls(session: Session, user_id: int, *, hours: int = 1) -> int:
    """How many AI calls this user made in the last hour (rate-limit input)."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    return session.exec(
        select(func.count())
        .select_from(AiLog)
        .where(AiLog.user_id == user_id, AiLog.created_at >= since)
    ).one()
