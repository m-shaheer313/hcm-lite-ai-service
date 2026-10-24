"""Pydantic models for requests and responses. Strict: extra fields are rejected."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.auth_service import validate_new_password


class StrictModel(BaseModel):
    """Base model: unknown fields are an error, not a silent ignore."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(BaseModel):
    """Body of GET /health."""

    status: str


class SetupRequest(StrictModel):
    """POST /setup — first run only. Fields optional: env vars are the fallback."""

    email: str | None = None
    password: str | None = None
    company_name: str | None = None


class LoginRequest(StrictModel):
    """POST /auth/login."""

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=254)


class LoginResponse(BaseModel):
    """Token plus the flags the UI needs right after login."""

    access_token: str
    role: str
    must_change_password: bool


class ChangePasswordRequest(StrictModel):
    """POST /auth/change-password."""

    old_password: str = Field(min_length=1, max_length=254)
    new_password: str = Field(min_length=1, max_length=254)

    def model_post_init(self, __context: object, /) -> None:
        validate_new_password(self.new_password)


class OkResponse(BaseModel):
    """Simple success body."""

    ok: bool = True


class MeResponse(BaseModel):
    """GET /me."""

    email: str
    role: str
    employee_id: int | None
    must_change_password: bool
    company_name: str


# ---- Departments ----


class DepartmentCreate(StrictModel):
    """POST /departments (Admin)."""

    name: str = Field(min_length=1, max_length=80)


class DepartmentOut(BaseModel):
    id: int
    name: str


# ---- Employees ----


class EmployeeCreate(StrictModel):
    """POST /employees (Admin/HR). basic_salary_minor is monthly basic in paisa."""

    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=1, max_length=120)
    department_id: int | None = None
    designation: str = Field(default="", max_length=80)
    join_date: date
    basic_salary_minor: int = Field(gt=0)


class EmployeeOut(BaseModel):
    """Directory view. Salary is deliberately not included."""

    id: int
    code: str
    full_name: str
    department_id: int | None
    designation: str
    join_date: date

    @classmethod
    def from_employee(cls, employee) -> "EmployeeOut":
        """Build from a SQLModel row (model_dump is unreliable on table rows)."""
        return cls(
            id=employee.id,
            code=employee.code,
            full_name=employee.full_name,
            department_id=employee.department_id,
            designation=employee.designation,
            join_date=employee.join_date,
        )


class EmployeeCreated(BaseModel):
    """Response of registration: employee + the one-time temporary password."""

    employee: EmployeeOut
    temporary_password: str


# ---- Attendance ----


class AttendanceOut(BaseModel):
    id: int
    day: date
    check_in_at: str | None
    check_out_at: str | None
    status: str


class BoardEntry(BaseModel):
    """One row of the HR daily board."""

    employee_id: int
    code: str
    full_name: str
    status: str


# ---- Leave ----


class LeaveApplyRequest(StrictModel):
    """POST /leaves (Employee)."""

    leave_type_code: str = Field(min_length=3, max_length=20)
    start_day: date
    end_day: date
    reason: str = Field(min_length=1, max_length=500)


class LeaveOut(BaseModel):
    id: int
    employee_id: int
    leave_type_id: int
    start_day: date
    end_day: date
    working_days: int
    reason: str
    status: str

    @classmethod
    def from_request(cls, request) -> "LeaveOut":
        """Build from a SQLModel row."""
        return cls(
            id=request.id,
            employee_id=request.employee_id,
            leave_type_id=request.leave_type_id,
            start_day=request.start_day,
            end_day=request.end_day,
            working_days=request.working_days,
            reason=request.reason,
            status=request.status,
        )


class BalanceOut(BaseModel):
    code: str
    name: str
    quota_days: int | None
    used_days: int
    remaining_days: int | None


class PendingOut(BaseModel):
    id: int
    employee_code: str
    employee_name: str
    leave_type: str
    start_day: date
    end_day: date
    working_days: int
    reason: str


class DecisionRequest(StrictModel):
    """Body of approve/reject. Comment is optional."""

    comment: str | None = Field(default=None, max_length=500)


# ---- Payroll ----


class PayrollRunCreate(StrictModel):
    """POST /payroll/runs (Admin/HR). Month looks like 'YYYY-MM'."""

    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class PayrollRunOut(BaseModel):
    id: int
    month: str
    status: str


class PayrollSummaryOut(BaseModel):
    month: str
    status: str
    employee_count: int
    gross_minor: int
    deductions_minor: int
    tax_minor: int
    net_minor: int


# ---- KPIs ----


class KpiResponse(BaseModel):
    """GET /analytics/kpis — shape is role-scoped (company or personal)."""

    scope: str
    from_day: date
    to_day: date
    kpis: dict[str, Any]


# ---- AI chat ----


class ChatRequest(StrictModel):
    """POST /ai/chat."""

    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    """Every AI answer carries the AI-generated label."""

    label: str
    answer: str
    tools_used: list[str]


class LeaveDraft(BaseModel):
    """A pre-fill for the leave form. Nothing is saved by the AI."""

    leave_type: str
    start: date
    end: date
    reason: str


class SmartLeaveResponse(BaseModel):
    """fallback=true means: show the normal leave form instead."""

    label: str
    fallback: bool
    draft: LeaveDraft | None


class SummaryResponse(BaseModel):
    """3 to 5 bullets. fallback=true means code-built bullets were used."""

    label: str
    summary: list[str]
    fallback: bool
