"""A fake model for tests: no API key, no network.

Scripted responses are returned in order (the last one repeats). A response
can be plain text or a tool-call step, so tests can exercise the real
agent loop including tool execution.
"""

from typing import Any

from agents import Model, ModelResponse, Usage


def text_response(text: str) -> list[dict]:
    """A plain assistant message (Responses-API item shape)."""
    return [
        {
            "type": "message",
            "id": "msg_fake",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
    ]


def tool_call(name: str, arguments: str = "{}") -> list[dict]:
    """A function-call step; the SDK will run the real tool and continue."""
    return [
        {
            "type": "function_call",
            "id": "fc_fake",
            "call_id": "call_1",
            "name": name,
            "arguments": arguments,
        }
    ]


class FakeModel(Model):
    """A real Agents-SDK Model with scripted outputs: no key, no network.

    Subclassing Model is required so the SDK recognizes it as a model,
    not a model name string.
    """

    def __init__(self, steps: list[list[dict]] | None = None) -> None:
        self.steps = steps or [text_response("Hello from the fake model.")]
        self.calls: list[dict] = []  # what the runner asked, for assertions

    async def get_response(
        self,
        system_instructions: str | None,
        input: Any,
        model_settings: Any,
        tools: Any,
        tool_choice: Any = None,
        usage: Any = None,
        **kwargs: Any,
    ) -> ModelResponse:
        self.calls.append(
            {
                "system_instructions": system_instructions,
                "input": input,
                "tools": tools,
            }
        )
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        return ModelResponse(output=step, usage=Usage(), response_id=f"fake-{len(self.calls)}")

    def stream_response(self, *args: Any, **kwargs: Any) -> Any:
        """Not needed: chat runs are not streamed in this project."""
        raise NotImplementedError("FakeModel does not support streaming")


class SlowFakeModel(FakeModel):
    """Always too slow — used to test the timeout path."""

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        import asyncio

        await asyncio.sleep(5)
        return await super().get_response(*args, **kwargs)
