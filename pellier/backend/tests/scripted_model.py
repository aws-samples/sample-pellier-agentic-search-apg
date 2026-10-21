"""A Strands model that asks for scripted tool calls, then answers.

Only the model is fake. The agent, its tool executor, the decorated tools and
the hooks are Strands' own, so a test sees the ``AfterToolCallEvent`` Strands
really builds for a call that raised, failed validation, named a tool the agent
does not hold, was cancelled, or came back as an error result.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Sequence, Tuple

from strands.models import Model

ToolCall = Tuple[str, Dict[str, Any]]


class ScriptedModel(Model):
    """Asks for ``calls`` in its first turn, all at once, and says ``answer`` in its second.

    Args:
        calls: ``(tool name, input)`` for each tool use, in order.
        answer: The text of the final turn.
    """

    def __init__(self, calls: Sequence[ToolCall], answer: str = "Done.") -> None:
        self.calls: List[ToolCall] = list(calls)
        self.answer = answer
        self.turns = 0

    def update_config(self, **_model_config: Any) -> None:
        return None

    def get_config(self) -> Dict[str, Any]:
        return {"model_id": "scripted"}

    async def structured_output(self, *_args: Any, **_kwargs: Any) -> AsyncIterator[Any]:
        raise NotImplementedError("the scripted model has no structured output")
        yield  # pragma: no cover - makes this an async generator

    async def stream(self, messages: Any, tool_specs: Any = None, system_prompt: Any = None,
                     **_kwargs: Any) -> AsyncIterator[Dict[str, Any]]:
        self.turns += 1
        yield {"messageStart": {"role": "assistant"}}
        if self.turns == 1 and self.calls:
            for index, (name, tool_input) in enumerate(self.calls):
                yield {"contentBlockStart": {"start": {"toolUse": {
                    "name": name, "toolUseId": f"use-{index}"}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {
                    "input": json.dumps(tool_input)}}}}
                yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
            return
        yield {"contentBlockDelta": {"delta": {"text": self.answer}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
