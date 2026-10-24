"""Attendance routes: HTTP only."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.context import UserContext
from app.deps import get_db, require_roles
from app.schemas import AttendanceOut, BoardEntry
from app.services import attendance_service

router = APIRouter(tags=["attendance"])

DbSession = Annotated[Session, Depends(get_db)]
AnyRole = Annotated[UserContext, Depends(require_roles("admin", "hr", "employee"))]
HrOrAdmin = Annotated[UserContext, Depends(require_roles("admin", "hr"))]


def _out(record) -> AttendanceOut:
    return AttendanceOut(
        id=record.id,
        day=record.day,
        check_in_at=record.check_in_at.isoformat() if record.check_in_at else None,
        check_out_at=record.check_out_at.isoformat() if record.check_out_at else None,
        status=record.status,
    )


@router.post("/attendance/check-in", response_model=AttendanceOut)
def check_in(ctx: AnyRole, session: DbSession) -> AttendanceOut:
    """Server stamps the check-in. Second same-day check-in: 409. After 09:15: late."""
    return _out(attendance_service.check_in(session, ctx))


@router.post("/attendance/check-out", response_model=AttendanceOut)
def check_out(ctx: AnyRole, session: DbSession) -> AttendanceOut:
    """Server stamps the check-out. Under 5 worked hours: half day."""
    return _out(attendance_service.check_out(session, ctx))


@router.get("/attendance/me", response_model=list[AttendanceOut])
def my_records(
    ctx: AnyRole,
    session: DbSession,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> list[AttendanceOut]:
    """My own records in a range."""
    return [_out(r) for r in attendance_service.my_records(session, ctx, start=start, end=end)]


@router.get("/attendance", response_model=list[BoardEntry])
def daily_board(ctx: HrOrAdmin, session: DbSession, day: date) -> list[BoardEntry]:
    """Admin/HR daily board: present, late, half day, missing checkout, absent."""
    return [BoardEntry(**row) for row in attendance_service.daily_board(session, ctx, day=day)]
