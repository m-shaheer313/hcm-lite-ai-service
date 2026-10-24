"""Attendance services: server-stamped check-in/out and the daily board."""

from datetime import UTC, date, datetime

from sqlmodel import Session

from app.context import UserContext
from app.errors import ConflictError, ForbiddenError, NotFoundError
from app.models import Attendance
from app.repositories import attendance as att_repo
from app.repositories import employees as emp_repo
from app.repositories import leaves as leave_repo
from app.services import rules


def _require_employee_id(ctx: UserContext) -> int:
    if ctx.employee_id is None:
        raise ForbiddenError("Only users linked to an employee record can use attendance.")
    return ctx.employee_id


def check_in(session: Session, ctx: UserContext, *, utc_now: datetime | None = None) -> Attendance:
    """Server stamps the time. One record per day (409 on a second check-in).

    Checking in after 09:15 Karachi time marks the day as late.
    """
    employee_id = _require_employee_id(ctx)
    now = utc_now or datetime.now(UTC)
    day = rules.today_in_karachi(now)

    if att_repo.get_by_day(session, employee_id, day):
        raise ConflictError("You have already checked in today. Only one record per day.")

    late = rules.is_late(rules.karachi_now(now))
    return att_repo.create(
        session,
        Attendance(
            employee_id=employee_id,
            day=day,
            check_in_at=now,
            status="late" if late else "present",
        ),
    )


def check_out(session: Session, ctx: UserContext, *, utc_now: datetime | None = None) -> Attendance:
    """Server stamps the check-out. Under 5 worked hours makes the day a half day."""
    employee_id = _require_employee_id(ctx)
    now = utc_now or datetime.now(UTC)
    day = rules.today_in_karachi(now)

    record = att_repo.get_by_day(session, employee_id, day)
    if record is None:
        raise NotFoundError("You have not checked in today.")
    if record.check_out_at is not None:
        raise ConflictError("You have already checked out today.")

    record.check_out_at = now
    if rules.is_half_day(rules.worked_hours(record.check_in_at, now)):
        record.status = "half_day"
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def my_records(session: Session, ctx: UserContext, *, start: date, end: date) -> list[Attendance]:
    """My own attendance records in a range."""
    return att_repo.for_employee_between(session, _require_employee_id(ctx), start, end)


def daily_board(session: Session, ctx: UserContext, *, day: date) -> list[dict]:
    """Admin/HR board for one day: present, late, half day, missing checkout, absent.

    Absent = active employee with no record and no approved leave that day.
    'missing_checkout' only appears for a day that is already over; an open
    record today simply means the person has not checked out yet.
    """
    if ctx.role not in ("admin", "hr"):
        raise ForbiddenError("Only Admin or HR can view the daily board.")

    records = {r.employee_id: r for r in att_repo.for_day_all(session, day)}
    on_leave = {lr.employee_id for lr in leave_repo.approved_between_all(session, day, day)}
    holidays = leave_repo.holiday_dates(session, day, day)
    today = rules.today_in_karachi(datetime.now(UTC))

    board = []
    for emp in emp_repo.active_all(session):
        record = records.get(emp.id)
        if record is not None:
            status = record.status
            if record.check_out_at is None and day < today and record.status in ("present", "late"):
                status = "missing_checkout"
        elif emp.id in on_leave:
            status = "on_leave"
        elif day in holidays:
            status = "holiday"
        elif not rules.is_working_day(day, holidays):
            status = "weekend"
        elif day < emp.join_date:
            status = "not_joined"
        else:
            status = "absent"
        board.append(
            {
                "employee_id": emp.id,
                "code": emp.code,
                "full_name": emp.full_name,
                "status": status,
            }
        )
    return board
