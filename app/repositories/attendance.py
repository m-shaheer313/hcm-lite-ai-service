"""Database access for attendance. Parameterized queries only."""

from datetime import date

from sqlmodel import Session, select

from app.models import Attendance


def get_by_day(session: Session, employee_id: int, day: date) -> Attendance | None:
    return session.exec(
        select(Attendance).where(Attendance.employee_id == employee_id, Attendance.day == day)
    ).first()


def for_employee_between(
    session: Session, employee_id: int, start: date, end: date
) -> list[Attendance]:
    return list(
        session.exec(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.day >= start,
                Attendance.day <= end,
            )
        )
    )


def for_day_all(session: Session, day: date) -> list[Attendance]:
    return list(session.exec(select(Attendance).where(Attendance.day == day)))


def for_range_all(session: Session, start: date, end: date) -> list[Attendance]:
    return list(
        session.exec(select(Attendance).where(Attendance.day >= start, Attendance.day <= end))
    )


def create(session: Session, record: Attendance) -> Attendance:
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
