#!/usr/bin/env python3
"""Export a participant's proof for all four labs, read from the system of record.

One line per task, eight in all. Each one says whether the claim is proved
and prints the three things every check prints: what was expected, what was
observed, and the evidence behind it (the row, the decision, the key). A line
that is not proved says what to look at next. Nothing here writes a row,
needs a run id, or reads a notes file.

What each line reads:

    1A  your vector_search_sql in services/store_tools.py, run against
        pellier.product_catalog with embeddings whose nearest product is known
    1B  pellier.retrieval_receipts and pellier.product_catalog: what Anna asked
        for, what the search that answered kept, and every product it returned
    2A  pellier.tool_audit: Marco's latest Stock-agent turn, the grant that
        agent held, and its counts against pellier.warehouse_inventory
    2B  pellier.tool_audit: Marco's latest recorded check_stock call per case,
        against pellier.product_catalog and pellier.warehouse_inventory
    3A  the source: the Gateway's published tools and the caller binding
    3B  pellier.tool_audit (the executed build beside this checkout's digest,
        and every get_tickets read), AgentCore Memory (Theo's record), and the
        live row policies beside workshop/lab-3-row-ownership.sql, probed on both paths
    4A  policies/credit_limit.cedar, evaluated with Cedar here, then
        the stored Gateway denial and Jessica's credit in pellier.approvals,
        pellier.store_credits and pellier.tool_audit
    4B  the live credit function beside workshop/lab-4-credit-writer.sql, and
        the credit-writer role probed on both paths; every probe rolls back

Rows alone prove 1B, 2A and 2B, so those lines read no source and no code of
yours runs: 2A and 2B need Marco's requests sent again after the edit before
they can pass, where the guide's 2B check runs the live pellier.check_stock
directly. The other lines run or read what you wrote, so a region that still
holds its starter is NOT YET whatever the rows say; the summary's cleanup
restores the Cedar starter, so run this export before it.

Every line is in one of four states, never two (``workshop_check``):
PROVED, NOT YET, UNCHECKED and CONTRADICTED. UNCHECKED is not a soft NOT
YET: "this did not happen" and "I could not look" are different findings.
Lab 3B's direct Cedar probe calls the Gateway, so it stays in
``scripts/lab3_check.py``.

    uv run scripts/workshop_evidence.py
    uv run scripts/workshop_evidence.py --save /tmp/pellier-evidence/workshop-evidence.txt
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

Config = Optional[Dict[str, str]]
Connect = Callable[[Dict[str, str]], Any]

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import workshop_check as check  # noqa: E402  (sibling module)
from wait_progress import waiting  # noqa: E402  (sibling module)

REPO = check.REPO
BACKEND = REPO / "pellier" / "backend"
STARTERS = REPO / "workshop" / "starters"

PROVED, NOT_YET, UNCHECKED, CONTRADICTED = (
    check.PROVED, check.NOT_YET, check.UNCHECKED, check.CONTRADICTED)

# The marked region each task edits, and the starter it is compared with.
REGIONS: Dict[str, tuple] = {
    "1A": (BACKEND / "services" / "store_tools.py", "Vector search - order by meaning",
           STARTERS / "lab-1" / "vector-search.pyfrag"),
    "3A-catalog": (REPO / "scripts" / "deploy" / "gateway_tool_schemas.py",
                     "Gateway - published tools",
                     STARTERS / "lab-3" / "gateway-published-tools.pyfrag"),
    "3A-binding": (BACKEND / "services" / "agentcore_gateway.py",
                   "Support agent - Gateway tools",
                   STARTERS / "lab-3" / "support-gateway-tools.pyfrag"),
    "3B": (REPO / "workshop" / "lab-3-row-ownership.sql", "Row ownership - predicate",
           STARTERS / "lab-3-row-ownership.sql"),
    "4B": (REPO / "workshop" / "lab-4-credit-writer.sql", "Credit writer - privileges",
           STARTERS / "lab-4-credit-writer.sql"),
}
CEDAR_POLICY = REPO / "policies" / "credit_limit.cedar"
CEDAR_STARTER = STARTERS / "credit_limit.cedar"

TITLES = {
    "1": "Lab 1: Build and measure PostgreSQL hybrid retrieval",
    "2": "Lab 2: Build a PostgreSQL-grounded agent",
    "3": "Lab 3: Deploy agents and bind the caller with Amazon Bedrock AgentCore",
    "4": "Lab 4: Govern agent actions with Cedar policies and PostgreSQL privileges",
}


def source_state(key: str) -> str:
    path, label, starter = REGIONS[key]
    return check.region_state(path, label, starter)


def _starter_finding(task: str, title: str, expected: str, where: str) -> check.Finding:
    return check.Finding(task, title, NOT_YET, expected,
                         f"the marked region in {where} is unchanged: your edit is not saved there yet",
                         [f"{where}: unchanged from workshop/starters"],
                         f"complete Task {task} in {where}, then run its check.")


# ---------------------------------------------------------------------------
# Lab 1
# ---------------------------------------------------------------------------

def task_1a(cfg: Config, connect: Connect) -> check.Finding:
    """Run the participant's vector search with the Lab 1A check's probes."""
    import lab1_vector as lab1

    if source_state("1A") == check.STARTER:
        return _starter_finding("1A", lab1.TITLE, lab1.EXPECTED,
                                "pellier/backend/services/store_tools.py")

    def judge(conn: Any) -> check.Finding:
        conn.autocommit = True
        return lab1.evaluate(conn)[0]

    return _with_connection("1A", lab1.TITLE, lab1.EXPECTED, cfg, connect, judge)


def task_1b(cfg: Config, connect: Connect) -> check.Finding:
    """Lab 1B from Anna's newest receipt: what she asked, and what the answer kept."""
    import lab1_retry

    return _with_connection("1B", lab1_retry.TITLE, lab1_retry.EXPECTED, cfg, connect,
                            lambda conn: lab1_retry.evaluate(conn)[0])


# ---------------------------------------------------------------------------
# Lab 2
# ---------------------------------------------------------------------------


def task_2a(cfg: Config, connect: Connect) -> check.Finding:
    """Lab 2A from Marco's latest Stock-agent turn, with the grant that agent held."""
    import lab2_check as lab2

    title = "the Stock agent holds check_stock alone"
    return _with_connection("2A", title, lab2.EXPECTED_2A, cfg, connect, lab2.judge_2a)


def task_2b(cfg: Config, connect: Connect) -> check.Finding:
    """Lab 2B from Marco's recorded check_stock calls; no code is run."""
    import lab2_check as lab2

    title = "check_stock keeps not carried, several and sold out apart"
    return _with_connection("2B", title, lab2.EXPECTED_2B_RECORDED, cfg, connect,
                            lab2.judge_recorded_2b)


# ---------------------------------------------------------------------------
# Lab 3: the catalog from source, then the build and the reads from tool_audit
# ---------------------------------------------------------------------------


def task_3a() -> check.Finding:
    """Lab 3A by the same verdict the doctor prints, after the starter rule."""
    import lab3_check

    title = "get_tickets is published and bound to the signed-in caller"
    states = {key: source_state(key) for key in ("3A-catalog", "3A-binding")}
    if any(state == check.MISSING for state in states.values()):
        return check.Finding("3A", title, UNCHECKED, "both Lab 3 marked regions readable",
                             "a Lab 3 marked region could not be read",
                             [f"{key}: {state}" for key, state in states.items()])
    if any(state == check.STARTER for state in states.values()):
        where = " and ".join(
            {"3A-catalog": "scripts/deploy/gateway_tool_schemas.py",
             "3A-binding": "services/agentcore_gateway.py"}[key]
            for key, state in states.items() if state == check.STARTER)
        return _starter_finding("3A", title, "both Lab 3 marked regions edited", where)
    try:
        return lab3_check.catalog_verdict(
            lab3_check.judge_catalog(*lab3_check.source_catalog()))
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return check.Finding("3A", title, UNCHECKED, "the catalogs are readable",
                             "the check could not look", [f"{type(exc).__name__}: {exc}"])


def task_3b(rows: Optional[Dict[str, Any]], local_build: str,
            memory: Optional[Callable[[], check.Finding]] = None,
            ownership: Optional[Callable[[], List[check.Finding]]] = None) -> check.Finding:
    """Lab 3B: Theo's managed turn ran this build, was given his remembered taste
    from AgentCore Memory, read only his own tickets, and the live row policies
    are the predicate in workshop/lab-3-row-ownership.sql.

    ``memory`` reads AgentCore Memory (``lab3_check.memory_finding`` unless
    given); ``ownership`` reads and probes the live row policies
    (``lab3_row_ownership_check.collect``). The direct Cedar probe calls the Gateway, so it
    is ``scripts/lab3_check.py``'s alone.
    """
    import lab3_check
    import lab3_row_ownership_check

    title = ("your build answered Theo, remembered his taste, read only his own tickets, and "
             "your row policies hold")
    expected = (f"{lab3_check.BUILD_EXPECTED}; {lab3_check.MEMORY_EXPECTED}; "
                f"{lab3_check.TICKETS_EXPECTED}; {lab3_row_ownership_check.DEPLOYED_EXPECTED}")
    if rows is None:
        return check.Finding("3B", title, UNCHECKED, expected, "the check could not look")
    if source_state("3B") == check.STARTER:
        owned = [_starter_finding("3B", title, expected, "workshop/lab-3-row-ownership.sql")]
    else:
        owned = (ownership or lab3_row_ownership_check.collect)()
    return _combine("3B", title, expected, [
        lab3_check.judge_build(rows.get("build"), local_build),
        (memory or lab3_check.memory_finding)(),
        lab3_check.judge_tickets(rows.get("tickets") or []),
        *owned,
    ])


# ---------------------------------------------------------------------------
# Lab 4
# ---------------------------------------------------------------------------

# Jessica's approved credit executed once. The write key is the approved review's
# own, so the credit and the tool_audit row that applied it are found by that key
# and by nothing else; a retry must leave both counts at one. A call that failed
# or was refused before it leaves its own row with the key: an attempt, counted
# apart, never the write.
LAB4_SQL = """
SELECT sc.credit_id, sc.approval_id, sc.customer_id, sc.amount_cents,
       sc.idempotency_key,
       (a.args->>'amount_cents')::int AS approved_cents,
       (SELECT count(*) FROM pellier.store_credits
         WHERE idempotency_key = sc.idempotency_key) AS credit_rows,
       (SELECT count(*) FROM pellier.tool_audit
         WHERE tool = 'give_store_credit'
           AND args->>'idempotency_key' = sc.idempotency_key
           AND (result->>'status' = 'success'
                AND coalesce(result->>'idempotent_replay', 'false') <> 'true')) AS audit_rows,
       (SELECT count(*) FROM pellier.tool_audit
         WHERE tool = 'give_store_credit'
           AND args->>'idempotency_key' = sc.idempotency_key
           AND (result->>'status' = 'success'
                AND coalesce(result->>'idempotent_replay', 'false') <> 'true') IS NOT TRUE)
         AS attempt_rows
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
    expected = "one store_credits row and the one tool_audit row that applied the approved review's key"
    found = credit_findings(row)
    if not row:
        return check.Finding("4A", title, NOT_YET, expected, "no store credit yet", [],
                             "approve and execute Jessica's review as Nadia in the Operator.")
    evidence = [f"pellier.store_credits credit {row.get('credit_id')}, key "
                f"{row.get('idempotency_key')}: {row.get('credit_rows')} credit row(s), "
                f"{row.get('audit_rows')} audit row(s), {row.get('amount_cents')} of "
                f"{row.get('approved_cents')} cents approved"]
    attempts = int(row.get("attempt_rows") or 0)
    if attempts:
        evidence.append(f"tool_audit also keeps {attempts} other attempt(s) that did not apply")
    state = PROVED if set(found.values()) == {PROVED} else CONTRADICTED
    return check.Finding("4A", title, state, expected,
                         f"recorded once {found['once']}, approved amount {found['amount']}",
                         evidence, "read the rows for that key; a retry must add nothing.")


def task_4a(rows: Optional[Dict[str, Any]]) -> check.Finding:
    """Lab 4A: the rule passes Cedar here, the Gateway denied the over-limit
    credit with no row left, and Jessica's in-limit credit ran once."""
    import lab4_policy as lab4

    title = "the $100 credit limit holds, in Cedar and on the Gateway"
    expected = ("your rule passes the Cedar matrix; the over-limit credit was denied and left "
                "no row; Jessica's approved credit was recorded once")
    try:
        rule = CEDAR_POLICY.read_text(encoding="utf-8")
        starter = CEDAR_STARTER.read_text(encoding="utf-8")
    except OSError as exc:
        return check.Finding("4A", title, UNCHECKED, expected, f"unreadable: {exc}")
    if rule == starter:
        return _starter_finding("4A", title, expected, "policies/credit_limit.cedar")
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


def task_4b(writer: Optional[Callable[[], List[check.Finding]]] = None) -> check.Finding:
    """Lab 4B: the live credit function carries your statements, and the credit-writer role
    writes only through it on both paths (``lab4_credit.collect`` unless given)."""
    import lab4_credit as lab4b

    title = "the credit-writer role writes only through the credit function"
    expected = f"{lab4b.DEPLOYED_EXPECTED}; {lab4b.EXPECTED}"
    if source_state("4B") == check.STARTER:
        return _starter_finding("4B", title, expected, "workshop/lab-4-credit-writer.sql")
    return _combine("4B", title, expected, (writer or lab4b.collect)())


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
        import lab4_policy

        out: Dict[str, Any] = {"available": True, "lab3": lab3_check.read_rows(cfg, connect)}
        with connect(cfg) as conn, conn.cursor() as cur:
            cur.execute(LAB4_SQL)
            credit = cur.fetchone()
            cur.execute(lab4_policy.PROBE_SQL)
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
    import lab3_row_ownership_check
    import lab4_credit

    return [
        task_1a(cfg, connect),
        task_1b(cfg, connect),
        task_2a(cfg, connect),
        task_2b(cfg, connect),
        task_3a(),
        task_3b(rows.get("lab3") if available else None, lab3_check.local_fingerprint(),
                ownership=lambda: lab3_row_ownership_check.collect(env_path)),
        task_4a(rows.get("lab4") if available else None),
        task_4b(lambda: lab4_credit.collect(env_path)),
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
    with waiting("Reading the evidence for the eight tasks", typical=4):
        findings = collect()
    report = render_report(findings)
    print(report)
    if args.save:
        pathlib.Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.save).write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
