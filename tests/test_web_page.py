"""Tests for the web page, the setup-status endpoint, and guardrail
false-positive checks on the judge questions."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.guardrails.input_guardrail import screen_input
from tests.helpers import setup_company

APP_JS = Path("app/static/app.js").read_text(encoding="utf-8")


def test_root_serves_the_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "HCM Lite" in response.text
    assert "/static/app.js" in response.text


def test_app_js_is_served_and_never_uses_inner_html(client: TestClient) -> None:
    response = client.get("/static/app.js")
    assert response.status_code == 200
    # XSS rule: dynamic text must go through textContent, never innerHTML.
    assert "innerHTML" not in APP_JS
    assert "textContent" in APP_JS


def test_setup_status_before_and_after_setup(client: TestClient) -> None:
    first = client.get("/setup/status")
    assert first.status_code == 200
    assert first.json() == {"setup_done": False}

    setup_company(client)
    second = client.get("/setup/status")
    assert second.json() == {"setup_done": True}


def test_admin_can_create_hr_login_with_temp_password(client: TestClient, session: Session) -> None:
    token = setup_company(client)

    created = client.post(
        "/users", json={"email": "hr@co.com"}, headers={"Authorization": f"Bearer {token}"}
    )

    assert created.status_code == 200
    assert len(created.json()["temporary_password"]) >= 8

    # Non-admin cannot.
    from tests.helpers import add_user, token_for

    add_user(session, "emp@co.com", "employee")
    denied = client.post(
        "/users",
        json={"email": "x@co.com"},
        headers={"Authorization": f"Bearer {token_for(client, 'emp@co.com')}"},
    )
    assert denied.status_code == 403


def test_payslip_html_escapes_employee_names(client: TestClient, session: Session) -> None:
    from tests.helpers import add_employee, add_user, bearer, ensure_leave_types, token_for

    setup_company(client)
    ensure_leave_types(session)
    add_user(session, "hr@co.com", "hr")
    hr_token = token_for(client, "hr@co.com")
    evil = add_employee(session, code="E1", name="<script>alert(1)</script>")
    add_user(session, "evil@co.com", "employee", employee_id=evil.id)

    client.post("/payroll/runs", json={"month": "2026-10"}, headers=bearer(hr_token))
    html = client.get(
        "/payroll/me", params={"month": "2026-10"}, headers=bearer(token_for(client, "evil@co.com"))
    ).text

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html  # escaped, shown as text


# ---- the judge questions must never be blocked by the input screen ----


def test_judge_questions_pass_the_input_screen() -> None:
    judge_questions = [
        "How many active employees are in Engineering?",
        "Who came late most often this month?",
        "What is this month's attendance rate?",
        "How many sick leaves do I have left this year?",
        "What is Sara's salary?",
        "Summarize the dashboard for me.",
        "I need next Monday and Tuesday off for my sister's wedding",
        "Mujhe agle somwar aur mangal ko chutti chahiye behen ki shadi ke liye",
        "Kal se parso tak sick leave chahiye bukhar ki wajah se",
        "What time is considered late?",
        "How is payroll gross calculated?",
    ]
    for question in judge_questions:
        blocked, reason = screen_input(question)
        assert not blocked, f"false positive: {question!r} blocked as {reason}"
