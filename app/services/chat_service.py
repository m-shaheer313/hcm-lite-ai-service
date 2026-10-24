"""Chat service: one AI conversation turn with all the safety around it.

Flow: rate limit -> build agent for the caller's role -> run with timeout,
max_turns and token limits -> grounding check (retry once) -> log everything
to ai_logs -> always return a friendly answer with the AI-generated label.
"""

import asyncio
import re
import time
from datetime import UTC, datetime

from agents import ModelSettings, RunConfig, Runner
from sqlmodel import Session

from app import logging_db
from app.agents.chat_agent import build_chat_agent
from app.config import Settings
from app.context import UserContext
from app.errors import RateLimitError
from app.services import rules
from app.tools import ToolDeps

AI_LABEL = "AI-generated"
TIMEOUT_MESSAGE = (
    "Sorry, that took too long. Please try again in a moment — "
    "your data is safe, nothing was changed."
)
ERROR_MESSAGE = "Sorry, the assistant hit a problem on our side. Please try again in a moment."
NOT_CONFIGURED_MESSAGE = (
    "The AI assistant is not configured yet (missing AI_API_KEY). Please ask the admin to add it."
)
UNGROUNDABLE_MESSAGE = (
    "I could not fully verify the numbers for that question, so I will not guess. "
    "Please check the dashboard for the exact figures."
)

# Numbers with 2+ digits are checked; single digits are too easy to false-alarm.
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _normalize(text: str) -> set[str]:
    """All number tokens of a text, without commas."""
    return {match.replace(",", "") for match in _NUMBER_RE.findall(text)}


def find_ungrounded_numbers(answer: str, tool_text: str) -> list[str]:
    """Pure check: numbers in the answer that do not exist in the tool data."""
    return sorted(_normalize(answer) - _normalize(tool_text) - {"09", "15"})


async def _run_once(
    session: Session,
    ctx: UserContext,
    settings: Settings,
    message: str,
    *,
    model=None,
) -> tuple[str, ToolDeps]:
    """One agent run. Returns the answer text and the deps (tool usage)."""
    deps = ToolDeps(ctx=ctx, session=session)
    agent = build_chat_agent(
        ctx, today=rules.today_in_karachi(datetime.now(UTC)).isoformat(), model=model
    )
    result = await asyncio.wait_for(
        Runner.run(
            agent,
            message,
            context=deps,
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
    return str(result.final_output), deps


async def chat(
    session: Session,
    ctx: UserContext,
    settings: Settings,
    message: str,
    *,
    model=None,
) -> dict:
    """Handle one /ai/chat request. Never raises at the user."""
    started = time.monotonic()

    recent = logging_db.count_recent_calls(session, ctx.user_id)
    if recent >= settings.rate_limit_per_hour:
        latency = int((time.monotonic() - started) * 1000)
        logging_db.log_call(
            session,
            user_id=ctx.user_id,
            role=ctx.role,
            endpoint="/ai/chat",
            tool=None,
            status="rate_limited",
            latency_ms=latency,
        )
        raise RateLimitError(
            f"You have used your {settings.rate_limit_per_hour} AI requests for this hour. "
            "Please try again later."
        )

    if model is None and not settings.ai_api_key:
        latency = int((time.monotonic() - started) * 1000)
        logging_db.log_call(
            session,
            user_id=ctx.user_id,
            role=ctx.role,
            endpoint="/ai/chat",
            tool=None,
            status="not_configured",
            latency_ms=latency,
        )
        return {"label": AI_LABEL, "answer": NOT_CONFIGURED_MESSAGE, "tools_used": []}

    try:
        answer, deps = await _run_once(session, ctx, settings, message, model=model)

        # Grounding: every number in the answer must come from tool data.
        tool_text = " ".join(deps.tool_results)
        if find_ungrounded_numbers(answer, tool_text):
            answer2, deps2 = await _run_once(session, ctx, settings, message, model=model)
            deps.used_tools.extend(deps2.used_tools)
            deps.tool_results.extend(deps2.tool_results)
            tool_text = " ".join(deps.tool_results)
            if find_ungrounded_numbers(answer2, tool_text):
                answer, status = UNGROUNDABLE_MESSAGE, "ungrounded_fallback"
            else:
                answer, status = answer2, "ok"
        else:
            status = "ok"
    except TimeoutError:
        answer, status, deps = TIMEOUT_MESSAGE, "timeout", ToolDeps(ctx=ctx, session=session)
    except Exception:  # noqa: BLE001 — deliberate: the user must never see a traceback
        answer, status, deps = ERROR_MESSAGE, "error", ToolDeps(ctx=ctx, session=session)

    latency = int((time.monotonic() - started) * 1000)
    logging_db.log_call(
        session,
        user_id=ctx.user_id,
        role=ctx.role,
        endpoint="/ai/chat",
        tool=",".join(deps.used_tools) or None,
        status=status,
        latency_ms=latency,
    )
    return {
        "label": AI_LABEL,
        "answer": answer,
        "tools_used": deps.used_tools,
    }
