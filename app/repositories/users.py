"""Database access for users. Parameterized queries only."""

from sqlmodel import Session, func, select

from app.models import User


def get_by_email(session: Session, email: str) -> User | None:
    """Find a login by email (unique)."""
    return session.exec(select(User).where(User.email == email)).first()


def get_by_id(session: Session, user_id: int) -> User | None:
    """Find a login by id."""
    return session.get(User, user_id)


def count_users(session: Session) -> int:
    """How many logins exist. Used by /setup (first run check)."""
    return session.exec(select(func.count()).select_from(User)).one()


def create_user(
    session: Session,
    *,
    email: str,
    password_hash: str,
    role: str,
    employee_id: int | None = None,
    must_change_password: bool = False,
) -> User:
    """Insert one login row."""
    user = User(
        email=email,
        password_hash=password_hash,
        role=role,
        employee_id=employee_id,
        must_change_password=must_change_password,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
