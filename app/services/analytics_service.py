"""Analytics/KPI service. Role-scoped: company numbers for Admin/HR,
personal numbers for Employee. The AI tools and the AI dashboard summary
reuse exactly these functions, so all three always show the same numbers."""

import calendar
from datetime import date

from sqlmodel import Session

from app.context import UserContext
from app.errors import ForbiddenError, NotFoundError
from app.repositories import attendance as att_repo
from app.repositories import departments as dept_repo
from app.repositories import employees as emp_repo
from app.repositories import leaves as leave_repo
from app.services import rules

MAX_LATE_COMERS = 10


def _month_range(day: date) -> tuple[date, date]:
    """First and last day of day's month."""
    return (
        date(day.year, day.month, 1),
        date(day.year, day.month, calendar.monthrange(day.year, day.month)[1]),
    )


def _require_company_role(ctx: UserContext) -> None:
    if ctx.role not in ("admin", "hr"):
        raise ForbiddenError("Only Admin or HR can see company numbers.")


def _department_id_by_name(session: Session, department_name: str | None) -> int | None:
    """Turn a department name into its id. Unknown names are a clear error."""
    if not department_name:
        return None
    dept = dept_repo.get_by_name(session, department_name)
    if dept is None:
        raise NotFoundError(f"Unknown department '{department_name}'.")
    return dept.id


def _scoped_employees(session: Session, department_name: str | None) -> list:
    """Active employees, optionally narrowed to one department by name."""
    department_id = _department_id_by_name(session, department_name)
    employees = emp_repo.active_all(session)
    if department_id is None:
        return employees
    return [e for e in employees if e.department_id == department_id]


def company_kpis(
    session: Session,
    ctx: UserContext,
    *,
    start: date,
    end: date,
    department_id: int | None = None,
) -> dict:
    """Company KPIs for Admin/HR: headcount, attendance rate, late, absent, leave."""
    _require_company_role(ctx)

    employees = emp_repo.active_all(session)
    if department_id is not None:
        employees = [e for e in employees if e.department_id == department_id]
    headcount = len(employees)

    holidays = leave_repo.holiday_dates(session, start, end)
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
        "absent_days": max(expected - attended, 0),
        "employees_on_leave": on_leave,
        "approved_leave_days": sum(lr.working_days for lr in approved_leave),
    }


def company_headcount(
    session: Session, ctx: UserContext, *, department_name: str | None = None
) -> dict:
    """Headcount of active employees, whole company or one department."""
    _require_company_role(ctx)
    employees = _scoped_employees(session, department_name)
    return {"headcount": len(employees), "department": department_name or "all departments"}


def company_attendance_summary(
    session: Session,
    ctx: UserContext,
    *,
    start: date,
    end: date,
    department_name: str | None = None,
) -> dict:
    """Attendance summary for a range. Same math as the dashboard KPIs."""
    _require_company_role(ctx)
    department_id = _department_id_by_name(session, department_name)
    kpis = company_kpis(session, ctx, start=start, end=end, department_id=department_id)
    return {
        "from_day": start,
        "to_day": end,
        "department": department_name or "all departments",
        "headcount": kpis["headcount"],
        "working_days": kpis["working_days"],
        "attendance_rate_pct": kpis["attendance_rate_pct"],
        "present_days": kpis["present_days"],
        "late_days": kpis["late_days"],
        "half_days": kpis["half_days"],
        "absent_days": kpis["absent_days"],
    }


def company_late_comers(
    session: Session,
    ctx: UserContext,
    *,
    start: date,
    end: date,
    limit: int = 5,
) -> dict:
    """Who came late most often in the range, most-late first."""
    _require_company_role(ctx)
    employees = {e.id: e for e in emp_repo.active_all(session)}
    counts: dict[int, int] = {}
    for record in att_repo.for_range_all(session, start, end):
        if record.employee_id in employees and record.status == "late":
            counts[record.employee_id] = counts.get(record.employee_id, 0) + 1
    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return {
        "from_day": start,
        "to_day": end,
        "late_comers": [
            {
                "code": employees[emp_id].code,
                "full_name": employees[emp_id].full_name,
                "late_days": count,
            }
            for emp_id, count in top[: min(limit, MAX_LATE_COMERS)]
            if count > 0
        ],
    }


def company_leave_summary(
    session: Session,
    ctx: UserContext,
    *,
    start: date,
    end: date,
    department_name: str | None = None,
) -> dict:
    """Approved leave days by type plus pending count for the range."""
    _require_company_role(ctx)
    employees = _scoped_employees(session, department_name)
    by_emp = {e.id for e in employees}
    types = {t.id: t for t in leave_repo.all_types(session)}

    by_type: dict[str, int] = {}
    employees_on_leave = set()
    for lr in leave_repo.approved_between_all(session, start, end):
        if lr.employee_id not in by_emp:
            continue
        type_name = types[lr.leave_type_id].name if lr.leave_type_id in types else "?"
        by_type[type_name] = by_type.get(type_name, 0) + lr.working_days
        employees_on_leave.add(lr.employee_id)

    pending = sum(1 for lr in leave_repo.pending_all(session) if lr.employee_id in by_emp)
    return {
        "from_day": start,
        "to_day": end,
        "department": department_name or "all departments",
        "approved_days_by_type": by_type,
        "approved_days_total": sum(by_type.values()),
        "employees_on_leave": len(employees_on_leave),
        "pending_requests": pending,
    }


def my_kpis(session: Session, ctx: UserContext, *, start: date, end: date) -> dict:
    """Personal KPIs for an Employee: my check-ins, late count, half days, leave left."""
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
    """Entry point used by the route and by the AI tools."""
    if start is None or end is None:
        start, end = _month_range(date.today())
    if ctx.role in ("admin", "hr"):
        data = company_kpis(session, ctx, start=start, end=end, department_id=department_id)
        scope = "company"
    else:
        data = my_kpis(session, ctx, start=start, end=end)
        scope = "personal"
    return {"scope": scope, "from_day": start, "to_day": end, "kpis": data}
