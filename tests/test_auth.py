"""Rule tests for auth: setup, login, temp password, roles, scope, deactivation.

All passwords come from conftest (env overridable fixtures), never real values.
"""

import pytest
from sqlmodel import Session, select

from app.context import UserContext, assert_can_view_employee
from app.deps import require_roles
from app.errors import ForbiddenError
from app.models import LeaveType, User
from app.security import hash_password
from tests.conftest import TEST_NEW_PASSWORD, TEST_PASSWORD


def make_user(session: Session, email: str, role: str, **kwargs) -> User:
    user = User(
        email=email,
        password_hash=hash_password(TEST_PASSWORD),
        role=role,
        **kwargs,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_setup_creates_admin_and_default_leave_types(client, session: Session) -> None:
    response = client.post("/setup", json={"email": "admin@co.com", "password": TEST_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert body["access_token"]

    users = session.exec(select(User)).all()
    assert len(users) == 1 and users[0].role == "admin"

    quotas = {lt.code: lt.quota_days for lt in session.exec(select(LeaveType)).all()}
    assert quotas == {"annual": 14, "sick": 8, "casual": 10, "unpaid": None}


def test_second_setup_returns_409(client) -> None:
    client.post("/setup", json={"email": "admin@co.com", "password": TEST_PASSWORD})

    response = client.post("/setup", json={"email": "other@co.com", "password": TEST_PASSWORD})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_setup_without_any_credentials_returns_422(client) -> None:
    response = client.post("/setup", json={})

    assert response.status_code == 422


def test_login_wrong_password_returns_401(client) -> None:
    client.post("/setup", json={"email": "admin@co.com", "password": TEST_PASSWORD})

    response = client.post(
        "/auth/login", json={"email": "admin@co.com", "password": "WrongPass999"}
    )

    assert response.status_code == 401


def test_login_ok_returns_token_and_role(client) -> None:
    client.post("/setup", json={"email": "admin@co.com", "password": TEST_PASSWORD})

    response = client.post("/auth/login", json={"email": "admin@co.com", "password": TEST_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] and body["role"] == "admin"
    me = client.get("/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "admin@co.com"


def test_must_change_password_flow(client, session: Session) -> None:
    """A temp-password user: /me works, guarded routes block, change clears the flag."""
    make_user(session, "hr@co.com", "hr", must_change_password=True)

    login = client.post("/auth/login", json={"email": "hr@co.com", "password": TEST_PASSWORD})
    token = login.json()["access_token"]

    assert client.get("/me", headers=bearer(token)).status_code == 200

    changed = client.post(
        "/auth/change-password",
        json={"old_password": TEST_PASSWORD, "new_password": TEST_NEW_PASSWORD},
        headers=bearer(token),
    )
    assert changed.status_code == 200

    # Old password no longer logs in; new one does, flag is cleared.
    assert (
        client.post(
            "/auth/login", json={"email": "hr@co.com", "password": TEST_PASSWORD}
        ).status_code
        == 401
    )
    again = client.post("/auth/login", json={"email": "hr@co.com", "password": TEST_NEW_PASSWORD})
    assert again.json()["must_change_password"] is False


def test_guard_blocks_until_password_changed() -> None:
    guard = require_roles("hr")
    flagged = UserContext(user_id=1, role="hr", employee_id=None, must_change_password=True)

    with pytest.raises(ForbiddenError) as exc:
        guard(ctx=flagged)
    assert "temporary password" in exc.value.message


def test_role_guard_rejects_wrong_role() -> None:
    """Example rule: HR can never pass an admin-only guard (e.g. creating an admin)."""
    guard = require_roles("admin")
    hr = UserContext(user_id=2, role="hr", employee_id=None)
    admin = UserContext(user_id=1, role="admin", employee_id=None)

    with pytest.raises(ForbiddenError):
        guard(ctx=hr)
    assert guard(ctx=admin).role == "admin"


def test_employee_scope_blocks_other_employees() -> None:
    me = UserContext(user_id=9, role="employee", employee_id=1)
    assert_can_view_employee(me, 1)  # own row: fine

    with pytest.raises(ForbiddenError):
        assert_can_view_employee(me, 2)  # someone else's row: blocked


def test_deactivated_user_cannot_login_or_use_old_token(client, session: Session) -> None:
    client.post("/setup", json={"email": "admin@co.com", "password": TEST_PASSWORD})
    login = client.post("/auth/login", json={"email": "admin@co.com", "password": TEST_PASSWORD})
    token = login.json()["access_token"]

    user = session.exec(select(User)).one()
    user.is_active = False
    session.add(user)
    session.commit()

    assert client.get("/me", headers=bearer(token)).status_code == 401
    assert (
        client.post(
            "/auth/login", json={"email": "admin@co.com", "password": TEST_PASSWORD}
        ).status_code
        == 403
    )
