"""
SkillRouter — one-call LLM decider.

Given a user message and the registry's library of skills, the router
asks a fast model (Haiku 4.5) which skills to load for this turn. One
LLM call. No embeddings, no scoring, no multi-call cascades. The skill
descriptions ARE the activation contract — the router trusts them.

The output feeds two consumers:
  - The specialist agents, which inject loaded skill bodies into
    their system prompts via ``inject_skills()``
  - The SSE stream, which emits a ``skill_routing`` event so the
    Atelier UI can render the live activation log and the storefront
    can render the minimal attribution line

Parse behavior is defensive on purpose: Haiku at temperature 0.0 is
reliable, but the workshop is unforgiving of demo-time parse errors.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

from .models import RouterDecision, Skill
from .registry import SkillRegistry

logger = logging.getLogger(__name__)

# Fast, cheap routing model. Haiku 4.5 lands ~280-400ms per call which
# sits under our per-turn budget. Kept separate from the orchestrator
# model id (which is also Haiku today) so the two can diverge later
# without touching the router.
_ROUTER_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


_ROUTER_PROMPT_HEADER = """You are a skill router for an editorial boutique's AI agent.

Given a user message and a library of available skills (each with a name and an activation description), decide which skills should be loaded for this turn.

Load a skill only if its activation description clearly matches the message. Be conservative — extra skills cost tokens. If no skill matches, return an empty load array.

Respond with a single JSON object, nothing else:

{
  "load": ["skill-name", ...],
  "considered": [
    {"name": "skill-name", "reason": "brief explanation of why rejected or evaluated"}
  ]
}

The "load" array is the only field that drives behavior. The "considered" array is for auditing — include every skill you evaluated, whether loaded or not, with a short reason.

Available skills:
"""


class SkillRouter:
    """
    One-call skill router. Construct once with the registry; call
    ``route()`` per turn.
    """

    def __init__(
        self,
        registry: SkillRegistry,
        model_id: str = _ROUTER_MODEL_ID,
    ) -> None:
        self._registry = registry
        self._model_id = model_id
        self._agent = None  # Lazy — avoid Bedrock client init at import time

    def _build_prompt(self) -> str:
        """Compose the router system prompt with every skill's name/description."""
        skills = self._registry.get_all()
        lines = [_ROUTER_PROMPT_HEADER]
        for skill in skills:
            lines.append(f"- {skill.name}: {skill.description}")
        return "\n".join(lines)

    def _get_agent(self):
        """
        Build (or return cached) the Strands Agent used for routing.

        We construct a tool-free Agent with Haiku 4.5 at temperature 0.0
        and a fixed system prompt. The skill library is baked into the
        system prompt at construction time; when a skill is added at
        runtime we'd need to reset this cache (not a v1 concern — the
        registry loads at boot).
        """
        if self._agent is not None:
            return self._agent

        from strands import Agent
        from strands.models import BedrockModel

        self._agent = Agent(
            model=BedrockModel(
                model_id=self._model_id,
                max_tokens=512,
                temperature=0.0,
            ),
            system_prompt=self._build_prompt(),
            tools=[],
        )
        return self._agent

    def route(
        self,
        user_message: str,
        context: Optional[str] = None,
    ) -> RouterDecision:
        """
        Ask the router which skills to load for this message.

        Parameters:
            user_message: The current user message (primary input)
            context: Optional last 1-2 messages of prior context

        Returns:
            A ``RouterDecision``. On any parse failure or Bedrock error,
            returns an empty decision — skills stay dormant, the agent
            proceeds with its base prompt. Never raises to the caller.
        """
        message = (user_message or "").strip()
        if not message:
            return RouterDecision.empty(user_message)

        if len(self._registry) == 0:
            # Nothing to route. Short-circuit rather than burn a Bedrock call.
            return RouterDecision.empty(message)

        prompt = message
        if context:
            prompt = f"Prior context:\n{context.strip()}\n\nCurrent message:\n{message}"

        start = time.perf_counter()
        raw = ""
        try:
            agent = self._get_agent()
            result = agent(prompt)
            raw = str(result)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "Skill router failed after %dms: %s", elapsed_ms, exc
            )
            decision = RouterDecision.empty(message)
            decision.elapsed_ms = elapsed_ms
            return decision

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return self._parse(raw, elapsed_ms, message)

    def _parse(
        self,
        raw: str,
        elapsed_ms: int,
        user_message: str,
    ) -> RouterDecision:
        """
        Defensive JSON parser. Strips markdown fences, extracts the
        first JSON object, validates skill names against the registry,
        falls back to an empty decision on any failure.
        """
        parsed = _extract_json_object(raw)
        if parsed is None:
            logger.warning(
                "Skill router returned unparseable response (elapsed=%dms): %r",
                elapsed_ms,
                raw[:500],
            )
            decision = RouterDecision.empty(user_message)
            decision.elapsed_ms = elapsed_ms
            decision.raw_response = raw[:2000]
            return decision

        load_raw = parsed.get("load", []) if isinstance(parsed, dict) else []
        considered_raw = parsed.get("considered", []) if isinstance(parsed, dict) else []

        # Validate loaded names against the registry — drop anything
        # unknown. The router sometimes hallucinates skill names from
        # the message even when explicitly told the library.
        loaded: list[str] = []
        if isinstance(load_raw, list):
            for name in load_raw:
                if isinstance(name, str) and name in self._registry:
                    loaded.append(name)
                elif isinstance(name, str):
                    logger.info(
                        "Router loaded unknown skill %r — dropping", name
                    )

        # The considered list is for the Atelier UI's live log. Keep
        # shape stable: each entry is {name: str, reason: str}.
        considered: list[dict] = []
        if isinstance(considered_raw, list):
            for item in considered_raw:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                reason = item.get("reason", "")
                if isinstance(name, str) and isinstance(reason, str):
                    considered.append({"name": name, "reason": reason})

        return RouterDecision(
            loaded_skills=loaded,
            considered=considered,
            elapsed_ms=elapsed_ms,
            raw_response=raw[:2000],
            user_message=user_message[:500],
        )

    def loaded_skill_objects(self, decision: RouterDecision) -> list[Skill]:
        """
        Look up the Skill objects for a decision's loaded names.
        Convenience — the agent pipeline needs the full objects to
        inject bodies, not just names.
        """
        objs = []
        for name in decision.loaded_skills:
            skill = self._registry.get(name)
            if skill is not None:
                objs.append(skill)
        return objs


# ---------------------------------------------------------------------------
# JSON extraction — defensive parsing
# ---------------------------------------------------------------------------

_MARKDOWN_FENCE_RE = re.compile(r"```(?:json)?\s*\n?|\n?```", re.IGNORECASE)


def _extract_json_object(raw: str) -> Optional[dict]:
    """
    Pull the first JSON object out of a model response.

    Strategy:
      1. Strip markdown fences (\`\`\`json ... \`\`\`)
      2. Find the first '{' and walk to its matching '}'
      3. json.loads the resulting substring
      4. Return None on any failure

    Handles common response shapes:
      - Pure JSON
      - JSON wrapped in markdown fences
      - JSON with a prose preamble ("Here's the routing decision: {...}")
      - JSON with a prose postamble
    """
    if not raw:
        return None

    cleaned = _MARKDOWN_FENCE_RE.sub("", raw).strip()
    start = cleaned.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(cleaned[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start : i + 1]
                try:
                    obj = json.loads(candidate)
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None
