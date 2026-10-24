"""Database access for leave requests and types. Parameterized queries only."""

from datetime import date

from sqlmodel import Session, select

from app.models import Holiday, LeaveRequest, LeaveType


def get_type_by_code(session: Session, code: str) -> LeaveType | None:
    return session.exec(select(LeaveType).where(LeaveType.code == code)).first()


def all_types(session: Session) -> list[LeaveType]:
    return list(session.exec(select(LeaveType).order_by(LeaveType.id)))


def holiday_dates(session: Session, start: date, end: date) -> set[date]:
    rows = session.exec(select(Holiday.day).where(Holiday.day >= start, Holiday.day <= end)).all()
    return set(rows)


def get_request(session: Session, request_id: int) -> LeaveRequest | None:
    return session.get(LeaveRequest, request_id)


def overlapping(
    session: Session,
    employee_id: int,
    start: date,
    end: date,
    *,
    exclude_id: int | None = None,
) -> list[LeaveRequest]:
    """Pending or approved requests that touch [start, end] for this employee.

    exclude_id skips one request (used when re-validating a request on approve).
    """
    query = select(LeaveRequest).where(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status.in_(["pending", "approved"]),
        LeaveRequest.start_day <= end,
        LeaveRequest.end_day >= start,
    )
    if exclude_id is not None:
        query = query.where(LeaveRequest.id != exclude_id)
    return list(session.exec(query))


def approved_between(
    session: Session, employee_id: int, start: date, end: date
) -> list[LeaveRequest]:
    return list(
        session.exec(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == "approved",
                LeaveRequest.start_day <= end,
                LeaveRequest.end_day >= start,
            )
        )
    )


def pending_all(session: Session) -> list[LeaveRequest]:
    return list(
        session.exec(
            select(LeaveRequest)
            .where(LeaveRequest.status == "pending")
            .order_by(LeaveRequest.created_at)
        )
    )


def approved_between_all(session: Session, start: date, end: date) -> list[LeaveRequest]:
    return list(
        session.exec(
            select(LeaveRequest).where(
                LeaveRequest.status == "approved",
                LeaveRequest.start_day <= end,
                LeaveRequest.end_day >= start,
            )
        )
    )


def approved_for_year(session: Session, employee_id: int, year: int) -> list[LeaveRequest]:
    jan1 = date(year, 1, 1)
    dec31 = date(year, 12, 31)
    return list(
        session.exec(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == "approved",
                LeaveRequest.start_day <= dec31,
                LeaveRequest.end_day >= jan1,
            )
        )
    )


def create(session: Session, request: LeaveRequest) -> LeaveRequest:
    session.add(request)
    session.commit()
    session.refresh(request)
    return request
