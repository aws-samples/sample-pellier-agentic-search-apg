#!/usr/bin/env python3
"""Lab 3's checks: which build answered Theo, whose tickets ran, what Cedar refused,
and what the database returned.

Run after Theo's turns on the managed path (Task 3B), which
``uv run scripts/lab_run.py send --lab 3`` sends:

    uv run scripts/lab3_check.py --task 3B

It prints seven findings, each with Expected, Observed and Evidence:

    build    the newest Gateway tool call in a shopper turn ran this checkout's
             build (``tool_audit.build_fingerprint`` beside the local digest)
    memory   the managed rail's AgentCore Memory read for Theo returns the
             user-preference record extracted from his provisioning
             conversation, and prints its id
    tickets  every executed ``get_tickets`` call on the Gateway in Theo's turns
             read his own tickets, none read another customer's, and a forged
             call (the model asking for Jessica's tickets while Theo is signed
             in) leaves this checkout bound to Theo; the build finding shows
             this checkout is the build that answered
    probe    Theo's own token, asking the Gateway directly for Jessica's
             tickets, is denied by Cedar (the owner-only permit does not match,
             so nothing permits it) and leaves no ``tool_audit`` row
    rows     the row-ownership predicate from ``workshop/lab-3-row-ownership.sql`` is the
             live policy, and bound as Theo on both database paths a wrong
             query sees none of Jessica's rows and cannot write in her name
             (``scripts/lab3_row_ownership_check.py``, three findings)

Together the household request's three layers: the server binds a forged call
to Theo, Cedar refuses his direct read of Jessica's tickets, and the database
returns none of her rows even to a query that asks for them.

Task 3A's check is ``uv run scripts/lab3_check.py --task 3A``. It reads the
source before anything is deployed and prints four rules, one finding each:
get_tickets is published; the Support agent's Gateway tools include get_orders
and get_tickets; every tool that takes a customer_id is bound to the caller; and
give_store_credit is refused on a shopper agent. The doctor's prerequisites line
and the evidence export read the same rules through :func:`catalogue_verdict`.
The binding rule runs a forged call for each read through the checkout's own
binding (:func:`probe_binding`); Theo's real turns rarely make that call, because
the model seldom asks for another customer, so the probe makes it every time.
"""

from __future__ import annotations

import pathlib
import sys
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import workshop_check as check  # noqa: E402  (sibling module)

REPO = check.REPO
BACKEND = REPO / "pellier" / "backend"
DEPLOY = SCRIPTS / "deploy"

THEO, JESSICA = "CUST-THEO", "CUST-JESSICA"
PROBE_TOOL = "get_tickets"
# The reads Theo's household request needs. Of the nine tools, these two and the staff-only
# give_store_credit require a customer_id; ask_a_person takes one when the caller is known.
SHOPPER_READS = ("get_orders", "get_tickets")
SEND = "uv run scripts/lab_run.py send --lab 3"

# The Gateway Lambda writes a shopper turn's call with the turn id as its
# session and the build the Runtime reported. Rows carrying a build come first,
# because only they can be compared with this checkout.
BUILD_SQL = f"""
SELECT audit_id, session_id AS turn_id, tool, build_fingerprint AS deployed_fingerprint,
       created_at
  FROM pellier.tool_audit
 WHERE caller = 'gateway'
   AND session_id LIKE 'turn-%%'
   AND created_at >= {check.SINCE_SQL}
 ORDER BY (build_fingerprint IS NOT NULL) DESC, audit_id DESC
 LIMIT 1;
"""

# Theo's turns only: a turn is his when one of its Gateway calls was bound to
# CUST-THEO. Jessica asks for her credit on the managed path in Lab 4, and her
# own ticket read is not Theo's. The owner-only permit matches only a read whose
# customer is the token's; Cedar denies by default otherwise, so an executed read
# for another customer can only come from that customer's own turn.
TICKETS_SQL = f"""
SELECT t.audit_id, t.session_id AS turn_id, t.args->>'customer_id' AS customer_id, t.created_at
  FROM pellier.tool_audit t
 WHERE t.tool = 'get_tickets'
   AND t.caller = 'gateway'
   AND t.created_at >= {check.SINCE_SQL}
   AND EXISTS (SELECT 1
                 FROM pellier.tool_audit o
                WHERE o.caller = 'gateway'
                  AND o.session_id = t.session_id
                  AND o.args->>'customer_id' = 'CUST-THEO')
 ORDER BY t.audit_id;
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

_CATALOGUE_TITLE = "the Support agent, assembled: published, given its reads, bound to the caller"
_CATALOGUE_EXPECTED = ("get_tickets published, get_orders and get_tickets in the Support agent's "
                       "Gateway tools and bound to the caller, and give_store_credit refused")
STAFF_ONLY = frozenset({"give_store_credit"})
_NEXT_CUSTOMER_ID = "which of the nine tools take a customer_id?"


def probe_binding(bind: Callable[..., Dict[str, Any]], tool: str = PROBE_TOOL) -> Dict[str, str]:
    """A forged read through ``bind``, the server's binding, before it leaves Runtime.

    Theo is signed in and the model asks ``tool`` for Jessica. ``sent`` is the
    customer the call would carry to the Gateway. ``unsigned`` is what the same
    call does when no customer is verified: ``refused``, or the customer it would
    still carry.

    Args:
        bind: ``services.agentcore_gateway._bind_server_tool_context``.
        tool: the read to forge.
    """
    forged = {"name": f"pellier-store-tools___{tool}", "toolUseId": "lab3-forged",
              "input": {"customer_id": JESSICA}}
    sent = bind(forged, customer_id=THEO, turn_id="")["input"].get("customer_id")
    try:
        carried = bind(forged, customer_id="", turn_id="")["input"].get("customer_id")
        unsigned = str(carried or "none")
    except ValueError:
        unsigned = "refused"
    return {"sent": str(sent or "none"), "unsigned": unsigned}


def _probe_lines(probe: Dict[str, str], tool: str = PROBE_TOOL) -> List[str]:
    unsigned = "refused" if probe["unsigned"] == "refused" else f"sent as {probe['unsigned']}"
    return [(f"forged call: Theo signed in, the model asks {tool} for {JESSICA}; "
             f"the server sends {probe['sent']}"),
            f"the same {tool} call with no signed-in customer: {unsigned}"]


def _probe_binds(probe: Dict[str, str]) -> bool:
    return probe["sent"] == THEO and probe["unsigned"] == "refused"


def _and(names: Sequence[str]) -> str:
    return " and ".join(names) if len(names) < 3 else ", ".join(names[:-1]) + " and " + names[-1]


def _published_rule(published: frozenset, managed: Sequence[str]) -> check.Finding:
    title = "get_tickets is published on the Gateway"
    expected = "the Gateway publishes get_tickets and every tool the Support agent asks for"
    evidence = [f"scripts/deploy/gateway_tool_schemas.py publishes {len(published)} of the nine "
                f"tools: {', '.join(sorted(published))}"]
    next_step = ("which tool does the Gateway catalogue - published tools block still "
                 "withhold?")
    if PROBE_TOOL not in published:
        return check.Finding("3A", title, check.NOT_YET, expected,
                             "get_tickets is not published: scripts/deploy/gateway_tool_schemas.py "
                             "withholds it", evidence, next_step)
    unpublished = sorted(set(managed) - published)
    if unpublished:
        return check.Finding("3A", title, check.NOT_YET, expected,
                             f"the Support agent asks for {_and(unpublished)}, which the Gateway "
                             "does not publish", evidence, next_step)
    return check.Finding("3A", title, check.PROVED, expected,
                         f"{len(published)} of the nine tools published, get_tickets among them",
                         evidence)


def _reads_rule(managed: Sequence[str]) -> check.Finding:
    title = "the Support agent's Gateway tools include get_orders and get_tickets"
    expected = ("SUPPORT_GATEWAY_TOOLS holds the reads Theo's household request needs: "
                "get_orders and get_tickets")
    asks = _and(list(managed)) or "no tools"
    evidence = [f"services/agentcore_gateway.py: SUPPORT_GATEWAY_TOOLS asks for {asks}"]
    if any(read not in managed for read in SHOPPER_READS):
        return check.Finding("3A", title, check.NOT_YET, expected,
                             f"the Support agent asks for {asks}; Theo's household request needs "
                             "get_orders and get_tickets", evidence,
                             f"{_NEXT_CUSTOMER_ID} The reads among them are what his household "
                             "request needs.")
    return check.Finding("3A", title, check.PROVED, expected,
                         f"the Support agent asks for {asks}", evidence)


def _bound_rule(bound: frozenset,
                probes: Optional[Dict[str, Dict[str, str]]]) -> check.Finding:
    title = "every tool that takes a customer_id is bound to the caller"
    expected = ("get_orders and get_tickets are in SUPPORT_CALLER_BOUND_TOOLS, so the server sets "
                "their customer_id from the signed-in caller; ask_a_person's handoff is bound "
                "whenever the caller is known")
    evidence = ["services/agentcore_gateway.py binds to the caller: "
                + (", ".join(sorted(bound)) or "none")]
    for read in SHOPPER_READS:
        if probes and read in probes:
            evidence += _probe_lines(probes[read], read)
    unbound = [read for read in SHOPPER_READS
               if not (_probe_binds(probes[read]) if probes and read in probes
                       else read in bound)]
    if unbound:
        verb = "takes" if len(unbound) == 1 else "take"
        state = "is" if len(unbound) == 1 else "are"
        observed = (f"{_and(unbound)} {verb} a customer_id and {state} not bound to the caller, "
                    "so the model chooses whose records to read")
        leaking = [read for read in unbound
                   if probes and read in probes and probes[read]["sent"] != THEO]
        if leaking:
            observed += (f"; a forged {' or '.join(leaking)} call for {JESSICA} would leave as "
                         f"{probes[leaking[0]]['sent']}")
        return check.Finding("3A", title, check.NOT_YET, expected, observed, evidence,
                             f"{_NEXT_CUSTOMER_ID} Name each read among them in "
                             "SUPPORT_CALLER_BOUND_TOOLS; ask_a_person's handoff is bound for you.")
    observed = "get_orders and get_tickets bound to the signed-in caller"
    if probes and all(read in probes for read in SHOPPER_READS):
        observed = f"get_orders and get_tickets bound; a forged call for {JESSICA} leaves as {THEO}"
    return check.Finding("3A", title, check.PROVED, expected, observed, evidence)


def _staff_rule(managed: Sequence[str]) -> check.Finding:
    title = "give_store_credit is refused on a shopper agent"
    expected = ("published is not permitted: give_store_credit is published for the Operator, and "
                "no shopper agent names it")
    evidence = ["give_store_credit moves money; Cedar decides each call, and the Router refuses to "
                "build a shopper agent that names it"]
    named = sorted(set(managed) & STAFF_ONLY)
    if named:
        return check.Finding("3A", title, check.CONTRADICTED, expected,
                             "the Support agent names give_store_credit: published is not "
                             "permitted, and the Router refuses to build this agent", evidence,
                             "which of the nine tools moves money? Only the Operator calls it.")
    return check.Finding("3A", title, check.PROVED, expected,
                         "published is not permitted: the Support agent does not name "
                         "give_store_credit", evidence)


def judge_catalogue(
    published: Iterable[str], managed: Sequence[str], bound: Iterable[str],
    probes: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[check.Finding]:
    """Task 3A's four rules from its two marked regions and the forged calls, one finding each.

    ``probes`` (:func:`probe_binding` per read) decide the binding when they are
    given: they are what the server does, where ``bound`` is only what the region
    names.
    """
    published, bound = frozenset(published), frozenset(bound)
    return [_published_rule(published, managed), _reads_rule(managed),
            _bound_rule(bound, probes), _staff_rule(managed)]


def catalogue_verdict(findings: Sequence[check.Finding]) -> check.Finding:
    """One finding for the doctor and the evidence export: the first rule not met, or all four."""
    for finding in findings:
        if finding.state != check.PROVED:
            return finding
    published, reads, bound, _staff = findings
    return check.Finding("3A", _CATALOGUE_TITLE, check.PROVED, _CATALOGUE_EXPECTED,
                         f"{published.observed}; {reads.observed}; {bound.observed}",
                         [line for finding in findings for line in finding.evidence])


def source_catalogue() -> tuple:
    """``(published, support tools, caller-bound tools, forged calls)`` from the live source."""
    for path in (DEPLOY, BACKEND):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from gateway_tool_schemas import workshop_published_tools
    from services.agentcore_gateway import (
        SUPPORT_CALLER_BOUND_TOOLS,
        SUPPORT_GATEWAY_TOOLS,
        _bind_server_tool_context,
    )

    probes = {read: probe_binding(_bind_server_tool_context, read) for read in SHOPPER_READS}
    return (workshop_published_tools(), SUPPORT_GATEWAY_TOOLS, SUPPORT_CALLER_BOUND_TOOLS, probes)


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
                             f"run bash scripts/lab3-start.sh theo, then {SEND}."
                             + check.since_note(3, SEND))
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
                             "deploy with --mode participant, then send Theo's requests "
                             f"again in a new conversation: {SEND}.")
    if deployed == local:
        return check.Finding("3B", _BUILD_TITLE, check.PROVED, BUILD_EXPECTED,
                             "the two builds match", evidence)
    return check.Finding("3B", _BUILD_TITLE, check.CONTRADICTED, BUILD_EXPECTED,
                         "another build answered", evidence,
                         "deploy your Task 3A change with --mode participant, then send "
                         f"Theo's requests again in a new conversation: {SEND}.")


_TICKETS_TITLE = "every executed ticket read was Theo's own"
TICKETS_EXPECTED = ("at least one executed get_tickets call on the Gateway in Theo's turns, "
                    f"every one for {THEO}, none for another customer; a forged call for "
                    f"{JESSICA} leaves this checkout as {THEO}")
_NEXT_BIND = ("which support tool lets the model choose whose records to read? See "
              "SUPPORT_CALLER_BOUND_TOOLS in the Support agent - Gateway tools block, then "
              "deploy with --mode participant.")


def judge_tickets(rows: Sequence[Dict[str, Any]],
                  probe: Optional[Dict[str, str]] = None) -> check.Finding:
    """Whose tickets the executed Gateway reads asked for, and whose a forged one would.

    Theo's own reads carry CUST-THEO whether or not the server binds them,
    because the model usually names him. ``probe`` (:func:`probe_binding`)
    shows the server binds a request for someone else too.
    """
    evidence = [f"pellier.tool_audit audit {r.get('audit_id')}: get_tickets for "
                f"{r.get('customer_id') or 'no customer'} in turn {r.get('turn_id')}"
                for r in rows[-5:]]
    if probe is not None:
        evidence += _probe_lines(probe)
    if not rows:
        return check.Finding("3B", _TICKETS_TITLE, check.NOT_YET, TICKETS_EXPECTED,
                             "no get_tickets call has run on the Gateway yet", evidence,
                             f"send Theo's ticket question on the managed path: {SEND}."
                             + check.since_note(3, SEND))
    others = [r for r in rows if r.get("customer_id") != THEO]
    observed = (f"{len(rows)} executed call(s), {len(rows) - len(others)} for {THEO}, "
                f"{len(others)} for anyone else")
    if others:
        return check.Finding("3B", _TICKETS_TITLE, check.CONTRADICTED, TICKETS_EXPECTED,
                             observed, evidence, _NEXT_BIND)
    if probe is not None and not _probe_binds(probe):
        return check.Finding("3B", _TICKETS_TITLE, check.CONTRADICTED, TICKETS_EXPECTED,
                             observed + f"; a forged call for {JESSICA} would leave as "
                             f"{probe['sent']}", evidence, _NEXT_BIND)
    if probe is not None:
        observed += f"; a forged call for {JESSICA} leaves as {THEO}"
    return check.Finding("3B", _TICKETS_TITLE, check.PROVED, TICKETS_EXPECTED, observed, evidence)


def source_probe() -> tuple:
    """``(forged call, "")`` through this checkout's binding, or ``(None, the reason)``."""
    try:
        return source_catalogue()[3][PROBE_TOOL], ""
    except Exception as exc:  # noqa: BLE001 - reported as the tickets finding's reason
        return None, f"{type(exc).__name__}: {str(exc)[:160]}"


def tickets_finding(rows: Sequence[Dict[str, Any]]) -> check.Finding:
    """The tickets verdict, which needs the forged call: Theo's own reads alone prove nothing."""
    probe, reason = source_probe()
    if probe is None:
        return check.Finding("3B", _TICKETS_TITLE, check.UNCHECKED, TICKETS_EXPECTED,
                             "the forged call could not run through this checkout's binding",
                             [reason], "run this from the repository root on the workshop box, "
                             "with the backend's Python.")
    return judge_tickets(rows, probe)


# ---------------------------------------------------------------------------
# Task 3B: Theo's remembered taste, read the way the managed rail reads it
# ---------------------------------------------------------------------------

_MEMORY_TITLE = "the managed agent is given Theo's remembered taste"
MEMORY_EXPECTED = ("the managed rail's AgentCore Memory read for CUST-THEO returns the "
                   "user-preference record extracted from his provisioning conversation")


def _event_text(event: Dict[str, Any]) -> str:
    for payload in event.get("payload") or []:
        text = ((payload.get("conversational") or {}).get("content") or {}).get("text")
        if isinstance(text, str):
            return text[:90]
    return ""


def judge_memory(memory_id: str, seeded: Dict[str, Any],
                 remembered: Sequence[Dict[str, str]]) -> check.Finding:
    """What the managed rail reads for Theo, beside what provisioning recorded.

    ``seeded`` is ``seed_agentcore_memory.seeded_memory`` for CUST-THEO;
    ``remembered`` is ``AgentCoreMemory.get_semantic_memories`` with the strict
    client, the same read the storefront's managed rail makes at turn start.
    """
    provisioned = {str(r.get("memoryRecordId")) for r in seeded.get("records") or []}
    ids = [item["record_id"] for item in remembered]
    evidence = [f"AgentCore Memory {memory_id}, namespace {seeded.get('namespace')}"]
    evidence += [f"source event {e.get('eventId')} (actor {seeded.get('actor')}, session "
                 f"{seeded.get('session')}): {_event_text(e)}" for e in seeded.get("events") or []]
    evidence += [f"record {item['record_id']}: {item['preference'][:90]}" for item in remembered]
    observed = (f"the managed rail's read returns {len(ids)} record(s); provisioning's "
                f"conversation produced {len(provisioned)}")
    if not seeded.get("events"):
        return check.Finding("3B", _MEMORY_TITLE, check.CONTRADICTED, MEMORY_EXPECTED,
                             "Theo's provisioning conversation is missing", evidence,
                             "rerun scripts/deploy/seed_agentcore_memory.py.")
    if not provisioned:
        return check.Finding("3B", _MEMORY_TITLE, check.NOT_YET, MEMORY_EXPECTED, observed,
                             evidence, "extraction runs after the conversation; run this "
                                       "again in a minute.")
    if not ids or not set(ids) <= provisioned:
        return check.Finding("3B", _MEMORY_TITLE, check.CONTRADICTED, MEMORY_EXPECTED, observed,
                             evidence, "the read and the provisioning record disagree; check "
                                       "the namespace /pellier/preferences/CUST-THEO/.")
    return check.Finding("3B", _MEMORY_TITLE, check.PROVED, MEMORY_EXPECTED, observed, evidence)


def read_memory() -> Dict[str, Any]:
    """Theo's provisioning conversation, and what the managed rail's read returns for him."""
    import asyncio

    for path in (DEPLOY, BACKEND):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from gateway_client import _load_env

    _load_env()
    import boto3
    from config import settings
    from seed_agentcore_memory import seeded_memory
    from services.agentcore_memory import AgentCoreMemory
    from services.memory_showcase import AWS_CONFIG

    memory_id = settings.AGENTCORE_MEMORY_ID
    if not memory_id:
        raise RuntimeError("AGENTCORE_MEMORY_ID is not configured")
    region = settings.aws_region_resolved
    seeded = seeded_memory(
        boto3.client("bedrock-agentcore-control", region_name=region, config=AWS_CONFIG),
        boto3.client("bedrock-agentcore", region_name=region, config=AWS_CONFIG),
        memory_id, THEO,
    )
    strict = AgentCoreMemory(memory_id=memory_id, region=region, strict=True)
    remembered = asyncio.run(strict.get_semantic_memories(THEO))
    return {"memory_id": memory_id, "seeded": seeded, "remembered": remembered}


def memory_finding(read: Callable[[], Dict[str, Any]] = read_memory) -> check.Finding:
    """Theo's memory finding; UNCHECKED where AgentCore Memory cannot be read."""
    try:
        found = read()
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - reported as UNCHECKED
        return check.Finding("3B", _MEMORY_TITLE, check.UNCHECKED, MEMORY_EXPECTED,
                             "AgentCore Memory could not be read here",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"],
                             "run this on the workshop box, where Memory is provisioned.")
    return judge_memory(found["memory_id"], found["seeded"], found["remembered"])


# ---------------------------------------------------------------------------
# Task 3B: Theo's token asks the Gateway directly for Jessica's tickets
# ---------------------------------------------------------------------------

_PROBE_TITLE = "Cedar refuses Theo's direct read of Jessica's tickets"
PROBE_EXPECTED = ("a Cedar denial: the owner-only permit matches only Theo's own customer id, "
                  "so nothing permits the read; and no tool_audit row for the probe's turn: "
                  "a denied call never runs")


def judge_probe(payload: Dict[str, Any], audit_rows: Optional[int]) -> check.Finding:
    """The direct probe's outcome beside the rows its turn left."""
    evidence = [
        f"principal theo, action {payload.get('action')}, customer_id {JESSICA}",
        f"turn {payload.get('turn_id')}: "
        + (f"{audit_rows} tool_audit row(s)" if audit_rows is not None else "rows not read"),
    ]
    said = str(payload.get("error") or payload.get("result") or "")[:200]
    if said:
        evidence.append(f"Gateway diagnostic, verbatim: {said}")
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
    if audit_rows is None:
        return check.Finding("3B", _PROBE_TITLE, check.UNCHECKED, PROBE_EXPECTED,
                             "Cedar denied it, but the tool_audit rows could not be read",
                             evidence, "run this where the database settings are readable; "
                                       "a denial is half the proof, the absent row the other.")
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
        since = {"since": check.reset_point(3)}
        cur.execute(BUILD_SQL, since)
        build = cur.fetchone()
        cur.execute(TICKETS_SQL, since)
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
                             tickets_finding(rows["tickets"])]
        except Exception as exc:  # noqa: BLE001 - the reason is the finding
            reason = [f"{type(exc).__name__}: {str(exc)[:160]}"]
            rows_findings = [
                check.Finding("3B", _BUILD_TITLE, check.UNCHECKED, BUILD_EXPECTED,
                              "the check could not look", reason),
                check.Finding("3B", _TICKETS_TITLE, check.UNCHECKED, TICKETS_EXPECTED,
                              "the check could not look", reason),
            ]
    build, tickets = rows_findings
    import lab3_row_ownership_check

    ownership = lab3_row_ownership_check.collect(env_path)
    return [build, memory_finding(), tickets, run_probe(cfg), *ownership]


def findings_3a() -> List[check.Finding]:
    """Task 3A's four rules from this checkout's source, or one finding saying why not."""
    try:
        return judge_catalogue(*source_catalogue())
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return [check.Finding("3A", _CATALOGUE_TITLE, check.UNCHECKED, _CATALOGUE_EXPECTED,
                              "the check could not look", [f"{type(exc).__name__}: {exc}"],
                              "run this from the repository root, with the backend's Python.")]


def main_3a() -> int:
    """Task 3A from source, before any deploy: one finding per rule."""
    findings = findings_3a()
    print("Lab 3A: the Support agent, assembled for AgentCore")
    for finding in findings:
        print(check.render(finding))
    passed = all(finding.state == check.PROVED for finding in findings)
    print("Lab 3A check passed" if passed else "Lab 3A check failed")
    return 0 if passed else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", choices=("3A", "3B"), required=True,
                        help="3A checks the two Task 3A regions from source; 3B reads Theo's "
                             "managed turns")
    if parser.parse_args(argv).task == "3A":
        return main_3a()
    findings = collect()
    print("Lab 3B: Theo's managed turns, read from tool_audit, AgentCore Memory, the Gateway "
          "and the row policies")
    for finding in findings:
        print(check.render(finding))
    passed = all(finding.state == check.PROVED for finding in findings)
    print("Lab 3B check passed" if passed else "Lab 3B check failed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
