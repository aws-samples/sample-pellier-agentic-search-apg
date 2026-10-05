#!/usr/bin/env python3
"""Export a participant's proof for all four labs, read from the system of record.

One line per task, eight in all. Each one says whether the claim is proved
and prints the three things every check prints: what was expected, what was
observed, and the evidence behind it (the row, the decision, the key). A line
that is not proved says what to look at next. Nothing here writes a row,
needs a run id, or reads a notes file: the evidence is the database and the
source the labs changed.

Every line is in one of four states, never two (``workshop_check``):
PROVED, NOT YET, UNCHECKED and CONTRADICTED. UNCHECKED is not a soft NOT
YET: "this did not happen" and "I could not look" are different findings.

Labs 1 and 2 run the same checks the guide runs (``workshop/lab-1-rrf.sql``,
``scripts/lab1_compare.py``, ``scripts/lab2_contract_check.py``), so the
export and the lab never disagree. A task whose marked region still holds
its starter is NOT YET, whatever the rows say.

    python3 scripts/workshop_evidence.py
    python3 scripts/workshop_evidence.py --save /tmp/pellier-evidence/workshop-evidence.txt
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

Config = Optional[Dict[str, str]]
Connect = Callable[[Dict[str, str]], Any]

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import workshop_check as check  # noqa: E402  (sibling module)

REPO = check.REPO
BACKEND = REPO / "pellier" / "backend"
STARTERS = REPO / "workshop" / "starters"

PROVED, NOT_YET, UNCHECKED, CONTRADICTED = (
    check.PROVED, check.NOT_YET, check.UNCHECKED, check.CONTRADICTED)

# The marked region each task edits, and the starter it is compared with.
REGIONS: Dict[str, tuple] = {
    "1A": (REPO / "workshop" / "lab-1-rrf.sql", "PostgreSQL RRF - fusion expression",
           STARTERS / "lab-1-rrf.sql"),
    "1B": (BACKEND / "services" / "search_plan.py", "Search plan - preserve requirements",
           STARTERS / "lab-1" / "preserve-requirements.pyfrag"),
    "2A": (BACKEND / "services" / "agent_tools.py", "Stock agent - check_stock",
           STARTERS / "lab-2" / "check-stock-tool.pyfrag"),
    "2B": (BACKEND / "agents" / "stock_agent.py", "Stock agent - definition",
           STARTERS / "lab-2" / "stock-agent-definition.pyfrag"),
    "3A-catalogue": (REPO / "scripts" / "deploy" / "gateway_tool_schemas.py",
                     "Gateway catalogue - published tools",
                     STARTERS / "lab-3" / "gateway-published-tools.pyfrag"),
    "3A-binding": (BACKEND / "services" / "agentcore_gateway.py",
                   "Managed catalogue - support reconcile",
                   STARTERS / "lab-3" / "support-reconcile.pyfrag"),
    "4B-rls": (REPO / "workshop" / "lab-4-rls.sql", "Row ownership - predicate",
               STARTERS / "lab-4-rls.sql"),
    "4B-absence": (REPO / "workshop" / "lab-4-absence.sql", "Keyed absence - deny proof",
                   STARTERS / "lab-4-absence.sql"),
}
CEDAR_POLICY = REPO / "policies" / "workshop_identity_match_forbid.cedar"
CEDAR_STARTER = STARTERS / "workshop_identity_match_forbid.cedar"

TITLES = {
    "1": "Lab 1: Build and Measure PostgreSQL Hybrid Retrieval",
    "2": "Lab 2: Build a PostgreSQL-Grounded Agent",
    "3": "Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore",
    "4": "Lab 4: Build Governed Agent Actions with Cedar",
}


def source_state(key: str) -> str:
    path, label, starter = REGIONS[key]
    return check.region_state(path, label, starter)


def _starter_finding(task: str, title: str, expected: str, where: str) -> check.Finding:
    return check.Finding(task, title, NOT_YET, expected,
                         f"the marked region in {where} still holds its starter",
                         [f"{where}: unchanged from workshop/starters"],
                         f"complete Task {task} in {where}, then run its check.")


# ---------------------------------------------------------------------------
# Lab 1
# ---------------------------------------------------------------------------

_LAB1A_TITLE = "Anna's recorded ranking recomputes from its two ranks"
_LAB1A_EXPECTED = "every product's recomputed score equals the score its receipt recorded"


def task_1a(cfg: Optional[Dict[str, str]]) -> check.Finding:
    """Run the participant's worksheet and read its verdict."""
    if source_state("1A") == check.STARTER:
        return _starter_finding("1A", _LAB1A_TITLE, _LAB1A_EXPECTED, "workshop/lab-1-rrf.sql")
    if cfg is None:
        return check.Finding("1A", _LAB1A_TITLE, UNCHECKED, _LAB1A_EXPECTED,
                             "the check could not look", [check.missing_settings_reason()])
    psql = shutil.which("psql")
    if psql is None:
        return check.Finding("1A", _LAB1A_TITLE, UNCHECKED, _LAB1A_EXPECTED,
                             "the check could not look", ["psql is not on PATH"])
    done = subprocess.run(
        [psql, "-X", "-P", "pager=off", "-f", str(REGIONS["1A"][0])],
        env=check.psql_environment(cfg), capture_output=True, text=True, timeout=60,
    )
    return read_worksheet(done.stdout, done.stderr)


def read_worksheet(stdout: str, stderr: str) -> check.Finding:
    """The worksheet's own Expected, Observed and Evidence lines, as a finding."""
    def lines_after(tag: str) -> List[str]:
        out, taking = [], False
        for line in stdout.splitlines():
            if line.startswith(tag):
                taking = True
                out.append(line[len(tag):].strip())
            elif taking and line.startswith("          "):
                out.append(line.strip())
            else:
                taking = False
        return out

    last_error = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    evidence = lines_after("Evidence") or [last_error]
    observed = " ".join(lines_after("Observed")) or "the worksheet did not finish"
    if "Lab 1A check passed" in stdout:
        state = PROVED
    elif "persona-anna-" in observed and "none yet" in observed:
        state = NOT_YET
    elif "Lab 1A check failed" in stdout:
        state = CONTRADICTED
    else:
        state = UNCHECKED
    return check.Finding("1A", _LAB1A_TITLE, state, _LAB1A_EXPECTED, observed,
                         [line for line in evidence if line],
                         " ".join(lines_after("Next")) or "run psql -X -f workshop/lab-1-rrf.sql "
                                                          "and read its output.")


def task_1b(cfg: Config, connect: Connect) -> check.Finding:
    import lab1_compare

    title = "Anna's limits survive the fallback"
    if source_state("1B") == check.STARTER:
        return _starter_finding("1B", title, lab1_compare.EXPECTED, "services/search_plan.py")
    return _with_connection("1B", title, lab1_compare.EXPECTED, cfg, connect,
                            lambda conn: lab1_compare.evaluate(conn)[0])


# ---------------------------------------------------------------------------
# Lab 2
# ---------------------------------------------------------------------------


def task_2a(cfg: Config, connect: Connect) -> check.Finding:
    import lab2_contract_check as lab2

    title = "check_stock keeps not carried, several and sold out apart"
    expected = lab2.EXPECTED_2A
    if source_state("2A") == check.STARTER:
        return _starter_finding("2A", title, expected, "services/agent_tools.py")
    inputs = {case: (lab2.DEFAULT_INPUTS[case], "default") for case in lab2.CASES}

    def judge(conn: Any) -> check.Finding:
        conn.autocommit = True
        return lab2.judge_2a(conn, lab2.participant_tool(conn, cfg or {}), inputs)[0]

    return _with_connection("2A", title, expected, cfg, connect, judge)


def task_2b(cfg: Config, connect: Connect) -> check.Finding:
    import lab2_contract_check as lab2

    title = "the Stock agent's numbers equal one SELECT on warehouse_inventory"
    expected = ("the Stock agent is granted check_stock only, and its counts equal "
                "warehouse_inventory")
    if source_state("2B") == check.STARTER:
        return _starter_finding("2B", title, expected, "agents/stock_agent.py")
    return _with_connection("2B", title, expected, cfg, connect,
                            lambda conn: lab2.judge_2b(conn, lab2.granted_tools()))


# ---------------------------------------------------------------------------
# Labs 3 and 4: the build state and the newest evidence row
# ---------------------------------------------------------------------------

# Lab 3: the Gateway Lambda writes a shopper turn's read with the turn id as its
# session and the build the Runtime reported. Rows carrying a build come first,
# because only they can be compared with this checkout.
LAB3_SQL = """
SELECT audit_id, session_id AS turn_id, tool, build_fingerprint AS deployed_fingerprint,
       created_at
  FROM pellier.tool_audit
 WHERE caller = 'gateway'
   AND session_id LIKE 'turn-%'
 ORDER BY (build_fingerprint IS NOT NULL) DESC, audit_id DESC
 LIMIT 1;
"""

# Lab 4: an approved credit executed once. The write key is the approved review's
# own, so the credit and its tool_audit row are found by that key and by nothing
# else; a retry must leave both counts at one.
LAB4_SQL = """
SELECT sc.credit_id, sc.approval_id, sc.customer_id, sc.amount_cents,
       sc.idempotency_key,
       (a.args->>'amount_cents')::int AS approved_cents,
       (SELECT count(*) FROM pellier.store_credits
         WHERE idempotency_key = sc.idempotency_key) AS credit_rows,
       (SELECT count(*) FROM pellier.tool_audit
         WHERE tool = 'give_store_credit'
           AND args->>'idempotency_key' = sc.idempotency_key) AS audit_rows
  FROM pellier.store_credits sc
  JOIN pellier.approvals a ON a.id = sc.approval_id
 ORDER BY sc.credit_id DESC
 LIMIT 1;
"""


def credit_findings(row: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """One approved credit, recorded once, for the amount a person approved."""
    if not row:
        return {"once": NOT_YET, "amount": NOT_YET}
    once = int(row.get("credit_rows") or 0) == 1 and int(row.get("audit_rows") or 0) == 1
    amount = row.get("approved_cents") is not None and int(row["approved_cents"]) == int(
        row.get("amount_cents") or 0)
    return {"once": PROVED if once else CONTRADICTED, "amount": PROVED if amount else CONTRADICTED}


def task_3a() -> check.Finding:
    title = "get_tickets is published and bound to the caller"
    expected = "both Lab 3 marked regions edited"
    states = {key: source_state(key) for key in ("3A-catalogue", "3A-binding")}
    observed = ", ".join(f"{key.split('-')[1]} {state}" for key, state in states.items())
    if any(state == check.MISSING for state in states.values()):
        return check.Finding("3A", title, UNCHECKED, expected, observed,
                             ["a Lab 3 marked region could not be read"])
    done = all(state == check.EDITED for state in states.values())
    return check.Finding("3A", title, PROVED if done else NOT_YET, expected, observed,
                         ["scripts/deploy/gateway_tool_schemas.py, services/agentcore_gateway.py"],
                         "complete both Task 3A blocks.")


def task_3b(row: Optional[Dict[str, Any]], available: bool, local_build: str) -> check.Finding:
    title = "your build answered on the managed path"
    expected = "a Gateway tool_audit row stamped with this checkout's build fingerprint"
    if any(source_state(key) == check.STARTER for key in ("3A-catalogue", "3A-binding")):
        return check.Finding("3B", title, NOT_YET, expected, "Task 3A is not complete yet",
                             ["Task 3B deploys the Task 3A edits"], "complete Task 3A first.")
    if not available:
        return check.Finding("3B", title, UNCHECKED, expected, "the check could not look")
    if not row:
        return check.Finding("3B", title, NOT_YET, expected,
                             "no Gateway tool call for a shopper turn yet", [],
                             "run scripts/lab3-start.sh, then Theo's turn in Pellier.")
    deployed = str(row.get("deployed_fingerprint") or "").strip()
    evidence = [f"pellier.tool_audit audit {row.get('audit_id')}, turn {row.get('turn_id')}, "
                f"build {check.short(deployed) or 'none'}; "
                f"this checkout {check.short(local_build) or 'unknown'}"]
    if not deployed or not local_build:
        return check.Finding("3B", title, UNCHECKED, expected, "a build could not be compared",
                             evidence)
    state = PROVED if deployed == local_build else CONTRADICTED
    return check.Finding("3B", title, state, expected,
                         "the builds match" if state == PROVED else "another build answered",
                         evidence, "deploy your Task 3A change and run Theo's turn again.")


def task_4a() -> check.Finding:
    title = "the Cedar credit rule is authored"
    expected = "policies/workshop_identity_match_forbid.cedar differs from its starter"
    try:
        same = CEDAR_POLICY.read_bytes() == CEDAR_STARTER.read_bytes()
    except OSError as exc:
        return check.Finding("4A", title, UNCHECKED, expected, f"unreadable: {exc}")
    return check.Finding("4A", title, NOT_YET if same else PROVED, expected,
                         "unchanged from the starter" if same else "authored",
                         [str(CEDAR_POLICY.relative_to(REPO))], "complete the unless block.")


def task_4b(row: Optional[Dict[str, Any]], available: bool) -> check.Finding:
    title = "RLS authored and one approved credit recorded once"
    expected = "both Lab 4B regions edited; one credit and one audit row for the approved key"
    states = {key: source_state(key) for key in ("4B-rls", "4B-absence")}
    observed = ", ".join(f"{key.split('-')[1]} {state}" for key, state in states.items())
    if any(state == check.STARTER for state in states.values()):
        return check.Finding("4B", title, NOT_YET, expected, observed,
                             ["workshop/lab-4-rls.sql, workshop/lab-4-absence.sql"],
                             "complete both Task 4B blocks.")
    if not available:
        return check.Finding("4B", title, UNCHECKED, expected,
                             observed + "; the database could not be read")
    credit = credit_findings(row)
    evidence = []
    if row:
        evidence.append(f"pellier.store_credits credit {row.get('credit_id')}, key "
                        f"{row.get('idempotency_key')}: {row.get('credit_rows')} credit row(s), "
                        f"{row.get('audit_rows')} audit row(s), {row.get('amount_cents')} of "
                        f"{row.get('approved_cents')} cents approved")
    if CONTRADICTED in credit.values():
        state = CONTRADICTED
    elif all(s == check.EDITED for s in states.values()) and credit["once"] == PROVED:
        state = PROVED
    else:
        state = NOT_YET
    return check.Finding("4B", title, state, expected,
                         observed + f"; credit recorded once {credit['once']}", evidence,
                         "complete both Task 4B blocks, then approve and execute Jessica's "
                         "review as Nadia.")


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _with_connection(
    task: str, title: str, expected: str, cfg: Optional[Dict[str, str]],
    connect: Callable[[Dict[str, str]], Any], judge: Callable[[Any], check.Finding],
) -> check.Finding:
    if cfg is None:
        return check.Finding(task, title, UNCHECKED, expected, "the check could not look",
                             [check.missing_settings_reason()])
    try:
        with connect(cfg) as conn:
            return judge(conn)
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return check.Finding(task, title, UNCHECKED, expected, "the check could not look",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"])


def _rows(cfg: Config, connect: Connect) -> Dict[str, Any]:
    if cfg is None:
        return {"available": False}
    try:
        with connect(cfg) as conn, conn.cursor() as cur:
            out: Dict[str, Any] = {"available": True}
            for key, sql in (("lab3", LAB3_SQL), ("lab4", LAB4_SQL)):
                cur.execute(sql)
                out[key] = cur.fetchone()
            return out
    except Exception:  # noqa: BLE001 - reported as UNCHECKED on the lines that need it
        return {"available": False}


def local_fingerprint() -> str:
    """The digest a deploy from this checkout would stamp on the Runtime."""
    try:
        sys.path.insert(0, str(BACKEND))
        from services.build_fingerprint import compute_fingerprint

        return compute_fingerprint(BACKEND)
    except Exception:  # noqa: BLE001 - provenance is never load-bearing
        return ""


def collect(
    env_path: pathlib.Path = check.DEFAULT_ENV,
    connect: Callable[[Dict[str, str]], Any] = check.connect,
) -> List[check.Finding]:
    """All eight task findings, in lab order."""
    cfg = check.db_config(env_path)
    rows = _rows(cfg, connect)
    available = bool(rows.get("available"))
    return [
        task_1a(cfg),
        task_1b(cfg, connect),
        task_2a(cfg, connect),
        task_2b(cfg, connect),
        task_3a(),
        task_3b(rows.get("lab3"), available, local_fingerprint()),
        task_4a(),
        task_4b(rows.get("lab4"), available),
    ]


def render_report(findings: Sequence[check.Finding]) -> str:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = ["Pellier workshop evidence", f"Generated {stamp}", ""]
    for lab in ("1", "2", "3", "4"):
        lines.append(TITLES[lab])
        for finding in findings:
            if finding.task.startswith(lab):
                lines.append(check.render(finding))
        lines.append("")
    proved = sum(1 for finding in findings if finding.state == PROVED)
    lines.append(f"{proved} of {len(findings)} tasks proved")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--save", help="also write the report to this file")
    args = parser.parse_args(argv)
    findings = collect()
    report = render_report(findings)
    print(report)
    if args.save:
        pathlib.Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.save).write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
