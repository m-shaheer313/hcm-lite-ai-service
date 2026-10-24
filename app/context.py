"""UserContext: the verified user that every service call receives.

Routes build it from the JWT + database. AI tools (later tasks) receive the
SAME object, so the AI can never know more than the logged-in user.
"""

from dataclasses import dataclass

from app.errors import ForbiddenError


@dataclass
class UserContext:
    """Who is calling, verified server-side. Never trust a client copy."""

    user_id: int
    role: str  # 'admin' | 'hr' | 'employee'
    employee_id: int | None  # None for admin/hr without an employee record
    must_change_password: bool = False


def assert_can_view_employee(ctx: UserContext, employee_id: int) -> None:
    """Data-scope rule: an employee may only touch rows with their own employee_id."""
    if ctx.role == "employee" and ctx.employee_id != employee_id:
        raise ForbiddenError("You can only access your own records.")
