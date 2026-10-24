"""Shared test helpers: build users/employees quickly (test data only)."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Employee, LeaveType, User
from app.security import hash_password
from tests.conftest import TEST_PASSWORD


def setup_company(client: TestClient) -> str:
    """Run /setup once and return an admin token."""
    response = client.post(
        "/setup",
        json={"email": "admin@co.com", "password": TEST_PASSWORD, "company_name": "Co"},
    )
    return response.json()["access_token"]


def add_user(session: Session, email: str, role: str, *, employee_id: int | None = None) -> User:
    user = User(
        email=email,
        password_hash=hash_password(TEST_PASSWORD),
        role=role,
        employee_id=employee_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def add_employee(
    session: Session,
    *,
    code: str = "EMP-001",
    name: str = "Ali Khan",
    department_id: int | None = None,
    join_date: date | None = None,
    basic_salary_minor: int = 10_000_000,
) -> Employee:
    employee = Employee(
        code=code,
        full_name=name,
        department_id=department_id,
        join_date=join_date or date(2026, 1, 5),
        basic_salary_minor=basic_salary_minor,
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return employee


def ensure_leave_types(session: Session) -> None:
    """Insert the four default leave types (setup usually does this)."""
    count = session.exec(select(func.count()).select_from(LeaveType)).one()
    if count == 0:
        session.add_all(
            [
                LeaveType(code="annual", name="Annual", quota_days=14),
                LeaveType(code="sick", name="Sick", quota_days=8),
                LeaveType(code="casual", name="Casual", quota_days=10),
                LeaveType(code="unpaid", name="Unpaid", quota_days=None),
            ]
        )
        session.commit()


def token_for(client: TestClient, email: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    return response.json()["access_token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
