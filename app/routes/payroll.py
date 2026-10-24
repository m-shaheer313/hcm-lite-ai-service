"""Payroll routes: HTTP only. The payslip page returns printable HTML."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.context import UserContext
from app.deps import get_db, require_roles
from app.schemas import PayrollRunCreate, PayrollRunOut, PayrollSummaryOut
from app.services import payroll_service

router = APIRouter(tags=["payroll"])

DbSession = Annotated[Session, Depends(get_db)]
AnyRole = Annotated[UserContext, Depends(require_roles("admin", "hr", "employee"))]
HrOrAdmin = Annotated[UserContext, Depends(require_roles("admin", "hr"))]


@router.post("/payroll/runs", response_model=PayrollRunOut)
def create_run(body: PayrollRunCreate, ctx: HrOrAdmin, session: DbSession) -> PayrollRunOut:
    """Create the monthly draft (one run per month; 409 on a second)."""
    run = payroll_service.create_run(session, ctx, month=body.month, company_name="")
    return PayrollRunOut(id=run.id, month=run.month, status=run.status)


@router.post("/payroll/runs/{run_id}/finalize", response_model=PayrollRunOut)
def finalize(run_id: int, ctx: HrOrAdmin, session: DbSession) -> PayrollRunOut:
    """Admin only: lock the run (service re-checks the role)."""
    run = payroll_service.finalize(session, ctx, run_id)
    return PayrollRunOut(id=run.id, month=run.month, status=run.status)


@router.get("/payroll/summary", response_model=PayrollSummaryOut)
def summary(ctx: HrOrAdmin, session: DbSession, month: str) -> PayrollSummaryOut:
    """Totals for Admin/HR."""
    return PayrollSummaryOut(**payroll_service.summary(session, ctx, month=month))


@router.get("/payroll/me", response_class=HTMLResponse)
def my_payslip(ctx: AnyRole, session: DbSession, month: str) -> HTMLResponse:
    """My own payslip as a printable HTML page (browser Print -> PDF)."""
    return HTMLResponse(payroll_service.payslip_html(session, ctx, month=month))
