"""Opus first, Sonnet when Bedrock cannot serve Opus: the Catalog and Support agents' model.

On the 2026-10-26 test event Bedrock answered the Opus profile's ConverseStream with
``serviceUnavailableException`` for about an hour while Sonnet answered every call, and every
Catalog and Support turn failed. A turn now falls back to the Sonnet profile when Bedrock refuses
Opus before the model has streamed any content, so nothing the shopper saw is repeated. Once a
turn has fallen back it stays on Sonnet; the agents are built per turn, so the next turn tries
Opus again. The switch is reported through ``on_fallback`` so the Builder view names the model
that answered, not the one configured.

On the AgentCore Runtime nobody sees the answer until the turn ends, so ``run_turn`` also
covers a refusal that arrives after Opus has started writing: Sonnet continues the turn from its
last finished step. In the app, where text reaches the shopper as it is written, that case still
fails.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Callable, Optional

from botocore.exceptions import ClientError
from strands.models.bedrock import BedrockModel
from strands.types.exceptions import ModelThrottledException

from services.specialist_models import specialist_model

logger = logging.getLogger(__name__)

# Bedrock's codes for "cannot serve this model right now", in both casings it uses.
UNAVAILABLE_CODES = frozenset({
    "serviceUnavailableException", "ServiceUnavailableException",
    "internalServerException", "InternalServerException",
    "modelNotReadyException", "ModelNotReadyException",
})


def bedrock_unavailable(error: BaseException) -> bool:
    """Whether Bedrock refused the call for capacity or availability, not for the request."""
    if isinstance(error, ModelThrottledException):
        return True
    if isinstance(error, ClientError):
        return error.response.get("Error", {}).get("Code") in UNAVAILABLE_CODES
    return False


class FallbackBedrockModel(BedrockModel):
    """A Bedrock model that moves to a second model when Bedrock cannot serve the first."""

    def __init__(self, *, fallback_model_id: str, fallback_max_tokens: int, **config: Any) -> None:
        super().__init__(**config)
        self.fallback_model_id = fallback_model_id
        self.fallback_max_tokens = fallback_max_tokens
        self.fell_back_from: Optional[str] = None
        self.on_fallback: Optional[Callable[[str, str], None]] = None

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        """Stream from the current model; on an early Bedrock refusal, stream from the fallback.

        Events before the first content block (``messageStart``) are held, so a refusal that
        arrives after them still leaves nothing to take back.
        """
        held: Optional[list[Any]] = []
        seen: list[str] = []
        try:
            async for event in super().stream(*args, **kwargs):
                if isinstance(event, dict) and len(seen) < 8:
                    seen.append(",".join(sorted(event)))
                if held is not None and isinstance(event, dict) and set(event) <= {"messageStart"}:
                    held.append(event)
                    continue
                for early in held or ():
                    yield early
                held = None
                yield event
            for early in held or ():
                yield early
        except Exception as error:
            if held is None or not bedrock_unavailable(error) or not self.can_fall_back():
                if bedrock_unavailable(error):
                    logger.warning("Bedrock could not serve %s mid-answer, after %s",
                                   self.config.get("model_id"), seen)
                raise
            self.fall_back(error)
            async for event in super().stream(*args, **kwargs):
                yield event

    def can_fall_back(self) -> bool:
        """Whether a fallback is left: the turn is not already on it."""
        current = self.config.get("model_id")
        return bool(self.fallback_model_id) and current != self.fallback_model_id

    def fall_back(self, error: BaseException) -> None:
        """Move the rest of this turn to the fallback model, and say so."""
        primary = str(self.config.get("model_id") or "")
        self.fell_back_from = primary
        self.update_config(model_id=self.fallback_model_id, max_tokens=self.fallback_max_tokens)
        logger.warning("Bedrock could not serve %s (%s); %s answers this turn",
                       primary, error, self.fallback_model_id)
        if self.on_fallback is not None:
            self.on_fallback(primary, self.fallback_model_id)


def refused_by_bedrock(error: BaseException) -> bool:
    """Whether Bedrock's refusal is anywhere in the cause chain (Strands wraps it)."""
    seen: set[int] = set()
    current: Optional[BaseException] = error
    while current is not None and id(current) not in seen:
        if bedrock_unavailable(current):
            return True
        seen.add(id(current))
        current = (getattr(current, "original_exception", None) or current.__cause__
                   or current.__context__)
    return False


def run_turn(agent: Any, prompt: str) -> Any:
    """Run a turn whose answer nobody sees until it ends, as on the AgentCore Runtime.

    There a refusal even mid-answer leaves nothing on screen to take back, so the fallback
    continues the turn from the conversation as it stands. Strands keeps each finished tool call
    with its result and drops only the half-written reply, so no tool runs twice and the audit
    keeps one row per call.
    """
    model = getattr(agent, "model", None)
    try:
        return agent(prompt)
    except Exception as error:
        messages = getattr(agent, "messages", None) or []
        resumable = bool(messages) and messages[-1].get("role") == "user"
        if not isinstance(model, FallbackBedrockModel) or not model.can_fall_back() \
                or not refused_by_bedrock(error) or not resumable:
            raise
        model.fall_back(error)
        return agent()


def specialist_bedrock_model(model_id: str, max_tokens: int) -> BedrockModel:
    """The Bedrock model for a specialist: the Sonnet profile is the fallback for any other."""
    fallback_id, fallback_max = specialist_model("sonnet")
    if not fallback_id or fallback_id == model_id:
        return BedrockModel(model_id=model_id, max_tokens=max_tokens)
    return FallbackBedrockModel(model_id=model_id, max_tokens=max_tokens,
                                fallback_model_id=fallback_id, fallback_max_tokens=fallback_max)


def answered_with(model: Any, configured: str) -> str:
    """The model that answered: the fallback's when the turn moved to it."""
    config = getattr(model, "config", None)
    used = config.get("model_id") if isinstance(config, dict) else None
    return str(used or configured)
