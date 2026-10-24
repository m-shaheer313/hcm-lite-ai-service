"""Number-grounding checks. Pure functions.

An AI answer may only use numbers that come from trusted server-side text:
tool results, the policy file, or dates the server itself provided.
"""

import re

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _normalize(text: str) -> set[str]:
    """All number tokens of a text, without commas."""
    return {match.replace(",", "") for match in _NUMBER_RE.findall(text)}


def find_ungrounded_numbers(answer: str, allowed_text: str) -> list[str]:
    """Every number in the answer (even 1 digit) that is not in allowed_text.

    Dates decompose naturally: "2026-10-26" yields the tokens 2026, 10 and 26,
    so quoting a date from the tool output is automatically allowed.
    """
    return sorted(_normalize(answer) - _normalize(allowed_text))
