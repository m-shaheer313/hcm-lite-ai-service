"""Database tables (SQLModel). One model per table.

Rules kept here:
- Money is stored as INTEGER minor units (paisa; 1 PKR = 100 paisa). Never float.
- Every money column name ends with `_minor`.
- Uniqueness and date-range rules live in the DATABASE (constraints below),
  so the 409 / 422 rules cannot be broken even by a code bug.
- Types are Postgres-portable (deploy target is Neon); tests run on SQLite.
"""

from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """Current UTC time. The server always stamps times itself."""
    return datetime.now(UTC)


class Department(SQLModel, table=True):
    """A company department (e.g. Engineering)."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)


class User(SQLModel, table=True):
    """A login. role is 'admin', 'hr', or 'employee'."""

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str
    must_change_password: bool = False
    is_active: bool = True
    employee_id: int | None = Field(default=None, foreign_key="employee.id")
    created_at: datetime = Field(default_factory=utc_now)


class Employee(SQLModel, table=True):
    """A person employed by the company. Their login is a User row."""

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True)  # e.g. EMP-001
    full_name: str = Field(index=True)
    department_id: int | None = Field(default=None, foreign_key="department.id")
    designation: str = ""  # plain text on purpose; a designations table is not needed for the slice
    join_date: date
    basic_salary_minor: int  # monthly basic salary in paisa
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class Setting(SQLModel, table=True):
    """Company settings as key/value (office start, grace minutes, weekend days...)."""

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: str


class Holiday(SQLModel, table=True):
    """A public holiday (no attendance expected). The date must be unique."""

    id: int | None = Field(default=None, primary_key=True)
    day: date = Field(unique=True)
    name: str


class LeaveType(SQLModel, table=True):
    """A leave type with its yearly quota. quota_days None means unlimited (unpaid)."""

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True)  # annual | sick | casual | unpaid
    name: str
    quota_days: int | None = None  # None = unlimited


class LeaveRequest(SQLModel, table=True):
    """One leave application. status: pending | approved | rejected."""

    __table_args__ = (CheckConstraint("start_day <= end_day", name="ck_leave_date_order"),)

    id: int | None = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="employee.id", index=True)
    leave_type_id: int = Field(foreign_key="leavetype.id")
    start_day: date  # named start_day/end_day: "start" is special in SQLModel
    end_day: date
    working_days: int  # computed by the service when applying
    reason: str
    status: str = Field(default="pending", index=True)
    decided_by_user_id: int | None = Field(default=None, foreign_key="user.id")
    decision_comment: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Attendance(SQLModel, table=True):
    """One attendance record per employee per day — enforced by a DB unique constraint.

    status: present | late | half_day | missing_checkout (decided by the service).
    """

    __table_args__ = (UniqueConstraint("employee_id", "day", name="uq_attendance_employee_day"),)

    id: int | None = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="employee.id", index=True)
    day: date = Field(index=True)
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    status: str = Field(default="present")


class PayrollRun(SQLModel, table=True):
    """One monthly payroll. month is 'YYYY-MM' and unique (one run per month).

    status: draft | finalized. A finalized run is locked.
    """

    id: int | None = Field(default=None, primary_key=True)
    month: str = Field(unique=True, index=True)
    status: str = Field(default="draft")
    created_by_user_id: int = Field(foreign_key="user.id")
    finalized_by_user_id: int | None = Field(default=None, foreign_key="user.id")
    finalized_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Payslip(SQLModel, table=True):
    """One employee's pay inside a payroll run. All amounts are paisa (integers)."""

    __table_args__ = (
        UniqueConstraint("payroll_run_id", "employee_id", name="uq_payslip_run_employee"),
    )

    id: int | None = Field(default=None, primary_key=True)
    payroll_run_id: int = Field(foreign_key="payrollrun.id", index=True)
    employee_id: int = Field(foreign_key="employee.id", index=True)
    working_days: int
    paid_days: int
    absent_days: int
    unpaid_days: int
    half_days: int
    basic_minor: int
    gross_minor: int
    per_day_minor: int
    deductions_minor: int
    tax_minor: int
    net_minor: int


class AiLog(SQLModel, table=True):
    """One row per AI call. Also backs the rate limit (count by user + time window).

    Never store raw salaries, tokens, keys, or full prompts here.
    """

    __table_args__ = (Index("ix_ailog_user_created", "user_id", "created_at"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int
    role: str
    endpoint: str
    tool: str | None = None  # single tool name, or a comma-joined list
    status: str  # ok | error | timeout | refused | ...
    latency_ms: int
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
