"""Analytics/KPI routes: HTTP only. Role-scoped by the service."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.context import UserContext
from app.deps import get_db, require_roles
from app.schemas import KpiResponse
from app.services import analytics_service

router = APIRouter(tags=["analytics"])

DbSession = Annotated[Session, Depends(get_db)]
AnyRole = Annotated[UserContext, Depends(require_roles("admin", "hr", "employee"))]


@router.get("/analytics/kpis", response_model=KpiResponse)
def kpis(
    ctx: AnyRole,
    session: DbSession,
    start: date | None = None,
    end: date | None = None,
    department_id: Annotated[int | None, Query()] = None,
) -> KpiResponse:
    """Company KPIs for Admin/HR, personal KPIs for Employee. Defaults to this month."""
    return KpiResponse(
        **analytics_service.kpis(session, ctx, start=start, end=end, department_id=department_id)
    )
