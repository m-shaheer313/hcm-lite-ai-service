"""Tests for the AI tools. No API key needed: inner functions are called
directly with a ToolDeps (verified UserContext + session)."""

import json
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.context import UserContext
from app.models import LeaveType
from app.services.attendance_service import check_in as check_in_service
from app.tools import ALL_TOOLS, ToolDeps, tools_for_role
from app.tools.hr_tools import (
    _get_attendance_summary,
    _get_headcount,
    _get_late_comers,
    _get_leave_summary,
    _get_my_leave_balance,
    _get_payroll_summary,
    _safe,
    _search_employees,
)
from tests.helpers import (
    add_employee,
    add_user,
    bearer,
    ensure_leave_types,
    setup_company,
    token_for,
)

KARACHI = ZoneInfo("Asia/Karachi")


def hr_deps(session: Session) -> ToolDeps:
    return ToolDeps(ctx=UserContext(user_id=2, role="hr", employee_id=None), session=session)


def employee_deps(session: Session, employee_id: int) -> ToolDeps:
    return ToolDeps(
        ctx=UserContext(user_id=3, role="employee", employee_id=employee_id),
        session=session,
    )


def as_dict(result: str) -> dict:
    return json.loads(result) if isinstance(result, str) else result


# ---- allowlist ----


def test_employee_allowlist_has_only_own_balance() -> None:
    names = {t.name for t in tools_for_role("employee")}
    assert names == {"get_my_leave_balance"}


def test_admin_and_hr_get_all_seven_tools() -> None:
    assert len(tools_for_role("admin")) == 7
    assert len(tools_for_role("hr")) == 7
    assert {t.name for t in ALL_TOOLS} == {
        "get_headcount",
        "get_attendance_summary",
        "get_late_comers",
        "get_leave_summary",
        "get_payroll_summary",
        "search_employees",
        "get_my_leave_balance",
    }


def test_employee_cannot_use_payroll_tool(session: Session) -> None:
    """An Employee asking for payroll (e.g. a colleague's salary context)
    fails AT THE TOOL LAYER and gets a JSON error, never a traceback."""
    deps = employee_deps(session, employee_id=1)
    result = as_dict(_safe(_get_payroll_summary, deps, "2026-10"))
    assert result["error"] == "forbidden"


def test_employee_cannot_search_directory(session: Session) -> None:
    deps = employee_deps(session, employee_id=1)
    result = as_dict(_safe(_search_employees, deps, "Ali", None, 5))
    assert result["error"] == "forbidden"


# ---- own data ----


def test_my_leave_balance_returns_own_data(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    emp = add_employee(session, code="E1", name="Ali Khan")
    deps = employee_deps(session, emp.id)

    result = as_dict(_get_my_leave_balance(deps))

    codes = {b["code"] for b in result["balances"]}
    assert codes == {"annual", "sick", "casual", "unpaid"}
    casual = next(b for b in result["balances"] if b["code"] == "casual")
    assert casual["remaining_days"] == 10


# ---- company tools + dashboard equality ----


def seed_two_employees(session: Session):
    """Two employees; one checked in twice late, once present."""
    emp_a = add_employee(session, code="EA", name="Late Laila")
    emp_b = add_employee(session, code="EB", name="Punctual Bilal")
    for day, hour_utc in [
        (date(2026, 10, 26), 5),
        (date(2026, 10, 27), 5),
        (date(2026, 10, 28), 3),
    ]:
        ctx = UserContext(user_id=9, role="employee", employee_id=emp_a.id)
        check_in_service(
            session, ctx, utc_now=datetime(day.year, day.month, day.day, hour_utc, 0, tzinfo=UTC)
        )
    ctx = UserContext(user_id=10, role="employee", employee_id=emp_b.id)
    check_in_service(session, ctx, utc_now=datetime(2026, 10, 26, 3, 0, tzinfo=UTC))
    return emp_a, emp_b


def test_tool_numbers_match_dashboard(client: TestClient, session: Session) -> None:
    """Same filters -> the tool's numbers equal GET /analytics/kpis."""
    setup_company(client)
    ensure_leave_types(session)
    add_user(session, "hr@co.com", "hr")
    hr_token = token_for(client, "hr@co.com")
    seed_two_employees(session)

    deps = hr_deps(session)
    tool = as_dict(_get_attendance_summary(deps, date(2026, 10, 26), date(2026, 10, 28), None))

    board = client.get(
        "/analytics/kpis",
        params={"start": "2026-10-26", "end": "2026-10-28"},
        headers=bearer(hr_token),
    ).json()["kpis"]

    assert tool["headcount"] == board["headcount"]
    assert tool["present_days"] == board["present_days"]
    assert tool["late_days"] == board["late_days"]
    assert tool["attendance_rate_pct"] == board["attendance_rate_pct"]


def test_get_late_comers_orders_by_count(session: Session) -> None:
    deps = hr_deps(session)
    seed_two_employees(session)

    result = as_dict(_get_late_comers(deps, date(2026, 10, 26), date(2026, 10, 28), 5))

    # Laila checked in after 09:15 twice (10:00 Karachi); Bilal was on time.
    assert result["late_comers"][0]["full_name"] == "Late Laila"
    assert result["late_comers"][0]["late_days"] == 2
    assert len(result["late_comers"]) == 1


def test_headcount_with_department_filter(session: Session) -> None:
    deps = hr_deps(session)
    from app.repositories import departments as dept_repo

    eng = dept_repo.create(session, "Engineering")
    sales = dept_repo.create(session, "Sales")
    add_employee(session, code="E1", name="A", department_id=eng.id)
    add_employee(session, code="E2", name="B", department_id=eng.id)
    add_employee(session, code="E3", name="C", department_id=sales.id)

    all_count = as_dict(_safe(_get_headcount, deps, None))
    eng_count = as_dict(_safe(_get_headcount, deps, "Engineering"))
    unknown = as_dict(_safe(_get_headcount, deps, "Nope"))

    assert all_count["headcount"] == 3
    assert eng_count["headcount"] == 2
    assert unknown["error"] == "not_found"


def test_kpi_endpoint_accepts_range_and_department_filters(
    client: TestClient, session: Session
) -> None:
    """The dashboard KPI endpoint supports date range + department filters."""
    setup_company(client)
    ensure_leave_types(session)
    add_user(session, "hr@co.com", "hr")
    hr_token = token_for(client, "hr@co.com")
    from app.repositories import departments as dept_repo

    eng = dept_repo.create(session, "Engineering")
    add_employee(session, code="E1", name="A", department_id=eng.id)
    add_employee(session, code="E2", name="B")

    response = client.get(
        "/analytics/kpis",
        params={"start": "2026-10-01", "end": "2026-10-31", "department_id": eng.id},
        headers=bearer(hr_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["from_day"] == "2026-10-01"
    assert body["to_day"] == "2026-10-31"
    assert body["kpis"]["headcount"] == 1  # only Engineering


def test_leave_summary_counts_types(session: Session) -> None:
    deps = hr_deps(session)
    ensure_leave_types(session)
    emp_a, _ = seed_two_employees(session)
    _ = emp_a
    lt = session.exec(select(LeaveType).where(LeaveType.code == "casual")).one()
    from app.models import LeaveRequest

    session.add(
        LeaveRequest(
            employee_id=emp_a.id,
            leave_type_id=lt.id,
            start_day=date(2026, 11, 2),
            end_day=date(2026, 11, 3),
            working_days=2,
            reason="family",
            status="approved",
        )
    )
    session.commit()

    result = as_dict(_get_leave_summary(deps, date(2026, 11, 1), date(2026, 11, 30), None))

    assert result["approved_days_by_type"] == {"Casual": 2}
    assert result["employees_on_leave"] == 1


def test_payroll_summary_tool_matches_endpoint(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    add_user(session, "hr@co.com", "hr")
    hr_token = token_for(client, "hr@co.com")
    add_employee(session, code="E1", name="Ali Khan")

    created = client.post("/payroll/runs", json={"month": "2026-10"}, headers=bearer(hr_token))
    assert created.status_code == 200

    deps = hr_deps(session)
    tool = as_dict(_get_payroll_summary(deps, "2026-10"))
    endpoint = client.get(
        "/payroll/summary", params={"month": "2026-10"}, headers=bearer(hr_token)
    ).json()

    assert tool == endpoint
