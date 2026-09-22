#!/usr/bin/env python3
"""Assemble one portable build receipt for a participant's workshop run.

What this is
------------

Four labs each end in durable evidence, but that evidence is spread across
seven Aurora tables, a source-state check, and a managed-runtime receipt. A
participant who finishes the workshop has proved a great deal and has nothing
to take home that says so. This assembles exactly one artifact from evidence
that already exists -- it creates no tables, writes no rows, and invents no
state.

It is also the fastest table-lead diagnostic in the room: one command that says
which boundary a stuck participant has not crossed yet, and names the row that
would prove it.

The honesty rule
----------------

Every line reports one of four states, never two:

    PROVED       a durable row exists and satisfies the claim
    NOT YET      the lab has not left its evidence
    UNCHECKED    the query could not run (no database, no credentials)
    CONTRADICTED the search ran and found evidence against the claim

UNCHECKED is not a soft NOT YET. "This did not happen" and "I could not look"
are different findings, and a receipt that blurs them is worse than no receipt,
because it invites a participant to conclude they failed at something the tool
simply never examined. The same rule governs the DENY case: the absence of an
execution row is only evidence when the row was actually searched for.

The run
-------

Migration 049 stamps every evidence row with the ``run_id`` bound on the
connection that wrote it (see ``services/workshop_run.py``). When a run id is
known, from ``--run-id``, ``PELLIER_RUN_ID``, or ``~/.pellier/run_id``, every
query below is scoped to it, so a seeded incident or a facilitator's rehearsal
cannot stand in for the participant's own evidence. Rows written outside the
application's pool (the Lambda's Data API path, a direct script) carry no
run_id; the governance query admits those only when they were created after the
run started, and says so.

Usage
-----

    python3 scripts/build_receipt.py                     # newest participant
    python3 scripts/build_receipt.py --principal <sub>   # one participant
    python3 scripts/build_receipt.py --run-id run-0123456789ab
    python3 scripts/build_receipt.py --strict            # exit 1 unless complete
    python3 scripts/build_receipt.py --json receipt.json --markdown receipt.md
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import quote_plus

REPO = pathlib.Path(__file__).resolve().parents[1]
BACKEND = REPO / "pellier" / "backend"
DEFAULT_ENV = BACKEND / ".env"

PROVED = "PROVED"
NOT_YET = "NOT YET"
UNCHECKED = "UNCHECKED"
# A claim whose own evidence refutes it. Distinct from NOT YET (no evidence)
# and from UNCHECKED (no look): here the search ran, and what it found says the
# opposite of the claim. Collapsing this into either of the other two is how a
# receipt ends up asserting a non-execution that did execute.
CONTRADICTED = "CONTRADICTED"

RUN_ID_PATTERN = re.compile(r"^run-[0-9a-f]{12}$")
RUN_SCOPE_UNAVAILABLE = "unavailable (migration 049 not applied)"


# ---------------------------------------------------------------------------
# Source state -- read as text, deliberately
# ---------------------------------------------------------------------------
# The backend decides shipped-vs-exercise by importing the modules and
# inspecting their source. Importing them here would drag in FastAPI, settings,
# and a database handle, so a receipt could not be produced on a box whose
# backend does not start -- which is precisely when a table lead needs one. The
# marker strings below are the same ones routes/observatory.py looks for.


def _reads_as_stub(path: pathlib.Path, markers: tuple[str, ...]) -> Optional[bool]:
    """True when the file still reads as the shipped starter, None if unreadable."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return any(marker in source for marker in markers)


def _region_reads_as_stub(
    path: pathlib.Path, region: str, markers: tuple[str, ...]
) -> Optional[bool]:
    """Same question, asked only inside one ``WORKSHOP ·`` marked region.

    Several starters are a value the participant edits rather than a sentinel
    they delete, and that value's text also appears elsewhere in the same file
    (a docstring, a neighbouring catalogue). Searching the whole file would
    report a completed build as untouched forever.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    start = source.find(f"WORKSHOP \u00b7 {region}: START ===")
    end = source.find(f"WORKSHOP \u00b7 {region}: END ===")
    if start == -1 or end == -1 or end <= start:
        # The region is gone. That is not a starter, and it is not a finished
        # build either -- it is a file this receipt can no longer speak about.
        return None
    block = source[start:end]
    return any(marker in block for marker in markers)


# Source regions supporting four labs and eight participant tasks.
# A task may contain several edits or a deployed investigation. Source inspection
# alone does not establish that a participant ran the corresponding checks.
_BUILDS: tuple[tuple[str, str, pathlib.Path, Optional[str], tuple[str, ...]], ...] = (
    (
        "01_ground_the_answer", "1b_inventory_agent_defined",
        BACKEND / "agents" / "inventory_agent.py",
        None, ("_INVENTORY_AGENT_STUBBED = True",),
    ),
    (
        "01_ground_the_answer", "1a_inventory_tool_written",
        BACKEND / "services" / "agent_tools.py",
        None, ("check_inventory is in stub state", "received_product_query"),
    ),
    (
        "02_measure_hybrid_retrieval", "2a_rrf_expression_authored",
        REPO / "workshop" / "lab-2-rrf.sql",
        "PostgreSQL RRF \u00b7 fusion expression", ("0::numeric AS recomputed_rrf",),
    ),
    (
        "02_measure_hybrid_retrieval", "2b_requirements_preserved",
        BACKEND / "services" / "search_plan.py",
        "Search plan \u00b7 preserve requirements",
        ("Complete Task 2B before relaxing a preference",),
    ),
    (
        "03_operate_the_managed_path", "3a_gateway_tool_published",
        REPO / "scripts" / "deploy" / "gateway_tool_schemas.py",
        "Gateway catalogue \u00b7 published tools", ('"get_ticket_history"',),
    ),
    (
        "03_operate_the_managed_path", "3a_runtime_catalogue_reconciled",
        BACKEND / "services" / "agentcore_gateway.py",
        "Managed catalogue \u00b7 support reconcile",
        ("SUPPORT_CALLER_BOUND_TOOLS: frozenset[str] = frozenset()",),
    ),
    (
        "04_govern_and_prove", "4a_identity_rule_authored",
        REPO / "policies" / "workshop_identity_match_forbid.cedar",
        None, ("unless {\n  false\n}",),
    ),
    (
        "04_govern_and_prove", "4b_rls_predicate_authored",
        REPO / "workshop" / "lab-4-rls.sql",
        "Row ownership · predicate", ("ownership_predicate 'false'",),
    ),
    (
        "04_govern_and_prove", "4b_absence_query_authored",
        REPO / "workshop" / "lab-4-absence.sql",
        "Keyed absence \u00b7 deny proof",
        ("NULL::bigint AS denied_execution_rows",
         "NULL::bigint AS denied_write_rows",
         "NULL::bigint AS denied_finalized_writes",
         "NULL::bigint AS denied_ledger_rows",
         "NULL::bigint AS allowed_finalized_writes"),
    ),
)


def _source_state(is_stub: Optional[bool]) -> str:
    if is_stub is None:
        return UNCHECKED
    return NOT_YET if is_stub else PROVED


def collect_source_state() -> Dict[str, Any]:
    """Inspect every authored source region, not only Lab 1's two.

    A receipt that checked Lab 1's source and nothing else could report a
    complete workshop for a participant who never opened Labs 2, 3, or 4's
    starters, because their evidence rows can be produced by the shipped
    reference implementation running underneath them.
    """
    state: Dict[str, Any] = {}
    for lab, name, path, region, markers in _BUILDS:
        stub = (
            _region_reads_as_stub(path, region, markers)
            if region
            else _reads_as_stub(path, markers)
        )
        state[name] = {"lab": lab, "state": _source_state(stub)}
    return state


def collect_provenance() -> Dict[str, Any]:
    """Which content this box is running, and which revision it would deploy."""
    provenance: Dict[str, Any] = {}

    ref_file = REPO / ".workshop-ref.json"
    if ref_file.exists():
        try:
            provenance["source"] = json.loads(ref_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            provenance["source"] = {"error": "unreadable .workshop-ref.json"}
    else:
        # The env var is exported by CloudFormation UserData and dies with the
        # bootstrap shell, so it is a fallback, not the primary record.
        revision = os.environ.get("WORKSHOP_SOURCE_REVISION", "")
        provenance["source"] = {"repo_ref": revision} if revision else {}

    # The digest the renderer would stamp on a deploy from this tree. Comparing
    # it against what Runtime echoes is what proves the managed path executed
    # the participant's revision rather than a previous deployment.
    try:
        sys.path.insert(0, str(BACKEND))
        from services.build_fingerprint import compute_fingerprint

        provenance["runtime_build_fingerprint"] = compute_fingerprint(BACKEND)
    except Exception as exc:  # noqa: BLE001 - provenance is never load-bearing
        provenance["runtime_build_fingerprint"] = ""
        provenance["runtime_build_fingerprint_error"] = (
            f"{type(exc).__name__}: {str(exc)[:120]}"
        )
    return provenance


# ---------------------------------------------------------------------------
# Aurora evidence
# ---------------------------------------------------------------------------
# Each query carries a `{run_scope}` slot. It is filled with the run clause when
# a run id is in effect and migration 049 is installed, and left empty otherwise,
# so one query text serves both cases without a second copy to keep in sync.

_RUN_SCOPE_PROBE = "SELECT to_regclass('pellier.workshop_runs') AS installed;"

# Every identity that appears in this run, for the header. This is REPORTED,
# never bound into a lab filter.
#
# The workshop is one participant playing four people, and only two of them are
# signed in: Marco and Anna reach the storefront through `/api/persona/switch`,
# which needs no credential, so their turns carry a NULL `principal_sub`. Theo
# signs in for Lab 3 and Jessica for Lab 4. Scoping every lab to "the newest
# principal" therefore resolved to a Lab 3/4 identity and silently dropped
# Labs 1 and 2, because `NULL = 'sub-jessica'` is not true. The run id is the
# correct scope for one participant's two hours; the principal is a diagnostic.
_RUN_PRINCIPALS = """
SELECT principal_sub, MAX(created_at) AS last_seen
  FROM pellier.governed_turn_receipts
 WHERE principal_sub IS NOT NULL AND principal_sub <> ''
   {run_scope}
 GROUP BY principal_sub
 ORDER BY last_seen DESC
 LIMIT 8;
"""

# Lab 1 -- the tool ran and left an execution row.
_LAB1 = """
SELECT ta.audit_id, ta.session_id, ta.args->>'turn_id' AS turn_id,
       ta.caller, ta.latency_ms, ta.created_at
  FROM pellier.tool_audit ta
  LEFT JOIN pellier.governed_turn_receipts gtr
         ON gtr.turn_id = ta.args->>'turn_id'
 WHERE ta.tool = 'check_inventory'
   AND ta.result IS NOT NULL
   AND (%(sub)s::text IS NULL OR gtr.principal_sub = %(sub)s)
   {run_scope}
 ORDER BY ta.audit_id DESC
 LIMIT 1;
"""

# Lab 2 -- a receipt carrying BOTH retrieval ranks and their fusion. Vector or
# lexical alone is not hybrid retrieval, so all three must be populated.
_LAB2 = """
SELECT receipt_id, turn_id, query_preview, embedding_model, rerank_model,
       retrieval_config, latency_breakdown, modeled_cost_usd,
       jsonb_array_length(COALESCE(citation_ids, '[]'::jsonb)) AS citations,
       (rerank_scores IS NOT NULL AND rerank_scores <> '{}'::jsonb) AS reranked
  FROM pellier.retrieval_receipts
 WHERE (%(sub)s::text IS NULL OR principal_sub = %(sub)s)
   AND rrf_scores <> '{}'::jsonb
   AND vector_ranks <> '{}'::jsonb
   AND lexical_ranks <> '{}'::jsonb
   {run_scope}
 ORDER BY receipt_id DESC
 LIMIT 1;
"""

# Lab 3 -- the managed rail, proved durably rather than from the in-memory
# runtime receipt, which does not survive a backend restart.
#
# The proof is the turn receipt's own `rail`. `governed_turn_receipts` is
# written through the application pool
# (services/governed_turn_receipt.py::persist_turn_receipt), so migration 049's
# DEFAULT stamps this run on it, and the row records the rail that actually
# served the turn. That is exactly what Lab 3 sets out to establish.
#
# The gateway `tool_audit` row is reported, never required. Only the three
# mutation tools leave one -- the MCP Lambda audits them in
# scripts/deploy/common/dataapi.py -- and Gateway reads leave no tool_audit row
# at all. Lab 3's Theo journey ends at a pending review
# (tests/golden/journeys.json: `endsAt: proposal`) and performs no mutation, so
# demanding that row would make Lab 3 unprovable by completing Lab 3. The
# mutation chain is Lab 4's contract, on Jessica's return.
_LAB3 = """
SELECT gtr.turn_id, gtr.rail, gtr.terminal_status, gtr.created_at,
       gtr.trace->>'buildState'           AS build_state,
       gtr.trace->>'buildFingerprint'     AS deployed_fingerprint,
       gtr.trace->>'localBuildFingerprint' AS local_fingerprint,
       ta.audit_id AS gateway_mutation_audit_id
  FROM pellier.governed_turn_receipts gtr
  LEFT JOIN pellier.tool_audit ta
         ON ta.args->>'turn_id' = gtr.turn_id
        AND ta.caller = 'gateway'
 WHERE (%(sub)s::text IS NULL OR gtr.principal_sub = %(sub)s)
   AND gtr.rail = 'gateway-mcp'
   {run_scope}
 -- Prefer a managed turn that carries the fingerprint comparison. Lab 4 also
 -- runs on `gateway-mcp` and its turns are newer, so plain recency answered
 -- Lab 3's question with a Lab 4 row -- which proves the rail but can say
 -- nothing about which revision executed. Recency still decides among turns
 -- that carry the evidence.
 ORDER BY (gtr.trace ? 'buildState') DESC,
          gtr.created_at DESC,
          ta.audit_id DESC NULLS LAST
 LIMIT 1;
"""

# Lab 3 -- memory actually informed a turn, rather than merely being configured.
_LAB3_MEMORY = """
SELECT turn_id, trace->'memory' AS memory
  FROM pellier.governed_turn_receipts
 WHERE (%(sub)s::text IS NULL OR principal_sub = %(sub)s)
   AND principal_verified
   AND rail = 'gateway-mcp'
   AND terminal_status = 'complete'
   AND trace->'memory'->>'source' = 'agentcore-memory'
   AND trace->'memory'->>'namespace_scope' = 'verified-principal'
   AND trace->'memory'->>'read_status' = 'succeeded'
   AND trace->'memory'->>'write_status' = 'succeeded'
   AND trace->'memory'->'turns_loaded' >= '2'::jsonb
   AND trace->'memory'->'turns_persisted' >= '2'::jsonb
   {run_scope}
 ORDER BY created_at DESC
 LIMIT 1;
"""

# Lab 4 -- the decision chain.
#
# `audit_id IS NULL` on a DENY is NOT the absence proof. It is one signal, from
# the same row whose claim is under test, and a row cannot be its own alibi:
# a DENY receipt with a null audit_id can still carry an idempotency key whose
# write completed. What proves non-execution is searching for that key in the
# tables an execution would have written, which `_DENY_ABSENCE` does per key.
# `declared_key` is what makes that search possible.
_LAB4 = """
SELECT gr.receipt_id, gr.decision, gr.principal_label, gr.args, gr.policy_name, gr.policy_engine_id,
       gr.verified_subject, gr.identity_source, gr.audit_id, gr.created_at,
       COALESCE(ta.args->>'idempotency_key', gr.args->>'idempotency_key')
           AS declared_key,
       wo.idempotency_key, wo.operation, wo.completed_at
  FROM pellier.governed_receipts gr
  LEFT JOIN pellier.tool_audit ta ON ta.audit_id = gr.audit_id
  LEFT JOIN pellier.write_operations wo
         ON wo.idempotency_key = COALESCE(
              ta.args->>'idempotency_key', gr.args->>'idempotency_key')
 WHERE (%(sub)s::text IS NULL OR gr.principal_id = %(sub)s)
   AND gr.caller = 'gateway'
   AND gr.identity_source = 'cognito'
   AND NULLIF(gr.verified_subject, '') IS NOT NULL
   {run_scope}
 ORDER BY gr.receipt_id DESC
 LIMIT 8;
"""

# Absence, for ONE named operation, searched in the three places an execution
# leaves a trace. Modelled on `scripts/prove_identity_boundary.py`, which
# already holds the rule this receipt was missing: absence is only ever claimed
# for a key that was actually searched for.
#
# Deliberately NOT run-scoped. A denial whose key executed in some other run is
# still an execution of that key, and scoping the search would hide exactly the
# contradiction it exists to surface.
_DENY_ABSENCE = """
SELECT
    (SELECT count(*) FROM pellier.tool_audit
      WHERE args->>'idempotency_key' = %(key)s)                     AS execution_rows,
    (SELECT count(*) FROM pellier.write_operations
      WHERE idempotency_key = %(key)s)                                AS write_rows,
    (SELECT count(*) FROM pellier.write_operations
      WHERE idempotency_key = %(key)s
        AND completed_at IS NOT NULL)                                 AS completed_writes,
    (SELECT count(*) FROM pellier.inventory_ledger
      WHERE idempotency_key = %(key)s)                                AS ledger_rows;
"""

# Every application and CLI receipt is explicitly scoped to the participant run.
# Unattributed historical rows cannot prove this run, even if timestamps overlap.
_RUN_CLAUSES = {
    "principals": "AND run_id = %(run)s",
    "lab1": "AND ta.run_id = %(run)s",
    "lab2": "AND run_id = %(run)s",
    "lab3": "AND gtr.run_id = %(run)s",
    "lab3_memory": "AND run_id = %(run)s",
    "lab4": "AND gr.run_id = %(run)s",
}


def _scoped(sql: str, label: str, scoped: bool) -> str:
    return sql.replace("{run_scope}", _RUN_CLAUSES[label] if scoped else "")


def parse_dotenv(env_path: pathlib.Path) -> Dict[str, str]:
    """Read KEY=value lines from a dotenv file without shell interpolation."""
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            values[key] = value.strip().strip('"').strip("'")
    return values


def db_config(env_path: pathlib.Path) -> Optional[Dict[str, str]]:
    """Database settings from the backend .env, with the environment overriding."""
    cfg = parse_dotenv(env_path)
    for key in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_PORT"):
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    if not all(cfg.get(k) for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")):
        return None
    return cfg


def connection_dsn(cfg: Dict[str, str]) -> str:
    return (
        f"postgresql://{cfg['DB_USER']}:{quote_plus(cfg['DB_PASSWORD'])}"
        f"@{cfg['DB_HOST']}:{cfg.get('DB_PORT', '5432')}/{cfg['DB_NAME']}"
    )


def psycopg_connector() -> Optional[Callable[[str], Any]]:
    """Return a factory that opens one dict-row connection from a DSN.

    Sibling scripts (``workshop_doctor.py``) read the same Aurora with the same
    driver settings, so the factory is public rather than reimplemented there.

    Returns:
        A callable taking a DSN and returning a connection, or None when
        psycopg is not installed on this box.
    """
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        return None
    return lambda dsn: psycopg.connect(dsn, row_factory=dict_row, connect_timeout=15)


def _run_scope_installed(conn: Any) -> bool:
    with conn.cursor() as cur:
        cur.execute(_RUN_SCOPE_PROBE)
        row = cur.fetchone()
    return bool(row and row.get("installed"))


def read_evidence(
    env_path: pathlib.Path,
    principal: Optional[str],
    run_id: Optional[str] = None,
    connect: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Read every lab's evidence rows, scoped to ``run_id`` when one is known.

    Args:
        env_path: Backend ``.env`` to take database settings from.
        principal: Cognito subject to scope to; None selects the newest one.
        run_id: Workshop run to scope to; None leaves every query unscoped.
        connect: Connection factory taking a DSN; defaults to psycopg. Tests
            inject a fake here so the SQL contract runs offline.

    Returns:
        A dict with ``available`` and, when True, one entry per lab plus the
        run scope that was applied (``run_id``, ``none``, or the reason it
        could not be applied).
    """
    cfg = db_config(env_path)
    if cfg is None:
        return {
            "available": False,
            "reason": f"no database settings in {env_path} or the environment",
        }
    connect = connect or psycopg_connector()
    if connect is None:
        return {"available": False, "reason": "psycopg is not installed"}

    out: Dict[str, Any] = {"available": True, "run_id": run_id or ""}
    try:
        with connect(connection_dsn(cfg)) as conn:
            scoped = bool(run_id) and _run_scope_installed(conn)
            if scoped:
                out["run_scope"] = "run_id"
            else:
                out["run_scope"] = RUN_SCOPE_UNAVAILABLE if run_id else "none"
            params = {"sub": principal, "run": run_id if scoped else None}
            # `principal` stays exactly what the caller asked for. Without
            # --principal it is None, every lab query's guard short-circuits,
            # and the run id alone decides the scope -- which is the whole
            # participant, all four personas, signed in or not.
            with conn.cursor() as cur:
                cur.execute(_scoped(_RUN_PRINCIPALS, "principals", scoped), params)
                out["principals"] = [
                    r["principal_sub"] for r in (cur.fetchall() or [])
                ]
            out["principal_sub"] = principal or ""
            out["principal_filtered"] = principal is not None
            for label, sql in (
                ("lab1", _LAB1),
                ("lab2", _LAB2),
                ("lab3", _LAB3),
                ("lab3_memory", _LAB3_MEMORY),
            ):
                with conn.cursor() as cur:
                    cur.execute(_scoped(sql, label, scoped), params)
                    out[label] = cur.fetchone()
            with conn.cursor() as cur:
                cur.execute(_scoped(_LAB4, "lab4", scoped), params)
                rows = cur.fetchall() or []
            # Search for each denied operation's key independently, so the
            # non-execution claim rests on a search rather than on the absence
            # of a link in the row making the claim.
            for row in rows:
                if row.get("decision") != "DENY":
                    continue
                key = (row.get("declared_key") or "").strip()
                if not key:
                    row["absence"] = None
                    continue
                with conn.cursor() as cur:
                    cur.execute(_DENY_ABSENCE, {"key": key})
                    row["absence"] = cur.fetchone()
            out["lab4"] = rows
    except Exception as exc:  # noqa: BLE001 - report, never raise, to the room
        return {
            "available": False,
            "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
        }
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _classify_deny_absence(deny: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Decide the non-execution claim from a search, not from a missing link.

    Three outcomes, and the difference between them is the point:

      PROVED        a denial named a key, and that key appears in none of
                    ``tool_audit``, ``write_operations``, or ``inventory_ledger``
      CONTRADICTED  the key was searched and something WAS found -- most
                    dangerously a completed write, which means the denial and
                    the effect disagree and the receipt must not certify it
      UNCHECKED     the denial named no key, so there was nothing to search
                    for and non-execution cannot be claimed either way

    The previous rule -- ``audit_id IS NULL`` on the DENY row -- returned PROVED
    for all three, including a DENY whose own joined ``write_operations`` row
    carried a completion timestamp.
    """
    if not deny:
        return {"state": NOT_YET, "detail": {}}
    checked = [r for r in deny if r.get("absence")]
    if not checked:
        return {
            "state": UNCHECKED,
            "detail": {"reason": "no denied attempt named an idempotency key"},
        }
    for row in checked:
        found = row["absence"]
        traces = {
            "execution_rows": int(found.get("execution_rows") or 0),
            "write_rows": int(found.get("write_rows") or 0),
            "completed_writes": int(found.get("completed_writes") or 0),
            "ledger_rows": int(found.get("ledger_rows") or 0),
        }
        if any(traces.values()):
            return {
                "state": CONTRADICTED,
                "detail": {
                    "searched_key": row.get("declared_key"),
                    "receipt_id": row.get("receipt_id"),
                    **traces,
                },
            }
    if len(checked) != len(deny):
        return {
            "state": UNCHECKED,
            "detail": {"reason": "not every denied attempt has a keyed absence search"},
        }
    first = checked[0]
    return {
        "state": PROVED,
        "detail": {
            "searched_key": first.get("declared_key"),
            "receipt_id": first.get("receipt_id"),
            "keys_searched": len(checked),
        },
    }


def _fingerprint_state(lab3_row: Optional[Dict[str, Any]], available: bool) -> str:
    """Did the managed Runtime execute THIS checkout's package?

    A successful managed turn proves the service answered. It does not say
    whose code answered: ``qualifier=DEFAULT`` reads identically for the
    participant's deployment and for the one before it, which is exactly why
    the renderer stamps a content digest into the container and the entrypoint
    echoes it back. Recording the local digest in provenance -- which is all
    this receipt used to do -- compares nothing.

    ``services/agentcore_runtime.py`` computes the comparison as ``buildState``
    and ``services/governed_turn_receipt.py`` persists it, so the answer
    survives a backend restart and can be read here.
    """
    if not available:
        return UNCHECKED
    if not lab3_row:
        return NOT_YET
    state = (lab3_row.get("build_state") or "").strip().lower()
    if not state:
        # An in-process turn has no deployed package to compare against, and a
        # managed receipt written before this field was persisted has nothing
        # to read. Neither is a failed comparison.
        return UNCHECKED
    # The three states `services/agentcore_runtime.py::_build_state` emits.
    if state == "current":
        return PROVED
    if state == "stale":
        return CONTRADICTED
    return UNCHECKED  # "unknown": deployed before the fingerprint existed


def _lab4_findings(rows: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Classify the Cedar chain without collapsing its distinct evidence.

    A DENY receipt and the absence of an execution are two facts, and the
    second one is only a fact once it has been searched for by key.
    """
    if rows is None:
        return {"decisions": UNCHECKED}
    allow = [r for r in rows if r["decision"] == "ALLOW"]
    deny = [r for r in rows if r["decision"] == "DENY"]
    executed = [r for r in allow if r["audit_id"] is not None]
    committed = [r for r in executed if r.get("completed_at") is not None]
    absence = _classify_deny_absence(deny)

    return {
        "decisions": PROVED if rows else NOT_YET,
        "allow_seen": PROVED if allow else NOT_YET,
        "deny_seen": PROVED if deny else NOT_YET,
        "allow_executed": PROVED if executed else NOT_YET,
        "durable_effect": PROVED if committed else NOT_YET,
        "deny_did_not_execute": absence["state"],
        "deny_absence_search": absence["detail"],
        "policy_name": rows[0]["policy_name"] if rows else "",
        "latest_allow_audit_id": executed[0]["audit_id"] if executed else None,
        "latest_write_key": committed[0]["idempotency_key"] if committed else None,
    }


def assemble(evidence: Dict[str, Any]) -> Dict[str, Any]:
    source = collect_source_state()
    available = bool(evidence.get("available"))

    def row_state(key: str) -> str:
        if not available:
            return UNCHECKED
        return PROVED if evidence.get(key) else NOT_YET

    lab4 = _lab4_findings(evidence.get("lab4") if available else None)
    provenance = collect_provenance()
    lab3_row = evidence.get("lab3") if available else None

    def builds_for(lab: str) -> Dict[str, str]:
        return {
            name: entry["state"]
            for name, entry in source.items()
            if entry["lab"] == lab
        }

    receipt: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "principal_sub": evidence.get("principal_sub") or "",
        "principals": evidence.get("principals") or [],
        "principal_filtered": bool(evidence.get("principal_filtered")),
        "run_id": evidence.get("run_id") or "",
        "run_scope": evidence.get("run_scope") or "none",
        "evidence_source": (
            "aurora" if available else f"unavailable ({evidence.get('reason', '')})"
        ),
        "provenance": provenance,
        "labs": {
            "01_ground_the_answer": {
                **builds_for("01_ground_the_answer"),
                "execution_row": row_state("lab1"),
                "detail": evidence.get("lab1") if available else None,
            },
            "02_measure_hybrid_retrieval": {
                **builds_for("02_measure_hybrid_retrieval"),
                "hybrid_receipt": row_state("lab2"),
                "detail": evidence.get("lab2") if available else None,
            },
            "03_operate_the_managed_path": {
                **builds_for("03_operate_the_managed_path"),
                "managed_rail": row_state("lab3"),
                "memory_informed_a_turn": row_state("lab3_memory"),
                "runtime_revision_is_yours": _fingerprint_state(lab3_row, available),
                "detail": lab3_row,
            },
            "04_govern_and_prove": {
                **builds_for("04_govern_and_prove"),
                **lab4,
            },
        },
    }

    # An explicit list of what this run has NOT established. A receipt that only
    # lists successes reads as a certificate; the unproven column is the half a
    # participant can act on, and the half a table lead needs.
    unproven: List[str] = []
    _reported = {PROVED, NOT_YET, UNCHECKED, CONTRADICTED}
    for lab, claims in receipt["labs"].items():
        for claim, state in claims.items():
            # Only the four states are graded. `policy_name` and the search
            # detail are context, not claims, and must not be read as a pass
            # merely by not being one of the failure words.
            if not isinstance(state, str) or state not in _reported:
                continue
            if state != PROVED:
                unproven.append(f"{lab}.{claim}: {state}")
    receipt["unproven"] = unproven
    receipt["complete"] = not unproven
    return receipt


def _fmt(state: Any) -> str:
    return str(state) if isinstance(state, str) else str(state)


def render_markdown(receipt: Dict[str, Any]) -> str:
    lines: List[str] = []
    add = lines.append
    add("# Pellier build receipt")
    add("")
    add(f"- Generated: `{receipt['generated_at']}`")
    principals = receipt.get("principals") or []
    if receipt.get("principal_filtered"):
        add(f"- Participant: `{receipt['principal_sub']}` (filtered by --principal)")
    elif principals:
        # Named, not filtered on. Two of the four personas never sign in, so a
        # run legitimately shows fewer identities than it had participants.
        add(f"- Identities seen in this run: {', '.join(f'`{s}`' for s in principals)}")
        add("- Scope: the whole run, every persona, signed in or not")
    else:
        add("- Identities seen in this run: none signed in")
    if receipt.get("run_id"):
        add(f"- Run: `{receipt['run_id']}` (scope: {receipt.get('run_scope', 'none')})")
    else:
        add("- Run: `none` (no run id; evidence is not scoped to one participant run)")
    add(f"- Evidence source: `{receipt['evidence_source']}`")
    prov = receipt.get("provenance", {})
    src = prov.get("source") or {}
    if src.get("repo_ref") or src.get("resolved_sha"):
        add(
            f"- Source: `{src.get('repo_ref', '?')}` @ "
            f"`{str(src.get('resolved_sha', '?'))[:12]}`"
        )
    if prov.get("runtime_build_fingerprint"):
        add(f"- Runtime build (this checkout): `{prov['runtime_build_fingerprint'][:12]}`")
    lab3 = receipt["labs"].get("03_operate_the_managed_path", {})
    detail3 = lab3.get("detail") if isinstance(lab3.get("detail"), dict) else {}
    if detail3.get("deployed_fingerprint"):
        add(
            f"- Runtime build (executed): `{str(detail3['deployed_fingerprint'])[:12]}`"
            f" -- {detail3.get('build_state', 'unknown')}"
        )
    add("")

    # The lab as the participant met it. The keys are join keys and never
    # change; these are display strings and must match the guide's own titles,
    # because the receipt is the artifact that leaves the room and a reader
    # comparing it to the page should not have to work out that "02 Measure
    # hybrid retrieval" and "Build and Measure PostgreSQL Hybrid Retrieval"
    # are the same lab.
    titles = {
        "01_ground_the_answer": "Lab 1: Build a PostgreSQL-Grounded Agent",
        "02_measure_hybrid_retrieval": (
            "Lab 2: Build and Measure PostgreSQL Hybrid Retrieval"
        ),
        "03_operate_the_managed_path": (
            "Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore"
        ),
        "04_govern_and_prove": "Lab 4: Build Governed Agent Actions with Cedar",
    }
    for key, claims in receipt["labs"].items():
        add(f"## {titles.get(key, key)}")
        add("")
        for claim, state in claims.items():
            if claim == "detail" or not isinstance(state, str):
                continue
            add(f"- {claim.replace('_', ' ')}: **{_fmt(state)}**")
        detail = claims.get("detail")
        if isinstance(detail, dict):
            # `gateway_mutation_audit_id` is named in full so a reader can tell
            # the rail proof from the optional mutation evidence beside it.
            keys = [
                k
                for k in (
                    "audit_id",
                    "receipt_id",
                    "turn_id",
                    "rail",
                    "gateway_mutation_audit_id",
                )
                if detail.get(k)
            ]
            if keys:
                add("")
                add("  " + ", ".join(f"`{k}={detail[k]}`" for k in keys))
        add("")

    add("## Not yet proven")
    add("")
    if receipt["unproven"]:
        for item in receipt["unproven"]:
            add(f"- {item}")
        add("")
        add(
            "> `UNCHECKED` means the query could not run, not that the step "
            "failed. `CONTRADICTED` is neither: the search ran and found "
            "evidence against the claim. Three different findings."
        )
    else:
        add("- Nothing. Every boundary above is backed by a durable row.")
    add("")
    return "\n".join(lines)


def _resolve_run_id(explicit: Optional[str]) -> Optional[str]:
    """``--run-id`` wins; otherwise the run the service module considers current."""
    if explicit:
        return explicit
    try:
        sys.path.insert(0, str(BACKEND))
        from services.workshop_run import current_run_id
    except Exception:  # noqa: BLE001 - a receipt must build without the backend
        return None
    return current_run_id()


def _write_outputs(args: argparse.Namespace, receipt: Dict[str, Any], markdown: str) -> None:
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(receipt, indent=2, default=str) + "\n", encoding="utf-8"
        )
    if args.md_out:
        pathlib.Path(args.md_out).write_text(markdown, encoding="utf-8")
    if not args.json_out and not args.md_out:
        print(markdown)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--principal",
        default=None,
        help="Cognito sub to scope the receipt to (default: most recent turn)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="workshop run to scope to (default: PELLIER_RUN_ID or ~/.pellier/run_id)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 unless every lab's evidence contract is proved for the run",
    )
    parser.add_argument("--env", default=str(DEFAULT_ENV), help="backend .env path")
    parser.add_argument("--json", dest="json_out", default="", help="write JSON here")
    parser.add_argument(
        "--markdown", dest="md_out", default="", help="write Markdown here"
    )
    args = parser.parse_args(argv)

    run_id = _resolve_run_id(args.run_id)
    if run_id and not RUN_ID_PATTERN.fullmatch(run_id):
        print(f"build_receipt: run id {run_id!r} must match run-<12 hex>", file=sys.stderr)
        return 2
    if args.strict and not run_id:
        print(
            "build_receipt: --strict needs a run id; pass --run-id or run "
            "scripts/workshop-start.sh before Lab 1",
            file=sys.stderr,
        )
        return 1

    evidence = read_evidence(pathlib.Path(args.env), args.principal, run_id=run_id)
    receipt = assemble(evidence)
    _write_outputs(args, receipt, render_markdown(receipt))

    if not evidence.get("available"):
        # Only an unreadable evidence source is an error, because then the
        # receipt cannot speak to the run at all.
        return 1
    if args.strict and receipt["run_scope"] != "run_id":
        # Every query ran unscoped, so a seeded forensic row or a facilitator's
        # rehearsal would grade as this participant's proof. A strict receipt
        # that cannot tell those apart is worse than no receipt.
        print(
            f"STRICT: evidence could not be scoped to run {run_id} "
            f"(run_scope={receipt['run_scope']}). Apply "
            "scripts/migrations/049_workshop_runs.sql, rerun the labs, then "
            "rebuild the receipt.",
            file=sys.stderr,
        )
        return 1
    if args.strict and not receipt["complete"]:
        print(
            f"STRICT: {len(receipt['unproven'])} claim(s) not proved for run {run_id}:",
            file=sys.stderr,
        )
        for item in receipt["unproven"]:
            print(f"  {item}", file=sys.stderr)
        return 1
    # Default mode exits 0 even when boundaries are unproven: an incomplete run
    # is a true report, not a tool failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
