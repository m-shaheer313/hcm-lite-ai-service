"""Department and employee routes: HTTP only."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.context import UserContext
from app.deps import get_db, require_roles
from app.schemas import (
    DepartmentCreate,
    DepartmentOut,
    EmployeeCreate,
    EmployeeCreated,
    EmployeeOut,
)
from app.services import employee_service

router = APIRouter(tags=["org"])

DbSession = Annotated[Session, Depends(get_db)]
AnyRole = Annotated[UserContext, Depends(require_roles("admin", "hr", "employee"))]
HrOrAdmin = Annotated[UserContext, Depends(require_roles("admin", "hr"))]


@router.post("/departments", response_model=DepartmentOut)
def create_department(body: DepartmentCreate, ctx: HrOrAdmin, session: DbSession) -> DepartmentOut:
    """Admin creates a department (service also checks the role)."""
    dept = employee_service.create_department(session, ctx, name=body.name)
    return DepartmentOut(id=dept.id, name=dept.name)


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(ctx: AnyRole, session: DbSession) -> list[DepartmentOut]:
    """Any logged-in user can list departments."""
    return [DepartmentOut(id=d.id, name=d.name) for d in employee_service.list_departments(session)]


@router.post("/employees", response_model=EmployeeCreated)
def register_employee(body: EmployeeCreate, ctx: HrOrAdmin, session: DbSession) -> EmployeeCreated:
    """HR/Admin registers an employee; a login with a temp password is created."""
    employee, temp_password = employee_service.register_employee(
        session,
        ctx,
        email=body.email,
        full_name=body.full_name,
        department_id=body.department_id,
        designation=body.designation,
        join_date=body.join_date,
        basic_salary_minor=body.basic_salary_minor,
    )
    return EmployeeCreated(
        employee=EmployeeOut.from_employee(employee), temporary_password=temp_password
    )


@router.get("/employees", response_model=list[EmployeeOut])
def search_employees(
    ctx: HrOrAdmin,
    session: DbSession,
    search: str = "",
    department_id: int | None = None,
) -> list[EmployeeOut]:
    """Directory search (Admin/HR only). Salary is never in the response."""
    found = employee_service.search_employees(
        session, ctx, text=search, department_id=department_id
    )
    return [EmployeeOut.from_employee(e) for e in found]
