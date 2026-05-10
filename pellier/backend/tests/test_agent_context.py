"""Tests for AgentContext — trace_index + emit_panel shape.

``trace_index`` is the stable referent for frontend citation pills.
Ordering + monotonicity + panel-only scope are contract surfaces —
the Atelier chat's ``[trace N]`` citation pills read directly from
this field, so drift would break every citation link.
"""

from __future__ import annotations

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
        agent="memory",
        tag="MEMORY · PROCEDURAL",
        title="What similar customers bought",
        sql="SELECT * FROM orders",
        columns=["bean", "count"],
        rows=[["Sumatra", "2"]],
        meta="one JOIN",
        duration_ms=13,
        tag_class="cyan",
    )
    panel = ctx.events[0]
    assert panel["type"] == "panel"
    assert panel["tag"] == "MEMORY · PROCEDURAL"
    assert panel["tag_class"] == "cyan"
    assert panel["rows"] == [["Sumatra", "2"]]
    assert panel["duration_ms"] == 13
    assert panel["trace_index"] == 1
