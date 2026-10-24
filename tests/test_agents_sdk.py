"""Proof that the OpenAI Agents SDK is installed and importable.

No network, no API key, no model call — we only build an object.
"""

from agents import (
    Agent,
    GuardrailFunctionOutput,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    Runner,
    function_tool,
    input_guardrail,
)


def test_agents_sdk_imports_and_builds_an_agent() -> None:
    agent = Agent(name="smoke-test", instructions="Only a smoke test.")

    assert agent.name == "smoke-test"
    assert Runner is not None
    assert function_tool is not None
    assert input_guardrail is not None
    assert GuardrailFunctionOutput is not None
    assert RunContextWrapper is not None
    assert ModelSettings is not None
    assert RunConfig is not None
