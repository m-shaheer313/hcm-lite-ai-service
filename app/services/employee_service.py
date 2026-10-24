"""Employee and department services: onboarding with a temp password, search."""

import secrets

from sqlmodel import Session

from app.context import UserContext
from app.errors import ConflictError, NotFoundError
from app.models import Department, Employee
from app.repositories import departments as dept_repo
from app.repositories import employees as emp_repo
from app.repositories import users as user_repo
from app.security import hash_password

EMPLOYEE_CODE_PREFIX = "EMP"


def create_department(session: Session, ctx: UserContext, *, name: str) -> Department:
    """Admin creates a department. Duplicate names are rejected."""
    if ctx.role != "admin":
        from app.errors import ForbiddenError

        raise ForbiddenError("Only Admin can create departments.")
    if dept_repo.get_by_name(session, name):
        raise ConflictError(f"Department '{name}' already exists.")
    return dept_repo.create(session, name)


def list_departments(session: Session) -> list[Department]:
    """Any logged-in user can see departments."""
    return dept_repo.get_all(session)


def register_employee(
    session: Session,
    ctx: UserContext,
    *,
    email: str,
    full_name: str,
    department_id: int | None,
    designation: str,
    join_date,
    basic_salary_minor: int,
) -> tuple[Employee, str]:
    """HR/Admin registers an employee and creates their login.

    Returns the employee and the one-time temporary password (shown once).
    """
    if ctx.role not in ("admin", "hr"):
        from app.errors import ForbiddenError

        raise ForbiddenError("Only Admin or HR can register employees.")
    if "@" not in email:
        from app.errors import RuleViolationError

        raise RuleViolationError("Email must be a valid email address.")
    if basic_salary_minor <= 0:
        from app.errors import RuleViolationError

        raise RuleViolationError("Basic salary must be greater than zero.")
    if user_repo.get_by_email(session, email):
        raise ConflictError("A login with this email already exists.")
    if department_id is not None and not dept_repo.get_all(session):
        pass  # departments list empty is fine; validity checked below
    if department_id is not None and session.get(Department, department_id) is None:
        raise NotFoundError("Department not found.")

    employee = emp_repo.create(
        session,
        Employee(
            code="TMP",  # replaced with the real id-based code right after insert
            full_name=full_name,
            department_id=department_id,
            designation=designation,
            join_date=join_date,
            basic_salary_minor=basic_salary_minor,
        ),
    )
    employee.code = f"{EMPLOYEE_CODE_PREFIX}-{employee.id:03d}"
    session.add(employee)
    session.commit()
    session.refresh(employee)

    temp_password = secrets.token_urlsafe(8)
    user_repo.create_user(
        session,
        email=email,
        password_hash=hash_password(temp_password),
        role="employee",
        employee_id=employee.id,
        must_change_password=True,
    )
    return employee, temp_password


def search_employees(
    session: Session,
    ctx: UserContext,
    *,
    text: str = "",
    department_id: int | None = None,
) -> list[Employee]:
    """Directory search. Admin and HR only; employees use /me."""
    if ctx.role not in ("admin", "hr"):
        from app.errors import ForbiddenError

        raise ForbiddenError("Only Admin or HR can search the directory.")
    return emp_repo.search(session, text=text, department_id=department_id)
