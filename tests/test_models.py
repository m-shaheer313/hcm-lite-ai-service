"""Tests for the database models: happy path and the DB-level constraints."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import (
    Attendance,
    Department,
    Employee,
    LeaveRequest,
    LeaveType,
    PayrollRun,
    Payslip,
    User,
)


def _employee(session: Session, code: str = "EMP-001") -> Employee:
    dept = Department(name="Engineering")
    session.add(dept)
    session.flush()
    emp = Employee(
        code=code,
        full_name="Ali Khan",
        department_id=dept.id,
        join_date=date(2026, 1, 5),
        basic_salary_minor=10_000_000,  # PKR 100,000.00 in paisa
    )
    session.add(emp)
    session.commit()
    session.refresh(emp)
    return emp


def test_employee_roundtrip_keeps_money_as_integer(session: Session) -> None:
    emp = _employee(session)

    loaded = session.exec(select(Employee).where(Employee.code == "EMP-001")).one()
    assert loaded.full_name == "Ali Khan"
    assert loaded.id == emp.id
    assert isinstance(loaded.basic_salary_minor, int)


def test_second_attendance_same_day_is_rejected_by_db(session: Session) -> None:
    """Unique (employee_id, day) backs the 409 rule for a second check-in."""
    emp = _employee(session)
    session.add(Attendance(employee_id=emp.id, day=date(2026, 10, 24), status="present"))
    session.commit()

    session.add(Attendance(employee_id=emp.id, day=date(2026, 10, 24), status="late"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_employee_code_is_rejected(session: Session) -> None:
    _employee(session, code="EMP-001")

    session.add(
        Employee(
            code="EMP-001",
            full_name="Other Person",
            join_date=date(2026, 2, 1),
            basic_salary_minor=1,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_user_email_is_rejected(session: Session) -> None:
    session.add(User(email="a@x.com", password_hash="h", role="admin"))
    session.commit()

    session.add(User(email="a@x.com", password_hash="h", role="hr"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_leave_request_with_reversed_dates_is_rejected(session: Session) -> None:
    """CheckConstraint: start_day <= end_day, in the DB, not only in code."""
    emp = _employee(session)
    lt = LeaveType(code="casual", name="Casual", quota_days=10)
    session.add(lt)
    session.commit()

    session.add(
        LeaveRequest(
            employee_id=emp.id,
            leave_type_id=lt.id,
            start_day=date(2026, 10, 20),
            end_day=date(2026, 10, 18),
            working_days=1,
            reason="test",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_only_one_payroll_run_per_month(session: Session) -> None:
    admin = User(email="admin@x.com", password_hash="h", role="admin")
    session.add(admin)
    session.commit()

    session.add(PayrollRun(month="2026-10", created_by_user_id=admin.id))
    session.commit()

    session.add(PayrollRun(month="2026-10", created_by_user_id=admin.id))
    with pytest.raises(IntegrityError):
        session.commit()


def test_payslip_is_tied_to_one_employee_per_run(session: Session) -> None:
    admin = User(email="admin@x.com", password_hash="h", role="admin")
    emp = _employee(session)
    session.add(admin)
    session.commit()
    run = PayrollRun(month="2026-10", created_by_user_id=admin.id)
    session.add(run)
    session.commit()

    def slip() -> Payslip:
        return Payslip(
            payroll_run_id=run.id,
            employee_id=emp.id,
            working_days=22,
            paid_days=22,
            absent_days=0,
            unpaid_days=0,
            half_days=0,
            basic_minor=10_000_000,
            gross_minor=15_000_000,
            per_day_minor=681_818,
            deductions_minor=0,
            tax_minor=0,
            net_minor=15_000_000,
        )

    session.add(slip())
    session.commit()
    session.add(slip())
    with pytest.raises(IntegrityError):
        session.commit()
