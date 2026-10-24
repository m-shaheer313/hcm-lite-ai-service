"""Rule tests for departments, employees, attendance, leave, payroll, KPIs."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import LeaveRequest
from tests.helpers import (
    add_employee,
    add_user,
    bearer,
    ensure_leave_types,
    setup_company,
    token_for,
)

KARACHI = ZoneInfo("Asia/Karachi")


# ---- departments and employees ----


def test_employee_cannot_create_department(client: TestClient, session: Session) -> None:
    setup_company(client)
    emp = add_employee(session, code="E1", name="Ali")
    add_user(session, "ali@co.com", "employee", employee_id=emp.id)
    token = token_for(client, "ali@co.com")

    response = client.post("/departments", json={"name": "Sales"}, headers=bearer(token))

    assert response.status_code == 403


def test_hr_registers_employee_and_gets_temp_password(client: TestClient, session: Session) -> None:
    setup_company(client)
    add_user(session, "hr@co.com", "hr")
    hr_token = token_for(client, "hr@co.com")

    response = client.post(
        "/employees",
        json={
            "email": "sara@co.com",
            "full_name": "Sara Ahmed",
            "designation": "Engineer",
            "join_date": "2026-10-01",
            "basic_salary_minor": 8_000_000,
        },
        headers=bearer(hr_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["employee"]["code"].startswith("EMP-")
    assert len(body["temporary_password"]) >= 8
    # The temp login forces a password change.
    login = client.post(
        "/auth/login", json={"email": "sara@co.com", "password": body["temporary_password"]}
    )
    assert login.json()["must_change_password"] is True


def test_employee_cannot_search_directory(client: TestClient, session: Session) -> None:
    setup_company(client)
    emp = add_employee(session, code="E1", name="Ali")
    add_user(session, "ali@co.com", "employee", employee_id=emp.id)
    token = token_for(client, "ali@co.com")

    response = client.get("/employees", headers=bearer(token))

    assert response.status_code == 403
    assert "salary" not in response.text  # never leaks anything


# ---- attendance ----


def make_employee_with_login(
    client: TestClient, session: Session, email: str, code: str, name: str
):
    emp = add_employee(session, code=code, name=name)
    add_user(session, email, "employee", employee_id=emp.id)
    return emp, token_for(client, email)


def test_second_check_in_same_day_is_409(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    _, token = make_employee_with_login(client, session, "ali@co.com", "E1", "Ali Khan")

    first = client.post("/attendance/check-in", headers=bearer(token))
    second = client.post("/attendance/check-in", headers=bearer(token))

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_check_in_after_0915_is_late_and_short_day_is_half_day(
    client: TestClient, session: Session
) -> None:
    """Direct service test with injected times: late + half-day rules."""
    from app.context import UserContext
    from app.services import attendance_service

    setup_company(client)
    emp = add_employee(session, code="E9", name="Late Person")

    late_morning = datetime(2026, 10, 26, 9, 30, tzinfo=UTC).astimezone(
        KARACHI
    )  # 14:30 Karachi — definitely after 09:15
    ctx = UserContext(user_id=1, role="employee", employee_id=emp.id)

    record = attendance_service.check_in(session, ctx, utc_now=late_morning.astimezone(UTC))
    assert record.status == "late"

    # Works only 2 hours -> half day
    afternoon = late_morning.replace(hour=late_morning.hour + 2)
    closed = attendance_service.check_out(session, ctx, utc_now=afternoon.astimezone(UTC))
    assert closed.status == "half_day"


def test_daily_board_marks_absent_and_on_leave(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    add_user(session, "hr@co.com", "hr")
    hr_token = token_for(client, "hr@co.com")

    present_emp, _ = make_employee_with_login(
        client, session, "present@co.com", "E1", "Present Person"
    )
    add_employee(session, code="E2", name="Absent Person")
    leave_emp = add_employee(session, code="E3", name="On Leave")

    day = date(2026, 10, 26)  # Monday
    # Check "Present Person" in on that Monday with an injected time
    # (08:30 Karachi — on time, so the status is 'present', not 'late').
    from app.context import UserContext
    from app.services import attendance_service

    monday_morning = datetime(2026, 10, 26, 3, 30, tzinfo=UTC)
    ctx = UserContext(user_id=1, role="employee", employee_id=present_emp.id)
    attendance_service.check_in(session, ctx, utc_now=monday_morning)

    # leave_emp gets an approved annual leave for that day (inserted directly).
    from app.models import LeaveType

    lt = session.exec(select(LeaveType).where(LeaveType.code == "annual")).one()
    session.add(
        LeaveRequest(
            employee_id=leave_emp.id,
            leave_type_id=lt.id,
            start_day=day,
            end_day=day,
            working_days=1,
            reason="trip",
            status="approved",
        )
    )
    session.commit()

    board = client.get("/attendance", params={"day": day.isoformat()}, headers=bearer(hr_token))
    statuses = {row["full_name"]: row["status"] for row in board.json()}

    assert board.status_code == 200
    assert statuses["Present Person"] == "present"
    assert statuses["Absent Person"] == "absent"
    assert statuses["On Leave"] == "on_leave"


# ---- leave rules ----


def test_leave_overlap_and_over_balance_are_422(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    _, token = make_employee_with_login(client, session, "ali@co.com", "E1", "Ali Khan")

    ok = client.post(
        "/leaves",
        json={
            "leave_type_code": "annual",
            "start_day": "2026-11-02",
            "end_day": "2026-11-03",
            "reason": "trip",
        },
        headers=bearer(token),
    )
    assert ok.status_code == 200

    overlap = client.post(
        "/leaves",
        json={
            "leave_type_code": "sick",
            "start_day": "2026-11-03",
            "end_day": "2026-11-04",
            "reason": "sick",
        },
        headers=bearer(token),
    )
    assert overlap.status_code == 422
    assert "overlap" in overlap.json()["error"]["message"].lower()

    # Over balance: sick quota is 8; ask for 9.
    over = client.post(
        "/leaves",
        json={
            "leave_type_code": "sick",
            "start_day": "2027-01-04",
            "end_day": "2027-01-14",
            "reason": "long",
        },
        headers=bearer(token),
    )
    assert over.status_code == 422
    assert "balance" in over.json()["error"]["message"].lower()


def test_leave_on_weekend_only_is_rejected(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    _, token = make_employee_with_login(client, session, "ali@co.com", "E1", "Ali Khan")

    response = client.post(
        "/leaves",
        json={
            "leave_type_code": "casual",
            "start_day": "2026-12-05",  # Saturday
            "end_day": "2026-12-06",  # Sunday
            "reason": "weekend",
        },
        headers=bearer(token),
    )

    assert response.status_code == 422
    assert "working day" in response.json()["error"]["message"].lower()


def test_approve_consumes_balance_and_reject_does_not(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    add_user(session, "hr@co.com", "hr")
    hr_token = token_for(client, "hr@co.com")
    _, token = make_employee_with_login(client, session, "ali@co.com", "E1", "Ali Khan")

    applied = client.post(
        "/leaves",
        json={
            "leave_type_code": "casual",
            "start_day": "2026-11-02",
            "end_day": "2026-11-03",
            "reason": "family event",
        },
        headers=bearer(token),
    )
    request_id = applied.json()["id"]

    before = {b["code"]: b for b in client.get("/leaves/balance", headers=bearer(token)).json()}
    assert before["casual"]["used_days"] == 0

    approved = client.post(
        f"/leaves/{request_id}/approve", json={"comment": "ok"}, headers=bearer(hr_token)
    )
    assert approved.status_code == 200

    after = {b["code"]: b for b in client.get("/leaves/balance", headers=bearer(token)).json()}
    assert after["casual"]["used_days"] == 2
    assert after["casual"]["remaining_days"] == 8

    # Deciding twice fails.
    again = client.post(f"/leaves/{request_id}/approve", json={}, headers=bearer(hr_token))
    assert again.status_code == 422


def test_employee_cannot_approve_leave(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    _, token = make_employee_with_login(client, session, "ali@co.com", "E1", "Ali Khan")

    applied = client.post(
        "/leaves",
        json={
            "leave_type_code": "annual",
            "start_day": "2026-11-09",
            "end_day": "2026-11-10",
            "reason": "rest",
        },
        headers=bearer(token),
    )
    request_id = applied.json()["id"]

    response = client.post(f"/leaves/{request_id}/approve", json={}, headers=bearer(token))

    assert response.status_code == 403


# ---- payroll ----


def test_one_payroll_run_per_month_and_finalize_locks(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    add_user(session, "hr@co.com", "hr")
    add_employee(session, code="E1", name="Ali")
    hr_token = token_for(client, "hr@co.com")
    admin_token = token_for(client, "admin@co.com")

    first = client.post("/payroll/runs", json={"month": "2026-10"}, headers=bearer(hr_token))
    second = client.post("/payroll/runs", json={"month": "2026-10"}, headers=bearer(hr_token))

    assert first.status_code == 200
    assert second.status_code == 409

    run_id = first.json()["id"]

    # HR cannot finalize; admin can; then it is locked.
    denied = client.post(f"/payroll/runs/{run_id}/finalize", headers=bearer(hr_token))
    assert denied.status_code == 403

    ok = client.post(f"/payroll/runs/{run_id}/finalize", headers=bearer(admin_token))
    assert ok.status_code == 200
    assert ok.json()["status"] == "finalized"

    locked = client.post(f"/payroll/runs/{run_id}/finalize", headers=bearer(admin_token))
    assert locked.status_code == 409


def test_payslip_html_is_printable_and_personal(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    add_user(session, "hr@co.com", "hr")
    hr_token = token_for(client, "hr@co.com")
    _, token = make_employee_with_login(client, session, "ali@co.com", "E1", "Ali Khan")
    other = add_employee(session, code="E2", name="Other Person")
    add_user(session, "other@co.com", "employee", employee_id=other.id)
    other_token = token_for(client, "other@co.com")

    created = client.post("/payroll/runs", json={"month": "2026-10"}, headers=bearer(hr_token))
    assert created.status_code == 200

    mine = client.get("/payroll/me", params={"month": "2026-10"}, headers=bearer(token))
    assert mine.status_code == 200
    assert "Net pay" in mine.text and "print" in mine.text.lower()

    # Another employee sees their own payslip, never mine — and both exist.
    theirs = client.get("/payroll/me", params={"month": "2026-10"}, headers=bearer(other_token))
    assert theirs.status_code == 200
    assert mine.text != theirs.text

    # Employee cannot see the summary.
    denied = client.get("/payroll/summary", params={"month": "2026-10"}, headers=bearer(token))
    assert denied.status_code == 403


# ---- KPIs ----


def test_kpis_are_role_scoped(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    _, token = make_employee_with_login(client, session, "ali@co.com", "E1", "Ali Khan")

    mine = client.get("/analytics/kpis", headers=bearer(token))
    assert mine.status_code == 200
    body = mine.json()
    assert body["scope"] == "personal"
    assert "attendance_rate_pct" not in body["kpis"]  # company number, not mine

    add_user(session, "hr@co.com", "hr")
    hr_token = token_for(client, "hr@co.com")
    company = client.get("/analytics/kpis", headers=bearer(hr_token))
    assert company.json()["scope"] == "company"
    assert company.json()["kpis"]["headcount"] >= 1
