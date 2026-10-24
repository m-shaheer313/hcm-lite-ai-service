"""Smart leave: a plain sentence -> a validated leave DRAFT (never saved).

The LLM only extracts {type, day words, reason}. Deterministic code resolves
dates (Asia/Karachi) and validates. One retry, then {"fallback": true} so the
normal form shows. Shares the rate limit and ai_logs with /ai/chat.
"""

import asyncio
import time
from datetime import UTC, date, datetime, timedelta

from agents import ModelSettings, RunConfig, Runner
from sqlmodel import Session

from app import logging_db
from app.agents.smart_leave_agent import LeaveExtraction, build_smart_leave_agent
from app.config import Settings
from app.context import UserContext
from app.repositories import leaves as leave_repo
from app.services import resolve_dates, rules
from app.services.ai_common import AI_LABEL, enforce_rate_limit

ENDPOINT = "/ai/smart-leave"
VALID_TYPES = {"annual", "sick", "casual", "unpaid"}


def karachi_today() -> date:
    """Today in the office timezone."""
    return rules.today_in_karachi(datetime.now(UTC))


def build_draft(extraction: LeaveExtraction, today: date, holidays: set[date]) -> dict | None:
    """Turn an extraction into a validated draft, or None if invalid.

    Pure of LLM and database writes: type must exist, phrases must resolve,
    start <= end, not in the past, at least one working day.
    """
    leave_type = extraction.leave_type.strip().lower()
    if leave_type not in VALID_TYPES:
        return None
    start = resolve_dates.resolve_phrase(extraction.start_phrase, today)
    end = resolve_dates.resolve_phrase(extraction.end_phrase, today)
    if start is None or end is None:
        return None
    if end < start or start < today:
        return None
    if rules.count_working_days(start, end, holidays) == 0:
        return None
    return {
        "leave_type": leave_type,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "reason": extraction.reason.strip()[:200] or "leave",
    }


async def _extract(settings: Settings, message: str, today: str, *, model=None) -> LeaveExtraction:
    """Run the extraction agent with timeout, turn caps, and tracing off."""
    agent = build_smart_leave_agent(today, model=model)
    result = await asyncio.wait_for(
        Runner.run(
            agent,
            message,
            max_turns=settings.max_turns,
            run_config=RunConfig(
                tracing_disabled=True,
                model_settings=ModelSettings(
                    max_tokens=settings.max_output_tokens,
                    timeout=settings.ai_timeout_seconds,
                ),
            ),
        ),
        timeout=settings.ai_timeout_seconds,
    )
    return result.final_output


async def smart_leave(
    session: Session,
    ctx: UserContext,
    settings: Settings,
    message: str,
    *,
    today: date | None = None,
    model=None,
) -> dict:
    """Handle one /ai/smart-leave request. Never saves anything."""
    started = time.monotonic()
    enforce_rate_limit(session, ctx, settings, endpoint=ENDPOINT)
    today = today or karachi_today()
    holidays = leave_repo.holiday_dates(session, today, today + timedelta(days=62))

    def finish(status: str, draft: dict | None) -> dict:
        latency = int((time.monotonic() - started) * 1000)
        logging_db.log_call(
            session,
            user_id=ctx.user_id,
            role=ctx.role,
            endpoint=ENDPOINT,
            tool=None,
            status=status,
            latency_ms=latency,
        )
        if draft is None:
            return {"label": AI_LABEL, "fallback": True, "draft": None}
        return {"label": AI_LABEL, "fallback": False, "draft": draft}

    if model is None and not settings.ai_api_key:
        return finish("not_configured", None)

    try:
        for attempt in range(2):  # one retry, then the normal form shows
            try:
                extraction = await _extract(settings, message, today.isoformat(), model=model)
                draft = build_draft(extraction, today, holidays)
            except TimeoutError:
                return finish("timeout", None)
            if draft is not None:
                return finish("ok" if attempt == 0 else "ok_retry", draft)
        return finish("fallback", None)
    except Exception:  # noqa: BLE001 — deliberate: fallback instead of an error
        return finish("error", None)
