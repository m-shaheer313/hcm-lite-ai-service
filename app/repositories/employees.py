"""Database access for employees. Parameterized queries only."""

from sqlmodel import Session, func, select

from app.models import Employee


def get_by_id(session: Session, employee_id: int) -> Employee | None:
    return session.get(Employee, employee_id)


def get_by_code(session: Session, code: str) -> Employee | None:
    return session.exec(select(Employee).where(Employee.code == code)).first()


def search(
    session: Session, *, text: str = "", department_id: int | None = None, limit: int = 20
) -> list[Employee]:
    """Directory search by name or code, optionally in one department. Active only."""
    query = select(Employee).where(Employee.is_active)
    if text:
        pattern = f"%{text.lower()}%"
        query = query.where(
            func.lower(Employee.full_name).like(pattern) | func.lower(Employee.code).like(pattern)
        )
    if department_id is not None:
        query = query.where(Employee.department_id == department_id)
    return list(session.exec(query.limit(limit)))


def active_count(session: Session, department_id: int | None = None) -> int:
    query = select(func.count()).select_from(Employee).where(Employee.is_active)
    if department_id is not None:
        query = query.where(Employee.department_id == department_id)
    return session.exec(query).one()


def active_all(session: Session) -> list[Employee]:
    return list(session.exec(select(Employee).where(Employee.is_active)))


def create(session: Session, employee: Employee) -> Employee:
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return employee
