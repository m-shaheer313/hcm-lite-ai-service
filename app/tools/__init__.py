"""AI tools package: the agent's hands, and the role-based allowlist.

The allowlist is enforced in CODE, not in the prompt: an Employee agent is
built with only the employee tools, so the model physically has no tool to
fetch another person's data.
"""

from dataclasses import dataclass

from sqlmodel import Session

from app.context import UserContext
from app.tools.hr_tools import (
    get_attendance_summary,
    get_headcount,
    get_late_comers,
    get_leave_summary,
    get_my_leave_balance,
    get_payroll_summary,
    search_employees,
)

ALL_TOOLS = [
    get_headcount,
    get_attendance_summary,
    get_late_comers,
    get_leave_summary,
    get_payroll_summary,
    search_employees,
    get_my_leave_balance,
]

# Employees only ever get their own leave balance tool.
EMPLOYEE_TOOL_NAMES = {"get_my_leave_balance"}


@dataclass
class ToolDeps:
    """What every tool receives via RunContextWrapper.context.

    ctx is the verified user (role, ids) from the JWT; session is the request's
    database session. Tools call services with these — never SQL directly.
    """

    ctx: UserContext
    session: Session


def tools_for_role(role: str) -> list:
    """The tool allowlist for a role. Admin and HR get everything."""
    if role == "employee":
        return [tool for tool in ALL_TOOLS if tool.name in EMPLOYEE_TOOL_NAMES]
    return list(ALL_TOOLS)
