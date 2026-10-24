"""Auth logic: first-run setup, login, change password, my profile.

Business rules live here, not in routes. The app starts EMPTY; setup creates
the Admin and the default leave types (configuration, not dummy data).
"""

from sqlmodel import Session, select

from app.config import Settings
from app.context import UserContext
from app.errors import AuthError, ConflictError, ForbiddenError, RuleViolationError
from app.models import LeaveType, Setting, User
from app.repositories import users as user_repo
from app.security import create_access_token, hash_password, verify_password

# Default leave types from the brief: annual 14, sick 8, casual 10, unpaid unlimited.
DEFAULT_LEAVE_TYPES: list[tuple[str, str, int | None]] = [
    ("annual", "Annual", 14),
    ("sick", "Sick", 8),
    ("casual", "Casual", 10),
    ("unpaid", "Unpaid", None),
]

MIN_PASSWORD_BYTES = 8
MAX_PASSWORD_BYTES = 72  # bcrypt limit


def validate_new_password(password: str) -> str:
    """Length rules for every new password. Raises RuleViolationError."""
    size = len(password.encode("utf-8"))
    if size < MIN_PASSWORD_BYTES:
        raise RuleViolationError("Password must be at least 8 characters.")
    if size > MAX_PASSWORD_BYTES:
        raise RuleViolationError("Password is too long: max 72 bytes (bcrypt limit).")
    return password


def get_setting(session: Session, key: str) -> str | None:
    """Read one company setting."""
    row = session.exec(select(Setting).where(Setting.key == key)).first()
    return row.value if row else None


def set_setting(session: Session, key: str, value: str) -> None:
    """Write one company setting (insert or update)."""
    row = session.exec(select(Setting).where(Setting.key == key)).first()
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    session.commit()


def setup(
    session: Session,
    settings: Settings,
    *,
    email: str | None,
    password: str | None,
    company_name: str | None,
) -> User:
    """First-run setup: create the Admin and default leave types. Once only."""
    if user_repo.count_users(session) > 0:
        raise ConflictError("Setup is already done. Please log in instead.")

    # Form values win; env vars (ADMIN_EMAIL / ADMIN_PASSWORD) are the fallback.
    email = email or settings.admin_email
    password = password or settings.admin_password
    company_name = company_name or settings.company_name

    if not email or not password:
        raise RuleViolationError("Admin email and password are required for setup.")
    if "@" not in email:
        raise RuleViolationError("Admin email must be a valid email address.")
    validate_new_password(password)

    admin = user_repo.create_user(
        session,
        email=email,
        password_hash=hash_password(password),
        role="admin",
    )
    set_setting(session, "company_name", company_name)
    for code, name, quota in DEFAULT_LEAVE_TYPES:
        session.add(LeaveType(code=code, name=name, quota_days=quota))
    session.commit()
    return admin


def login(session: Session, settings: Settings, *, email: str, password: str) -> dict:
    """Check credentials and return a token plus must-change flag.

    We never reveal whether the email or the password was wrong.
    """
    user = user_repo.get_by_email(session, email)
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Email or password is wrong.")
    if not user.is_active:
        raise ForbiddenError("This account is deactivated. Please contact your admin.")

    token = create_access_token(
        user_id=user.id,
        role=user.role,
        secret=settings.jwt_secret,
        expires_minutes=settings.jwt_expires_minutes,
    )
    return {
        "access_token": token,
        "role": user.role,
        "must_change_password": user.must_change_password,
    }


def change_password(
    session: Session, ctx: UserContext, *, old_password: str, new_password: str
) -> None:
    """Change password and clear the must-change flag."""
    user = user_repo.get_by_id(session, ctx.user_id)
    if user is None or not verify_password(old_password, user.password_hash):
        raise AuthError("Old password is wrong.")
    validate_new_password(new_password)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    session.add(user)
    session.commit()


def me(session: Session, ctx: UserContext) -> dict:
    """Profile for GET /me. Also works while must_change_password is true."""
    user = user_repo.get_by_id(session, ctx.user_id)
    if user is None:
        raise AuthError("Your session is no longer valid. Please log in again.")
    return {
        "email": user.email,
        "role": user.role,
        "employee_id": user.employee_id,
        "must_change_password": user.must_change_password,
        "company_name": get_setting(session, "company_name") or "",
    }
