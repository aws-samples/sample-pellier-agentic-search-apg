"""Tests for AgentContext — trace_index + emit_panel shape.

``trace_index`` is the stable referent for frontend citation pills.
Ordering + monotonicity + panel-only scope are contract surfaces —
the Observatory chat's ``[trace N]`` citation pills read directly from
this field, so drift would break every citation link.
"""

from __future__ import annotations

import re

from services.agent_context import AgentContext


def test_trace_index_increments_across_emit_panel() -> None:
    """Each ``emit_panel`` call stamps a 1-based trace_index in order."""
    ctx = AgentContext(session_id="s1", query="q")
    ctx.emit_panel(agent="a", tag="T1", title="one")
    ctx.emit_panel(agent="a", tag="T2", title="two")
    ctx.emit_panel(agent="a", tag="T3", title="three")

    panels = [e for e in ctx.events if e["type"] == "panel"]
    assert [p["trace_index"] for p in panels] == [1, 2, 3]


def test_trace_index_is_scoped_to_panel_events_only() -> None:
    """Plan / step / response events MUST NOT carry trace_index —
    only panels get cited."""
    ctx = AgentContext(session_id="s1", query="q")
    ctx.emit_plan(steps=["a", "b"])
    ctx.step_active()
    ctx.emit_panel(agent="a", tag="T1", title="one")
    ctx.step_done()
    ctx.emit_response(text="done")

    for ev in ctx.events:
        if ev["type"] == "panel":
            assert "trace_index" in ev
        else:
            assert "trace_index" not in ev


def test_trace_index_survives_interleaved_steps() -> None:
    """Step events between panel emits must not advance the panel
    counter — otherwise ``trace_index`` would skip."""
    ctx = AgentContext(session_id="s1")
    ctx.emit_plan(steps=["a", "b", "c"])
    ctx.step_active()
    ctx.emit_panel(agent="x", tag="A", title="a")
    ctx.step_done()
    ctx.step_active()
    ctx.emit_panel(agent="x", tag="B", title="b")
    ctx.step_done()
    ctx.step_active()
    ctx.emit_panel(agent="x", tag="C", title="c")

    panels = [e for e in ctx.events if e["type"] == "panel"]
    assert [p["trace_index"] for p in panels] == [1, 2, 3]


def test_emit_panel_carries_tag_class_and_rows() -> None:
    """Sanity check the panel shape is otherwise unchanged."""
    ctx = AgentContext(session_id="s1")
    ctx.emit_panel(
        agent="evidence",
        tag="OPERATIONAL · TOOL HISTORY",
        title="Tool activity",
        sql="SELECT tool, count(*) FROM pellier.tool_audit GROUP BY tool",
        columns=["tool", "count"],
        rows=[["check_stock", "2"]],
        meta="live aggregate",
        duration_ms=13,
        tag_class="cyan",
    )
    panel = ctx.events[0]
    assert panel["type"] == "panel"
    assert panel["tag"] == "OPERATIONAL · TOOL HISTORY"
    assert panel["tag_class"] == "cyan"
    assert panel["rows"] == [["check_stock", "2"]]
    assert panel["duration_ms"] == 13
    assert panel["trace_index"] == 1


def test_the_agent_route_mints_a_turn_id() -> None:
    """The lineage's first link, and it was missing on the route the SPA uses.

    `services/chat.py` mints the turn id in both of its entry points, and its own
    comment says why: without it "a governed-boundary refusal produced an operator
    review with no source turn". That fix never reached `routes/agent.py`, so a real
    Theo return handoff landed in `pellier.approvals` with `source_turn_id = NULL`.
    """
    import pathlib

    source = pathlib.Path("routes/agent.py").read_text()
    stream = source[source.index("async def _stream_agent_response("):]
    stream = stream[: stream.index("\n@router")] if "\n@router" in stream else stream

    assert "from services.turn_identity import new_turn_id, turn_id_var" in stream
    assert "turn_id_var.set(turn_id)" in stream
    # Minted BEFORE the orchestrator runs, or a tool cannot read it.
    assert stream.index("turn_id_var.set(turn_id)") < stream.index("run_agent")
    # Reuses an id already in context rather than overwriting one.
    assert "turn_id_var.get() or new_turn_id()" in stream
    # And it is emitted, so a client can correlate what the turn produced.
    assert '"turn_id": turn_id' in stream


def test_the_person_handoff_reads_the_turn_id_from_context() -> None:
    """The review handoff must not invent or omit lineage."""
    import pathlib

    tools = pathlib.Path("services/agent_tools.py").read_text()
    handoff = tools[tools.index("def ask_a_person("):]
    next_tool = handoff.find("\n@tool")
    handoff = handoff if next_tool < 0 else handoff[:next_tool]
    assert re.search(
        r"from services\.turn_identity import \(\s*current_authorized_customer_id,"
        r"\s*current_principal_sub,\s*current_turn_id,\s*\)",
        handoff,
    )
    assert "source_turn_id=current_turn_id()" in handoff
