"""Database access for payroll runs and payslips. Parameterized queries only."""

from sqlmodel import Session, select

from app.models import PayrollRun, Payslip


def get_run_by_month(session: Session, month: str) -> PayrollRun | None:
    return session.exec(select(PayrollRun).where(PayrollRun.month == month)).first()


def get_run(session: Session, run_id: int) -> PayrollRun | None:
    return session.get(PayrollRun, run_id)


def payslips_for_run(session: Session, run_id: int) -> list[Payslip]:
    return list(session.exec(select(Payslip).where(Payslip.payroll_run_id == run_id)))


def payslip_for_employee(session: Session, run_id: int, employee_id: int) -> Payslip | None:
    return session.exec(
        select(Payslip).where(Payslip.payroll_run_id == run_id, Payslip.employee_id == employee_id)
    ).first()


def create_run(session: Session, run: PayrollRun) -> PayrollRun:
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def add_payslips(session: Session, slips: list[Payslip]) -> None:
    session.add_all(slips)
    session.commit()
