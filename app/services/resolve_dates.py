"""Deterministic date resolution for smart leave. Pure functions.

The LLM NEVER does date maths. It only copies out day phrases; this module
turns them into exact dates using "today" in the office timezone
(Asia/Karachi), which the caller provides.

Rules:
- "next <weekday>" (or "agle <weekday>") = the first such weekday STRICTLY
  after today. A bare "<weekday>" means the same: the coming one.
- "next week" = Monday of next week.
- English and Roman Urdu day words are both supported.
"""

import re
from datetime import date, timedelta

WEEKDAY_WORDS: dict[str, int] = {
    # English + Roman Urdu
    "monday": 0,
    "somwar": 0,
    "somvaar": 0,
    "tuesday": 1,
    "mangal": 1,
    "mangalwar": 1,
    "wednesday": 2,
    "budh": 2,
    "budhwar": 2,
    "thursday": 3,
    "jumerat": 3,
    "jummerat": 3,
    "friday": 4,
    "jumma": 4,
    "juma": 4,
    "saturday": 5,
    "hafta": 5,
    "hafte": 5,
    "sunday": 6,
    "itwar": 6,
    "etwar": 6,
}

NEXT_MARKERS = {"next", "agle", "agla", "agli", "aglae"}
TODAY_WORDS = {"today", "aaj"}
TOMORROW_WORDS = {"tomorrow", "kal"}
DAY_AFTER_WORDS = {"parso", "perso", "parson"}

_TOKEN_RE = re.compile(r"[a-z]+")


def next_weekday(today: date, target: int, *, strict: bool = True) -> date:
    """The first `target` weekday strictly after today (or today itself when
    strict=False and today already is that weekday)."""
    offset = (target - today.weekday()) % 7
    if offset == 0 and strict:
        offset = 7
    return today + timedelta(days=offset)


def next_monday(today: date) -> date:
    """Monday of next week (always strictly after today)."""
    return next_weekday(today, 0, strict=True)


def resolve_phrase(phrase: str, today: date) -> date | None:
    """Turn one day phrase into an exact date, or None if not understood."""
    tokens = _TOKEN_RE.findall(phrase.lower())
    if not tokens:
        return None
    joined = " ".join(tokens)

    if "day after tomorrow" in joined or tokens[-1] in DAY_AFTER_WORDS:
        return today + timedelta(days=2)
    if "tomorrow" in tokens or "kal" in tokens:
        return today + timedelta(days=1)
    if tokens[-1] in TODAY_WORDS or "today" in tokens:
        return today
    if "next week" in joined or joined in {"agle hafte", "agla hafte", "agli hafta"}:
        return next_monday(today)

    for token in tokens:
        if token in WEEKDAY_WORDS:
            return next_weekday(today, WEEKDAY_WORDS[token], strict=True)
    return None
