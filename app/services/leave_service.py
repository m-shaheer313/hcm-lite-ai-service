"""Leave services: apply with rule checks, balances, HR approve/reject."""

from datetime import UTC, date, datetime

from sqlmodel import Session

from app.context import UserContext
from app.errors import ForbiddenError, NotFoundError, RuleViolationError
from app.models import LeaveRequest
from app.repositories import employees as emp_repo
from app.repositories import leaves as leave_repo
from app.services import rules


def karachi_today() -> date:
    """Today in the office timezone — never the server's UTC date."""
    return rules.today_in_karachi(datetime.now(UTC))


def _require_employee_id(ctx: UserContext) -> int:
    if ctx.employee_id is None:
        raise ForbiddenError("Only users linked to an employee record can use leave.")
    return ctx.employee_id


def used_days(session: Session, employee_id: int, type_code: str, *, year: int) -> int:
    """Approved working days of one leave type this year."""
    used = 0
    for req in leave_repo.approved_for_year(session, employee_id, year):
        lt = leave_repo.get_type_by_code(session, type_code)
        if lt and req.leave_type_id == lt.id:
            used += req.working_days
    return used


def balances(session: Session, ctx: UserContext) -> list[dict]:
    """My remaining balance per leave type (quota minus approved days this year)."""
    employee_id = _require_employee_id(ctx)
    year = karachi_today().year
    result = []
    for lt in leave_repo.all_types(session):
        used = 0
        for req in leave_repo.approved_for_year(session, employee_id, year):
            if req.leave_type_id == lt.id:
                used += req.working_days
        remaining = None if lt.quota_days is None else max(lt.quota_days - used, 0)
        result.append(
            {
                "code": lt.code,
                "name": lt.name,
                "quota_days": lt.quota_days,
                "used_days": used,
                "remaining_days": remaining,  # None = unlimited
            }
        )
    return result


def _validate_and_count(
    session: Session,
    employee_id: int,
    *,
    leave_type_code: str,
    start: date,
    end: date,
    today: date,
    exclude_id: int | None = None,
) -> tuple[int, int]:
    """Shared rule checks for apply and approve. Returns (type_id, working_days).

    Raises RuleViolationError with a clear message on any broken rule.
    """
    lt = leave_repo.get_type_by_code(session, leave_type_code)
    if lt is None:
        raise RuleViolationError(f"Unknown leave type '{leave_type_code}'.")

    if end < start:
        raise RuleViolationError("End date cannot be before the start date.")
    if start < today:
        raise RuleViolationError("Leave cannot start in the past.")

    holidays = leave_repo.holiday_dates(session, start, end)
    working_days = rules.count_working_days(start, end, holidays)
    if working_days == 0:
        raise RuleViolationError("The chosen dates contain no working day.")

    if leave_repo.overlapping(session, employee_id, start, end, exclude_id=exclude_id):
        raise RuleViolationError("These dates overlap another pending or approved leave.")

    if lt.quota_days is not None:
        year = start.year
        used = used_days(session, employee_id, lt.code, year=year)
        if used + working_days > lt.quota_days:
            remaining = max(lt.quota_days - used, 0)
            raise RuleViolationError(
                f"Not enough {lt.name.lower()} balance: {remaining} day(s) left, "
                f"{working_days} requested."
            )
    return lt.id, working_days


def apply(
    session: Session,
    ctx: UserContext,
    *,
    leave_type_code: str,
    start: date,
    end: date,
    reason: str,
    today: date | None = None,
) -> LeaveRequest:
    """Employee applies for leave. Overlap or over-balance is a 422."""
    employee_id = _require_employee_id(ctx)
    today = today or karachi_today()

    type_id, working_days = _validate_and_count(
        session,
        employee_id,
        leave_type_code=leave_type_code,
        start=start,
        end=end,
        today=today,
    )
    return leave_repo.create(
        session,
        LeaveRequest(
            employee_id=employee_id,
            leave_type_id=type_id,
            start_day=start,
            end_day=end,
            working_days=working_days,
            reason=reason,
        ),
    )


def pending_list(session: Session, ctx: UserContext) -> list[dict]:
    """HR/Admin approval inbox with names and leave types."""
    if ctx.role not in ("admin", "hr"):
        raise ForbiddenError("Only Admin or HR can see the approval inbox.")
    types = {lt.id: lt for lt in leave_repo.all_types(session)}
    employees = {e.id: e for e in emp_repo.active_all(session)}
    result = []
    for req in leave_repo.pending_all(session):
        emp = employees.get(req.employee_id)
        result.append(
            {
                "id": req.id,
                "employee_code": emp.code if emp else "?",
                "employee_name": emp.full_name if emp else "Unknown",
                "leave_type": types[req.leave_type_id].name if req.leave_type_id in types else "?",
                "start_day": req.start_day,
                "end_day": req.end_day,
                "working_days": req.working_days,
                "reason": req.reason,
            }
        )
    return result


def _decide(
    session: Session,
    ctx: UserContext,
    request_id: int,
    *,
    approve: bool,
    comment: str | None,
    today: date | None = None,
) -> LeaveRequest:
    if ctx.role not in ("admin", "hr"):
        raise ForbiddenError("Only Admin or HR can decide leave requests.")
    req = leave_repo.get_request(session, request_id)
    if req is None:
        raise NotFoundError("Leave request not found.")
    if req.status != "pending":
        raise RuleViolationError(f"This request is already {req.status}.")

    if approve:
        lt = next((t for t in leave_repo.all_types(session) if t.id == req.leave_type_id), None)
        if lt is None:
            raise NotFoundError("Leave type no longer exists.")
        # Re-check rules: other leaves may have been approved since this was
        # filed. The request itself is excluded from the overlap check.
        today = today or karachi_today()
        if req.end_day >= today:  # a fully past request is approved as history
            type_id, working_days = _validate_and_count(
                session,
                req.employee_id,
                leave_type_code=lt.code,
                start=req.start_day,
                end=req.end_day,
                today=min(today, req.start_day),
                exclude_id=req.id,
            )
            if type_id != lt.id:
                raise NotFoundError("Leave type no longer exists.")
            req.working_days = working_days

    req.status = "approved" if approve else "rejected"
    req.decided_by_user_id = ctx.user_id
    req.decision_comment = comment
    session.add(req)
    session.commit()
    session.refresh(req)
    return req


def approve(
    session: Session, ctx: UserContext, request_id: int, *, comment: str | None = None
) -> LeaveRequest:
    """HR/Admin approves. Balance and overlap are re-checked first."""
    return _decide(session, ctx, request_id, approve=True, comment=comment)


def reject(
    session: Session, ctx: UserContext, request_id: int, *, comment: str | None = None
) -> LeaveRequest:
    """HR/Admin rejects. Rejected leave does not consume balance."""
    return _decide(session, ctx, request_id, approve=False, comment=comment)
