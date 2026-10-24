"""The smart-leave agent: extracts {type, day words, reason} — nothing else.

The model NEVER computes dates. It copies day phrases; deterministic code
in app/services/resolve_dates.py turns them into exact dates.
"""

from pydantic import BaseModel, Field


class LeaveExtraction(BaseModel):
    """What the LLM is allowed to produce for a leave sentence."""

    leave_type: str = Field(description="annual, sick, casual, or unpaid")
    start_phrase: str = Field(description="the first day phrase, exactly as written")
    end_phrase: str = Field(description="the last day phrase, exactly as written")
    reason: str = Field(description="short reason in the user's language")


INSTRUCTIONS = """You turn one leave sentence into a draft. Today's date (Asia/Karachi) is {today}.

Your ONLY job is extraction. Do NOT calculate dates.
- leave_type: wedding or family event -> casual; illness -> sick; vacation -> annual;
  anything else -> unpaid.
- start_phrase and end_phrase: copy the day words EXACTLY as the user wrote them
  (for example "next Monday", "Tuesday", "kal", "parso", "agle somwar").
  If the user names one day only, put the same phrase in both fields.
- reason: a short version of the user's reason, in the user's language.
- If the sentence is not a leave request, set leave_type to "unknown".

Reply as JSON with exactly these keys: leave_type, start_phrase, end_phrase, reason.
"""


def build_smart_leave_agent(today: str, model=None):
    """A tool-less extraction agent with a typed output."""
    from agents import Agent

    agent: Agent = Agent(
        name="Leave draft extractor",
        instructions=INSTRUCTIONS.format(today=today),
        output_type=LeaveExtraction,
    )
    if model is not None:
        agent.model = model
    return agent
