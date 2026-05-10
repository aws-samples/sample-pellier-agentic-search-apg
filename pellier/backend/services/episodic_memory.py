"""episodic_memory — Aurora-backed fixture for the workshop's MEMORY · EPISODIC panel.

Teaching frame: AgentCore Memory owns session history in production.
The Atelier demo needs deterministic, pre-seeded episodes so a
workshop attendee picking "Marco" sees continuity without provisioning
an AgentCore Memory resource. This module is the OFFLINE FALLBACK —
the table it reads from is ``customer_episodic_seed``, seeded by
migration 003.

Two callers:

- ``routes/workshop.py`` — invokes ``emit_memory_episodic_panel`` when
  the turn's customer_id is not anonymous so the right-rail telemetry
  tab shows a real MEMORY · EPISODIC card on the resume turn.
- ``services/agentcore_memory`` (future) — may delegate here when the
  real AgentCore store returns an empty namespace for a seeded demo
  customer. Not wired today; this module stays pure-read so the
  dependency direction remains one-way.

Failure semantics: on any DB or schema error we emit a skipped panel
with the error in ``meta`` (same pattern as the Gateway panel) rather
than raising. Episodic is a teaching overlay; it must never break the
user-facing turn.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from services.agent_context import AgentContext

logger = logging.getLogger(__name__)


_SELECT_SEED_SQL = (
    "SELECT summary_text, ts_offset_days "
    "FROM customer_episodic_seed "
    "WHERE customer_id = %s "
    "ORDER BY ts_offset_days DESC "
    "LIMIT %s"
)


async def fetch_episodic_seed(
    db_service: Any,
    customer_id: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Return episodic seed rows for ``customer_id``, newest first.

    Each row is ``{"summary_text": str, "ts_offset_days": int}``.
    Returns ``[]`` for anonymous callers, unknown customers, or any
    query error (logged as a warning — see module docstring).
    """
    if not customer_id or customer_id == "anonymous":
        return []

    try:
        rows = await db_service.fetch_all(_SELECT_SEED_SQL, customer_id, limit)
    except Exception as exc:  # pragma: no cover - defensive DB path
        logger.warning(
            "fetch_episodic_seed failed for customer=%s: %s", customer_id, exc
        )
        return []

    return [
        {
            "summary_text": r["summary_text"],
            "ts_offset_days": int(r["ts_offset_days"]),
        }
        for r in rows
    ]


def _format_relative(days: int) -> str:
    """Turn a negative day-offset into a human-readable relative string.

    -1 → "1 day ago", -14 → "2 weeks ago", -30 → "1 month ago".
    Kept rough because the workshop doesn't want calendar precision;
    the row is there to set the stage, not be audited.
    """
    days = abs(days)
    if days < 1:
        return "today"
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    if days < 30:
        weeks = max(1, round(days / 7))
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = max(1, round(days / 30))
    return f"{months} month{'s' if months != 1 else ''} ago"


async def emit_memory_episodic_panel(
    ctx: AgentContext,
    *,
    db_service: Any,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Emit a ``MEMORY · EPISODIC`` panel for the current turn.

    Skip-emits a panel with a friendly meta line when the turn's
    customer is anonymous — the emit is still a real panel event so
    the telemetry tab stays coherent (attendees see "no episodic
    recall for anonymous sessions" rather than a silent gap).
    """
    t0 = time.time()

    if not ctx.customer_id or ctx.customer_id == "anonymous":
        ctx.emit_panel(
            agent="memory",
            tag="MEMORY · EPISODIC",
            tag_class="cyan",
            title="Session history · AgentCore Memory (Aurora-seeded)",
            sql="",
            columns=["when", "summary"],
            rows=[],
            meta="anonymous session — no episodic recall",
            duration_ms=int((time.time() - t0) * 1000),
        )
        return []

    rows = await fetch_episodic_seed(db_service, ctx.customer_id, limit=limit)
    rendered = [[_format_relative(r["ts_offset_days"]), r["summary_text"]] for r in rows]

    meta = (
        f'{len(rows)} episode(s) for {ctx.customer_id} · '
        'Aurora seed (AgentCore interface in prod)'
    )
    if not rows:
        meta = (
            f'no seed rows for {ctx.customer_id} — '
            'run <code>psql -f scripts/migrations/003_workshop_episodic_seed.sql</code>'
        )

    ctx.emit_panel(
        agent="memory",
        tag="MEMORY · EPISODIC",
        tag_class="cyan",
        title="Session history · AgentCore Memory (Aurora-seeded)",
        sql=_SELECT_SEED_SQL,
        columns=["when", "summary"],
        rows=rendered,
        meta=meta,
        duration_ms=int((time.time() - t0) * 1000),
    )
    return rows


# ---------------------------------------------------------------------------
# Procedural + Preferences emitters — used together with the episodic
# emitter above on the welcome-back resume turn. All three read from
# Aurora (customers, orders, customer_episodic_seed); AgentCore is the
# abstraction level above episodic in production, but the workshop's
# teaching point is that procedural and preferences are always Aurora-owned.
# ---------------------------------------------------------------------------


_SELECT_PREFERENCES_SQL = (
    "SELECT name, preferences_summary FROM customers WHERE id = %s"
)

_SELECT_PROCEDURAL_SQL = (
    "SELECT pc.\"name\" AS name, COUNT(*) AS bought "
    "FROM orders o "
    "JOIN pellier.product_catalog pc "
    "  ON pc.\"productId\" = o.product_id "
    "WHERE o.product_id IN ( "
    "    SELECT product_id FROM orders WHERE customer_id = %s "
    ") "
    "AND o.customer_id <> %s "
    "GROUP BY pc.\"name\" "
    "ORDER BY bought DESC "
    "LIMIT %s"
)


async def emit_memory_preferences_panel(
    ctx: AgentContext,
    *,
    db_service: Any,
) -> Dict[str, Any] | None:
    """Emit a ``MEMORY · PREFERENCES`` panel reading ``customers.preferences_summary``.

    Preferences live in Aurora (source of truth). A future AgentCore
    mirror under ``user:{id}:preferences`` covers user-edited prefs;
    this panel shows the Aurora-seeded baseline, so it's honest about
    where the teaching frame lands.
    """
    t0 = time.time()

    if not ctx.customer_id or ctx.customer_id == "anonymous":
        ctx.emit_panel(
            agent="memory",
            tag="MEMORY · PREFERENCES",
            tag_class="cyan",
            title="Stated preferences · Aurora",
            sql="",
            columns=["field", "value"],
            rows=[],
            meta="anonymous session — no stated preferences",
            duration_ms=int((time.time() - t0) * 1000),
        )
        return None

    try:
        row = await db_service.fetch_one(
            _SELECT_PREFERENCES_SQL, ctx.customer_id
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "emit_memory_preferences_panel DB error for customer=%s: %s",
            ctx.customer_id, exc,
        )
        row = None

    rendered: List[List[str]] = []
    if row:
        if row.get("name"):
            rendered.append(["name", str(row["name"])])
        if row.get("preferences_summary"):
            rendered.append(["summary", str(row["preferences_summary"])])

    meta = (
        f'Aurora source of truth for stated prefs · customer_id = {ctx.customer_id}'
        if rendered
        else f'no preferences row for {ctx.customer_id}'
    )

    ctx.emit_panel(
        agent="memory",
        tag="MEMORY · PREFERENCES",
        tag_class="cyan",
        title="Stated preferences · Aurora",
        sql=_SELECT_PREFERENCES_SQL,
        columns=["field", "value"],
        rows=rendered,
        meta=meta,
        duration_ms=int((time.time() - t0) * 1000),
    )
    return row if isinstance(row, dict) else None


async def emit_memory_procedural_panel(
    ctx: AgentContext,
    *,
    db_service: Any,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Emit a ``MEMORY · PROCEDURAL`` panel — cohort overlap from orders.

    "Customers like you also bought" — the procedural signal is pure
    Aurora (no AgentCore primitive to delegate to). The JOIN runs
    ``orders ⋈ product_catalog`` to surface product names other
    customers in the same order-history cohort landed on.
    """
    t0 = time.time()

    if not ctx.customer_id or ctx.customer_id == "anonymous":
        ctx.emit_panel(
            agent="memory",
            tag="MEMORY · PROCEDURAL",
            tag_class="cyan",
            title="Cohort overlap · Aurora (orders ⋈ product_catalog)",
            sql="",
            columns=["product", "bought_by_cohort"],
            rows=[],
            meta="anonymous session — no cohort to compare against",
            duration_ms=int((time.time() - t0) * 1000),
        )
        return []

    try:
        rows = await db_service.fetch_all(
            _SELECT_PROCEDURAL_SQL, ctx.customer_id, ctx.customer_id, limit
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "emit_memory_procedural_panel DB error for customer=%s: %s",
            ctx.customer_id, exc,
        )
        rows = []

    rendered = [[str(r.get("name", "")), str(r.get("bought", 0))] for r in rows]
    meta = (
        f'{len(rows)} cohort overlap row(s) for {ctx.customer_id} · Aurora-owned'
        if rows
        else f'no cohort overlap for {ctx.customer_id} — cohort may not have shared purchases yet'
    )

    ctx.emit_panel(
        agent="memory",
        tag="MEMORY · PROCEDURAL",
        tag_class="cyan",
        title="Cohort overlap · Aurora (orders ⋈ product_catalog)",
        sql=_SELECT_PROCEDURAL_SQL,
        columns=["product", "bought_by_cohort"],
        rows=rendered,
        meta=meta,
        duration_ms=int((time.time() - t0) * 1000),
    )
    return [dict(r) for r in rows]
