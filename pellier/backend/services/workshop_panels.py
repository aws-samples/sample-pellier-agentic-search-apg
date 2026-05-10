"""workshop_panels — shared helpers that turn service calls into Card 7 panels.

Each helper takes an ``AgentContext`` + the raw inputs, performs the
underlying work (or detects a skip condition), and emits a panel event.
Returning the raw result alongside the emission means the orchestrator
can still use the value (e.g. a Gateway tool list feeding follow-up
routing logic).

Two panels for Week 2 Card 7:

- ``TOOL REGISTRY · DISCOVER`` — pgvector query against the ``tools``
  table. Always runs on workshop turns (Aurora is the teaching surface).
- ``GATEWAY · DISCOVER`` — MCP ``list_tools`` against the configured
  Gateway URL. Emits a "skipped" panel when ``AGENTCORE_GATEWAY_URL``
  is unset so attendees can tell the difference between dual-rank
  (Gateway present) and single-source (Gateway absent) at a glance.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from config import settings
from services.agent_context import AgentContext
from services.tool_registry import discover_tools

logger = logging.getLogger(__name__)


async def emit_tool_registry_panel(
    ctx: AgentContext,
    *,
    db_service: Any,
    query_embedding: List[float],
    limit: int = 3,
) -> Dict[str, Any]:
    """Run pgvector tool discovery and emit a ``TOOL REGISTRY · DISCOVER`` panel.

    Always runs — this is the Aurora-teaching surface. Even when the
    table is empty (seeder not run yet), we still emit a panel, just
    with zero rows and a clear meta line telling the attendee to run
    the seeder. Silent no-ops are the wrong shape for a teaching surface.
    """
    result = await discover_tools(db_service, query_embedding, limit=limit)
    rows_render: List[List[str]] = []
    for r in result["rows"]:
        rows_render.append(
            [
                str(r.get("name", "")),
                f"{r.get('similarity', 0.0):.3f}",
            ]
        )

    meta_parts: List[str] = []
    if result.get("error"):
        meta_parts.append(
            f'<span style="color:#b45309">error: {result["error"]}</span>'
        )
    meta_parts.append(
        f'{result.get("total_count", 0)} tool(s) indexed, '
        f"top-{limit} by cosine similarity"
    )
    if result.get("total_count", 0) == 0 and not result.get("error"):
        meta_parts.append(
            '<span style="color:#b45309">run <code>python scripts/seed_tool_registry.py</code> to populate</span>'
        )

    ctx.emit_panel(
        agent="tool-registry",
        tag="TOOL REGISTRY · DISCOVER",
        tag_class="cyan",
        title="pgvector tool ranking · Aurora",
        sql=result["sql"],
        columns=["name", "similarity"],
        rows=rows_render,
        meta=" · ".join(meta_parts),
        duration_ms=int(result["duration_ms"]),
    )
    return result


def emit_gateway_panel(
    ctx: AgentContext,
    *,
    query_text: str,
) -> Dict[str, Any]:
    """Emit a ``GATEWAY · DISCOVER`` panel describing what Gateway would return.

    This deliberately does NOT invoke Gateway per-turn for ranked
    results — Gateway's ``list_tools`` returns the full catalog, not
    a ranking. The side-by-side teaching moment on Card 7 is:

        "Aurora ranked these tools for THIS query.
         Gateway publishes these tools, with descriptions;
         the runtime's MCP client picks one per the model's own judgement."

    When ``AGENTCORE_GATEWAY_URL`` is unset, we emit a "skipped" panel
    so Card 7 can show attendees that the single-source (Aurora only)
    rendering is deliberate, not a bug.

    The actual live tool list for Card 7 comes from the existing
    ``/api/agentcore/gateway/tools`` endpoint — we don't re-fetch here
    because Card 7 does its own fetch on open.
    """
    gateway_url = settings.AGENTCORE_GATEWAY_URL
    if not gateway_url:
        ctx.emit_panel(
            agent="gateway",
            tag="GATEWAY · DISCOVER",
            tag_class="amber",
            title="MCP tool discovery · AgentCore Gateway",
            sql="",
            columns=[],
            rows=[],
            meta=(
                '<span style="color:#b45309">'
                "AGENTCORE_GATEWAY_URL not set — Gateway skipped. "
                "Card 7 renders Aurora ranking only."
                "</span>"
            ),
            duration_ms=0,
        )
        return {"configured": False, "url": None}

    start = time.time()
    tools: List[Dict[str, Any]] = []
    error: Optional[str] = None
    try:
        from services.agentcore_gateway import list_gateway_tools

        tools = list_gateway_tools()
    except Exception as exc:
        error = str(exc)
        logger.warning("list_gateway_tools failed: %s", exc)

    duration_ms = int((time.time() - start) * 1000)
    rows_render = [[t.get("name", ""), (t.get("description") or "")[:80]] for t in tools[:9]]
    meta = f"{len(tools)} tool(s) published via MCP streamable-http"
    if error:
        meta = f'<span style="color:#b45309">error: {error}</span>'

    ctx.emit_panel(
        agent="gateway",
        tag="GATEWAY · DISCOVER",
        tag_class="amber",
        title="MCP tool discovery · AgentCore Gateway",
        sql="",
        columns=["name", "description"] if rows_render else [],
        rows=rows_render,
        meta=meta,
        duration_ms=duration_ms,
    )
    return {"configured": True, "url": gateway_url, "tools": tools, "error": error}
