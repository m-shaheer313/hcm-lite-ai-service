"""Tests for deterministic date resolution (no LLM, no key)."""

from datetime import UTC, date

from app.services import resolve_dates as rd


def test_next_weekday_strictly_after_today() -> None:
    # Today is Monday 2026-10-26: "next Monday" is 7 days later.
    assert rd.next_weekday(date(2026, 10, 26), 0) == date(2026, 11, 2)
    # Today is Sunday: "next Monday" is tomorrow.
    assert rd.next_weekday(date(2026, 10, 25), 0) == date(2026, 10, 26)
    # Today is Wednesday: "next Friday" is in 2 days.
    assert rd.next_weekday(date(2026, 10, 28), 4) == date(2026, 10, 30)
    # Non-strict allows today itself.
    assert rd.next_weekday(date(2026, 10, 26), 0, strict=False) == date(2026, 10, 26)


def test_resolve_next_monday_for_several_todays() -> None:
    cases = {
        date(2026, 10, 24): date(2026, 10, 26),  # Saturday -> this Monday
        date(2026, 10, 25): date(2026, 10, 26),  # Sunday -> this Monday
        date(2026, 10, 26): date(2026, 11, 2),  # Monday -> next week's Monday
        date(2026, 10, 30): date(2026, 11, 2),  # Friday -> next Monday
    }
    for today, expected in cases.items():
        assert rd.resolve_phrase("next Monday", today) == expected, today


def test_resolve_relative_words_english_and_roman_urdu() -> None:
    today = date(2026, 10, 26)  # Monday
    assert rd.resolve_phrase("today", today) == today
    assert rd.resolve_phrase("aaj", today) == today
    assert rd.resolve_phrase("tomorrow", today) == date(2026, 10, 27)
    assert rd.resolve_phrase("kal", today) == date(2026, 10, 27)
    assert rd.resolve_phrase("day after tomorrow", today) == date(2026, 10, 28)
    assert rd.resolve_phrase("parso", today) == date(2026, 10, 28)
    assert rd.resolve_phrase("Tuesday", today) == date(2026, 10, 27)
    assert rd.resolve_phrase("agle somwar", today) == date(2026, 11, 2)  # next Monday
    assert rd.resolve_phrase("mangal", today) == date(2026, 10, 27)  # Tuesday
    assert rd.resolve_phrase("jumma", today) == date(2026, 10, 30)  # Friday


def test_resolve_next_week_is_next_monday() -> None:
    assert rd.resolve_phrase("next week", date(2026, 10, 26)) == date(2026, 11, 2)
    assert rd.resolve_phrase("next week", date(2026, 10, 31)) == date(2026, 11, 2)


def test_resolve_unknown_phrase_returns_none() -> None:
    assert rd.resolve_phrase("someday maybe", date(2026, 10, 26)) is None


def test_office_timezone_rules_at_0920_pkt() -> None:
    """09:20 PKT is 04:20 UTC: late. 09:10 PKT (04:10 UTC) is on time."""
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    from app.services import rules

    karachi = ZoneInfo("Asia/Karachi")
    late = datetime(2026, 10, 26, 4, 20, tzinfo=UTC).astimezone(karachi)
    on_time = datetime(2026, 10, 26, 4, 10, tzinfo=UTC).astimezone(karachi)

    assert late.time() == time(9, 20) and rules.is_late(late)
    assert on_time.time() == time(9, 10) and not rules.is_late(on_time)

    # The office DATE also follows Karachi, not UTC: 20:30 UTC is the next day.
    night_utc = datetime(2026, 10, 26, 20, 30, tzinfo=UTC)
    assert rules.today_in_karachi(night_utc) == date(2026, 10, 27)
