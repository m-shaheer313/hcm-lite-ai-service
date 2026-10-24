"""Tests for /ai/smart-leave and /ai/dashboard-summary. Fake model, no key."""

import asyncio
import json
from datetime import date

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import Settings
from app.context import UserContext
from app.models import AiLog
from app.services import smart_leave_service, summary_service
from tests.fake_model import FakeModel, text_response
from tests.helpers import (
    add_employee,
    add_user,
    bearer,
    ensure_leave_types,
    setup_company,
    token_for,
)


def settings() -> Settings:
    return Settings(_env_file=None)


def emp_ctx(employee_id: int = 1) -> UserContext:
    return UserContext(user_id=7, role="employee", employee_id=employee_id)


def hr_ctx() -> UserContext:
    return UserContext(user_id=2, role="hr", employee_id=None)


def extraction_json(leave_type: str, start: str, end: str, reason: str = "family event") -> str:
    return json.dumps(
        {
            "leave_type": leave_type,
            "start_phrase": start,
            "end_phrase": end,
            "reason": reason,
        }
    )


# ---- smart leave ----


def test_wedding_sentence_becomes_casual_with_exact_dates(
    client: TestClient, session: Session
) -> None:
    """'next Monday and Tuesday' resolved by code, not by the model."""
    setup_company(client)
    ensure_leave_types(session)
    today = date(2026, 10, 24)  # Saturday: next Monday = 26th, Tuesday = 27th

    model = FakeModel([text_response(extraction_json("casual", "next Monday", "Tuesday"))])
    result = asyncio.run(
        smart_leave_service.smart_leave(
            session,
            emp_ctx(),
            settings(),
            "I need next Monday and Tuesday off",
            today=today,
            model=model,
        )
    )

    assert result["fallback"] is False
    assert result["draft"]["leave_type"] == "casual"
    assert result["draft"]["start"] == "2026-10-26"
    assert result["draft"]["end"] == "2026-10-27"
    assert result["label"] == "AI-generated"
    rows = session.exec(select(AiLog)).all()
    assert rows[-1].status == "ok" and rows[-1].endpoint == "/ai/smart-leave"


def test_roman_urdu_kal_parso_resolve() -> None:
    model = FakeModel([text_response(extraction_json("sick", "kal", "parso", "bukhar"))])
    from sqlalchemy.pool import StaticPool
    from sqlmodel import create_engine

    from app.db import init_db

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    init_db(engine)
    with Session(engine) as s:
        result = asyncio.run(
            smart_leave_service.smart_leave(
                s,
                emp_ctx(),
                settings(),
                "kal se parso tak sick leave",
                today=date(2026, 10, 26),
                model=model,
            )
        )
    engine.dispose()
    assert result["fallback"] is False
    assert result["draft"]["start"] == "2026-10-27"
    assert result["draft"]["end"] == "2026-10-28"


def test_bad_extraction_retries_then_falls_back(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)

    model = FakeModel(
        [
            text_response(extraction_json("birthday", "someday", "someday")),  # bad type
            text_response(extraction_json("annual", "never", "never")),  # bad phrases
        ]
    )
    result = asyncio.run(
        smart_leave_service.smart_leave(
            session, emp_ctx(), settings(), "party!", today=date(2026, 10, 26), model=model
        )
    )

    assert result["fallback"] is True
    assert result["draft"] is None
    rows = session.exec(select(AiLog)).all()
    assert rows[-1].status == "fallback"


def test_weekend_only_range_falls_back(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)

    model = FakeModel([text_response(extraction_json("annual", "Saturday", "Sunday"))])
    result = asyncio.run(
        smart_leave_service.smart_leave(
            session, emp_ctx(), settings(), "weekend off", today=date(2026, 10, 26), model=model
        )
    )
    # Saturday+Sunday after Monday 2026-10-26 = Nov 7/8 -> zero working days.
    assert result["fallback"] is True


def test_smart_leave_route_roles_and_auth(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    add_user(session, "hr@co.com", "hr")
    emp = add_employee(session, code="E1", name="Ali")
    add_user(session, "ali@co.com", "employee", employee_id=emp.id)
    admin_token = token_for(client, "admin@co.com")

    # Admin is not allowed on smart-leave (Employee and HR only).
    denied = client.post(
        "/ai/smart-leave",
        json={"message": "leave please"},
        headers=bearer(admin_token),
    )
    assert denied.status_code == 403

    # Anonymous is not allowed either.
    assert client.post("/ai/smart-leave", json={"message": "x"}).status_code == 401


def test_smart_leave_never_writes_leave_rows(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    from app.models import LeaveRequest

    model = FakeModel([text_response(extraction_json("casual", "next Monday", "Tuesday"))])
    asyncio.run(
        smart_leave_service.smart_leave(
            session, emp_ctx(), settings(), "wedding", today=date(2026, 10, 24), model=model
        )
    )
    assert session.exec(select(LeaveRequest)).all() == []


# ---- dashboard summary ----


def seeded_kpi_company(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    add_user(session, "hr@co.com", "hr")
    add_employee(session, code="E1", name="Ali")
    add_employee(session, code="E2", name="Bilal")


def test_summary_returns_grounded_bullets(client: TestClient, session: Session) -> None:
    seeded_kpi_company(client, session)

    model = FakeModel(
        [
            text_response(
                "- Headcount is 2 employees.\n"
                "- Attendance rate is 0.0% this month.\n"
                "- No late days recorded."
            )
        ]
    )
    result = asyncio.run(
        summary_service.dashboard_summary(session, hr_ctx(), settings(), model=model)
    )

    assert result["fallback"] is False
    assert 3 <= len(result["summary"]) <= 5
    assert result["label"] == "AI-generated"
    rows = session.exec(select(AiLog)).all()
    assert rows[-1].status == "ok" and rows[-1].endpoint == "/ai/dashboard-summary"


def test_summary_invented_number_retries_then_code_fallback(
    client: TestClient, session: Session
) -> None:
    seeded_kpi_company(client, session)

    model = FakeModel(
        [
            # headcount is really 2; "47" is invented
            text_response("- Headcount is 47.\n- Rate 0.0%.\n- Late 0 days."),
            text_response("- Headcount is 48.\n- Rate 0.0%.\n- Late 0 days."),
        ]
    )
    result = asyncio.run(
        summary_service.dashboard_summary(session, hr_ctx(), settings(), model=model)
    )

    assert result["fallback"] is True
    joined = "\n".join(result["summary"])
    assert "2" in joined  # honest bullets built from the real KPI JSON
    rows = session.exec(select(AiLog)).all()
    assert rows[-1].status == "summary_fallback"


def test_summary_employee_gets_403(client: TestClient, session: Session) -> None:
    setup_company(client)
    ensure_leave_types(session)
    emp = add_employee(session, code="E1", name="Ali")
    add_user(session, "ali@co.com", "employee", employee_id=emp.id)
    token = token_for(client, "ali@co.com")

    response = client.post("/ai/dashboard-summary", headers=bearer(token))

    assert response.status_code == 403


def test_summary_uses_server_computed_kpis(client: TestClient, session: Session) -> None:
    """The KPIs come from the analytics service, never from the request body."""
    seeded_kpi_company(client, session)
    hr_token = token_for(client, "hr@co.com")

    model = FakeModel([text_response("- Headcount is 2.\n- Rate 0.0%.\n- Late 0.")])
    result = asyncio.run(
        summary_service.dashboard_summary(
            session,
            hr_ctx(),
            settings(),
            start=date(2026, 10, 1),
            end=date(2026, 10, 31),
            model=model,
        )
    )
    board = client.get(
        "/analytics/kpis",
        params={"start": "2026-10-01", "end": "2026-10-31"},
        headers=bearer(hr_token),
    ).json()["kpis"]

    assert result["fallback"] is False
    assert board["headcount"] == 2
    assert "2" in "\n".join(result["summary"])
