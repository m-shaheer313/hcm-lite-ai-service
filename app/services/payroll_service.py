"""Payroll services: monthly draft, finalize lock, summary, my payslip."""

import calendar
from datetime import date

from sqlmodel import Session

from app.context import UserContext
from app.errors import ConflictError, ForbiddenError, NotFoundError, RuleViolationError
from app.models import PayrollRun, Payslip
from app.repositories import attendance as att_repo
from app.repositories import employees as emp_repo
from app.repositories import leaves as leave_repo
from app.repositories import payroll as pay_repo
from app.services import rules


def _parse_month(month: str) -> tuple[int, int]:
    """'YYYY-MM' -> (year, month)."""
    try:
        year, mon = month.split("-")
        if not (1 <= int(mon) <= 12):
            raise ValueError
        return int(year), int(mon)
    except ValueError:
        raise RuleViolationError("Month must look like 'YYYY-MM', for example '2026-10'.") from None


def create_run(session: Session, ctx: UserContext, *, month: str, company_name: str) -> PayrollRun:
    """HR/Admin creates the monthly draft. One run per month (409 on a second)."""
    if ctx.role not in ("admin", "hr"):
        raise ForbiddenError("Only Admin or HR can create a payroll run.")
    _parse_month(month)
    if pay_repo.get_run_by_month(session, month):
        raise ConflictError(f"A payroll run for {month} already exists.")

    run = pay_repo.create_run(session, PayrollRun(month=month, created_by_user_id=ctx.user_id))
    slips = [_payslip_for(session, run.id, emp, month) for emp in emp_repo.active_all(session)]
    pay_repo.add_payslips(session, [s for s in slips if s is not None])
    return run


def _payslip_for(session: Session, run_id: int, employee, month: str) -> Payslip | None:
    """Compute one employee's line. Joiners are prorated; future joiners skipped."""
    year, mon = _parse_month(month)
    first, last = date(year, mon, 1), date(year, mon, calendar.monthrange(year, mon)[1])
    window_start = max(first, employee.join_date)
    if window_start > last:
        return None  # joined after this month

    holidays = leave_repo.holiday_dates(session, first, last)
    working_days = rules.count_working_days(window_start, last, holidays)

    records = att_repo.for_employee_between(session, employee.id, window_start, last)
    attended = sum(1 for r in records if r.check_in_at is not None)
    half_days = sum(1 for r in records if r.status == "half_day")

    approved = leave_repo.approved_between(session, employee.id, window_start, last)
    types = {t.id: t for t in leave_repo.all_types(session)}
    paid_leave = sum(r.working_days for r in approved if types[r.leave_type_id].code != "unpaid")
    unpaid_leave = sum(r.working_days for r in approved if types[r.leave_type_id].code == "unpaid")

    line = rules.calc_payslip(
        basic_minor=employee.basic_salary_minor,
        working_days=working_days,
        attended_days=attended,
        half_days=half_days,
        paid_leave_days=paid_leave,
        unpaid_leave_days=unpaid_leave,
    )
    return Payslip(payroll_run_id=run_id, employee_id=employee.id, **line)


def finalize(session: Session, ctx: UserContext, run_id: int) -> PayrollRun:
    """Admin locks a draft run. A finalized run can never change (409 on retry)."""
    if ctx.role != "admin":
        raise ForbiddenError("Only Admin can finalize payroll.")
    run = pay_repo.get_run(session, run_id)
    if run is None:
        raise NotFoundError("Payroll run not found.")
    if run.status == "finalized":
        raise ConflictError("This payroll run is already finalized and locked.")
    run.status = "finalized"
    run.finalized_by_user_id = ctx.user_id
    from app.models import utc_now

    run.finalized_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def summary(session: Session, ctx: UserContext, *, month: str) -> dict:
    """Totals for Admin/HR: employees, gross, deductions, tax, net."""
    if ctx.role not in ("admin", "hr"):
        raise ForbiddenError("Only Admin or HR can see the payroll summary.")
    _parse_month(month)
    run = pay_repo.get_run_by_month(session, month)
    if run is None:
        raise NotFoundError(f"No payroll run for {month}.")
    slips = pay_repo.payslips_for_run(session, run.id)
    return {
        "month": month,
        "status": run.status,
        "employee_count": len(slips),
        "gross_minor": sum(s.gross_minor for s in slips),
        "deductions_minor": sum(s.deductions_minor for s in slips),
        "tax_minor": sum(s.tax_minor for s in slips),
        "net_minor": sum(s.net_minor for s in slips),
    }


def my_payslip(session: Session, ctx: UserContext, *, month: str) -> Payslip:
    """My own payslip line. Employees can only ever read their own."""
    if ctx.employee_id is None:
        raise ForbiddenError("Only users linked to an employee record have payslips.")
    _parse_month(month)
    run = pay_repo.get_run_by_month(session, month)
    if run is None:
        raise NotFoundError(f"No payroll run for {month}.")
    slip = pay_repo.payslip_for_employee(session, run.id, ctx.employee_id)
    if slip is None:
        raise NotFoundError("No payslip for you in this month.")
    return slip


def payslip_html(session: Session, ctx: UserContext, *, month: str) -> str:
    """My payslip as a simple printable HTML page (browser Print -> PDF)."""
    slip = my_payslip(session, ctx, month=month)
    employee = emp_repo.get_by_id(session, ctx.employee_id)
    name = employee.full_name if employee else "?"

    def pkr(minor: int) -> str:
        return f"PKR {minor / 100:,.2f}"

    rows = [
        ("Working days", str(slip.working_days)),
        ("Paid days", str(slip.paid_days)),
        ("Absent days", str(slip.absent_days)),
        ("Unpaid leave days", str(slip.unpaid_days)),
        ("Half days", str(slip.half_days)),
        ("Basic", pkr(slip.basic_minor)),
        ("Gross (1.5 x basic)", pkr(slip.gross_minor)),
        ("Per day", pkr(slip.per_day_minor)),
        ("Deductions", f"-{pkr(slip.deductions_minor)}"),
        ("Tax", f"-{pkr(slip.tax_minor)}"),
    ]
    body = "".join(
        f"<tr><td>{label}</td><td style='text-align:right'>{value}</td></tr>"
        for label, value in rows
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Payslip {month}</title>
<style>
  body {{ font-family: sans-serif; margin: 40px auto; max-width: 480px; }}
  h1 {{ font-size: 20px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  td, th {{ padding: 6px 4px; border-bottom: 1px solid #ddd; font-size: 14px; }}
  .net {{ font-weight: bold; font-size: 16px; }}
  @media print {{ .no-print {{ display: none; }} }}
</style></head>
<body>
<h1>Payslip — {month}</h1>
<p>{name}</p>
<table>{body}</table>
<table style="margin-top:12px"><tr class="net"><td>Net pay</td>
<td style="text-align:right">{pkr(slip.net_minor)}</td></tr></table>
<p class="no-print"><button onclick="window.print()">Print / Save as PDF</button></p>
</body></html>"""
