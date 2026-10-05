#!/usr/bin/env python3
"""Lab 4A's check: your Cedar rule, evaluated with Cedar, then enforced by the Gateway.

    python3 scripts/lab4_policy_check.py

Part 1 runs here and deploys nothing. It evaluates your
``policies/workshop_credit_limit.cedar`` with the real Cedar engine (the
``cedarpy`` package), beside the baseline the provisioner renders, against
the Gateway's Cedar schema rendered from the published tool schemas:

* every policy must parse, validate against the schema and evaluate without
  an error (an erroring forbid is skipped, which would read as an ALLOW);
* the decision matrix: a shopper at $100, and Nadia at 9999, 10000 and 10001
  cents, plus an ordinary amount and a second staff member;
* five wrong rules (``false``, ``true``, staff-only, ``< 10000`` and
  ``<= 100``) put in place of your ``unless`` block, each of which the matrix
  must catch;
* the matrix with your rule left out: Nadia's 10001-cent request must then be
  allowed, so the denial is your rule's.

Part 2 runs on the workshop box. It reads the deployed ``workshop_credit_limit``
statement, which must be your file, then sends one over-limit credit through
the Gateway with Nadia's own token. The credit has its own review: 10001
cents on Jessica's account, covering no order, approved under Nadia's
identity. Cedar must deny it, and its key must leave no ``tool_audit`` row and
no ``store_credits`` row. Nothing here deploys a policy.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import workshop_check as check  # noqa: E402  (sibling module)

REPO = check.REPO
BACKEND = REPO / "pellier" / "backend"
DEPLOY = SCRIPTS / "deploy"
for _path in (DEPLOY, BACKEND):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from gateway_tool_schemas import TOOL_SCHEMAS, workshop_target_tools  # noqa: E402
from render_agentcore_project import (  # noqa: E402
    CREDIT_LIMIT_POLICY,
    CREDIT_LIMIT_SOURCE,
    CREDIT_LIMIT_STARTER,
    GATEWAY_ARN_PLACEHOLDER,
    GIVE_STORE_CREDIT_ACTION,
    baseline_policies,
)

POLICY_FILE = REPO / CREDIT_LIMIT_SOURCE
STARTER_FILE = REPO / CREDIT_LIMIT_STARTER
LOCAL_GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/pellier-local-check"
ALLOW, DENY = "ALLOW", "DENY"
LIMIT_CENTS, PROBE_CENTS = 10000, 10001

# The isolated over-limit review Part 2 sends. It names Jessica's account but
# covers no order, so even a wrongly allowed call could pay nothing, and it is
# found again by its issue: the absence check reads its key from it.
PROBE_CUSTOMER = "CUST-JESSICA"
PROBE_REASON = "Over-limit probe for the Lab 4 policy check"
PROBE_ISSUE = "Lab 4 over-limit probe: covers no order"


@dataclass(frozen=True)
class Caller:
    """A signed-in principal as AgentCore Policy sees it: an id and claim tags."""

    label: str
    principal_id: str
    tags: Dict[str, str]


SHOPPER = Caller("A shopper (Jessica)", "jessica",
                 {"username": "jessica", "custom:customer_id": "CUST-JESSICA"})
NADIA = Caller("Nadia", "nadia", {"username": "nadia", "custom:staff_scope": "returns"})
OTHER_STAFF = Caller("Another staff member", "staff-two",
                     {"username": "staff-two", "custom:staff_scope": "returns"})

# The four rows the guide predicts, then three that catch a hardcoded amount
# or a hardcoded person.
MATRIX: Tuple[Tuple[Caller, int, str], ...] = (
    (SHOPPER, 10000, DENY),
    (NADIA, 9999, ALLOW),
    (NADIA, 10000, ALLOW),
    (NADIA, 10001, DENY),
)
MORE: Tuple[Tuple[Caller, int, str], ...] = (
    (NADIA, 5000, ALLOW),
    (OTHER_STAFF, 10000, ALLOW),
    (OTHER_STAFF, 10001, DENY),
)

# Wrong rules put in place of the participant's unless block. Each must fail
# the matrix, or the matrix could not tell a right rule from a wrong one.
MUTATIONS: Tuple[Tuple[str, str], ...] = (
    ("unless { false }, the starter", "false"),
    ("unless { true }", "true"),
    ("staff-only", 'principal.hasTag("custom:staff_scope") && '
                   'principal.getTag("custom:staff_scope") == "returns"'),
    ("a strict boundary, < 10000",
     "context.input has amount_cents && context.input.amount_cents < 10000"),
    ("dollars, not cents, <= 100",
     "context.input has amount_cents && context.input.amount_cents <= 100"),
)


def dollars(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"


def row_label(caller: Caller, cents: int) -> str:
    return f"{caller.label}, {dollars(cents)} ({cents} cents)"


# ---------------------------------------------------------------------------
# The Gateway's Cedar schema and the policy set
# ---------------------------------------------------------------------------


def _cedar_type(node: Dict[str, Any]) -> Dict[str, Any]:
    """One JSON Schema node as a Cedar type, by AgentCore's documented mapping."""
    kind = node.get("type")
    if kind == "object":
        required = set(node.get("required") or ())
        return {"type": "Record", "attributes": {
            name: {**_cedar_type(child), "required": name in required}
            for name, child in (node.get("properties") or {}).items()}}
    if kind == "array":
        return {"type": "Set", "element": _cedar_type(node.get("items") or {"type": "string"})}
    if kind == "number":
        return {"type": "Extension", "name": "decimal"}
    return {"type": {"integer": "Long", "boolean": "Boolean"}.get(str(kind), "String")}


def gateway_cedar_schema() -> Dict[str, Any]:
    """The Cedar schema AgentCore Policy generates for the published tools.

    Per the AgentCore schema constraints: principals are ``AgentCore::OAuthUser``
    with an ``id`` and String claim tags, the resource is ``AgentCore::Gateway``,
    each published tool is an action under ``CallTool`` and ``Mcp``, and the
    only context is ``context.input``, typed from the tool's input schema
    (string String, integer Long, boolean Bool, number Decimal, array Set,
    object Record, ``required`` deciding required attributes).
    """
    published = {tool for tools in workshop_target_tools().values() for tool in tools}
    actions: Dict[str, Any] = {"Mcp": {}, "CallTool": {"memberOf": [{"id": "Mcp"}]}}
    for config in TOOL_SCHEMAS.values():
        for tool in config["tools"]:
            if tool["name"] not in published:
                continue
            actions[f"{config['target_name']}___{tool['name']}"] = {
                "memberOf": [{"id": "CallTool"}],
                "appliesTo": {
                    "principalTypes": ["OAuthUser"],
                    "resourceTypes": ["Gateway"],
                    "context": {"type": "Record", "attributes": {
                        "input": {**_cedar_type(tool["inputSchema"]), "required": True}}},
                },
            }
    return {"AgentCore": {
        "entityTypes": {
            "OAuthUser": {"shape": {"type": "Record",
                                    "attributes": {"id": {"type": "String"}}},
                          "tags": {"type": "String"}},
            "Gateway": {},
        },
        "actions": actions,
    }}


def baseline_set(gateway_arn: str = LOCAL_GATEWAY_ARN) -> List[Tuple[str, str]]:
    """The provisioner's baseline permits, as ``(name, statement)``.

    The output guardrail is left out: it checks a credit's response text after
    the tool runs and is not an authorization policy Cedar can evaluate here.
    """
    return [(policy["name"], policy["statement"])
            for policy in baseline_policies(gateway_arn=gateway_arn)]


def render_rule(text: str, gateway_arn: str = LOCAL_GATEWAY_ARN) -> str:
    """The rule as the deploy renders it: the Gateway placeholder filled in."""
    return text.replace(GATEWAY_ARN_PLACEHOLDER, gateway_arn)


def cedar_code(text: str) -> str:
    """The policy without its whole-line ``//`` comments, which may quote ``unless``."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


def _split_unless(text: str) -> Tuple[str, str]:
    """``(everything before, the final unless block)`` of a policy's code."""
    code = cedar_code(text)
    start = code.rfind("unless")
    if start < 0 or "{" not in code[start:] or "}" not in code[start:]:
        raise ValueError("the policy has no final unless block")
    return code[:start], code[start:]


def with_unless(text: str, body: str) -> str:
    """``text`` with its final ``unless`` block replaced by ``body``."""
    head, _tail = _split_unless(text)
    return f"{head}unless {{\n  {body}\n}};\n"


def unless_body(text: str) -> str:
    """The final ``unless`` block's condition, trailing comments dropped, on one line."""
    try:
        _head, tail = _split_unless(text)
    except ValueError:
        return ""
    inner = tail[tail.index("{") + 1:tail.rindex("}")]
    lines = [line.split("//", 1)[0].strip() for line in inner.splitlines()]
    return " ".join(line for line in lines if line)


def same_rule(left: str, right: str) -> bool:
    """Whether two statements are the same Cedar, comments and spacing aside."""
    return " ".join(cedar_code(left).split()) == " ".join(cedar_code(right).split())


def _policy_text(policies: Sequence[Tuple[str, str]]) -> str:
    return "\n".join(f'@id("{name}")\n{statement}' for name, statement in policies)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@dataclass
class Decision:
    decision: str
    decided_by: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def decide(policies: Sequence[Tuple[str, str]], schema: Dict[str, Any], caller: Caller,
           cents: int, gateway_arn: str = LOCAL_GATEWAY_ARN) -> Decision:
    """One Cedar authorization of a schema-valid give_store_credit request."""
    import cedarpy

    request = {
        "principal": {"type": "AgentCore::OAuthUser", "id": caller.principal_id},
        "action": {"type": "AgentCore::Action", "id": GIVE_STORE_CREDIT_ACTION},
        "resource": {"type": "AgentCore::Gateway", "id": gateway_arn},
        "context": {"input": {"customer_id": "CUST-JESSICA", "amount_cents": cents,
                              "reason": "Lab 4 policy check",
                              "idempotency_key": "lab4-local-check"}},
    }
    entities = [
        {"uid": {"type": "AgentCore::OAuthUser", "id": caller.principal_id},
         "attrs": {"id": caller.principal_id}, "parents": [], "tags": dict(caller.tags)},
        {"uid": {"type": "AgentCore::Gateway", "id": gateway_arn}, "attrs": {}, "parents": []},
    ]
    result = cedarpy.is_authorized(request, _policy_text(policies), entities, schema=schema)
    names = result.diagnostics.id_annotations_by_reason
    return Decision(
        ALLOW if result.allowed else DENY,
        [names.get(reason, reason) for reason in result.diagnostics.reasons],
        [str(error) for error in result.diagnostics.errors],
    )


def validation_errors(policies: Sequence[Tuple[str, str]], schema: Dict[str, Any]) -> List[str]:
    """Parse and schema errors for the whole set; empty when Cedar accepts it."""
    import cedarpy

    try:
        result = cedarpy.validate_policies(_policy_text(policies), schema)
    except Exception as exc:  # noqa: BLE001 - a parse failure is a finding
        return [f"{type(exc).__name__}: {exc}"]
    return [] if result.validation_passed else [str(error) for error in result.errors]


@dataclass
class Assessment:
    """The matrix, plus whatever stopped Cedar from deciding it."""

    errors: List[str]
    rows: List[Tuple[Caller, int, str, Decision]]

    @property
    def wrong(self) -> List[Tuple[Caller, int, str, Decision]]:
        return [row for row in self.rows if row[3].decision != row[2] or row[3].errors]

    @property
    def passed(self) -> bool:
        return not self.errors and not self.wrong


def assess(rule: Optional[str], schema: Dict[str, Any],
           baseline: Sequence[Tuple[str, str]]) -> Assessment:
    """The matrix for the baseline plus ``rule`` (``None`` leaves the rule out)."""
    policies = list(baseline) + ([(CREDIT_LIMIT_POLICY, rule)] if rule is not None else [])
    errors = validation_errors(policies, schema)
    if errors:
        return Assessment(errors, [])
    rows = [(caller, cents, want, decide(policies, schema, caller, cents))
            for caller, cents, want in MATRIX + MORE]
    return Assessment([], rows)


@dataclass
class LocalResult:
    finding: check.Finding
    table: List[List[str]]


def _first_wrong(assessment: Assessment) -> str:
    if assessment.errors:
        return "Cedar rejects it: " + assessment.errors[0][:120]
    caller, cents, want, got = assessment.wrong[0]
    return f"{row_label(caller, cents)} reads {got.decision}, expected {want}"


def _next_step(assessment: Assessment) -> str:
    if assessment.errors:
        return "fix the syntax or the attribute name: Cedar must accept the rule before it decides."
    wrong = {(c.label, cents) for c, cents, _w, _d in assessment.wrong}
    if ("Nadia", 10001) in wrong or ("Another staff member", 10001) in wrong:
        return ("your rule lets an over-limit credit through: true, staff-only, or the wrong unit "
                "lets 10001 cents pass.")
    if ("Nadia", 10000) in wrong and ("Nadia", 9999) not in wrong:
        return "your comparison excludes the limit: 10000 cents must pass."
    return "your rule denies an in-limit credit: compare amount_cents, in cents, with 10000."


def local_check(rule_text: str, starter_text: str) -> LocalResult:
    """Part 1: the matrix, the five wrong rules and the counterfactual."""
    schema = gateway_cedar_schema()
    baseline = baseline_set()
    rule = render_rule(rule_text)
    yours = assess(rule, schema, baseline)
    starter = assess(render_rule(starter_text), schema, baseline)
    alone = assess(None, schema, baseline)
    caught = [(label, assess(with_unless(rule, body), schema, baseline))
              for label, body in MUTATIONS]
    escaped = [label for label, mutant in caught if mutant.passed]

    def cell(assessment: Assessment, index: int) -> str:
        if assessment.errors:
            return "error"
        decision = assessment.rows[index][3]
        return decision.decision + (" (error)" if decision.errors else "")

    table = [[row_label(caller, cents), cell(alone, i), cell(starter, i), cell(yours, i), want,
              "matches" if not yours.errors and yours.rows[i][3].decision == want
              and not yours.rows[i][3].errors else "differs"]
             for i, (caller, cents, want) in enumerate(MATRIX + MORE)]

    over_limit_alone = next((d for c, cents, _w, d in alone.rows
                             if c is NADIA and cents == PROBE_CENTS), None)
    counterfactual_holds = over_limit_alone is not None and over_limit_alone.decision == ALLOW
    digest = hashlib.sha256(rule.encode("utf-8")).hexdigest()
    evidence = [
        f"{CREDIT_LIMIT_SOURCE} sha256:{digest[:16]}, unless {{ {unless_body(rule_text)} }}",
        f"evaluated with Cedar beside {len(baseline)} baseline policies "
        f"({', '.join(name for name, _ in baseline)}) and the Gateway schema for "
        f"{len(schema['AgentCore']['actions']) - 2} published tools",
    ]
    if not yours.errors:
        decided = next((d for c, cents, _w, d in yours.rows if c is NADIA and cents == PROBE_CENTS))
        evidence.append(f"Nadia at {PROBE_CENTS} cents: {decided.decision}, decided by "
                        f"{', '.join(decided.decided_by) or 'no policy (default deny)'}")
    evidence += [f"wrong rule {label}: {'caught' if not m.passed else 'NOT caught'}, "
                 f"{_first_wrong(m) if not m.passed else 'the matrix passed it'}"
                 for label, m in caught]
    evidence.append("without your rule, Nadia at 10001 cents: "
                    + (over_limit_alone.decision if over_limit_alone else "not evaluated")
                    + (f", decided by {', '.join(over_limit_alone.decided_by)}"
                       if over_limit_alone and over_limit_alone.decided_by else ""))

    title = "your rule limits one credit to $100"
    expected = ("Cedar accepts the rule; shopper $100 DENY, Nadia 9999 and 10000 ALLOW, 10001 "
                "DENY, the same for a second staff member; the five wrong rules are caught; "
                "without your rule Nadia's 10001 cents is allowed")
    observed = (f"{sum(1 for row in table if row[-1] == 'matches')} of {len(table)} decisions "
                f"match; {len(caught) - len(escaped)} of {len(caught)} wrong rules caught; "
                f"without your rule Nadia's 10001 cents is "
                f"{over_limit_alone.decision if over_limit_alone else 'not evaluated'}")
    if yours.errors:
        observed = f"Cedar rejects your rule: {yours.errors[0][:160]}"
    if rule_text == starter_text:
        state, next_step = check.NOT_YET, "edit the final unless block, then run this again."
    elif yours.passed and not escaped and counterfactual_holds:
        state, next_step = check.PROVED, ""
    elif escaped or not counterfactual_holds:
        state = check.UNCHECKED
        next_step = ("the check itself is not sound here: a wrong rule passed or the baseline "
                     "alone denies 10001 cents. Report it; do not change your rule for it.")
    else:
        state, next_step = check.CONTRADICTED, _next_step(yours)
    return LocalResult(check.Finding("4A", title, state, expected, observed, evidence, next_step),
                       table)


# ---------------------------------------------------------------------------
# Part 2: the deployed rule and one over-limit credit through the Gateway
# ---------------------------------------------------------------------------

PROBE_ROWS_SQL = """
SELECT (SELECT count(*) FROM pellier.tool_audit
         WHERE args->>'idempotency_key' = %(key)s) AS audit_rows,
       (SELECT count(*) FROM pellier.store_credits
         WHERE idempotency_key = %(key)s) AS credit_rows;
"""

_APPROVE_PROBE_SQL = """
UPDATE pellier.approvals
   SET status = 'approved', decided_by = %s, decided_by_name = %s, decided_at = now()
 WHERE id = %s AND status = 'pending'
"""

_PROBE_ROW_SQL = """
SELECT id, status, action_hash, args, order_ids, decided_by_name
  FROM pellier.approvals
 WHERE id = %s
"""

_MANAGED_TITLE = "the Gateway enforces your rule on an over-limit credit"
MANAGED_EXPECTED = ("the deployed workshop_credit_limit is your file; Nadia's approved 10001-cent "
                    "credit is a Cedar denial, and its key leaves 0 tool_audit and 0 "
                    "store_credits rows")


def _runner(conn: Any) -> Any:
    def run(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall()) if cur.description else []
    return run


def ensure_probe_review(conn: Any, *, staff_sub: str, staff_name: str) -> Dict[str, Any]:
    """The isolated over-limit review, opened once and approved under the staff identity.

    Returns its row with the write key it admits. Running the check again
    resolves to the same live review and so the same key.
    """
    from services import store_tools

    review = store_tools.open_credit_review(
        _runner(conn), customer_id=PROBE_CUSTOMER, amount_cents=PROBE_CENTS,
        reason=PROBE_REASON, source_turn_id=None, requested_by_sub=staff_sub,
        requester_kind="operator", order_ids=(), issue=PROBE_ISSUE,
        recommendation={"primaryAction": "give_store_credit", "rationale": PROBE_ISSUE},
    )
    if review is None:
        raise RuntimeError("the over-limit review could not be opened")
    with conn.cursor() as cur:
        cur.execute(_APPROVE_PROBE_SQL, (staff_sub, staff_name, review.id))
        cur.execute(_PROBE_ROW_SQL, (review.id,))
        row = dict(cur.fetchone())
    conn.commit()
    row["idempotency_key"] = store_tools.execution_idempotency_key(row["id"], row["action_hash"])
    return row


_RECORD_ATTEMPT_SQL = """
UPDATE pellier.approvals
   SET last_attempt = %s::jsonb,
       execution_turn_id = coalesce(execution_turn_id, %s)
 WHERE id = %s
"""

# The over-limit review, as the tables recorded it: the Gateway's answer the
# check stored on it, and the rows its key left.
PROBE_SQL = f"""
SELECT a.id, a.status, a.last_attempt,
       'operator-review:' || a.id || ':' || left(a.action_hash, 32) AS idempotency_key,
       (SELECT count(*) FROM pellier.tool_audit
         WHERE args->>'idempotency_key'
               = 'operator-review:' || a.id || ':' || left(a.action_hash, 32)) AS audit_rows,
       (SELECT count(*) FROM pellier.store_credits
         WHERE idempotency_key
               = 'operator-review:' || a.id || ':' || left(a.action_hash, 32)) AS credit_rows
  FROM pellier.approvals a
 WHERE a.tool = 'give_store_credit'
   AND a.status = 'approved'
   AND a.issue = '{PROBE_ISSUE}'
 ORDER BY a.id DESC
 LIMIT 1;
"""


def attempt_for(payload: Dict[str, Any], key: str, engine: Dict[str, Any]) -> Dict[str, Any]:
    """The Gateway's answer to the over-limit call, in ``approvals.last_attempt``'s shape."""
    from services import governed_execution as ge

    if payload.get("outcome") == "deny" and payload.get("cedar_denial"):
        outcome, policy = ge.ATTEMPT_DENIED, ge.POLICY_DENY
    elif payload.get("outcome") == "allow":
        outcome, policy = ge.ATTEMPT_ALLOWED, ge.POLICY_ALLOW
    else:
        outcome, policy = ge.ATTEMPT_FAILED, ge.POLICY_EVALUATION_INCOMPLETE
    return ge.last_attempt(outcome, idempotency_key=key, rail=ge.RAIL_GATEWAY, policy=policy,
                           engine_state=ge.PolicyEngineState.from_engine_read(engine),
                           detail=payload.get("error"))


def record_probe_attempt(conn: Any, review_id: int, attempt: Dict[str, Any]) -> None:
    """Store the answer on the review, so the Operator and the export read it too."""
    import json
    import uuid

    with conn.cursor() as cur:
        turn = f"turn-lab4-probe-{uuid.uuid4().hex[:12]}"
        cur.execute(_RECORD_ATTEMPT_SQL, (json.dumps(attempt), turn, review_id))
    conn.commit()


def judge_recorded_probe(row: Optional[Dict[str, Any]]) -> check.Finding:
    """The over-limit review's stored answer and the rows its key left."""
    title = "Cedar denied the over-limit credit, and it left no row"
    expected = ("the Lab 4A check's over-limit review stored a Gateway denial, and its key has "
                "0 tool_audit and 0 store_credits rows")
    if not row:
        return check.Finding("4A", title, check.NOT_YET, expected,
                             "no over-limit review has been sent yet", [],
                             "deploy your rule, then run python3 scripts/lab4_policy_check.py.")
    attempt = row.get("last_attempt")
    if isinstance(attempt, str):
        import json

        attempt = json.loads(attempt)
    attempt = attempt or {}
    evidence = [f"pellier.approvals review {row.get('id')}, key {row.get('idempotency_key')}",
                f"stored answer: {attempt.get('outcome') or 'none'}, policy "
                f"{attempt.get('policy') or 'none'}, policy set "
                f"{str(attempt.get('policy_digest') or 'unread')[:23]}",
                f"tool_audit rows {row.get('audit_rows')}, "
                f"store_credits rows {row.get('credit_rows')}"]
    rows_left = int(row.get("audit_rows") or 0) + int(row.get("credit_rows") or 0)
    if rows_left or attempt.get("outcome") == "allowed":
        return check.Finding("4A", title, check.CONTRADICTED, expected,
                             "the over-limit credit got past Cedar", evidence,
                             "run python3 scripts/lab4_policy_check.py and read part 2.")
    if attempt.get("outcome") != "denied":
        return check.Finding("4A", title, check.NOT_YET, expected,
                             "no Gateway denial is stored for the over-limit review", evidence,
                             "deploy your rule, then run python3 scripts/lab4_policy_check.py.")
    return check.Finding("4A", title, check.PROVED, expected,
                         "the Gateway denied it and its key left no row", evidence)


def judge_managed(*, deployed: Optional[str], local_rule: str, local_proved: bool,
                  payload: Optional[Dict[str, Any]], rows: Optional[Dict[str, int]],
                  review: Optional[Dict[str, Any]], engine: Dict[str, Any]) -> check.Finding:
    """Part 2's verdict from what the control plane, the Gateway and the tables said."""
    policy_id = (engine.get("policy_ids") or {}).get(CREDIT_LIMIT_POLICY, "unknown")
    evidence = [f"policy {CREDIT_LIMIT_POLICY} {policy_id}, policy set "
                f"{str(engine.get('policy_digest') or 'unread')[:23]}, read just before the call"]
    if deployed is None:
        return check.Finding("4A", _MANAGED_TITLE, check.CONTRADICTED, MANAGED_EXPECTED,
                             f"{CREDIT_LIMIT_POLICY} is not on the policy engine", evidence,
                             "provisioning deploys the starter; ask for the environment to be "
                             "reprovisioned.")
    if not same_rule(deployed, local_rule):
        return check.Finding("4A", _MANAGED_TITLE, check.NOT_YET, MANAGED_EXPECTED,
                             "the deployed rule is not your file yet", evidence,
                             'deploy it: python3 scripts/provision_agentcore_end_to_end.py '
                             '--repo-path "$PWD" --mode participant')
    if not local_proved:
        return check.Finding("4A", _MANAGED_TITLE, check.NOT_YET, MANAGED_EXPECTED,
                             "your rule is deployed but did not pass Part 1", evidence,
                             "fix the rule until Part 1 passes, then deploy it again.")
    if payload is None or review is None or rows is None:
        return check.Finding("4A", _MANAGED_TITLE, check.UNCHECKED, MANAGED_EXPECTED,
                             "the over-limit call could not be made", evidence)
    evidence += [
        f"review {review['id']} for {PROBE_CUSTOMER}, {PROBE_CENTS} cents, covers no order, "
        f"{review['status']} by {review.get('decided_by_name') or 'staff'}",
        f"idempotency key {review['idempotency_key']}",
        f"the Gateway said: {str(payload.get('error') or payload.get('result') or '')[:160]}",
        f"tool_audit rows {rows['audit_rows']}, store_credits rows {rows['credit_rows']} "
        "for that key",
    ]
    if payload.get("outcome") == "allow" or rows["credit_rows"] or rows["audit_rows"]:
        return check.Finding("4A", _MANAGED_TITLE, check.CONTRADICTED, MANAGED_EXPECTED,
                             "the over-limit credit got past Cedar", evidence,
                             "Part 1 and the deployed rule disagree with the Gateway; read the "
                             "deployed statement and the enforcement mode "
                             "(scripts/policy_mode.py).")
    if payload.get("outcome") != "deny" or not payload.get("cedar_denial"):
        return check.Finding("4A", _MANAGED_TITLE, check.UNCHECKED, MANAGED_EXPECTED,
                             "the call failed for another reason, so it says nothing about Cedar",
                             evidence, "a 401, a validation failure or a transport error is not "
                                       "a policy decision; read the Gateway's words above.")
    return check.Finding("4A", _MANAGED_TITLE, check.PROVED, MANAGED_EXPECTED,
                         "Cedar denied the over-limit credit before the tool ran; its key left "
                         "no row", evidence)


def managed_check(
    local: LocalResult, rule_text: str, cfg: Optional[Dict[str, str]],
) -> check.Finding:
    """Part 2 on the workshop box; UNCHECKED where no Gateway is provisioned."""
    try:
        import anyio
        from gateway_client import _load_env, _require, _token_from_cognito, _verified_identity
        from gateway_policy_probe import _call_tool, classify_call

        _load_env()
        gateway_url = _require("AGENTCORE_GATEWAY_URL")
        gateway_arn = _require("AGENTCORE_GATEWAY_ARN")
        from services import managed_policy

        engine = anyio.run(managed_policy.engine_state_for_action, GIVE_STORE_CREDIT_ACTION)
        if engine is None:
            raise RuntimeError("AGENTCORE_POLICY_ENGINE_ID is not set")
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - reported as UNCHECKED
        return check.Finding("4A", _MANAGED_TITLE, check.UNCHECKED, MANAGED_EXPECTED,
                             "the managed environment is not configured here",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"],
                             "run this on the workshop box, where the Gateway is provisioned.")
    deployed = (engine.get("statements") or {}).get(CREDIT_LIMIT_POLICY)
    common = {"deployed": deployed, "local_rule": render_rule(rule_text, gateway_arn),
              "local_proved": local.finding.state == check.PROVED, "engine": engine}
    if deployed is None or not same_rule(deployed, common["local_rule"]) \
            or not common["local_proved"] or cfg is None:
        return judge_managed(payload=None, rows=None, review=None, **common)
    token = _token_from_cognito("nadia")
    identity = _verified_identity(token)
    with check.connect(cfg) as conn:
        review = ensure_probe_review(conn, staff_sub=identity["verified_subject"],
                                     staff_name=identity["verified_username"])
    key = review["idempotency_key"]
    arguments = {"customer_id": PROBE_CUSTOMER, "amount_cents": PROBE_CENTS,
                 "reason": PROBE_REASON, "idempotency_key": key}
    call, failure = None, None
    try:
        call = anyio.run(_call_tool, gateway_url, token, GIVE_STORE_CREDIT_ACTION, arguments)
    except Exception as exc:  # noqa: BLE001 - every failure shape is classified
        failure = exc
    payload = classify_call(call, failure)
    with check.connect(cfg) as conn:
        record_probe_attempt(conn, int(review["id"]), attempt_for(payload, key, engine))
        with conn.cursor() as cur:
            cur.execute(PROBE_ROWS_SQL, {"key": key})
            rows = {k: int(v) for k, v in dict(cur.fetchone()).items()}
    return judge_managed(payload=payload, rows=rows, review=review, **common)


def print_table(rows: List[List[str]]) -> None:
    header = ["request", "baseline alone", "with the starter", "with your rule", "expected",
              "verdict"]
    print(check.table(header, rows))


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    rule_text = POLICY_FILE.read_text(encoding="utf-8")
    local = local_check(rule_text, STARTER_FILE.read_text(encoding="utf-8"))
    print("Lab 4A, part 1: your rule, evaluated with Cedar beside the baseline (nothing deployed)")
    print_table(local.table)
    print(check.render(local.finding))
    print("")
    print("Lab 4A, part 2: the deployed rule and one over-limit credit through the Gateway")
    managed = managed_check(local, rule_text, check.db_config())
    print(check.render(managed))
    passed = local.finding.state == check.PROVED and managed.state == check.PROVED
    print("Lab 4A check passed" if passed else "Lab 4A check failed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
