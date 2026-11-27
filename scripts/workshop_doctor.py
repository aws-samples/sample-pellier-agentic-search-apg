#!/usr/bin/env python3
"""Name the prerequisite a stuck participant has not met, one lab at a time.

The evidence export says which tasks a run has proved. This answers the
question that comes first at a table: "why is Lab N not working for me?" Each
lab has a short list of things that must already be true before its task
can leave evidence, and each one is checked directly rather than inferred from
a symptom.

    Lab 1  retrieval_receipts records citation snapshots; Anna's session has a
           search receipt.
    Lab 2  Aurora reachable; the Stock agent definition grants check_stock alone,
           and the Stock agent that answered Marco's latest stock turn held that
           grant too (a definition saved after his latest turn is named as such);
           the SQL file's not-carried test is written and its pellier.check_stock
           is the live one.
    Lab 3  Task 3A's four rules: get_tickets published, the Support agent asking
           for get_orders and get_tickets, both bound to the signed-in caller,
           and give_store_credit refused on a shopper agent;
           the service environment carries the two settings resolve_rail
           reads (USE_AGENTCORE_RUNTIME, AGENTCORE_RUNTIME_ENDPOINT); a managed
           tool call left its tool_audit row with the build that made it.
    Lab 4  The Cedar policy is present and its rule passes Lab 4A's Cedar check;
           row-level security guards orders and support tickets; an approved
           store credit was recorded exactly once.

Every line prints PASS or FAIL with the reason, and the exit status is 1 on any
FAIL. A database that cannot be reached is a FAIL with the connection error, not
a silent pass: the doctor exists to be believed.

One workshop box serves one participant and a reset rebuilds its database, so
every check reads the newest evidence on the box.

``--environment`` prints the psql client's version beside the server's, which
the session start shows: a client older than the server prints a version
warning at the top of every interactive psql session.

``--memory`` reads Theo's AgentCore Memory preference records once, with a time
cap. Lab 3's Memory finding needs them, so their absence is a facilitator issue
named before the event; the doctor never seeds them and never waits for
extraction.

``--runtimes`` reads each AgentCore Runtime's status and platform version once,
one tab-separated ``ok`` or ``warn`` line per Runtime, for the facilitator's
readiness record only. Every Runtime stays on V1 until AWS retires it, and
readiness must confirm it: a Runtime off V1, or one whose version cannot be
read, makes the box not ready.

Usage::

    uv run scripts/workshop_doctor.py --lab 1
    uv run scripts/workshop_doctor.py --lab 3 --phase prerequisites
    uv run scripts/workshop_doctor.py --environment
    uv run scripts/workshop_doctor.py --memory
    uv run scripts/workshop_doctor.py --runtimes
"""

from __future__ import annotations

import argparse
import ast
import os
import pathlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

REPO = pathlib.Path(__file__).resolve().parents[1]
BACKEND = REPO / "pellier" / "backend"
SCRIPTS = REPO / "scripts"
DEFAULT_ENV = BACKEND / ".env"
DEFAULT_RUN_ENV = pathlib.Path("/etc/pellier/run.env")

sys.path.insert(0, str(SCRIPTS))
import workshop_check  # noqa: E402  (sibling module: database settings, region state)
import lab2_check  # noqa: E402  (sibling script: Lab 2B's live-function reading)
import lab3_check  # noqa: E402  (sibling script: Lab 3's catalog verdict and build query)
import workshop_evidence  # noqa: E402  (sibling script: the Lab 4 evidence query)

PASS = "PASS"
FAIL = "FAIL"

STARTERS = REPO / "workshop" / "starters"
FUNCTION_REGION = lab2_check.FUNCTION_REGION
AGENT_REGION = "Stock agent - definition"

CEDAR_POLICY = "policies/credit_limit.cedar"
CEDAR_STARTER = "workshop/starters/credit_limit.cedar"
POLICY_FILES = (CEDAR_POLICY,)

# Every AgentCore Runtime stays on platform V1 until AWS retires it (owner, 2026-11-11).
# render_agentcore_project.py deploys PINNED_RUNTIME_PLATFORM; a test holds the two in step.
PINNED_RUNTIME_PLATFORM = "V1"
# Each Runtime the box records, by its .env key and the name bootstrap deploys it under.
RUNTIMES = (
    ("AGENTCORE_RUNTIME_ENDPOINT", "pellier_orchestrator"),
    ("AGENTCORE_OPERATOR_RUNTIME_ENDPOINT", "pellier_operator"),
)
# A runtime reaches V2 here only through PELLIER_RUNTIME_PLATFORM_VERSION=V2, which writes
# V2 into the deployed template; deploying without it writes V1, and CloudFormation moves
# the runtime back in place (event 31, 2026-11-04).
REDEPLOY_ON_V1 = ("before the session starts, remove PELLIER_RUNTIME_PLATFORM_VERSION from "
                  ".env, then run bash scripts/deploy/deploy_all.sh from a new terminal. "
                  "CloudFormation moves the runtime back to V1 in place.")
RUNTIME_READ_TIMEOUT_SECONDS = 10

# The workshop runs on Claude Opus 5.5 and Sonnet 5.5 through their global profiles, Cohere
# Rerank 3.5 and Cohere Embed v4 (owner, 2026-11-25). check_model_access.py's MODELS holds the
# IDs; readiness calls each live. Its health gate already fails the stack without Sonnet, Rerank
# or Embed, but lets Sonnet stand in for a denied Opus, so readiness also reads which model the
# Catalog and Support agents were configured with, and which one the running backend loaded:
# recheck_model_access.sh saves Opus 5.5 before it restarts Pellier, and a restart that did not
# land leaves the old process serving the model it started with. That reading stays here, in the
# readiness record, because a failed health gate fails the whole stack and this is a one-command
# fix on a working box.
READINESS_MODELS = ("Claude Opus 5.5", "Claude Sonnet", "Cohere Rerank v3.5", "Cohere Embed v4")
MODEL_SHOWN = {"Claude Sonnet": "Claude Sonnet 5.5"}
OPUS_MODEL = "Claude Opus 5.5"
MODEL_FIX = ("once this account's Bedrock access allows it, run bash "
             "scripts/recheck_model_access.sh, then uv run scripts/event_readiness.py --live; "
             "or give the participant a spare account.")
RELOAD_FIX = ("run bash scripts/recheck_model_access.sh, which restarts Pellier and checks the "
              "model it loaded, then uv run scripts/event_readiness.py --live.")
DEFAULT_HEALTH_URL = "http://localhost:8000/api/health"
HEALTH_READ_TIMEOUT_SECONDS = 3
# The whole readiness record has 180 s (event_readiness.py). A call takes at most two tries of
# 3 s to connect and 8 s to answer, and no model is called once 40 s have gone, so the check
# ends within about 85 s even when Embed's two IDs start at the deadline. A model call usually
# answers in 1 to 3 s.
MODEL_CONNECT_TIMEOUT_SECONDS = 3
MODEL_READ_TIMEOUT_SECONDS = 8
MODEL_CHECK_BUDGET_SECONDS = 40

_DB_REACHABLE = "SELECT 1 AS ok;"
# The grant the Stock agent held on Marco's latest turn it answered, as its
# in-process audit row recorded it.
_RUNNING_STOCK_GRANT = """
SELECT audit_id, args->'grant' AS grant
  FROM pellier.tool_audit
 WHERE session_id LIKE 'persona-marco-%'
   AND args->>'agent' = 'stock'
 ORDER BY audit_id DESC
 LIMIT 1;
"""
# Anna's newest search receipt: the session choosing Anna on the home page starts.
_ANNA_RECEIPT = """
SELECT receipt_id
  FROM pellier.retrieval_receipts
 WHERE session_id LIKE 'persona-anna-%'
 ORDER BY receipt_id DESC
 LIMIT 1;
"""
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
           AND policyname IN ('orders_own_rows', 'support_tickets_own_rows')) AS policies
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
    cfg = workshop_check.db_config(env_path)
    if cfg is None:
        return Evidence(reason=workshop_check.missing_settings_reason(env_path))
    try:
        return Evidence(conn=workshop_check.connect(cfg, timeout=5))
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


def psql_versions(evidence: Evidence, run: Optional[Callable[..., Any]] = None) -> Check:
    """``psql --version`` beside ``SHOW server_version``; the client must not be the older major.

    Args:
        evidence: the read-only Aurora surface that answers ``SHOW server_version``.
        run: runs ``psql --version``; ``subprocess.run`` unless a test injects one.

    Returns:
        A check whose detail is the client's version line and the server's version.
    """
    name = "psql client and server"
    run = run or subprocess.run
    try:
        client = run(["psql", "--version"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return Check(name, False, f"psql --version failed ({exc}); install postgresql18")
    client = client.strip()
    if not client:
        return Check(name, False, "psql --version printed nothing; install postgresql18")
    if not evidence.available:
        return Check(name, False, f"{client}; server unreachable: {evidence.reason}")
    try:
        row = evidence.one("SHOW server_version;") or {}
    except Exception as exc:  # noqa: BLE001 - the error is the finding
        return Check(name, False, f"{client}; SHOW server_version failed: {exc}")
    server = str(row.get("server_version") or "").split()[0] if row else ""
    detail = f"{client}, server_version {server}"
    client_major = re.search(r"\(PostgreSQL\) (\d+)", client)
    server_major = re.match(r"(\d+)", server)
    if not client_major or not server_major:
        return Check(name, False, f"{detail}: could not read both major versions")
    if int(client_major.group(1)) < int(server_major.group(1)):
        return Check(name, False, f"{detail}: the client is older than the server; install "
                                  f"postgresql{server_major.group(1)}")
    return Check(name, True, detail)


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


def _region_built(name: str, path: pathlib.Path, region: str, starter: pathlib.Path) -> Check:
    state = workshop_check.region_state(path, region, starter)
    if state == workshop_check.MISSING:
        return Check(name, False, f"the {region} markers are missing from {path.name}")
    if state == workshop_check.STARTER:
        return Check(name, False, f"the {region} block in {path.name} is unchanged: your edit is not saved there yet")
    return Check(name, True, f"the {region} block in {path.name} is edited")


def source_grant(path: pathlib.Path) -> Optional[List[str]]:
    """The tool names ``_STOCK_TOOLS`` lists in the definition's source, or None."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_STOCK_TOOLS"
                and isinstance(node.value, (ast.List, ast.Tuple))):
            return [item.attr if isinstance(item, ast.Attribute) else getattr(item, "id", "?")
                    for item in node.value.elts]
    return None


def _running_stock_grant(evidence: Evidence) -> Optional[Dict[str, Any]]:
    if not evidence.available:
        return None
    try:
        return evidence.one(_RUNNING_STOCK_GRANT)
    except Exception:  # noqa: BLE001 - the source check still stands on its own
        return None


def _grant_check(evidence: Evidence, path: pathlib.Path) -> Check:
    """The definition grants check_stock alone, and the running agent loaded it."""
    name = "Stock agent granted check_stock alone"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if workshop_check.region_body(text, AGENT_REGION) is None:
        return Check(name, False, f"the {AGENT_REGION} markers are missing from {path.name}")
    grant = source_grant(path)
    if grant != ["check_stock"]:
        listed = ", ".join(grant) if grant else "no readable _STOCK_TOOLS list"
        return Check(name, False, f"{path.name} grants {listed}; Task 2A connects check_stock "
                                  "alone, the one tool that reads warehouse_inventory")
    running = _running_stock_grant(evidence)
    held = (running or {}).get("grant")
    if isinstance(held, list) and held != ["check_stock"]:
        return Check(name, False, (
            f"{path.name} grants check_stock alone, but the Stock agent that answered Marco's "
            f"latest stock turn (audit {running.get('audit_id')}) held {', '.join(held)}: "
            "send his request again: uv run scripts/lab_run.py send --lab 2 --task 2A"))
    return Check(name, True, f"{path.name} grants check_stock alone")


def _function_check(evidence: Evidence, worksheet: pathlib.Path,
                    starter: pathlib.Path) -> Check:
    """The not-carried test is written, and the function the SQL file holds is live."""
    name = "check_stock committed"
    built = _region_built(name, worksheet, FUNCTION_REGION, starter)
    if not built.passed:
        return built
    if not evidence.available:
        return Check(name, False, evidence.reason or "database unavailable")
    try:
        row = evidence.one(lab2_check._LIVE_FUNCTION) or {}
    except Exception as exc:  # noqa: BLE001 - the error is the finding
        return Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    body = lab2_check.function_body(worksheet.read_text(encoding="utf-8"))
    if body is not None and row.get("source_sha") == lab2_check._sha(body):
        return Check(name, True, f"the live pellier.check_stock is the one {worksheet.name} holds")
    return Check(name, False, (f"{worksheet.name} is edited, but the live pellier.check_stock is "
                               f"not its function: run {lab2_check.WORKSHEET_RUN}"))


def lab2_checks(evidence: Evidence, *, backend: pathlib.Path = BACKEND,
                workshop: pathlib.Path = REPO / "workshop") -> List[Check]:
    return [
        _db_reachable(evidence),
        _grant_check(evidence, backend / "agents" / "stock_agent.py"),
        _function_check(evidence, workshop / "lab-2-check-stock.sql",
                        STARTERS / "lab-2-check-stock.sql"),
    ]


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
        name="Anna's search receipt",
        sql=_ANNA_RECEIPT,
        key="receipt_id",
        hint="no pellier.retrieval_receipts row in a session of Anna's; send her request "
             "with uv run scripts/lab_run.py send --lab 1",
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
    # Later files win, as in the unit: the repo .env, then run.env.
    layered: Dict[str, Tuple[str, str]] = {}
    for path in (env_path, run_env):
        for key, value in workshop_check.parse_dotenv(path).items():
            if value:
                layered[key] = (value, str(path))

    def _value(key: str) -> str:
        if key in layered:
            return layered[key][0].strip()
        return environ.get(key, "").strip()

    missing = []
    switch = _value("USE_AGENTCORE_RUNTIME")
    if switch.lower() != "true":
        missing.append(f"USE_AGENTCORE_RUNTIME={switch or 'unset'} (want true)")
    if not _value("AGENTCORE_RUNTIME_ENDPOINT"):
        missing.append("AGENTCORE_RUNTIME_ENDPOINT unset (the Runtime ARN)")
    if missing:
        return Check(name, False, "; ".join(missing) + "; run scripts/lab3-start.sh")
    # Name the file that actually set the switch, never one that does not exist.
    return Check(name, True, layered.get("USE_AGENTCORE_RUNTIME", ("", "process environment"))[1])


def _managed_catalogs_agree() -> Check:
    """Lab 3A, read from source before anything is deployed.

    The managed Router asks the Gateway for exactly the tools the Support agent
    names. A tool the Gateway does not publish is left out of the agent, which
    then tells Theo it can't look up his support tickets here: a turn that
    "works" and answers nothing. Naming the gap here is cheaper than finding it
    in a trace. The verdict is ``lab3_check.catalog_verdict`` over Task 3A's
    four rules, which the evidence export reads too.
    """
    name = "Gateway published tools and Runtime support contract agree"
    try:
        finding = lab3_check.catalog_verdict(
            lab3_check.judge_catalog(*lab3_check.source_catalog()))
    except Exception as exc:  # noqa: BLE001 - the doctor must not crash here
        return Check(name, False, f"could not read the catalogs: {exc}")
    if finding.state == workshop_check.PASSED:
        return Check(name, True, finding.observed)
    return Check(name, False, f"{finding.observed}: {finding.next_step}")


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
        _managed_catalogs_agree(),
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
        row = evidence.one(lab3_check.BUILD_SQL, {"since": workshop_check.reset_point(3)})
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    if not row:
        return Check(name, False, "no Gateway tool_audit row for a shopper turn; run "
                                  "bash scripts/lab3-start.sh theo to switch the rail, then "
                                  "uv run scripts/lab_run.py send --lab 3")
    build = str(row.get("deployed_fingerprint") or "")
    if not build:
        return Check(name, False, f"turn {row.get('turn_id')} carries no build; deploy your "
                                  "Task 3A change, then uv run scripts/lab_run.py send --lab 3")
    return Check(name, True, f"turn {row.get('turn_id')} ran build {build[:12]}")


# ---------------------------------------------------------------------------
# Lab 4
# ---------------------------------------------------------------------------


def _cedar_checks(repo: pathlib.Path) -> List[Check]:
    """The policy file is present, and its rule passes Lab 4A's Cedar check here."""
    import lab4_policy

    missing = [rel for rel in POLICY_FILES if not (repo / rel).is_file()]
    pair = Check(
        "Cedar policy present in policies/",
        not missing,
        "missing: " + ", ".join(missing) if missing else ", ".join(POLICY_FILES),
    )
    name = "credit limit passes the Cedar check"
    try:
        policy = (repo / CEDAR_POLICY).read_text(encoding="utf-8")
        starter = (repo / CEDAR_STARTER).read_text(encoding="utf-8")
    except OSError as exc:
        return [pair, Check(name, False, f"unreadable: {exc}")]
    if policy == starter:
        return [pair, Check(name, False, f"{CEDAR_POLICY} is unchanged: "
                                          "complete the unless block")]
    try:
        finding = lab4_policy.local_check(policy, starter).finding
    except Exception as exc:  # noqa: BLE001 - the doctor must not crash here
        return [pair, Check(name, False, f"the Cedar check could not run: {exc}")]
    if finding.state == workshop_check.PASSED:
        return [pair, Check(name, True, finding.observed)]
    return [pair, Check(name, False, f"{finding.observed}: {finding.next_step}")]


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
        row = evidence.one(workshop_evidence.LAB4_SQL)
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"{type(exc).__name__}: {str(exc)[:120]}")
    findings = workshop_evidence.credit_findings(row)
    passed = all(state == workshop_check.PASSED for state in findings.values())
    if passed:
        return Check(name, True, f"key {row.get('idempotency_key')}")
    if not row:
        return Check(name, False, "no store credit yet; approve and execute Jessica's review "
                                  "as Nadia in the Operator")
    return Check(name, False, f"key {row.get('idempotency_key')}: {row.get('credit_rows')} credit "
                              f"row(s), {row.get('audit_rows')} audit row(s), "
                              f"{row.get('amount_cents')} cents of "
                              f"{row.get('approved_cents')} approved")


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
        return lab3_checks(evidence, run_env=run_env, env_path=env_path,
                           include_proof=phase == "proof")
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


THEO = "CUST-THEO"
MEMORY_TIMEOUT_SECONDS = 10.0
SEED_MEMORY = "scripts/deploy/seed_agentcore_memory.py"


def read_theo_preferences() -> List[Dict[str, str]]:
    """Theo's preference records, read the way the managed rail reads them at turn start."""
    import asyncio

    for path in (BACKEND, SCRIPTS / "deploy"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from gateway_client import _load_env

    _load_env()
    from config import settings
    from services.agentcore_memory import AgentCoreMemory

    memory_id = settings.AGENTCORE_MEMORY_ID
    if not memory_id:
        raise RuntimeError("AGENTCORE_MEMORY_ID is not configured")
    strict = AgentCoreMemory(memory_id=memory_id, region=settings.aws_region_resolved,
                             strict=True)
    return asyncio.run(strict.get_semantic_memories(THEO))


def memory_ready(read: Callable[[], List[Dict[str, str]]],
                 timeout: float = MEMORY_TIMEOUT_SECONDS) -> Check:
    """One bounded read of Theo's records; never a seed, a retry or a wait for extraction."""
    import threading

    outcome: Dict[str, Any] = {}

    def attempt() -> None:
        try:
            outcome["records"] = read()
        except Exception as exc:  # noqa: BLE001 - reported with its type, never raised
            outcome["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    worker = threading.Thread(target=attempt, daemon=True)
    worker.start()
    worker.join(timeout)
    name = "Theo's AgentCore Memory"
    if worker.is_alive():
        return Check(name, False, f"Facilitator: {name} did not answer within {timeout:g} s; "
                                  "check the Memory resource before Lab 3.")
    if "error" in outcome:
        return Check(name, False, f"Facilitator: {name} could not be read "
                                  f"({outcome['error']}); check it before Lab 3.")
    count = len(outcome.get("records") or [])
    if not count:
        return Check(name, False, f"Facilitator: {name} has no preference records, so Lab 3's "
                                  f"Memory finding will fail. Run {SEED_MEMORY} on this box "
                                  "before Lab 3.")
    noun = "record" if count == 1 else "records"
    return Check(name, True, f"{name} holds {count} preference {noun} for Lab 3")


def read_runtime_raw(arn: str, client: Any = None) -> Dict[str, Any]:
    """``GetAgentRuntime`` as the service sent it.

    The raw body is read because a botocore that predates the field drops
    ``platformVersion`` while parsing; 1.43.51, the backend's lock, is one.
    """
    import json

    if client is None:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "bedrock-agentcore-control", region_name=arn.split(":")[3],
            config=Config(connect_timeout=5, read_timeout=RUNTIME_READ_TIMEOUT_SECONDS,
                          retries={"max_attempts": 2}))
    captured: Dict[str, bytes] = {}

    def keep(response_dict: Dict[str, Any], **_: Any) -> None:
        captured["body"] = response_dict.get("body") or b""

    client.meta.events.register("before-parse.bedrock-agentcore-control.GetAgentRuntime", keep)
    client.get_agent_runtime(agentRuntimeId=arn.rsplit("/", 1)[-1])
    return json.loads(captured.get("body") or b"{}")


def runtime_platform_check(name: str, raw: Mapping[str, Any]) -> Check:
    """One Runtime's line: READY on the pinned platform, or what stops the box being ready."""
    label = f"AgentCore Runtime {raw.get('agentRuntimeName') or name}"
    status = raw.get("status") or "unknown"
    if status != "READY":
        return Check(label, False, f"Facilitator: {label}: status {status}, not READY")
    platform = raw.get("platformVersion")
    if platform is None:
        return Check(label, False, f"Facilitator: {label}: could not read the platform version "
                                   "(the response has no platformVersion)")
    if platform != PINNED_RUNTIME_PLATFORM:
        return Check(label, False, f"Facilitator: {label}: platform {platform}, not the pinned "
                                   f"{PINNED_RUNTIME_PLATFORM}. Fix: {REDEPLOY_ON_V1}")
    return Check(label, True, f"{label}: READY on platform {PINNED_RUNTIME_PLATFORM}")


def runtime_platform_checks(env: Mapping[str, str],
                            read: Callable[[str], Mapping[str, Any]]) -> List[Check]:
    """Each Runtime the box records, read once; readiness must confirm V1 on every one."""
    checks: List[Check] = []
    for key, name in RUNTIMES:
        label = f"AgentCore Runtime {name}"
        arn = (env.get(key) or "").strip()
        if not arn:
            checks.append(Check(label, False, f"Facilitator: {label}: could not read the "
                                              f"platform version ({key} is not set)"))
            continue
        try:
            raw = read(arn)
        except Exception as exc:  # noqa: BLE001 - reported with its type, never raised
            checks.append(Check(label, False, f"Facilitator: {label}: could not read the "
                                              f"platform version ({type(exc).__name__}: "
                                              f"{str(exc)[:160]})"))
            continue
        checks.append(runtime_platform_check(name, raw))
    return checks


def readiness_models() -> List[Dict[str, Any]]:
    """The four models the workshop runs on, as check_model_access.py defines them."""
    import check_model_access  # sibling script; loads no .env when imported

    by_name = {model["name"]: model for model in check_model_access.MODELS}
    return [by_name[name] for name in READINESS_MODELS]


def bedrock_clients(env: Mapping[str, str]) -> Tuple[Any, Any]:
    """bedrock-runtime and bedrock-agent-runtime (Rerank) in the box's Region."""
    import boto3
    from botocore.config import Config

    region = (env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "us-east-1").strip()
    config = Config(connect_timeout=MODEL_CONNECT_TIMEOUT_SECONDS,
                    read_timeout=MODEL_READ_TIMEOUT_SECONDS,
                    retries={"max_attempts": 2})
    return (boto3.client("bedrock-runtime", region_name=region, config=config),
            boto3.client("bedrock-agent-runtime", region_name=region, config=config))


def probe_bedrock_model(model: Mapping[str, Any],
                        clients: Tuple[Any, Any]) -> Tuple[bool, str, str]:
    """Call one model as the preflight does: (answered, model ID, the preflight's reason)."""
    import contextlib
    import io
    import check_model_access

    attempt = dict(model)  # check_model records the variant that answered on its argument
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        answered = check_model_access.check_model(clients[0], clients[1], attempt)
    model_id = (attempt.get("_resolved_id") or attempt.get("model_id")
                or attempt["model_id_variants"][0])
    reason = " ".join(line.strip() for line in printed.getvalue().splitlines() if line.strip())
    return answered, model_id, reason[:200]


def running_editorial_default(health_url: str) -> Optional[bool]:
    """Whether the running backend loaded the default editorial model, from /api/health.

    None when the endpoint does not answer or does not say: readiness cannot confirm it then.
    """
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(health_url, timeout=HEALTH_READ_TIMEOUT_SECONDS) as response:
            loaded = json.load(response).get("editorial_model_is_default")
    except (OSError, ValueError, AttributeError):  # unreachable, not JSON, or not an object
        return None
    return loaded if isinstance(loaded, bool) else None


def editorial_model_check(configured: str, opus_id: str,
                          loaded: Callable[[], Optional[bool]]) -> Check:
    """Which model the Catalog and Support agents use, saved and as the running backend loaded it."""
    if configured != opus_id:
        return Check("editorial model", False, (
            f"Facilitator: the Catalog and Support agents use {configured}, not Claude Opus 5.5 "
            f"({opus_id}). Fix: {MODEL_FIX}"))
    running = loaded()
    if running is True:
        return Check("editorial model", True, "The Catalog and Support agents use Claude Opus 5.5")
    saved = ("Facilitator: the saved settings put the Catalog and Support agents on Claude Opus "
             f"5.5 ({opus_id}), but")
    if running is False:
        return Check("editorial model", False, (
            f"{saved} the running Pellier still uses the model it started with. Fix: {RELOAD_FIX}"))
    return Check("editorial model", False, (
        f"{saved} /api/health did not say which model the running Pellier loaded. "
        f"Fix: {RELOAD_FIX}"))


def bedrock_model_checks(env: Mapping[str, str],
                         probe: Callable[[Mapping[str, Any]], Tuple[bool, str, str]],
                         *,
                         loaded: Callable[[], Optional[bool]],
                         clock: Callable[[], float] = time.monotonic,
                         budget: float = MODEL_CHECK_BUDGET_SECONDS) -> List[Check]:
    """One line per model it calls, then which model the Catalog and Support agents use.

    Args:
        env: The settings as the pellier unit reads them.
        probe: Calls one model: (answered, model ID, the preflight's reason).
        loaded: Whether the running backend loaded the default editorial model; None if unknown.
        clock: Seconds, for the budget.
        budget: Seconds after which no further model is called.
    """
    checks: List[Check] = []
    opus_id = ""
    started = clock()
    for model in readiness_models():
        shown = MODEL_SHOWN.get(model["name"], model["name"])
        first = model.get("model_id") or model["model_id_variants"][0]
        opus_id = first if model["name"] == OPUS_MODEL else opus_id
        if clock() - started > budget:
            checks.append(Check(shown, False, (
                f"Facilitator: Bedrock {shown} was not checked ({first}): the model check ran "
                f"past {budget:g} s. Fix: record readiness again with uv run "
                "scripts/event_readiness.py --live")))
            continue
        try:
            answered, model_id, reason = probe(model)
        except Exception as exc:  # noqa: BLE001 - reported with its type, never raised
            answered, model_id, reason = False, first, f"{type(exc).__name__}: {str(exc)[:160]}"
        if answered:
            checks.append(Check(shown, True, f"Bedrock {shown} answers ({model_id})"))
        else:
            checks.append(Check(shown, False, f"Facilitator: Bedrock {shown} does not answer "
                                              f"({model_id}): {reason or 'no reason given'}. "
                                              f"Fix: {MODEL_FIX}"))
    configured = (env.get("BEDROCK_OPUS_MODEL") or "").strip() or opus_id
    checks.append(editorial_model_check(configured, opus_id, loaded))
    return checks


def models_main(env_path: pathlib.Path, run_env: pathlib.Path) -> int:
    """--models: print one ok/warn line per check; exit 1 when any is not ready.

    The settings are read as the pellier unit reads them: .env, then run.env over it.
    """
    env = {**workshop_check.parse_dotenv(env_path), **workshop_check.parse_dotenv(run_env),
           **os.environ}
    clients = bedrock_clients(env)
    health_url = (env.get("HEALTH_URL") or "").strip() or DEFAULT_HEALTH_URL
    checks = bedrock_model_checks(env, lambda model: probe_bedrock_model(model, clients),
                                  loaded=lambda: running_editorial_default(health_url))
    for check in checks:
        print(f"{'ok' if check.passed else 'warn'}\t{check.detail}")
    return 0 if all(check.passed for check in checks) else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check one lab's prerequisites.")
    parser.add_argument("--lab", type=int, choices=(1, 2, 3, 4))
    parser.add_argument(
        "--environment", action="store_true",
        help="print psql --version beside SHOW server_version, and nothing else",
    )
    parser.add_argument(
        "--memory", action="store_true",
        help="read Theo's AgentCore Memory preference records once, and nothing else",
    )
    parser.add_argument(
        "--runtimes", action="store_true",
        help="read each AgentCore Runtime's status and platform version, and nothing else",
    )
    parser.add_argument(
        "--models", action="store_true",
        help="call the four Bedrock models the workshop runs on, and nothing else",
    )
    parser.add_argument("--env", default=str(DEFAULT_ENV), help="backend .env path")
    parser.add_argument(
        "--run-env", default=str(DEFAULT_RUN_ENV), help="service run.env the unit sources"
    )
    parser.add_argument(
        "--phase", choices=("prerequisites", "proof"), default="proof",
        help="prerequisites checks authored code/config; proof also requires recorded outcomes",
    )
    args = parser.parse_args(argv)
    if args.lab is None and not (args.environment or args.memory or args.runtimes
                                 or args.models):
        parser.error("name a lab with --lab, or pass --environment, --memory, --runtimes "
                     "or --models")
    if args.models:
        return models_main(pathlib.Path(args.env), pathlib.Path(args.run_env))
    if args.memory:
        memory = memory_ready(read_theo_preferences)
        print(memory.detail)
        return 0 if memory.passed else 1
    if args.runtimes:
        env = {**workshop_check.parse_dotenv(pathlib.Path(args.env)), **os.environ}
        runtimes = runtime_platform_checks(env, read_runtime_raw)
        for check in runtimes:
            print(f"{'ok' if check.passed else 'warn'}\t{check.detail}")
        return 0 if all(check.passed for check in runtimes) else 1

    env_path = pathlib.Path(args.env)
    if args.environment:
        with open_evidence(env_path) as evidence:
            versions = psql_versions(evidence)
        print(versions.detail)
        return 0 if versions.passed else 1
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
