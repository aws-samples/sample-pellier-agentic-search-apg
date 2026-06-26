"""episodic_memory — Aurora-backed fixture for the workshop's MEMORY · EPISODIC panel.

Teaching frame: AgentCore Memory owns session history in production.
The Atelier demo needs deterministic, pre-seeded episodes so a
workshop attendee picking "Marco" sees continuity without provisioning
an AgentCore Memory resource. This module is the OFFLINE FALLBACK —
the table it reads from is ``pellier.customer_episodic_seed``, seeded by
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
    "FROM pellier.customer_episodic_seed "
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
            'run <code>psql -f scripts/migrations/003_persona_seed.sql</code>'
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
# Aurora (pellier.customers / orders / customer_episodic_seed); AgentCore is the
# abstraction level above episodic in production, but the workshop's
# teaching point is that procedural and preferences are always Aurora-owned.
# ---------------------------------------------------------------------------


_SELECT_PREFERENCES_SQL = (
    "SELECT name, preferences_summary FROM pellier.customers WHERE id = %s"
)

_SELECT_PROCEDURAL_SQL = (
    "SELECT pc.\"name\" AS name, COUNT(*) AS bought "
    "FROM pellier.orders o "
    "JOIN pellier.product_catalog pc "
    "  ON pc.\"productId\" = o.product_id "
    "WHERE o.product_id IN ( "
    "    SELECT product_id FROM pellier.orders WHERE customer_id = %s "
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


# ---------------------------------------------------------------------------
# Working + Semantic emitters — the two AgentCore-OWNED substrates. The
# composite resume turn emits all four substrates in teaching order so a
# participant sees the same "anatomy of a turn" the MemoryDashboard shows:
#
#   WORKING   → AgentCore STM (the persona's latest storefront session)
#   SEMANTIC  → AgentCore long-term (durable taste we learned)
#   EPISODIC  → Aurora (past events for this customer)
#   PROCEDURAL→ Aurora tool_audit (which tools fire, how fast)
#
# Working + Semantic read the SAME path the standalone Atelier panels read
# (services.agentcore_memory) so the resume turn and GET /memory/{persona}
# agree. Both degrade honestly to an empty panel (never a fabricated row)
# when the session has no turns / the extraction strategy is unsettled.
# ---------------------------------------------------------------------------


# Resolve a persona's most-recent storefront session — the exact query the
# standalone Working panel (atelier_observatory._load_live_working) uses, so
# the resume turn surfaces the same "what we were just talking about" thread.
_SELECT_LATEST_PERSONA_SESSION_SQL = (
    "SELECT session_id "
    "FROM pellier.tool_audit "
    "WHERE session_id LIKE %s "
    "ORDER BY audit_id DESC "
    "LIMIT 1"
)


async def emit_memory_working_panel(
    ctx: AgentContext,
    *,
    db_service: Any,
    persona: str | None = None,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """Emit a ``MEMORY · WORKING`` panel — recent session turns, in order.

    Working memory is AgentCore STM (short-term, session-scoped). The
    session we read depends on the caller:

    - With a ``persona`` (the resume "welcome back" turn), we resolve that
      persona's latest *storefront* session from ``pellier.tool_audit`` and
      read it back — the same path the standalone Atelier Working panel
      takes, so "what we were just talking about" matches the dashboard.
    - Without one, we fall back to this turn's own ``session_id``.

    Either way the namespace is the anonymous ``anon-{session_id}`` the
    storefront writes under, read through
    ``AgentCoreMemory.get_session_history`` (live SDK on a provisioned box,
    in-memory fallback otherwise).

    Honest degrade: no turns yet → empty panel with a "make a turn first"
    meta line, never a fabricated row.
    """
    t0 = time.time()
    title = "Session timeline · AgentCore STM"

    if not ctx.customer_id or ctx.customer_id == "anonymous":
        ctx.emit_panel(
            agent="memory",
            tag="MEMORY · WORKING",
            tag_class="cyan",
            title=title,
            sql="",
            columns=["turn", "content"],
            rows=[],
            meta="anonymous session — no working memory · AgentCore-owned (STM)",
            duration_ms=int((time.time() - t0) * 1000),
        )
        return []

    # Resolve which session's turns to show. Default to this turn's own
    # session; upgrade to the persona's latest storefront session when we
    # can find one (best-effort — a failed lookup just keeps the default).
    working_session_id = ctx.session_id
    resolved_from = "this session"
    if persona and db_service is not None:
        try:
            row = await db_service.fetch_one(
                _SELECT_LATEST_PERSONA_SESSION_SQL, f"persona-{persona.lower()}-%"
            )
            sid = dict(row).get("session_id") if row else None
            if sid:
                working_session_id = sid
                resolved_from = f"{persona}'s latest storefront session"
        except Exception as exc:  # pragma: no cover - defensive DB path
            logger.warning(
                "emit_memory_working_panel session resolve failed for persona=%s: %s",
                persona, exc,
            )

    turns: List[Dict[str, Any]] = []
    try:
        from services.agentcore_identity import AgentCoreIdentityService
        from services.agentcore_memory import AgentCoreMemory

        namespace = AgentCoreIdentityService.build_namespace(None, working_session_id)
        memory = AgentCoreMemory()
        turns = await memory.get_session_history(namespace)
    except Exception as exc:  # pragma: no cover - defensive SDK/store path
        logger.warning(
            "emit_memory_working_panel read failed for session=%s: %s",
            working_session_id, exc,
        )
        turns = []

    rendered = [
        [str(t.get("role", "")), str(t.get("content", ""))[:160]]
        for t in turns[-limit:]
    ]
    meta = (
        f'{len(rendered)} turn(s) from {resolved_from} · AgentCore-owned '
        f'(STM, namespace anon-{working_session_id})'
        if rendered
        else f'no turns yet for {resolved_from} — make a storefront turn first '
        '· AgentCore-owned (STM)'
    )

    ctx.emit_panel(
        agent="memory",
        tag="MEMORY · WORKING",
        tag_class="cyan",
        title=title,
        sql="",
        columns=["turn", "content"],
        rows=rendered,
        meta=meta,
        duration_ms=int((time.time() - t0) * 1000),
    )
    return turns


async def emit_memory_semantic_panel(
    ctx: AgentContext,
    *,
    db_service: Any,
) -> List[str]:
    """Emit a ``MEMORY · SEMANTIC`` panel — durable, extracted preferences.

    Semantic memory is AgentCore long-term: prose preferences a
    ``USER_PREFERENCE`` extraction strategy learns from conversation and
    stores under ``/pellier/preferences/{customer_id}/``. We read it with
    the dedicated ``get_semantic_memories`` method (NOT
    ``get_user_preferences``, which serves storefront personalization).

    Honest degrade: ``[]`` (SDK absent, extraction still settling, or
    memory unprovisioned) → empty panel, never a fabricated preference.
    """
    t0 = time.time()
    title = "Learned preferences · AgentCore (USER_PREFERENCE)"

    if not ctx.customer_id or ctx.customer_id == "anonymous":
        ctx.emit_panel(
            agent="memory",
            tag="MEMORY · SEMANTIC",
            tag_class="cyan",
            title=title,
            sql="",
            columns=["learned preference"],
            rows=[],
            meta="anonymous session — no semantic memory · AgentCore-owned (long-term)",
            duration_ms=int((time.time() - t0) * 1000),
        )
        return []

    preferences: List[str] = []
    try:
        from services.agentcore_memory import AgentCoreMemory

        memory = AgentCoreMemory()
        preferences = await memory.get_semantic_memories(ctx.customer_id)
    except Exception as exc:  # pragma: no cover - defensive SDK path
        logger.warning(
            "emit_memory_semantic_panel read failed for customer=%s: %s",
            ctx.customer_id, exc,
        )
        preferences = []

    cleaned = [str(p).strip() for p in (preferences or []) if str(p).strip()]
    rendered = [[p[:200]] for p in cleaned]
    meta = (
        f'{len(rendered)} extracted preference(s) for {ctx.customer_id} · '
        'AgentCore-owned (long-term, USER_PREFERENCE strategy)'
        if rendered
        else 'extraction not settled yet — no records · AgentCore-owned (long-term)'
    )

    ctx.emit_panel(
        agent="memory",
        tag="MEMORY · SEMANTIC",
        tag_class="cyan",
        title=title,
        sql="",
        columns=["learned preference"],
        rows=rendered,
        meta=meta,
        duration_ms=int((time.time() - t0) * 1000),
    )
    return cleaned


# ---------------------------------------------------------------------------
# Procedural (tool_audit aggregate) — the live per-tool signal.
#
# The cohort-overlap emitter above (``emit_memory_procedural_panel``) is a
# *recommendation* signal ("customers like you also bought"), not the
# procedural substrate the owner model names. Procedural = "which tools fire,
# how fast" and its live source is ``pellier.tool_audit`` (every ALLOWed call,
# reads + writes alike) — the SAME aggregate the standalone Atelier Procedural
# panel reads (atelier_observatory._load_live_procedural). The composite
# resume turn uses THIS emitter so there is one procedural query shape, not a
# third variant.
# ---------------------------------------------------------------------------


_SELECT_TOOL_AUDIT_SQL = (
    "SELECT tool, "
    "count(*)::int AS calls, "
    "round(avg(latency_ms)::numeric, 0)::int AS avg_ms "
    "FROM pellier.tool_audit "
    "GROUP BY tool "
    "ORDER BY calls DESC, tool ASC "
    "LIMIT %s"
)


async def emit_memory_tool_audit_panel(
    ctx: AgentContext,
    *,
    db_service: Any,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """Emit a ``MEMORY · PROCEDURAL`` panel from the tool_audit aggregate.

    Per-tool call counts + average latency across every ALLOWed tool call.
    Unlike the cohort emitter, this is NOT customer-scoped — procedural
    memory is the system's learned operating signal ("how the tools
    behave"), so it aggregates over all callers. Degrades to an empty
    panel on DB error or an empty table.
    """
    t0 = time.time()
    title = "Tool activity · Aurora (pellier.tool_audit aggregate)"

    rows: List[Dict[str, Any]] = []
    try:
        fetched = await db_service.fetch_all(_SELECT_TOOL_AUDIT_SQL, limit)
        rows = [dict(r) for r in fetched]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("emit_memory_tool_audit_panel DB error: %s", exc)
        rows = []

    rendered = [
        [str(r.get("tool", "")), str(r.get("calls", 0)), f"{r.get('avg_ms', 0)}ms"]
        for r in rows
    ]
    meta = (
        f'{len(rows)} tool(s) by call volume · Aurora-owned (every ALLOWed call, '
        'reads + writes)'
        if rows
        else 'no tool_audit rows yet — make a few storefront turns first · Aurora-owned'
    )

    ctx.emit_panel(
        agent="memory",
        tag="MEMORY · PROCEDURAL",
        tag_class="cyan",
        title=title,
        sql=_SELECT_TOOL_AUDIT_SQL,
        columns=["tool", "calls", "avg_latency"],
        rows=rendered,
        meta=meta,
        duration_ms=int((time.time() - t0) * 1000),
    )
    return rows
