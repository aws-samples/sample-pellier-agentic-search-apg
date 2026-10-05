#!/usr/bin/env python3
"""Name the prerequisite a stuck participant has not met, one lab at a time.

The build receipt says which boundaries a run has proved. This answers the
question that comes first at a table: "why is Lab N not working for me?" Each
lab has a short list of things that must already be true before its exercise
can leave evidence, and each one is checked directly rather than inferred from
a symptom.

    Lab 1  retrieval_receipts records citation snapshots; a hybrid retrieval
           receipt exists.
    Lab 2  Aurora reachable; check_stock wired past the stub; the Stock agent
           definition no longer stubbed.
    Lab 3  The service environment carries the two settings resolve_rail
           reads (USE_AGENTCORE_RUNTIME, AGENTCORE_RUNTIME_ENDPOINT); a managed
           tool call left its tool_audit row with the build that made it.
    Lab 4  The Cedar policy is present and its rule has been authored;
           row-level security guards orders and support tickets; an approved
           store credit was recorded exactly once.

Every line prints PASS or FAIL with the reason, and the exit status is 1 on any
FAIL. A database that cannot be reached is a FAIL with the connection error, not
a silent pass: the doctor exists to be believed.

One workshop box serves one participant and a reset rebuilds its database, so
every check reads the newest evidence on the box.

Usage::

    python3 scripts/workshop_doctor.py --lab 1
    python3 scripts/workshop_doctor.py --lab 3 --phase prerequisites
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
import build_receipt  # noqa: E402  (sibling script: dotenv, DSN, the evidence queries)

PASS = "PASS"
FAIL = "FAIL"

TOOL_BLOCK_START = "# === WORKSHOP - Stock agent - check_stock: START ==="
TOOL_BLOCK_END = "# === WORKSHOP - Stock agent - check_stock: END ==="
TOOL_STUB_MARKERS = ("check_stock is in stub state", "received_product_query")
AGENT_STUB_MARKER = "_STOCK_AGENT_STUBBED = True"
# The SQL keyword, not the English words `selected` and `selection`, which a
# stub envelope can easily contain.
_SELECT_KEYWORD = re.compile(r"\bSELECT\b", re.IGNORECASE)

CEDAR_POLICY = "policies/workshop_identity_match_forbid.cedar"
CEDAR_STARTER = "workshop/starters/workshop_identity_match_forbid.cedar"
POLICY_FILES = (CEDAR_POLICY,)

_DB_REACHABLE = "SELECT 1 AS ok;"
_CITATION_COLUMNS = """
SELECT count(*) AS n
  FROM information_schema.columns
 WHERE table_schema = 'pellier'
   AND table_name = 'retrieval_receipts'
   AND column_name IN ('citation_snapshots', 'citation_snapshot_hash');
"""
# Row-level security on the two customer tables, and the owner policy on each.
_ROW_SECURITY = """
SELECT count(*) FILTER (WHERE c.relrowsecurity) AS enabled,
       count(*) AS n,
       (SELECT count(*) FROM pg_policies
         WHERE schemaname = 'pellier'
           AND policyname IN ('orders_owner', 'support_tickets_owner')) AS policies
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'pellier'
   AND c.relname IN ('orders', 'support_tickets');
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


def _newest_row(evidence: Evidence, *, name: str, sql: str, key: str, hint: str) -> Check:
    """PASS when ``sql`` finds a row; FAIL names what is missing."""
    if not evidence.available:
        return Check(name, False, evidence.reason or "database unavailable")
    try:
        row = evidence.one(sql)
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    if row:
        return Check(name, True, f"{key}={row.get(key)}")
    return Check(name, False, hint)


# ---------------------------------------------------------------------------
# Lab 2
# ---------------------------------------------------------------------------


def _tool_wired(source: str) -> Check:
    name = "check_stock wired"
    start = source.find(TOOL_BLOCK_START)
    end = source.find(TOOL_BLOCK_END)
    if start < 0 or end < 0 or end < start:
        return Check(name, False, "workshop marker block not found in services/agent_tools.py")
    block = source[start + len(TOOL_BLOCK_START):end]
    if any(marker in block for marker in TOOL_STUB_MARKERS):
        return Check(name, False, "the marker block still returns the shipped stub envelope")
    if "check_stock(" not in block and not _SELECT_KEYWORD.search(block):
        return Check(name, False, "the marker block has no query: it neither calls "
                                  "store_tools.check_stock nor runs SQL")
    return Check(name, True, "marker block calls into the stock read")


def lab2_checks(evidence: Evidence, *, backend: pathlib.Path = BACKEND) -> List[Check]:
    checks = [_db_reachable(evidence)]
    try:
        tool_source = (backend / "services" / "agent_tools.py").read_text(encoding="utf-8")
        checks.append(_tool_wired(tool_source))
    except OSError as exc:
        checks.append(Check("check_stock wired", False, f"unreadable: {exc}"))
    try:
        agent_source = (backend / "agents" / "stock_agent.py").read_text(encoding="utf-8")
        stubbed = AGENT_STUB_MARKER in agent_source
        checks.append(
            Check(
                "Stock agent defined",
                not stubbed,
                "_STOCK_AGENT_STUBBED is still True in agents/stock_agent.py"
                if stubbed else "",
            )
        )
    except OSError as exc:
        checks.append(Check("Stock agent defined", False, f"unreadable: {exc}"))
    return checks


# ---------------------------------------------------------------------------
# Lab 1
# ---------------------------------------------------------------------------


def lab1_checks(evidence: Evidence, *, include_proof: bool = True) -> List[Check]:
    name = "retrieval receipts record citation snapshots"
    if not evidence.available:
        columns = Check(name, False, evidence.reason or "database unavailable")
    else:
        try:
            row = evidence.one(_CITATION_COLUMNS)
            n = int((row or {}).get("n") or 0)
            columns = Check(
                name, n == 2,
                "" if n == 2 else f"{n} of 2 citation columns on pellier.retrieval_receipts; "
                                  "rebuild with 'reset-governed'",
            )
        except Exception as exc:  # noqa: BLE001
            columns = Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    if not include_proof:
        return [columns]
    receipt = _newest_row(
        evidence,
        name="hybrid retrieval receipt",
        sql=build_receipt._LAB1,
        key="receipt_id",
        hint="no pellier.retrieval_receipts row with both ranks and their fusion; "
             "run Anna's hybrid turn",
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
            if "get_tickets" in missing:
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
        for tool in ("get_tickets",)
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
    return [*checks, _managed_build(evidence)]


def _managed_build(evidence: Evidence) -> Check:
    """A managed tool call left its tool_audit row, stamped with its build."""
    name = "managed tool call recorded with its build"
    if not evidence.available:
        return Check(name, False, evidence.reason or "database unavailable")
    try:
        row = evidence.one(build_receipt._LAB3)
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    if not row:
        return Check(name, False, "no Gateway tool_audit row for a shopper turn; run "
                                  "scripts/lab3-start.sh to switch the rail, then run a Theo "
                                  "turn in Pellier as a signed-in caller")
    build = str(row.get("deployed_fingerprint") or "")
    if not build:
        return Check(name, False, f"turn {row.get('turn_id')} carries no build; deploy your "
                                  "Task 3A change and run Theo's turn again")
    return Check(name, True, f"turn {row.get('turn_id')} ran build {build[:12]}")


# ---------------------------------------------------------------------------
# Lab 4
# ---------------------------------------------------------------------------


def _cedar_checks(repo: pathlib.Path) -> List[Check]:
    missing = [rel for rel in POLICY_FILES if not (repo / rel).is_file()]
    pair = Check(
        "Cedar policy present in policies/",
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
    name = "row-level security on orders and support tickets"
    if not evidence.available:
        return Check(name, False, evidence.reason or "database unavailable")
    try:
        row = evidence.one(_ROW_SECURITY) or {}
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    enabled, n, policies = (int(row.get(k) or 0) for k in ("enabled", "n", "policies"))
    passed = enabled == 2 and n == 2 and policies == 2
    return Check(
        name, passed,
        "" if passed else f"{enabled} of 2 tables enforce it, {policies} of 2 owner policies; "
                          "rebuild with 'reset-governed'",
    )


def _credit_recorded_once(evidence: Evidence) -> Check:
    """Jessica's approved credit, one store_credits row and one tool_audit row for its key."""
    name = "approved credit recorded once"
    if not evidence.available:
        return Check(name, False, evidence.reason or "database unavailable")
    try:
        row = evidence.one(build_receipt._LAB4)
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    findings = build_receipt._lab4_findings(row, True)
    passed = all(state == build_receipt.PROVED for state in findings.values())
    if passed:
        return Check(name, True, f"key {row.get('idempotency_key')}")
    if not row:
        return Check(name, False, "no store credit yet; approve and execute Jessica's review "
                                  "as Nadia in the Operator")
    return Check(name, False, f"key {row.get('idempotency_key')}: {row.get('credit_rows')} credit "
                              f"row(s), {row.get('audit_rows')} audit row(s), "
                              f"{row.get('amount_cents')} cents of {row.get('approved_cents')} approved")


def lab4_checks(
    evidence: Evidence, *, repo: pathlib.Path = REPO, include_proof: bool = True,
) -> List[Check]:
    checks = [
        *_cedar_checks(repo),
        _rls_check(evidence),
    ]
    if include_proof:
        checks.append(_credit_recorded_once(evidence))
    return checks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_lab(
    lab: int,
    evidence: Evidence,
    *,
    run_env: pathlib.Path = DEFAULT_RUN_ENV,
    env_path: pathlib.Path = DEFAULT_ENV,
    phase: str = "proof",
) -> List[Check]:
    if lab == 1:
        return lab1_checks(evidence, include_proof=phase == "proof")
    if lab == 2:
        return lab2_checks(evidence)
    if lab == 3:
        return lab3_checks(evidence, run_env=run_env, env_path=env_path, include_proof=phase == "proof")
    return lab4_checks(evidence, include_proof=phase == "proof")


def render(lab: int, checks: List[Check]) -> str:
    lines = [f"Pellier doctor: Lab {lab}", "-" * 60]
    for check in checks:
        state = PASS if check.passed else FAIL
        lines.append(f"{state}  {check.name}" + (f"  ({check.detail})" if check.detail else ""))
    failed = sum(1 for check in checks if not check.passed)
    lines.append("-" * 60)
    lines.append("READY" if failed == 0 else f"NOT READY: {failed} check(s) failed")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check one lab's prerequisites.")
    parser.add_argument("--lab", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--env", default=str(DEFAULT_ENV), help="backend .env path")
    parser.add_argument(
        "--run-env", default=str(DEFAULT_RUN_ENV), help="service run.env the unit sources"
    )
    parser.add_argument(
        "--phase", choices=("prerequisites", "proof"), default="proof",
        help="prerequisites checks authored code/config; proof also requires recorded outcomes",
    )
    args = parser.parse_args(argv)

    env_path = pathlib.Path(args.env)
    with open_evidence(env_path) as evidence:
        checks = run_lab(
            args.lab,
            evidence,
            run_env=pathlib.Path(args.run_env),
            env_path=env_path,
            phase=args.phase,
        )
    print(f"Phase: {args.phase}")
    print(render(args.lab, checks))
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
