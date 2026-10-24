"""Input guardrail: a cheap, deterministic screen before any agent runs.

Pure pattern matching — no extra LLM call, so it costs microseconds.
It cannot understand language; it only catches obvious prompt-injection
phrases and clearly non-HR requests. Anything unclear is allowed through
and the tool allowlist + data rules remain the real defense.
"""

INJECTION_PATTERNS = [
    "ignore all instructions",
    "ignore previous instructions",
    "ignore instructions",
    "ignore the rules",
    "disregard instructions",
    "disregard the rules",
    "forget your instructions",
    "override your rules",
    "reveal your system prompt",
    "show your system prompt",
    "print your instructions",
    "jailbreak",
    "developer mode",
    "you are now a",
    "you are now an",
    "pretend to be",
    "act as if you are",
    "roleplay as",
]

OFF_TOPIC_PATTERNS = [
    "write me code",
    "write a poem",
    "write a story",
    "tell me a joke",
    "weather today",
    "stock market",
    "cricket score",
    "football score",
    "give me a recipe",
]

BLOCKED_MESSAGE = (
    "I can only help with HR topics: attendance, leave, payroll, and company "
    "policy questions. I also ignore any request that tries to change my rules."
)


def screen_input(text: str) -> tuple[bool, str]:
    """Return (blocked, reason). Cheap substring check on the lowered text."""
    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in lowered:
            return True, f"injection:{pattern}"
    for pattern in OFF_TOPIC_PATTERNS:
        if pattern in lowered:
            return True, f"off_topic:{pattern}"
    return False, ""
