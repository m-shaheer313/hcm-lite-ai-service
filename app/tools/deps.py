"""ToolDeps: what every tool receives via RunContextWrapper.context."""

from dataclasses import dataclass, field

from sqlmodel import Session

from app.context import UserContext


@dataclass
class ToolDeps:
    """The verified user plus the request's DB session.

    used_tools and tool_results record what the agent actually fetched
    (used for ai_logs and the grounding check).
    """

    ctx: UserContext
    session: Session
    used_tools: list[str] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)
