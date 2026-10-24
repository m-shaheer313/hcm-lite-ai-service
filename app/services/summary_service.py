"""Dashboard summary: server-computed KPIs -> 3-5 grounded bullets.

The client never sends numbers; the server recomputes the KPIs with the same
analytics function the dashboard uses. Bullets may only use those numbers.
On grounding failure after one retry, honest code-built bullets are returned
(and the fallback is logged, never silent).
"""

import asyncio
import json
import time

from agents import ModelSettings, RunConfig, Runner
from sqlmodel import Session

from app import logging_db
from app.agents.summary_agent import build_summary_agent
from app.config import Settings
from app.context import UserContext
from app.services.ai_common import AI_LABEL, enforce_rate_limit
from app.services.analytics_service import kpis as compute_kpis
from app.services.grounding import find_ungrounded_numbers

ENDPOINT = "/ai/dashboard-summary"
MIN_BULLETS = 3
MAX_BULLETS = 5


def fallback_bullets(kpi_data: dict) -> list[str]:
    """Bullets built directly from the KPI numbers in code. Always grounded."""
    return [
        f"Headcount: {kpi_data['headcount']} active employees.",
        f"Attendance rate: {kpi_data['attendance_rate_pct']}% over {kpi_data['working_days']} working days.",
        f"Late days: {kpi_data['late_days']}, absent days: {kpi_data['absent_days']}.",
        f"Half days: {kpi_data['half_days']}.",
        f"Approved leave: {kpi_data['approved_leave_days']} day(s); {kpi_data['employees_on_leave']} employee(s) on leave.",
    ]


def parse_bullets(answer: str) -> list[str]:
    """Split a model answer into clean bullets (drop markers/empties)."""
    bullets = []
    for line in answer.splitlines():
        cleaned = line.strip().lstrip("-*• ").strip()
        if cleaned:
            bullets.append(cleaned)
    return bullets[:MAX_BULLETS]


async def _generate(settings: Settings, kpi_text: str, *, model=None) -> str:
    """One writer run with timeout, turn caps, and tracing off."""
    agent = build_summary_agent(model=model)
    prompt = f"Summarize this dashboard data in 3 to 5 bullets.\n<data>\n{kpi_text}\n</data>"
    result = await asyncio.wait_for(
        Runner.run(
            agent,
            prompt,
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
    return str(result.final_output)


async def dashboard_summary(
    session: Session,
    ctx: UserContext,
    settings: Settings,
    *,
    start=None,
    end=None,
    department_id: int | None = None,
    model=None,
) -> dict:
    """Handle one /ai/dashboard-summary request (Admin/HR only)."""
    started = time.monotonic()
    enforce_rate_limit(session, ctx, settings, endpoint=ENDPOINT)

    # The SERVER computes the numbers; nothing the client sent is trusted.
    kpi = compute_kpis(session, ctx, start=start, end=end, department_id=department_id)
    kpi_text = json.dumps(kpi["kpis"], default=str)

    def finish(status: str, bullets: list[str], fallback: bool) -> dict:
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
        return {"label": AI_LABEL, "summary": bullets, "fallback": fallback}

    if model is None and not settings.ai_api_key:
        return finish("not_configured", fallback_bullets(kpi["kpis"]), True)

    try:
        for attempt in range(2):  # one retry on bad or ungrounded bullets
            try:
                answer = await _generate(settings, kpi_text, model=model)
            except TimeoutError:
                return finish("timeout", fallback_bullets(kpi["kpis"]), True)
            bullets = parse_bullets(answer)
            grounded = not find_ungrounded_numbers("\n".join(bullets), kpi_text)
            if len(bullets) >= MIN_BULLETS and grounded:
                return finish("ok" if attempt == 0 else "ok_retry", bullets, False)
        return finish("summary_fallback", fallback_bullets(kpi["kpis"]), True)
    except Exception:  # noqa: BLE001 — deliberate: honest fallback, never a crash
        return finish("error", fallback_bullets(kpi["kpis"]), True)
