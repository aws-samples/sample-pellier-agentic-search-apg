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

Each line runs the same verdict the guide's check prints
(``workshop/lab-1-rrf.sql``, ``scripts/lab1_compare.py``,
``scripts/lab2_contract_check.py``, ``scripts/lab3_check.py``), so the export
and the lab never disagree. Lab 3B's direct Cedar probe calls the Gateway, so
it stays in ``lab3_check.py``; the export reads only the systems of record:
the database, the source and, for Theo's remembered taste, AgentCore Memory.
A task whose marked region still holds its starter is NOT YET, whatever the
rows say.

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
    "4B": (REPO / "workshop" / "lab-4-rls.sql", "Row ownership - predicate",
           STARTERS / "lab-4-rls.sql"),
}
CEDAR_POLICY = REPO / "policies" / "workshop_credit_limit.cedar"
CEDAR_STARTER = STARTERS / "workshop_credit_limit.cedar"
ABSENCE_WORKSHEET = REPO / "workshop" / "lab-4-absence.sql"

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
# Lab 3: the catalogue from source, then the build and the reads from tool_audit
# ---------------------------------------------------------------------------


def task_3a() -> check.Finding:
    """Lab 3A by the same verdict the doctor prints, after the starter rule."""
    import lab3_check

    title = "get_tickets is published and bound to the signed-in caller"
    states = {key: source_state(key) for key in ("3A-catalogue", "3A-binding")}
    if any(state == check.MISSING for state in states.values()):
        return check.Finding("3A", title, UNCHECKED, "both Lab 3 marked regions readable",
                             "a Lab 3 marked region could not be read",
                             [f"{key}: {state}" for key, state in states.items()])
    if any(state == check.STARTER for state in states.values()):
        where = " and ".join(
            {"3A-catalogue": "scripts/deploy/gateway_tool_schemas.py",
             "3A-binding": "services/agentcore_gateway.py"}[key]
            for key, state in states.items() if state == check.STARTER)
        return _starter_finding("3A", title, "both Lab 3 marked regions edited", where)
    try:
        return lab3_check.judge_catalogue(*lab3_check.source_catalogue())
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return check.Finding("3A", title, UNCHECKED, "the catalogues are readable",
                             "the check could not look", [f"{type(exc).__name__}: {exc}"])


def task_3b(rows: Optional[Dict[str, Any]], local_build: str,
            memory: Optional[Callable[[], check.Finding]] = None) -> check.Finding:
    """Lab 3B: Theo's managed turn ran this build, was given his remembered taste
    from AgentCore Memory, and read only his own tickets.

    ``memory`` reads AgentCore Memory (``lab3_check.memory_finding`` unless
    given). The direct Cedar probe calls the Gateway, so it is
    ``scripts/lab3_check.py``'s alone.
    """
    import lab3_check

    title = "your build answered Theo, remembered his taste, and read only his own tickets"
    expected = (f"{lab3_check.BUILD_EXPECTED}; {lab3_check.MEMORY_EXPECTED}; "
                f"{lab3_check.TICKETS_EXPECTED}")
    if any(source_state(key) == check.STARTER for key in ("3A-catalogue", "3A-binding")):
        return check.Finding("3B", title, NOT_YET, expected, "Task 3A is not complete yet",
                             ["Task 3B deploys the Task 3A edits"], "complete Task 3A first.")
    if rows is None:
        return check.Finding("3B", title, UNCHECKED, expected, "the check could not look")
    return _combine("3B", title, expected, [
        lab3_check.judge_build(rows.get("build"), local_build),
        (memory or lab3_check.memory_finding)(),
        lab3_check.judge_tickets(rows.get("tickets") or []),
    ])


# ---------------------------------------------------------------------------
# Lab 4
# ---------------------------------------------------------------------------

# Jessica's approved credit executed once. The write key is the approved review's
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
 WHERE sc.customer_id = 'CUST-JESSICA'
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


def _combine(task: str, title: str, expected: str,
             parts: Sequence[check.Finding]) -> check.Finding:
    """One task line from several verdicts: any contradiction wins, then any gap."""
    states = [part.state for part in parts]
    if CONTRADICTED in states:
        state = CONTRADICTED
    elif all(s == PROVED for s in states):
        state = PROVED
    elif UNCHECKED in states:
        state = UNCHECKED
    else:
        state = NOT_YET
    return check.Finding(task, title, state, expected,
                         "; ".join(part.observed for part in parts),
                         [line for part in parts for line in part.evidence],
                         next((part.next_step for part in parts if part.state != PROVED), ""))


def credit_finding(row: Optional[Dict[str, Any]]) -> check.Finding:
    """Jessica's approved credit, executed once for the approved amount."""
    title = "Jessica's approved credit was recorded once"
    expected = "one store_credits row and one tool_audit row for the approved review's key"
    found = credit_findings(row)
    if not row:
        return check.Finding("4A", title, NOT_YET, expected, "no store credit yet", [],
                             "approve and execute Jessica's review as Nadia in the Operator.")
    evidence = [f"pellier.store_credits credit {row.get('credit_id')}, key "
                f"{row.get('idempotency_key')}: {row.get('credit_rows')} credit row(s), "
                f"{row.get('audit_rows')} audit row(s), {row.get('amount_cents')} of "
                f"{row.get('approved_cents')} cents approved"]
    state = PROVED if set(found.values()) == {PROVED} else CONTRADICTED
    return check.Finding("4A", title, state, expected,
                         f"recorded once {found['once']}, approved amount {found['amount']}",
                         evidence, "read the rows for that key; a retry must add nothing.")


def task_4a(rows: Optional[Dict[str, Any]]) -> check.Finding:
    """Lab 4A: the rule passes Cedar here, the Gateway denied the over-limit
    credit with no row left, and Jessica's in-limit credit ran once."""
    import lab4_policy_check as lab4

    title = "the $100 credit limit holds, in Cedar and on the Gateway"
    expected = ("your rule passes the Cedar matrix; the over-limit credit was denied and left "
                "no row; Jessica's approved credit was recorded once")
    try:
        rule = CEDAR_POLICY.read_text(encoding="utf-8")
        starter = CEDAR_STARTER.read_text(encoding="utf-8")
    except OSError as exc:
        return check.Finding("4A", title, UNCHECKED, expected, f"unreadable: {exc}")
    if rule == starter:
        return _starter_finding("4A", title, expected, "policies/workshop_credit_limit.cedar")
    try:
        local = lab4.local_check(rule, starter).finding
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        local = check.Finding("4A", title, UNCHECKED, expected, "the Cedar check could not run",
                              [f"{type(exc).__name__}: {str(exc)[:160]}"])
    if rows is None:
        return _combine("4A", title, expected, [local, check.Finding(
            "4A", title, UNCHECKED, expected, "the database could not be read")])
    return _combine("4A", title, expected, [
        local, lab4.judge_recorded_probe(rows.get("probe")), credit_finding(rows.get("credit"))])


def _psql_verdict(cfg: Config, path: pathlib.Path, passed: str, task: str, title: str,
                  expected: str) -> check.Finding:
    """Run one supplied worksheet and read its own verdict line."""
    if cfg is None:
        return check.Finding(task, title, UNCHECKED, expected, "the check could not look",
                             [check.missing_settings_reason()])
    psql = shutil.which("psql")
    if psql is None:
        return check.Finding(task, title, UNCHECKED, expected, "the check could not look",
                             ["psql is not on PATH"])
    done = subprocess.run([psql, "-X", "-P", "pager=off", "-f", str(path)],
                          env=check.psql_environment(cfg), capture_output=True, text=True,
                          timeout=60)
    def line(tag: str) -> str:
        return next((text[len(tag):].strip() for text in done.stdout.splitlines()
                     if text.startswith(tag)), "")

    observed = line("Observed") or "the worksheet did not finish"
    where = path.relative_to(REPO)
    if passed in done.stdout:
        return check.Finding(task, title, PROVED, expected, observed, [f"{where}: {passed}"])
    state = CONTRADICTED if "check failed" in done.stdout else UNCHECKED
    if "none yet" in done.stdout:
        state = NOT_YET
    if state == NOT_YET:
        reason = "nothing to check yet"
    elif state == CONTRADICTED:
        reason = "check failed"
    else:
        reason = (done.stderr.strip().splitlines() or ["no verdict"])[-1]
    return check.Finding(task, title, state, expected, observed, [f"{where}: {reason}"],
                         line("Next") or f"run psql -X -P pager=off -f {where} and read it.")


def task_4b(cfg: Config) -> check.Finding:
    """Lab 4B: the RLS worksheet's own verdict, then the supplied absence check."""
    title = "row-level security holds, and the denied credit moved nothing"
    expected = ("Theo's own rows visible, Jessica's 0, a write in her name 42501, staff reads "
                "intact, rolled back; the denied key 0 and 0, the allowed key 1")
    if source_state("4B") == check.STARTER:
        return _starter_finding("4B", title, expected, "workshop/lab-4-rls.sql")
    path = REGIONS["4B"][0]
    return _combine("4B", title, expected, [
        _psql_verdict(cfg, path, "Lab 4B check passed", "4B", title, expected),
        _psql_verdict(cfg, ABSENCE_WORKSHEET, "Lab 4 absence check passed", "4B", title,
                      expected),
    ])


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
    import lab3_check

    if cfg is None:
        return {"available": False}
    try:
        import lab4_policy_check

        out: Dict[str, Any] = {"available": True, "lab3": lab3_check.read_rows(cfg, connect)}
        with connect(cfg) as conn, conn.cursor() as cur:
            cur.execute(LAB4_SQL)
            credit = cur.fetchone()
            cur.execute(lab4_policy_check.PROBE_SQL)
            out["lab4"] = {"credit": credit, "probe": cur.fetchone()}
        return out
    except Exception:  # noqa: BLE001 - reported as UNCHECKED on the lines that need it
        return {"available": False}


def collect(
    env_path: pathlib.Path = check.DEFAULT_ENV,
    connect: Callable[[Dict[str, str]], Any] = check.connect,
) -> List[check.Finding]:
    """All eight task findings, in lab order."""
    import lab3_check

    cfg = check.db_config(env_path)
    rows = _rows(cfg, connect)
    available = bool(rows.get("available"))
    return [
        task_1a(cfg),
        task_1b(cfg, connect),
        task_2a(cfg, connect),
        task_2b(cfg, connect),
        task_3a(),
        task_3b(rows.get("lab3") if available else None, lab3_check.local_fingerprint()),
        task_4a(rows.get("lab4") if available else None),
        task_4b(cfg),
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
