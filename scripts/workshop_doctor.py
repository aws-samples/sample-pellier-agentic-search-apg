#!/usr/bin/env python3
"""Name the prerequisite a stuck participant has not met, one lab at a time.

The build receipt says which boundaries a run has proved. This answers the
question that comes first at a table: "why is Lab N not working for me?" Each
lab has a short list of things that must already be true before its exercise
can leave evidence, and each one is checked directly rather than inferred from
a symptom.

    Lab 1  Aurora reachable; check_inventory wired past the stub; the Inventory
           Agent definition no longer stubbed.
    Lab 2  Migration 046's citation columns present; a retrieval receipt exists
           for this run.
    Lab 3  The service environment carries the two settings resolve_rail
           reads (USE_AGENTCORE_RUNTIME, AGENTCORE_RUNTIME_ENDPOINT); a turn
           receipt in this run records the gateway-mcp rail, and a turn in this
           run was informed by memory.
    Lab 4  The Cedar policy pair is present and the identity rule has been
           authored; Row-Level Security is enabled on the tables the proof
           exercises; the direct Gateway decision chain exists for this run.

Every line prints PASS or FAIL with the reason, and the exit status is 1 on any
FAIL. A database that cannot be reached is a FAIL with the connection error, not
a silent pass: the doctor exists to be believed.

Usage::

    python3 scripts/workshop_doctor.py --lab 1
    python3 scripts/workshop_doctor.py --lab 3 --run-id run-0123456789ab
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO = pathlib.Path(__file__).resolve().parents[1]
BACKEND = REPO / "pellier" / "backend"
SCRIPTS = REPO / "scripts"
DEFAULT_ENV = BACKEND / ".env"
DEFAULT_RUN_ENV = pathlib.Path("/etc/pellier/run.env")

sys.path.insert(0, str(SCRIPTS))
import build_receipt  # noqa: E402  (sibling script: dotenv, DSN, run id shape)

PASS = "PASS"
FAIL = "FAIL"

TOOL_BLOCK_START = "# === WORKSHOP · Inventory Agent · check_inventory: START ==="
TOOL_BLOCK_END = "# === WORKSHOP · Inventory Agent · check_inventory: END ==="
TOOL_STUB_MARKERS = ("check_inventory is in stub state", "received_product_query")
AGENT_STUB_MARKER = "_INVENTORY_AGENT_STUBBED = True"
# The SQL keyword, not the English words `selected` and `selection`, which a
# stub envelope can easily contain.
_SELECT_KEYWORD = re.compile(r"\bSELECT\b", re.IGNORECASE)

CEDAR_POLICY = "policies/workshop_identity_match_forbid.cedar"
CEDAR_STARTER = "workshop/starters/workshop_identity_match_forbid.cedar"
CONTEXT_POLICY = "policies/advanced_verified_customer_context.dogwood"
POLICY_FILES = (CEDAR_POLICY, CONTEXT_POLICY)

_DB_REACHABLE = "SELECT 1 AS ok;"
_MIGRATION_046 = """
SELECT count(*) AS n
  FROM information_schema.columns
 WHERE table_schema = 'pellier'
   AND table_name = 'retrieval_receipts'
   AND column_name IN ('citation_snapshots', 'citation_snapshot_hash');
"""
_RETRIEVAL_FOR_RUN = """
SELECT receipt_id
  FROM pellier.retrieval_receipts
 WHERE run_id = %(run)s
 ORDER BY receipt_id DESC
 LIMIT 1;
"""
# The managed rail's own record of itself. `governed_turn_receipts` is written
# through the application pool, so migration 049's DEFAULT stamps the run on it,
# and the row's `rail` is the rail that actually served the turn. That is the
# whole of what Lab 3 asks a participant to establish.
#
# This deliberately does not require a `caller = 'gateway'` tool_audit row. Only
# the three mutation tools leave one (the MCP Lambda writes it in
# scripts/deploy/common/dataapi.py) and Gateway reads leave no tool_audit row at
# all, while Lab 3's Theo journey ends at a pending review with no mutation
# performed. Requiring that row would fail a participant who completed Lab 3
# exactly as designed. build_receipt.py's Lab 3 query matches this one.
_MANAGED_RAIL_TURN_FOR_RUN = """
SELECT gtr.turn_id
  FROM pellier.governed_turn_receipts gtr
 WHERE gtr.run_id = %(run)s
   AND gtr.rail = 'gateway-mcp'
 ORDER BY gtr.created_at DESC
 LIMIT 1;
"""
_MEMORY_FOR_RUN = """
SELECT turn_id
  FROM pellier.governed_turn_receipts
 WHERE run_id = %(run)s
   AND principal_verified
   AND rail = 'gateway-mcp'
   AND terminal_status = 'complete'
   AND trace->'memory'->>'source' = 'agentcore-memory'
   AND trace->'memory'->>'namespace_scope' = 'verified-principal'
   AND trace->'memory'->>'read_status' = 'succeeded'
   AND trace->'memory'->>'write_status' = 'succeeded'
   AND trace->'memory'->'turns_loaded' >= '2'::jsonb
   AND trace->'memory'->'turns_persisted' >= '2'::jsonb
 ORDER BY created_at DESC
 LIMIT 1;
"""
_RLS_TABLES = """
SELECT bool_and(c.relrowsecurity) AS enabled, count(*) AS n
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'pellier'
   AND c.relname IN ('orders', 'returns');
"""



@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


class Evidence:
    """One read-only query surface over Aurora, or the reason there is none.

    Use it as a context manager. The doctor is a short-lived command, but it is
    run repeatedly at a table of participants against one shared cluster, so
    each invocation returns its connection rather than waiting for interpreter
    exit to do it.
    """

    def __init__(self, conn: Any = None, reason: str = "") -> None:
        self._conn = conn
        self.reason = reason

    @property
    def available(self) -> bool:
        return self._conn is not None and not self.reason

    def one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if self._conn is None:
            return None
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def close(self) -> None:
        """Release the connection. Safe to call more than once."""
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - closing must never mask a finding
                pass

    def __enter__(self) -> "Evidence":
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.close()
        return False


def open_evidence(env_path: pathlib.Path) -> Evidence:
    """Open the read-only Aurora surface named by ``env_path``, or say why not."""
    cfg = build_receipt.db_config(env_path)
    if cfg is None:
        return Evidence(reason=f"no database settings in {env_path} or the environment")
    connect = build_receipt.psycopg_connector()
    if connect is None:
        return Evidence(reason="psycopg is not installed")
    try:
        return Evidence(conn=connect(build_receipt.connection_dsn(cfg) + "?connect_timeout=5"))
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return Evidence(reason=f"{type(exc).__name__}: {str(exc)[:160]}")


# ---------------------------------------------------------------------------
# Shared check builders
# ---------------------------------------------------------------------------


def _db_reachable(evidence: Evidence) -> Check:
    if not evidence.available:
        return Check("database reachable", False, evidence.reason or "no connection")
    try:
        row = evidence.one(_DB_REACHABLE)
    except Exception as exc:  # noqa: BLE001 - the error is the finding
        return Check("database reachable", False, f"{type(exc).__name__}: {str(exc)[:120]}")
    return Check("database reachable", bool(row), "" if row else "SELECT 1 returned nothing")


def _row_for_run(
    evidence: Evidence, *, name: str, sql: str, run_id: Optional[str], key: str, hint: str
) -> Check:
    """PASS when ``sql`` finds a row for ``run_id``; FAIL names what is missing."""
    if not run_id:
        return Check(name, False, "no run id in effect; run scripts/workshop-start.sh first")
    if not evidence.available:
        return Check(name, False, evidence.reason or "database unavailable")
    try:
        row = evidence.one(sql, {"run": run_id})
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    if row:
        return Check(name, True, f"{key}={row.get(key)}")
    return Check(name, False, hint)


# ---------------------------------------------------------------------------
# Lab 1
# ---------------------------------------------------------------------------


def _tool_wired(source: str) -> Check:
    name = "check_inventory wired"
    start = source.find(TOOL_BLOCK_START)
    end = source.find(TOOL_BLOCK_END)
    if start < 0 or end < 0 or end < start:
        return Check(name, False, "workshop marker block not found in services/agent_tools.py")
    block = source[start + len(TOOL_BLOCK_START):end]
    if any(marker in block for marker in TOOL_STUB_MARKERS):
        return Check(name, False, "the marker block still returns the shipped stub envelope")
    if "check_inventory(" not in block and not _SELECT_KEYWORD.search(block):
        return Check(name, False, "the marker block has no query: it neither calls "
                                  "BusinessLogic.check_inventory nor runs SQL")
    return Check(name, True, "marker block calls into the inventory read")


def lab1_checks(evidence: Evidence, *, backend: pathlib.Path = BACKEND) -> List[Check]:
    checks = [_db_reachable(evidence)]
    try:
        tool_source = (backend / "services" / "agent_tools.py").read_text(encoding="utf-8")
        checks.append(_tool_wired(tool_source))
    except OSError as exc:
        checks.append(Check("check_inventory wired", False, f"unreadable: {exc}"))
    try:
        agent_source = (backend / "agents" / "inventory_agent.py").read_text(encoding="utf-8")
        stubbed = AGENT_STUB_MARKER in agent_source
        checks.append(
            Check(
                "Inventory Agent defined",
                not stubbed,
                "_INVENTORY_AGENT_STUBBED is still True in agents/inventory_agent.py"
                if stubbed else "",
            )
        )
    except OSError as exc:
        checks.append(Check("Inventory Agent defined", False, f"unreadable: {exc}"))
    return checks


# ---------------------------------------------------------------------------
# Lab 2
# ---------------------------------------------------------------------------


def lab2_checks(
    evidence: Evidence, run_id: Optional[str], *, include_proof: bool = True,
) -> List[Check]:
    name = "migration 046 columns present"
    if not evidence.available:
        columns = Check(name, False, evidence.reason or "database unavailable")
    else:
        try:
            row = evidence.one(_MIGRATION_046)
            n = int((row or {}).get("n") or 0)
            columns = Check(
                name, n == 2,
                "" if n == 2 else f"{n} of 2 citation columns on pellier.retrieval_receipts; "
                                  "apply scripts/migrations/046_retrieval_citation_snapshots.sql",
            )
        except Exception as exc:  # noqa: BLE001
            columns = Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    if not include_proof:
        return [columns]
    receipt = _row_for_run(
        evidence,
        name="retrieval receipt for this run",
        sql=_RETRIEVAL_FOR_RUN,
        run_id=run_id,
        key="receipt_id",
        hint="no pellier.retrieval_receipts row for this run; run Anna's hybrid turn",
    )
    return [columns, receipt]


# ---------------------------------------------------------------------------
# Lab 3
# ---------------------------------------------------------------------------


def _managed_rail_selected(
    run_env: pathlib.Path, env_path: pathlib.Path, environ: Mapping[str, str]
) -> Check:
    """PASS when the settings the backend actually reads select the Runtime.

    ``services/execution_rail.py::resolve_rail`` reads exactly two settings:
    ``USE_AGENTCORE_RUNTIME`` decides whether the managed rail is requested, and
    ``AGENTCORE_RUNTIME_ENDPOINT`` decides whether it can serve. Nothing in the
    backend reads a rail-name variable, so nothing here checks for one.

    Args:
        run_env: The service ``run.env`` the systemd unit sources.
        env_path: The backend ``.env`` provisioning wrote the endpoint into.
        environ: Process environment, consulted when neither file carries a key.
    """
    name = "service env selects the managed rail"
    layered: Dict[str, str] = {}
    for source in (build_receipt.parse_dotenv(env_path), build_receipt.parse_dotenv(run_env)):
        layered.update({key: value for key, value in source.items() if value})

    def _value(key: str) -> str:
        return (layered.get(key) or environ.get(key, "")).strip()

    missing = []
    switch = _value("USE_AGENTCORE_RUNTIME")
    if switch.lower() != "true":
        missing.append(f"USE_AGENTCORE_RUNTIME={switch or 'unset'} (want true)")
    if not _value("AGENTCORE_RUNTIME_ENDPOINT"):
        missing.append("AGENTCORE_RUNTIME_ENDPOINT unset (the Runtime ARN)")
    if missing:
        return Check(name, False, "; ".join(missing) + f"; run scripts/lab3-start.sh ({run_env})")
    return Check(name, True, f"{run_env}")


def _managed_catalogues_agree(repo: pathlib.Path = REPO) -> Check:
    """Lab 3's two builds, read from source before anything is deployed.

    The managed dispatcher asks the Gateway for exactly the tools it names and
    raises ``Gateway is missing support tools`` when one is absent. That error
    surfaces as an apologetic answer rather than a stack trace, so a
    participant who has published a tool but not bound its caller sees a turn that "works" and a
    receipt that never arrives. Naming the mismatch here is cheaper than
    letting them find it in a trace.
    """
    name = "Gateway catalogue and Runtime support contract agree"
    try:
        sys.path.insert(0, str(repo / "scripts" / "deploy"))
        sys.path.insert(0, str(BACKEND))
        from gateway_tool_schemas import workshop_published_tools
        from services.agentcore_gateway import (
            STAFF_ONLY_GATEWAY_TOOLS,
            SUPPORT_CALLER_BOUND_TOOLS,
            SUPPORT_MANAGED_TOOLS,
        )
    except Exception as exc:  # noqa: BLE001 - the doctor must not crash here
        return Check(name, False, f"could not read the catalogues: {exc}")

    published = workshop_published_tools()
    missing = sorted(set(SUPPORT_MANAGED_TOOLS) - published)
    staff_only = sorted(set(SUPPORT_MANAGED_TOOLS) & STAFF_ONLY_GATEWAY_TOOLS)
    if missing or staff_only:
        # Name the step that is actually outstanding. Telling someone who has
        # finished 3a to go and do 3a sends them to re-read a file they just
        # got right.
        facts, steps = [], []
        if missing:
            facts.append(
                "the support specialist asks the Gateway for "
                f"{', '.join(missing)}, which it does not publish"
            )
            if "get_ticket_history" in missing:
                steps.append("Lab 3a (publish the customer-scoped read)")
        if staff_only:
            facts.append(
                f"the support specialist names staff-only Gateway tools: {', '.join(staff_only)} "
                "(published for the operator desk; a shopper-facing specialist must not bind "
                "them and the dispatcher refuses to build one that does)"
            )
            steps.append("Task 3a (drop the staff-only tool from the specialist)")
        remedy = " and ".join(steps) or "Lab 3"
        return Check(name, False, f"{'; '.join(facts)}: complete {remedy}")
    unbound = sorted(
        tool
        for tool in ("get_ticket_history",)
        if tool in SUPPORT_MANAGED_TOOLS and tool not in SUPPORT_CALLER_BOUND_TOOLS
    )
    if unbound:
        return Check(
            name,
            False,
            f"{', '.join(unbound)} is published but not bound to the "
            "authenticated caller: complete Task 3a caller binding so the server sets "
            "customer_id instead of the model",
        )
    return Check(name, True, f"{len(published)} tools published, support serveable")


def lab3_checks(
    evidence: Evidence,
    run_id: Optional[str],
    *,
    run_env: pathlib.Path = DEFAULT_RUN_ENV,
    env_path: pathlib.Path = DEFAULT_ENV,
    environ: Optional[Mapping[str, str]] = None,
    include_proof: bool = True,
) -> List[Check]:
    env = os.environ if environ is None else environ
    checks = [
        _managed_catalogues_agree(),
        _managed_rail_selected(run_env, env_path, env),
    ]
    if not include_proof:
        return checks
    return [
        *checks,
        _row_for_run(
            evidence,
            name="managed-rail turn receipt for this run",
            sql=_MANAGED_RAIL_TURN_FOR_RUN,
            run_id=run_id,
            key="turn_id",
            hint="no pellier.governed_turn_receipts row in this run carries "
                 "rail='gateway-mcp'; run scripts/lab3-start.sh to switch the rail, "
                 "then run a Theo turn in Pellier as a signed-in caller",
        ),
        _row_for_run(
            evidence,
            name="memory informed a turn in this run",
            sql=_MEMORY_FOR_RUN,
            run_id=run_id,
            key="turn_id",
            hint="no completed managed turn in this run recorded a successful Memory read and write; "
                 "run Theo's second turn in the same session",
        ),
    ]


# ---------------------------------------------------------------------------
# Lab 4
# ---------------------------------------------------------------------------


def _cedar_checks(repo: pathlib.Path) -> List[Check]:
    missing = [rel for rel in POLICY_FILES if not (repo / rel).is_file()]
    pair = Check(
        "Cedar policy pair present in policies/",
        not missing,
        "missing: " + ", ".join(missing) if missing else ", ".join(POLICY_FILES),
    )
    name = "identity rule authored"
    try:
        policy = (repo / CEDAR_POLICY).read_bytes()
        starter = (repo / CEDAR_STARTER).read_bytes()
    except OSError as exc:
        return [pair, Check(name, False, f"unreadable: {exc}")]
    if policy == starter:
        return [pair, Check(name, False, f"{CEDAR_POLICY} is byte-identical to the starter; "
                                          "complete the unless block")]
    return [pair, Check(name, True, f"{CEDAR_POLICY} differs from the starter")]


def _rls_check(evidence: Evidence) -> Check:
    name = "RLS enabled on orders and returns"
    if not evidence.available:
        return Check(name, False, evidence.reason or "database unavailable")
    try:
        row = evidence.one(_RLS_TABLES) or {}
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    n = int(row.get("n") or 0)
    enabled = bool(row.get("enabled")) and n == 2
    return Check(
        name, enabled,
        "" if enabled else f"{n} of 2 tables found, relrowsecurity={row.get('enabled')}; "
                           "apply scripts/migrations/016_runtime_roles_rls.sql",
    )


def _governance_chain(evidence: Evidence, run_id: Optional[str]) -> Check:
    """Check keyed policy/execution/data evidence without executing a review."""
    name = "Jessica Gateway decision chain for this run"
    if not run_id:
        return Check(name, False, "no run id in effect; run scripts/workshop-start.sh first")
    if not evidence.available:
        return Check(name, False, evidence.reason or "database unavailable")
    sql = build_receipt._scoped(build_receipt._LAB4, "lab4", True).strip().rstrip(";")
    try:
        bundle = evidence.one(
            f"WITH decisions AS ({sql}) SELECT jsonb_agg(to_jsonb(decisions)) AS rows FROM decisions",
            {"sub": None, "run": run_id},
        ) or {}
        rows = [
            row for row in (bundle.get("rows") or [])
            if (row.get("args") or {}).get("customer_id") == "CUST-JESSICA"
        ]
        for row in rows:
            if row.get("decision") == "DENY":
                row["absence"] = (
                    evidence.one(build_receipt._DENY_ABSENCE, {"key": row["declared_key"]})
                    if row.get("declared_key") else None
                )
        findings = build_receipt._lab4_findings(rows)
        denied = {row["principal_label"].lower() for row in rows if row["decision"] == "DENY"}
        passed = (
            "marco" in denied
            and any(row["principal_label"].lower() == "jessica" and row["decision"] == "ALLOW" for row in rows)
            and all(findings.get(key) == build_receipt.PROVED for key in (
                "allow_executed", "durable_effect", "deny_did_not_execute",
            ))
        )
        return Check(name, passed, "" if passed else
                     "run Lab 4's direct Gateway Marco DENY and Jessica REFUSE/ALLOW/replay proof; "
                     "the Operator journey ends at the pending human checkpoint")
    except Exception as exc:
        return Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")


def _boundary_outcomes(evidence: Evidence, run_id: Optional[str]) -> Check:
    name = "five governance outcomes"
    if not run_id:
        return Check(name, False, "start the workshop run before collecting boundary evidence")
    try:
        sys.path.insert(0, str(BACKEND))
        from services.governance_boundaries import summarize
        bundle = evidence.one("""
            WITH latest AS (
                SELECT proof_run_id FROM pellier.governance_boundary_observations
                 WHERE workshop_run_id = %(run)s
                 GROUP BY proof_run_id ORDER BY max(observation_id) DESC LIMIT 1
            )
            SELECT jsonb_agg(jsonb_build_object(
                'proofRunId', proof_run_id, 'caseName', case_name,
                'observationId', observation_id, 'invocationId', invocation_id,
                'operationKey', operation_key, 'tool', tool,
                'verifiedUsername', verified_username, 'createdAt', created_at,
                'observation', observation) ORDER BY observation_id DESC) AS rows
              FROM pellier.governance_boundary_observations
             WHERE proof_run_id IN (SELECT proof_run_id FROM latest)
        """, {"run": run_id}) or {}
        runs = summarize(bundle.get("rows") or [])["runs"]
        passed = bool(runs and runs[0]["complete"])
        return Check(name, passed, "" if passed else
                     "run prove_governance_outcomes.py and inspect each incomplete boundary; output suppression is not rollback")
    except Exception:
        return Check(name, False, "boundary evidence unavailable; verify migration 055 and the current run")


def lab4_checks(
    evidence: Evidence, run_id: Optional[str], *, repo: pathlib.Path = REPO,
    include_proof: bool = True,
) -> List[Check]:
    checks = [
        *_cedar_checks(repo),
        _rls_check(evidence),
    ]
    if include_proof:
        checks.append(_governance_chain(evidence, run_id))
        checks.append(_boundary_outcomes(evidence, run_id))
    return checks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_lab(
    lab: int,
    evidence: Evidence,
    run_id: Optional[str],
    *,
    run_env: pathlib.Path = DEFAULT_RUN_ENV,
    env_path: pathlib.Path = DEFAULT_ENV,
    phase: str = "proof",
) -> List[Check]:
    if lab == 1:
        return lab1_checks(evidence)
    if lab == 2:
        return lab2_checks(evidence, run_id, include_proof=phase == "proof")
    if lab == 3:
        return lab3_checks(evidence, run_id, run_env=run_env, env_path=env_path, include_proof=phase == "proof")
    return lab4_checks(evidence, run_id, include_proof=phase == "proof")


def render(lab: int, run_id: Optional[str], persona: Optional[str], checks: List[Check]) -> str:
    run = f"run {run_id}" if run_id else "no run id"
    if persona:
        run += f", persona {persona}"
    lines = [f"Pellier doctor: Lab {lab} ({run})", "-" * 60]
    for check in checks:
        state = PASS if check.passed else FAIL
        lines.append(f"{state}  {check.name}" + (f"  ({check.detail})" if check.detail else ""))
    failed = sum(1 for check in checks if not check.passed)
    lines.append("-" * 60)
    lines.append("READY" if failed == 0 else f"NOT READY: {failed} check(s) failed")
    return "\n".join(lines)


def _current_run() -> tuple[Optional[str], Optional[str]]:
    try:
        sys.path.insert(0, str(BACKEND))
        from services.workshop_run import current_run_id, current_run_persona
    except Exception:  # noqa: BLE001 - the doctor must run without the backend
        return None, None
    return current_run_id(), current_run_persona()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check one lab's prerequisites.")
    parser.add_argument("--lab", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--run-id", default=None, help="run to scope to (default: current run)")
    parser.add_argument("--env", default=str(DEFAULT_ENV), help="backend .env path")
    parser.add_argument(
        "--run-env", default=str(DEFAULT_RUN_ENV), help="service run.env the unit sources"
    )
    parser.add_argument(
        "--phase", choices=("prerequisites", "proof"), default="proof",
        help="prerequisites checks authored code/config; proof also requires recorded outcomes",
    )
    args = parser.parse_args(argv)

    run_id, persona = (args.run_id, None) if args.run_id else _current_run()
    if run_id and not build_receipt.RUN_ID_PATTERN.fullmatch(run_id):
        print(f"workshop_doctor: run id {run_id!r} must match run-<12 hex>", file=sys.stderr)
        return 2

    env_path = pathlib.Path(args.env)
    with open_evidence(env_path) as evidence:
        checks = run_lab(
            args.lab,
            evidence,
            run_id,
            run_env=pathlib.Path(args.run_env),
            env_path=env_path,
            phase=args.phase,
        )
    print(f"Phase: {args.phase}")
    print(render(args.lab, run_id, persona, checks))
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
