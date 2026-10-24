"""AI routes: HTTP only. The services own everything else."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.config import Settings
from app.context import UserContext
from app.deps import get_db, require_roles
from app.schemas import (
    ChatRequest,
    ChatResponse,
    SmartLeaveResponse,
    SummaryResponse,
)
from app.services import chat_service, smart_leave_service, summary_service

router = APIRouter(prefix="/ai", tags=["ai"])

DbSession = Annotated[Session, Depends(get_db)]
AnyRole = Annotated[UserContext, Depends(require_roles("admin", "hr", "employee"))]
EmployeeOrHr = Annotated[UserContext, Depends(require_roles("employee", "hr"))]
HrOrAdmin = Annotated[UserContext, Depends(require_roles("admin", "hr"))]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest, ctx: AnyRole, request: Request, session: DbSession
) -> ChatResponse:
    """One chat turn. The agent only has this user's allowed tools."""
    settings: Settings = request.app.state.settings
    result = await chat_service.chat(session, ctx, settings, body.message)
    return ChatResponse(**result)


@router.post("/smart-leave", response_model=SmartLeaveResponse)
async def smart_leave(
    body: ChatRequest,
    ctx: EmployeeOrHr,
    request: Request,
    session: DbSession,
) -> SmartLeaveResponse:
    """A plain sentence -> a leave draft (never saved). fallback=true shows the form."""
    settings: Settings = request.app.state.settings
    result = await smart_leave_service.smart_leave(session, ctx, settings, body.message)
    return SmartLeaveResponse(**result)


@router.post("/dashboard-summary", response_model=SummaryResponse)
async def dashboard_summary(
    ctx: HrOrAdmin,
    request: Request,
    session: DbSession,
    start: date | None = None,
    end: date | None = None,
    department_id: Annotated[int | None, Query()] = None,
) -> SummaryResponse:
    """Server-computed KPIs -> 3-5 grounded bullets. Admin and HR only."""
    settings: Settings = request.app.state.settings
    result = await summary_service.dashboard_summary(
        session, ctx, settings, start=start, end=end, department_id=department_id
    )
    return SummaryResponse(**result)
