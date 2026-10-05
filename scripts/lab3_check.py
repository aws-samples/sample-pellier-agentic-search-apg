#!/usr/bin/env python3
"""Lab 3's checks: which build answered Theo, whose tickets ran, and what Cedar refused.

Run after Theo's turns on the managed path (Task 3B):

    python3 scripts/lab3_check.py

It prints three findings, each with Expected, Observed and Evidence:

    build    the newest Gateway tool call in a shopper turn ran this checkout's
             build (``tool_audit.build_fingerprint`` beside the local digest)
    tickets  every executed ``get_tickets`` call on the Gateway read Theo's own
             tickets, and none read another customer's
    probe    Theo's own token, asking the Gateway directly for Jessica's
             tickets, is denied by the owner-only permit and leaves no
             ``tool_audit`` row

Task 3A's check is the doctor's prerequisites line
(``scripts/workshop_doctor.py --lab 3 --phase prerequisites``); it and the
evidence export judge the source with :func:`judge_catalogue` below.
"""

from __future__ import annotations

import pathlib
import sys
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import workshop_check as check  # noqa: E402  (sibling module)

REPO = check.REPO
BACKEND = REPO / "pellier" / "backend"
DEPLOY = SCRIPTS / "deploy"

THEO, JESSICA = "CUST-THEO", "CUST-JESSICA"
PROBE_TOOL = "get_tickets"

# The Gateway Lambda writes a shopper turn's call with the turn id as its
# session and the build the Runtime reported. Rows carrying a build come first,
# because only they can be compared with this checkout.
BUILD_SQL = """
SELECT audit_id, session_id AS turn_id, tool, build_fingerprint AS deployed_fingerprint,
       created_at
  FROM pellier.tool_audit
 WHERE caller = 'gateway'
   AND session_id LIKE 'turn-%'
 ORDER BY (build_fingerprint IS NOT NULL) DESC, audit_id DESC
 LIMIT 1;
"""

TICKETS_SQL = """
SELECT audit_id, session_id AS turn_id, args->>'customer_id' AS customer_id, created_at
  FROM pellier.tool_audit
 WHERE tool = 'get_tickets'
   AND caller = 'gateway'
 ORDER BY audit_id;
"""

PROBE_ROWS_SQL = """
SELECT count(*) AS n
  FROM pellier.tool_audit
 WHERE tool = 'get_tickets'
   AND session_id = %s;
"""


# ---------------------------------------------------------------------------
# Task 3A: the published catalogue and the caller binding, read from source
# ---------------------------------------------------------------------------

_CATALOGUE_TITLE = "get_tickets is published and bound to the signed-in caller"
_CATALOGUE_EXPECTED = ("the Gateway publishes every tool the Support agent asks for, and the "
                       "server binds get_tickets to the signed-in caller")
STAFF_ONLY = frozenset({"give_store_credit"})


def judge_catalogue(
    published: Iterable[str], managed: Sequence[str], bound: Iterable[str],
) -> check.Finding:
    """Task 3A's verdict from the two lists in its marked regions."""
    published, bound = frozenset(published), frozenset(bound)
    evidence = [
        f"scripts/deploy/gateway_tool_schemas.py publishes {len(published)} tools",
        f"services/agentcore_gateway.py: the Support agent asks for {', '.join(managed)}",
        "services/agentcore_gateway.py binds to the caller: "
        + (", ".join(sorted(bound)) or "none"),
    ]
    staff_only = sorted(set(managed) & STAFF_ONLY)
    if staff_only:
        return check.Finding(
            "3A", _CATALOGUE_TITLE, check.CONTRADICTED, _CATALOGUE_EXPECTED,
            f"the Support agent names the staff-only tool {', '.join(staff_only)}", evidence,
            "take the staff-only tool out of SUPPORT_MANAGED_TOOLS; only the Operator calls it.")
    unpublished = sorted(set(managed) - published)
    if unpublished:
        return check.Finding(
            "3A", _CATALOGUE_TITLE, check.NOT_YET, _CATALOGUE_EXPECTED,
            f"the Support agent asks for {', '.join(unpublished)}, which is not published "
            "on the Gateway", evidence,
            "publish it in the Gateway catalogue - published tools block.")
    if PROBE_TOOL in managed and PROBE_TOOL not in bound:
        return check.Finding(
            "3A", _CATALOGUE_TITLE, check.NOT_YET, _CATALOGUE_EXPECTED,
            "get_tickets is published but not bound to the signed-in caller, so the model "
            "chooses whose tickets to read", evidence,
            "add get_tickets to SUPPORT_CALLER_BOUND_TOOLS in the Managed catalogue - "
            "support reconcile block.")
    return check.Finding("3A", _CATALOGUE_TITLE, check.PROVED, _CATALOGUE_EXPECTED,
                         f"{len(published)} tools published, get_tickets bound to the "
                         "signed-in caller", evidence)


def source_catalogue() -> tuple:
    """``(published, support tools, caller-bound tools)`` from the live source."""
    for path in (DEPLOY, BACKEND):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from gateway_tool_schemas import workshop_published_tools
    from services.agentcore_gateway import SUPPORT_CALLER_BOUND_TOOLS, SUPPORT_MANAGED_TOOLS

    return workshop_published_tools(), SUPPORT_MANAGED_TOOLS, SUPPORT_CALLER_BOUND_TOOLS


# ---------------------------------------------------------------------------
# Task 3B: the executed build and the executed reads, read from tool_audit
# ---------------------------------------------------------------------------

_BUILD_TITLE = "your build answered on the managed path"
BUILD_EXPECTED = ("the newest Gateway tool call in a shopper turn carries this checkout's "
                  "build fingerprint")


def local_fingerprint() -> str:
    """The digest a deploy from this checkout stamps on the Runtime, or empty."""
    try:
        if str(BACKEND) not in sys.path:
            sys.path.insert(0, str(BACKEND))
        from services.build_fingerprint import compute_fingerprint

        return compute_fingerprint(BACKEND)
    except Exception:  # noqa: BLE001 - an unreadable checkout is reported, not raised
        return ""


def judge_build(row: Optional[Dict[str, Any]], local: str) -> check.Finding:
    """The deployed build beside this checkout's, from one tool_audit row."""
    if not row:
        return check.Finding("3B", _BUILD_TITLE, check.NOT_YET, BUILD_EXPECTED,
                             "no Gateway tool call in a shopper turn yet", [],
                             "run scripts/lab3-start.sh theo, then Theo's turn in Ask Pellier.")
    deployed = str(row.get("deployed_fingerprint") or "").strip()
    evidence = [
        f"pellier.tool_audit audit {row.get('audit_id')}: {row.get('tool')} in turn "
        f"{row.get('turn_id')}",
        f"deployed build   {deployed or 'none recorded'}",
        f"this checkout    {local or 'unreadable'}",
    ]
    if not deployed or not local:
        return check.Finding("3B", _BUILD_TITLE, check.UNCHECKED, BUILD_EXPECTED,
                             "a build could not be compared", evidence,
                             "deploy with --mode participant, then run Theo's turn again.")
    if deployed == local:
        return check.Finding("3B", _BUILD_TITLE, check.PROVED, BUILD_EXPECTED,
                             "the two builds match", evidence)
    return check.Finding("3B", _BUILD_TITLE, check.CONTRADICTED, BUILD_EXPECTED,
                         "another build answered", evidence,
                         "deploy your Task 3A change with --mode participant, then run "
                         "Theo's turn again.")


_TICKETS_TITLE = "every executed ticket read was Theo's own"
TICKETS_EXPECTED = ("at least one executed get_tickets call on the Gateway, every one for "
                    f"{THEO}, none for another customer")


def judge_tickets(rows: Sequence[Dict[str, Any]]) -> check.Finding:
    """Whose tickets the executed Gateway reads asked for."""
    evidence = [f"pellier.tool_audit audit {r.get('audit_id')}: get_tickets for "
                f"{r.get('customer_id') or 'no customer'} in turn {r.get('turn_id')}"
                for r in rows[-5:]]
    if not rows:
        return check.Finding("3B", _TICKETS_TITLE, check.NOT_YET, TICKETS_EXPECTED,
                             "no get_tickets call has run on the Gateway yet", evidence,
                             "ask Theo's ticket question in Ask Pellier on the managed path.")
    others = [r for r in rows if r.get("customer_id") != THEO]
    observed = (f"{len(rows)} executed call(s), {len(rows) - len(others)} for {THEO}, "
                f"{len(others)} for anyone else")
    if others:
        return check.Finding("3B", _TICKETS_TITLE, check.CONTRADICTED, TICKETS_EXPECTED,
                             observed, evidence,
                             "check SUPPORT_CALLER_BOUND_TOOLS names get_tickets, then deploy.")
    return check.Finding("3B", _TICKETS_TITLE, check.PROVED, TICKETS_EXPECTED, observed, evidence)


# ---------------------------------------------------------------------------
# Task 3B: Theo's token asks the Gateway directly for Jessica's tickets
# ---------------------------------------------------------------------------

_PROBE_TITLE = "Cedar refuses Theo's direct read of Jessica's tickets"
PROBE_EXPECTED = ("a Cedar policy denial from the owner-only permit, and no tool_audit row "
                  "for the probe's turn: a denied call never runs")


def judge_probe(payload: Dict[str, Any], audit_rows: Optional[int]) -> check.Finding:
    """The direct probe's outcome beside the rows its turn left."""
    evidence = [
        f"principal theo, action {payload.get('action')}, customer_id {JESSICA}",
        f"turn {payload.get('turn_id')}: "
        + (f"{audit_rows} tool_audit row(s)" if audit_rows is not None else "rows not read"),
    ]
    said = str(payload.get("error") or payload.get("result") or "")[:200]
    if said:
        evidence.append(f"the Gateway said: {said}")
    outcome = payload.get("outcome")
    if outcome == "allow":
        return check.Finding("3B", _PROBE_TITLE, check.CONTRADICTED, PROBE_EXPECTED,
                             "the Gateway ran the read for Jessica's tickets", evidence,
                             "check that get_tickets_owner_only is deployed and active.")
    if outcome != "deny" or not payload.get("cedar_denial"):
        return check.Finding("3B", _PROBE_TITLE, check.UNCHECKED, PROBE_EXPECTED,
                             "the call failed for another reason, so it says nothing about "
                             "Cedar", evidence,
                             "read the Gateway's words above; a 401 or a transport error is "
                             "not a policy decision.")
    if audit_rows != 0:
        return check.Finding("3B", _PROBE_TITLE, check.CONTRADICTED, PROBE_EXPECTED,
                             f"denied, but {audit_rows} tool_audit row(s) carry its turn",
                             evidence, "a denied call must leave no row; read those rows.")
    return check.Finding("3B", _PROBE_TITLE, check.PROVED, PROBE_EXPECTED,
                         "Cedar denied it before the tool ran; no row was written", evidence)


def run_probe(cfg: Optional[Dict[str, str]]) -> check.Finding:
    """Mint Theo's token, ask the Gateway for Jessica's tickets, count the rows left."""
    turn_id = f"turn-lab3-probe-{uuid.uuid4().hex[:12]}"
    try:
        if str(DEPLOY) not in sys.path:
            sys.path.insert(0, str(DEPLOY))
        import anyio
        from gateway_client import _load_env, _require, _token_from_cognito
        from gateway_policy_probe import DEFAULT_TARGET, _call_tool, classify_call

        _load_env()
        gateway_url = _require("AGENTCORE_GATEWAY_URL")
        token = _token_from_cognito("theo")
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - reported as UNCHECKED
        return check.Finding("3B", _PROBE_TITLE, check.UNCHECKED, PROBE_EXPECTED,
                             "the managed environment is not configured here",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"],
                             "run this on the workshop box, where the Gateway is provisioned.")
    action = f"{DEFAULT_TARGET}___{PROBE_TOOL}"
    arguments = {"customer_id": JESSICA, "turn_id": turn_id}
    call, failure = None, None
    try:
        call = anyio.run(_call_tool, gateway_url, token, action, arguments)
    except Exception as exc:  # noqa: BLE001 - every failure shape is classified
        failure = exc
    payload = {"action": action, "turn_id": turn_id, **classify_call(call, failure)}
    rows = _probe_rows(cfg, turn_id)
    return judge_probe(payload, rows)


def _probe_rows(cfg: Optional[Dict[str, str]], turn_id: str) -> Optional[int]:
    if cfg is None:
        return None
    try:
        with check.connect(cfg) as conn, conn.cursor() as cur:
            cur.execute(PROBE_ROWS_SQL, (turn_id,))
            return int((cur.fetchone() or {}).get("n") or 0)
    except Exception:  # noqa: BLE001 - reported as rows not read
        return None


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def read_rows(cfg: Dict[str, str], connect: Any = check.connect) -> Dict[str, Any]:
    """The build row and every executed Gateway ticket read."""
    with connect(cfg) as conn, conn.cursor() as cur:
        cur.execute(BUILD_SQL)
        build = cur.fetchone()
        cur.execute(TICKETS_SQL)
        tickets = list(cur.fetchall())
    return {"build": build, "tickets": tickets}


def collect(env_path: pathlib.Path = check.DEFAULT_ENV) -> List[check.Finding]:
    cfg = check.db_config(env_path)
    if cfg is None:
        reason = [check.missing_settings_reason(env_path)]
        rows_findings = [
            check.Finding("3B", _BUILD_TITLE, check.UNCHECKED, BUILD_EXPECTED,
                          "the check could not look", reason),
            check.Finding("3B", _TICKETS_TITLE, check.UNCHECKED, TICKETS_EXPECTED,
                          "the check could not look", reason),
        ]
    else:
        try:
            rows = read_rows(cfg)
            rows_findings = [judge_build(rows["build"], local_fingerprint()),
                             judge_tickets(rows["tickets"])]
        except Exception as exc:  # noqa: BLE001 - the reason is the finding
            reason = [f"{type(exc).__name__}: {str(exc)[:160]}"]
            rows_findings = [
                check.Finding("3B", _BUILD_TITLE, check.UNCHECKED, BUILD_EXPECTED,
                              "the check could not look", reason),
                check.Finding("3B", _TICKETS_TITLE, check.UNCHECKED, TICKETS_EXPECTED,
                              "the check could not look", reason),
            ]
    return [*rows_findings, run_probe(cfg)]


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    findings = collect()
    print("Lab 3B: Theo's managed turns, read from tool_audit and the Gateway")
    for finding in findings:
        print(check.render(finding))
    passed = all(finding.state == check.PROVED for finding in findings)
    print("Lab 3B check passed" if passed else "Lab 3B check failed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
