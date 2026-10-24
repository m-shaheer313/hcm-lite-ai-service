"""Leave routes: HTTP only."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.context import UserContext
from app.deps import get_db, require_roles
from app.schemas import (
    BalanceOut,
    DecisionRequest,
    LeaveApplyRequest,
    LeaveOut,
    PendingOut,
)
from app.services import leave_service

router = APIRouter(tags=["leave"])

DbSession = Annotated[Session, Depends(get_db)]
AnyRole = Annotated[UserContext, Depends(require_roles("admin", "hr", "employee"))]
HrOrAdmin = Annotated[UserContext, Depends(require_roles("admin", "hr"))]


@router.post("/leaves", response_model=LeaveOut)
def apply_leave(body: LeaveApplyRequest, ctx: AnyRole, session: DbSession) -> LeaveOut:
    """Apply for leave. Overlap or over-balance: 422."""
    req = leave_service.apply(
        session,
        ctx,
        leave_type_code=body.leave_type_code,
        start=body.start_day,
        end=body.end_day,
        reason=body.reason,
    )
    return LeaveOut.from_request(req)


@router.get("/leaves/balance", response_model=list[BalanceOut])
def my_balance(ctx: AnyRole, session: DbSession) -> list[BalanceOut]:
    """My balance per leave type for this year."""
    return [BalanceOut(**b) for b in leave_service.balances(session, ctx)]


@router.get("/leaves/pending", response_model=list[PendingOut])
def pending(ctx: HrOrAdmin, session: DbSession) -> list[PendingOut]:
    """HR/Admin approval inbox."""
    return [PendingOut(**p) for p in leave_service.pending_list(session, ctx)]


@router.post("/leaves/{request_id}/approve", response_model=LeaveOut)
def approve(
    request_id: int,
    body: DecisionRequest,
    ctx: HrOrAdmin,
    session: DbSession,
) -> LeaveOut:
    """Approve a pending request. Balance and overlap are re-checked first."""
    req = leave_service.approve(session, ctx, request_id, comment=body.comment)
    return LeaveOut.from_request(req)


@router.post("/leaves/{request_id}/reject", response_model=LeaveOut)
def reject(
    request_id: int,
    body: DecisionRequest,
    ctx: HrOrAdmin,
    session: DbSession,
) -> LeaveOut:
    """Reject a pending request. Rejected leave does not consume balance."""
    req = leave_service.reject(session, ctx, request_id, comment=body.comment)
    return LeaveOut.from_request(req)
