"""Database access for departments. Parameterized queries only."""

from sqlmodel import Session, select

from app.models import Department


def get_all(session: Session) -> list[Department]:
    return list(session.exec(select(Department).order_by(Department.name)))


def get_by_name(session: Session, name: str) -> Department | None:
    return session.exec(select(Department).where(Department.name == name)).first()


def create(session: Session, name: str) -> Department:
    dept = Department(name=name)
    session.add(dept)
    session.commit()
    session.refresh(dept)
    return dept
