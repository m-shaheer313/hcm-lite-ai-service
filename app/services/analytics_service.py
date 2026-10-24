"""Analytics/KPI service. Role-scoped: company numbers for Admin/HR,
personal numbers for Employee. The AI dashboard summary will reuse this."""

from datetime import date

from sqlmodel import Session

from app.context import UserContext
from app.errors import ForbiddenError
from app.repositories import attendance as att_repo
from app.repositories import employees as emp_repo
from app.repositories import leaves as leave_repo


def _month_range(day: date) -> tuple[date, date]:
    """First and last day of day's month."""
    import calendar

    return (
        date(day.year, day.month, 1),
        date(day.year, day.month, calendar.monthrange(day.year, day.month)[1]),
    )


def company_kpis(
    session: Session,
    ctx: UserContext,
    *,
    start: date,
    end: date,
    department_id: int | None = None,
) -> dict:
    """Company KPIs for Admin/HR: headcount, attendance rate, late, absent, leave."""
    if ctx.role not in ("admin", "hr"):
        raise ForbiddenError("Only Admin or HR can see company KPIs.")

    employees = emp_repo.active_all(session)
    if department_id is not None:
        employees = [e for e in employees if e.department_id == department_id]
    headcount = len(employees)

    holidays = leave_repo.holiday_dates(session, start, end)
    from app.services import rules

    working_days = rules.count_working_days(start, end, holidays)
    expected = working_days * headcount

    records = att_repo.for_range_all(session, start, end)
    by_emp = {e.id for e in employees}
    attended = sum(1 for r in records if r.employee_id in by_emp and r.check_in_at)
    late = sum(1 for r in records if r.employee_id in by_emp and r.status == "late")
    half = sum(1 for r in records if r.employee_id in by_emp and r.status == "half_day")

    approved_leave = [
        lr
        for lr in leave_repo.approved_between_all(session, start, end)
        if lr.employee_id in by_emp
    ]
    on_leave = sum(1 for e in employees if any(lr.employee_id == e.id for lr in approved_leave))
    attendance_rate = round(attended / expected * 100, 1) if expected else 0.0

    return {
        "headcount": headcount,
        "working_days": working_days,
        "attendance_rate_pct": attendance_rate,
        "present_days": attended,
        "late_days": late,
        "half_days": half,
        "employees_on_leave": on_leave,
        "approved_leave_days": sum(lr.working_days for lr in approved_leave),
    }


def my_kpis(session: Session, ctx: UserContext, *, start: date, end: date) -> dict:
    """Personal KPIs for an Employee: my hours, late count, half days, leave left."""
    if ctx.employee_id is None:
        raise ForbiddenError("Only users linked to an employee record have personal KPIs.")
    records = att_repo.for_employee_between(session, ctx.employee_id, start, end)
    late = sum(1 for r in records if r.status == "late")
    half = sum(1 for r in records if r.status == "half_day")

    from app.services import leave_service

    balances = leave_service.balances(session, ctx)
    return {
        "days_checked_in": len(records),
        "late_days": late,
        "half_days": half,
        "leave_balances": {
            b["code"]: b["remaining_days"] if b["remaining_days"] is not None else "unlimited"
            for b in balances
        },
    }


def kpis(
    session: Session,
    ctx: UserContext,
    *,
    start: date | None = None,
    end: date | None = None,
    department_id: int | None = None,
) -> dict:
    """Entry point used by the route and later by the AI tools."""
    if start is None or end is None:
        start, end = _month_range(date.today())
    if ctx.role in ("admin", "hr"):
        data = company_kpis(session, ctx, start=start, end=end, department_id=department_id)
        scope = "company"
    else:
        data = my_kpis(session, ctx, start=start, end=end)
        scope = "personal"
    return {"scope": scope, "from_day": start, "to_day": end, "kpis": data}
