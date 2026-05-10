"""AgentContext — structured telemetry emission for the /workshop route.

Wraps a single workshop turn (customer_id + query + session_id). Agents emit
plain-dict events through a small set of helpers. The FastAPI layer serialises
the events list as the turn response; the React frontend replays them with
per-event animation beats (plan decomposes first, steps tick queued→active→done,
panels stream in, response closes).

Contract is frozen — matches the Coffee Roastery reference
(``conferences/2026-postgresconf-agentic-ai/agents.py``) so the frontend
renderer ports 1:1. See ``docs/pellier-telemetry-audit.md`` Section 4
for the Pellier panel plan: 13 panels on the standard showcase
query, 14 on the approval-gated path (adds ``GUARDRAIL · APPROVAL``).
Query-shape-dependent — a lightweight "linen pieces" query emits ~6,
while the headline cohort-overlap query emits the full 13. MEMORY ·
CONFIDENCE is a deterministic panel computed from upstream panel row
coverage (no LLM introspection) and emits between GROUNDING and
LLM · OPUS · SYNTHESIZE.

Not every turn emits every event type. Minimum wire shape is
``{session_id, events: [{type: "response", ...}]}`` — i.e., a bare response
with no plan / steps / panels still validates. Panels layer in as the
orchestrator and specialists get instrumented (Weeks 2-6).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentContext:
    """One turn of workshop telemetry.

    Parameters
    ----------
    session_id:
        Stable across turns in a /workshop session. The client persists it
        in localStorage and passes it back on subsequent requests.
    customer_id:
        Demo customer id (seeded in ``customers`` table). The recommendation
        agent's ``MEMORY · PROCEDURAL`` query uses this as the ``<> %s``
        exclusion so the cohort-overlap result doesn't include the caller.
        Defaults to ``anonymous`` for unauthenticated /workshop visits.
    query:
        The raw user message for this turn. Stored here so emitters can
        echo it back into panel meta lines without the caller threading it
        through every emit_panel call.
    events:
        Accumulating list of event dicts. Caller reads this at end-of-turn
        to serialise as the HTTP response body.
    """

    session_id: str
    customer_id: str = "anonymous"
    query: str = ""
    events: list[dict] = field(default_factory=list)
    _plan_step_index: int = 0
    _panel_index: int = 0

    # -- base emitter --------------------------------------------------------
    def emit(self, ev: dict) -> None:
        """Append one raw event dict. Stamps monotonic ``ts_ms`` for ordering.

        Prefer the typed helpers (``emit_plan``, ``emit_panel``, etc.) over
        calling this directly — they build the correct shape for the
        frontend renderer. Kept public for future event types (e.g.
        ``reasoning`` or ``citation``) that would otherwise need a new
        helper each time.
        """
        ev["ts_ms"] = int(time.time() * 1000)
        self.events.append(ev)

    # -- plan decomposition --------------------------------------------------
    def emit_plan(
        self,
        steps: list[str],
        duration_ms: int = 0,
        title: Optional[str] = None,
    ) -> None:
        """Emit the PLAN card shown first on screen.

        Renders as a numbered list with every step in the ``queued`` state.
        Subsequent ``step_active`` / ``step_done`` calls flip state in
        order. Resetting ``_plan_step_index`` here lets a single turn
        emit multiple plans (e.g., replan after a tool error) — each new
        plan starts its step counter from zero.
        """
        self._plan_step_index = 0
        self.emit(
            {
                "type": "plan",
                "title": title or "Plan",
                "steps": list(steps),
                "duration_ms": duration_ms,
            }
        )

    def step_active(self, index: Optional[int] = None) -> None:
        """Mark a step active.

        When ``index`` is None, flips the next queued step. Callers that
        emit panels between steps in parallel can pass an explicit index
        to flip non-sequentially.
        """
        self.emit(
            {
                "type": "step",
                "index": index if index is not None else self._plan_step_index,
                "state": "active",
            }
        )

    def step_done(self, index: Optional[int] = None) -> None:
        """Mark a step done. Auto-advances the internal pointer when no
        explicit ``index`` is supplied, matching Coffee Roastery's
        ``step_done()`` ergonomics."""
        step_idx = index if index is not None else self._plan_step_index
        self.emit(
            {
                "type": "step",
                "index": step_idx,
                "state": "done",
            }
        )
        if index is None:
            self._plan_step_index += 1

    # -- data panels ---------------------------------------------------------
    def emit_panel(
        self,
        *,
        agent: str,
        tag: str,
        title: str,
        sql: str = "",
        columns: Optional[list[str]] = None,
        rows: Optional[list[list[str]]] = None,
        meta: str = "",
        duration_ms: int = 0,
        tag_class: str = "cyan",
    ) -> None:
        """Emit one telemetry panel for a DB or LLM operation.

        ``tag_class`` maps to a pill colour: cyan (data op — pgvector,
        Gateway, Memory), amber (LLM / Guardrail), green (grounding /
        success). Any other value falls back to cyan on the renderer side.
        ``rows`` should be pre-stringified — the renderer does ``esc()``
        on each cell and nothing else.

        ``trace_index`` is a monotonically-incrementing 1-based counter
        stamped on every panel in the order they're emitted. The
        frontend uses it as the stable referent for citation pills —
        an LLM-synthesised sentence carrying ``[trace 7]`` resolves
        to the 7th panel emitted this turn. Tied to panel events
        specifically (not plan / step / response) because only panels
        get cited.
        """
        self._panel_index += 1
        self.emit(
            {
                "type": "panel",
                "agent": agent,
                "tag": tag,
                "tag_class": tag_class,
                "title": title,
                "sql": sql,
                "columns": list(columns) if columns else [],
                "rows": list(rows) if rows else [],
                "meta": meta,
                "duration_ms": duration_ms,
                "trace_index": self._panel_index,
            }
        )

    # -- narrative text fragments --------------------------------------------
    def emit_text(self, text: str) -> None:
        """Emit a short narrative text fragment that interleaves with panels.

        These are NOT the final response — they're brief status lines
        ("Looking through your history...") that appear in the chat column
        between tool chips, giving the replay a conversational cadence.
        The final composed answer is still ``emit_response()``.
        """
        self.emit({"type": "text", "text": text})

    # -- final response ------------------------------------------------------
    def emit_response(
        self,
        text: str,
        citations: Optional[list[dict]] = None,
        confidence: Optional[float] = None,
    ) -> None:
        """Close the turn with the composed assistant text.

        ``citations`` is a list of ``{k: <key>, ref: <panel_tag>}`` dicts
        for the ``<cite data-k="...">`` tokens the renderer links back to
        panels. Empty list is fine for turns without citations.
        """
        self.emit(
            {
                "type": "response",
                "text": text,
                "citations": list(citations) if citations else [],
                "confidence": confidence,
            }
        )
