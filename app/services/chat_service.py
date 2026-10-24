"""Chat service: one AI conversation turn with all the safety around it.

Flow: rate limit -> build agent for the caller's role -> run with timeout,
max_turns and token limits -> grounding check (retry once) -> log everything
to ai_logs -> always return a friendly answer with the AI-generated label.
"""

import asyncio
import time
from datetime import UTC, datetime

from agents import ModelSettings, RunConfig, Runner
from sqlmodel import Session

from app import logging_db
from app.agents.chat_agent import build_chat_agent, load_policy
from app.config import Settings
from app.context import UserContext
from app.guardrails.input_guardrail import BLOCKED_MESSAGE, screen_input
from app.services import rules
from app.services.ai_common import AI_LABEL, enforce_rate_limit
from app.services.grounding import find_ungrounded_numbers
from app.tools import ToolDeps

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


def allowed_number_sources(tool_text: str, today: str) -> str:
    """Numbers may come from tool data, the policy, or the server's date."""
    return f"{tool_text}\n{load_policy()}\n{today}"


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

    enforce_rate_limit(session, ctx, settings, endpoint="/ai/chat")

    # Cheap input screen BEFORE any agent runs: microseconds, no LLM call.
    blocked, reason = screen_input(message)
    if blocked:
        latency = int((time.monotonic() - started) * 1000)
        logging_db.log_call(
            session,
            user_id=ctx.user_id,
            role=ctx.role,
            endpoint="/ai/chat",
            tool=None,
            status="blocked",
            latency_ms=latency,
            error=reason,
        )
        return {"label": AI_LABEL, "answer": BLOCKED_MESSAGE, "tools_used": []}

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
        today = rules.today_in_karachi(datetime.now(UTC)).isoformat()
        answer, deps = await _run_once(session, ctx, settings, message, model=model)

        # Grounding: every number in the answer must come from trusted text.
        allowed = allowed_number_sources(" ".join(deps.tool_results), today)
        if find_ungrounded_numbers(answer, allowed):
            answer2, deps2 = await _run_once(session, ctx, settings, message, model=model)
            deps.used_tools.extend(deps2.used_tools)
            deps.tool_results.extend(deps2.tool_results)
            allowed = allowed_number_sources(" ".join(deps.tool_results), today)
            if find_ungrounded_numbers(answer2, allowed):
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
