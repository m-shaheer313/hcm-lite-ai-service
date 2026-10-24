"""Real-LLM tests — run ONLY on request: `uv run pytest -m llm`.

These need AI_API_KEY (and optionally AI_MODEL) in the environment.
They never run in the default suite (addopts excludes the marker).
"""

import asyncio
import os

import pytest
from sqlmodel import Session

from app.config import Settings
from app.context import UserContext
from app.services import chat_service
from tests.helpers import add_employee, ensure_leave_types

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        not os.environ.get("AI_API_KEY"), reason="AI_API_KEY not set; real-LLM test"
    ),
]


def test_hr_headcount_answer_matches_data(client, session: Session) -> None:
    ensure_leave_types(session)
    add_employee(session, code="E1", name="Ali")
    add_employee(session, code="E2", name="Bilal")
    settings = Settings(_env_file=None)
    ctx = UserContext(user_id=1, role="hr", employee_id=None)

    result = asyncio.run(
        chat_service.chat(session, ctx, settings, "How many active employees are there?")
    )

    assert result["label"] == "AI-generated"
    # The model may write the digit or the word.
    assert "2" in result["answer"] or "two" in result["answer"].lower()
