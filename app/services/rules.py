"""Pure business rules from the brief. No database, no HTTP — easy to test.

Money is integer paisa everywhere. Dates use the plain `date` type.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import (
    GROSS_MULTIPLIER_DEN,
    GROSS_MULTIPLIER_NUM,
    LATE_AFTER,
    MIN_FULL_DAY_HOURS,
    OFFICE_TIMEZONE,
    WEEKEND_DAYS,
)

_PKR = ZoneInfo(OFFICE_TIMEZONE)


def karachi_now(utc_now: datetime) -> datetime:
    """Convert a UTC timestamp to Karachi office time."""
    return utc_now.astimezone(_PKR)


def today_in_karachi(utc_now: datetime) -> date:
    """The office date for a given UTC moment (a date can differ from UTC date)."""
    return karachi_now(utc_now).date()


def is_weekend(day: date) -> bool:
    """Weekend is Saturday and Sunday."""
    return day.weekday() in WEEKEND_DAYS


def is_working_day(day: date, holidays: set[date]) -> bool:
    """A working day is not a weekend and not a known holiday."""
    return not is_weekend(day) and day not in holidays


def count_working_days(start: date, end: date, holidays: set[date]) -> int:
    """How many working days are in [start, end] inclusive."""
    if end < start:
        return 0
    count = 0
    day = start
    while day <= end:
        if is_working_day(day, holidays):
            count += 1
        day += timedelta(days=1)
    return count


def is_late(check_in_karachi: datetime) -> bool:
    """Late means checking in after 09:15 (09:00 plus 15 minutes grace)."""
    hh, mm = (int(part) for part in LATE_AFTER.split(":"))
    return check_in_karachi.time() > time(hh, mm)


def worked_hours(check_in: datetime, check_out: datetime) -> float:
    """Hours between check-in and check-out."""
    return (check_out - check_in).total_seconds() / 3600.0


def is_half_day(hours: float) -> bool:
    """A day with less than 5 worked hours is a half day."""
    return hours < MIN_FULL_DAY_HOURS


def div_round(numerator: int, denominator: int) -> int:
    """Integer division rounded to the nearest paisa (half rounds up)."""
    if denominator == 0:
        return 0
    return (2 * numerator + denominator) // (2 * denominator)


def gross_from_basic(basic_minor: int) -> int:
    """gross = 1.5 x basic (HRA 40% + medical 10% of basic). Integer paisa."""
    return div_round(basic_minor * GROSS_MULTIPLIER_NUM, GROSS_MULTIPLIER_DEN)


# Yearly tax slabs from the brief, on annual gross (paisa).
# (limit_minor, fixed_minor, rate_percent over the previous limit)
_TAX_SLABS: list[tuple[int, int, int]] = [
    (600_000 * 100, 0, 0),  # up to 600k: 0%
    (1_200_000 * 100, 0, 5),  # up to 1.2M: 5% over 600k
    (2_400_000 * 100, 30_000 * 100, 15),  # up to 2.4M: 30k + 15% over 1.2M
    (3_600_000 * 100, 210_000 * 100, 25),  # up to 3.6M: 210k + 25% over 2.4M
    (float("inf"), 510_000 * 100, 35),  # above 3.6M: 510k + 35%
]
_PREV_LIMITS = [0, 600_000 * 100, 1_200_000 * 100, 2_400_000 * 100, 3_600_000 * 100]


def annual_tax_minor(annual_gross_minor: int) -> int:
    """Yearly tax on annual gross using the brief's slabs (illustrative)."""
    for (limit, fixed, rate), prev in zip(_TAX_SLABS, _PREV_LIMITS, strict=True):
        if annual_gross_minor <= limit:
            return fixed + div_round((annual_gross_minor - prev) * rate, 100)
    return 0  # unreachable; inf slab always matches


def monthly_tax_minor(gross_minor: int) -> int:
    """Monthly tax: compute the yearly tax on gross x 12, then divide by 12."""
    return div_round(annual_tax_minor(gross_minor * 12), 12)


def calc_payslip(
    *,
    basic_minor: int,
    working_days: int,
    attended_days: int,
    half_days: int,
    paid_leave_days: int,
    unpaid_leave_days: int,
) -> dict:
    """Compute one payslip line. Pure function of its inputs.

    absent = expected working days - attended - leave days (never below 0).
    deductions = gross x (absent + unpaid + 0.5 x half days) / working days,
    capped at gross, so net pay can never go negative.
    """
    absent = max(working_days - attended_days - paid_leave_days - unpaid_leave_days, 0)
    gross = gross_from_basic(basic_minor)
    per_day = div_round(gross, working_days) if working_days > 0 else 0
    # Deductions are computed from gross directly (not per_day x days) so that
    # rounding never accumulates beyond the full gross; 0.5 x half days stays
    # exact by doubling everything, then dividing once. Capped at gross.
    if working_days > 0:
        deductions = div_round(
            gross * (2 * absent + 2 * unpaid_leave_days + half_days),
            2 * working_days,
        )
    else:
        deductions = 0
    deductions = min(deductions, gross)
    # Tax follows the brief's slabs, applied to what is actually paid this month.
    taxable = max(gross - deductions, 0)
    tax = monthly_tax_minor(taxable)
    net = gross - deductions - tax
    return {
        "working_days": working_days,
        "paid_days": max(working_days - absent - unpaid_leave_days, 0),
        "absent_days": absent,
        "unpaid_days": unpaid_leave_days,
        "half_days": half_days,
        "basic_minor": basic_minor,
        "gross_minor": gross,
        "per_day_minor": per_day,
        "deductions_minor": deductions,
        "tax_minor": tax,
        "net_minor": net,
    }
