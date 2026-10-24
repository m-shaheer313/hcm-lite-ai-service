"""Tests for the pure business rules in app/services/rules.py."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.services import rules

KARACHI = ZoneInfo("Asia/Karachi")


def dt(hour: int, minute: int, day: int = 24) -> datetime:
    """A Karachi datetime on 2026-10-<day>."""
    return datetime(2026, 10, day, hour, minute, tzinfo=KARACHI)


def utc_at(hour_khi: int, minute_khi: int) -> datetime:
    """The UTC instant that equals the given Karachi wall time."""
    return dt(hour_khi, minute_khi).astimezone(UTC)


# ---- working days ----


def test_saturday_and_sunday_are_not_working_days() -> None:
    # 2026-10-24 is a Saturday, 2026-10-25 a Sunday.
    assert rules.is_weekend(date(2026, 10, 24))
    assert rules.is_weekend(date(2026, 10, 25))
    assert not rules.is_weekend(date(2026, 10, 26))  # Monday


def test_count_working_days_skips_weekend_and_holidays() -> None:
    # Mon 26 Oct - Fri 30 Oct = 5 working days; Wed 28 Oct is a holiday -> 4.
    holidays = {date(2026, 10, 28)}
    assert rules.count_working_days(date(2026, 10, 26), date(2026, 10, 30), holidays) == 4


def test_count_working_days_reversed_range_is_zero() -> None:
    assert rules.count_working_days(date(2026, 10, 30), date(2026, 10, 26), set()) == 0


# ---- late rule ----


def test_check_in_at_0915_is_not_late_but_one_minute_more_is() -> None:
    assert not rules.is_late(dt(9, 15))
    assert rules.is_late(dt(9, 16))


def test_today_in_karachi_uses_office_timezone() -> None:
    # 21:00 UTC on Oct 24 is 02:00 Karachi on Oct 25.
    moment = datetime(2026, 10, 24, 21, 0, tzinfo=UTC)
    assert rules.today_in_karachi(moment) == date(2026, 10, 25)


# ---- half day ----


def test_under_five_hours_is_a_half_day() -> None:
    assert rules.is_half_day(4.99)
    assert not rules.is_half_day(5.0)


# ---- money ----


def test_gross_is_one_and_a_half_times_basic() -> None:
    assert rules.gross_from_basic(10_000_000) == 15_000_000  # PKR 100k -> 150k
    assert rules.gross_from_basic(33) == 50  # odd paisa rounds up


def test_annual_tax_follows_the_brief_slabs() -> None:
    k = 100  # one rupee in paisa
    assert rules.annual_tax_minor(600_000 * k) == 0
    assert rules.annual_tax_minor(1_200_000 * k) == 30_000 * k  # 5% of 600k
    assert rules.annual_tax_minor(2_400_000 * k) == 30_000 * k + 180_000 * k  # 30k + 15% of 1.2M
    assert rules.annual_tax_minor(3_600_000 * k) == 210_000 * k + 300_000 * k
    assert rules.annual_tax_minor(4_800_000 * k) == 510_000 * k + 420_000 * k


def test_calc_payslip_full_month_no_absence() -> None:
    slip = rules.calc_payslip(
        basic_minor=10_000_000,
        working_days=22,
        attended_days=22,
        half_days=0,
        paid_leave_days=0,
        unpaid_leave_days=0,
    )
    assert slip["gross_minor"] == 15_000_000
    assert slip["absent_days"] == 0
    assert slip["deductions_minor"] == 0
    assert slip["net_minor"] == 15_000_000 - slip["tax_minor"]


def test_calc_payslip_absent_unpaid_and_half_day_deductions() -> None:
    slip = rules.calc_payslip(
        basic_minor=10_000_000,
        working_days=20,
        attended_days=17,  # 3 days: 1 absent, 1 unpaid leave, 1 half day
        half_days=1,
        paid_leave_days=1,
        unpaid_leave_days=1,
    )
    assert slip["absent_days"] == 1
    per_day = slip["per_day_minor"]
    # deductions = per_day x (1 absent + 1 unpaid + 0.5 half day)
    assert slip["deductions_minor"] == per_day * 5 // 2


def test_calc_payslip_fully_absent_month_never_goes_negative() -> None:
    """Regression: rounding must not push deductions above gross, and tax
    follows actual pay, so net is never negative."""
    slip = rules.calc_payslip(
        basic_minor=8_000_000,
        working_days=22,
        attended_days=0,
        half_days=0,
        paid_leave_days=0,
        unpaid_leave_days=0,
    )
    assert slip["absent_days"] == 22
    assert slip["deductions_minor"] == slip["gross_minor"]  # capped at gross
    assert slip["tax_minor"] == 0  # nothing paid, nothing taxed
    assert slip["net_minor"] == 0
