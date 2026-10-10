#!/usr/bin/env python3
"""Lab 4A's check: your Cedar rule, evaluated with Cedar, then enforced by the Gateway.

    python3 scripts/lab4_policy_check.py

Part 1 runs here and deploys nothing. It evaluates your
``policies/workshop_credit_limit.cedar`` with the real Cedar engine (the
``cedarpy`` package), beside the baseline the provisioner renders, against
the Gateway's Cedar schema rendered from the published tool schemas:

* everything before the final ``unless`` block must be the starter's: the
  principal, the ``give_store_credit`` action and the Gateway are not yours to
  change;
* every policy must parse, validate against the schema and evaluate without
  an error (an erroring forbid is skipped, which would read as an ALLOW);
* the file must hold exactly one policy, the forbid: a second policy would
  deploy beside your rule, so a permit appended after the ``unless`` block is
  refused before any decision is read;
* the decision matrix: a shopper at $100, and Nadia at 9999, 10000 and 10001
  cents, plus a one-cent credit, an ordinary amount and a second staff member,
  for other customers and reasons; then four tools the rule does not govern: a
  shopper's return policy, a shopper's own orders and a staff stock check stay
  allowed, and a shopper reading another customer's orders stays denied;
* eight wrong rules, seven put in place of your ``unless`` block (``false``,
  ``true``, staff-only, ``< 10000``, ``<= 100``, one customer only and a lower
  bound) and one that widens your rule to every action, each of which the
  matrix must catch;
* the matrix with your rule left out: Nadia's 10001-cent request must then be
  allowed, so the denial is your rule's.

Part 2 runs on the workshop box. It reads the deployed ``workshop_credit_limit``
statement, which must be your file, then sends one over-limit credit through
the Gateway with Nadia's own token. The credit has its own review: 10001
cents on Jessica's account, covering no order, opened and confirmed by this
check (no person asks for it or approves it, and the Operator says so). Cedar
must deny it, and its key must leave no ``tool_audit`` row and no
``store_credits`` row. Nothing here deploys a policy.
"""

from __future__ import annotations

import hashlib
import json
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
    STORE_TARGET,
    baseline_policies,
)
from services.operator_review import (  # noqa: E402
    POLICY_CHECK_DECIDER,
    POLICY_CHECK_PROBE_ISSUE as PROBE_ISSUE,
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


@dataclass(frozen=True)
class Request:
    """One authorization the matrix asks Cedar for, and the decision it must get."""

    label: str
    caller: Caller
    tool: str
    tool_input: Dict[str, Any]
    want: str

    @property
    def action(self) -> str:
        return f"{STORE_TARGET}___{self.tool}"

    @property
    def cents(self) -> Optional[int]:
        return self.tool_input.get("amount_cents") if self.tool == "give_store_credit" else None


def dollars(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"


def credit_input(cents: int, customer_id: str = PROBE_CUSTOMER,
                 reason: str = "Lab 4 policy check") -> Dict[str, Any]:
    """A schema-valid give_store_credit input for ``cents``."""
    return {"customer_id": customer_id, "amount_cents": cents,
            "reason": reason, "idempotency_key": "lab4-local-check"}


def credit(caller: Caller, cents: int, want: str, customer_id: str = PROBE_CUSTOMER,
           reason: str = "Lab 4 policy check") -> Request:
    unit = "cent" if cents == 1 else "cents"
    return Request(f"{caller.label}, {dollars(cents)} ({cents} {unit})", caller,
                   "give_store_credit", credit_input(cents, customer_id, reason), want)


# The four rows the guide predicts, then four that catch a hardcoded amount, a
# lower bound, or a hardcoded person, customer or reason.
MATRIX: Tuple[Request, ...] = (
    credit(SHOPPER, 10000, DENY),
    credit(NADIA, 9999, ALLOW),
    credit(NADIA, 10000, ALLOW),
    credit(NADIA, 10001, DENY),
)
MORE: Tuple[Request, ...] = (
    credit(NADIA, 1, ALLOW, "CUST-ANNA", "Late delivery"),
    credit(NADIA, 5000, ALLOW, "CUST-THEO", "Chipped on arrival"),
    credit(OTHER_STAFF, 10000, ALLOW, "CUST-MARCO", "Wrong size sent"),
    credit(OTHER_STAFF, 10001, DENY, "CUST-MARCO", "Wrong size sent"),
)
# Tools the rule does not govern. A rule that reaches them is wrong however it
# treats credits: widened to every action, it would deny every shopper tool, and
# a permit slipped in beside it would let a shopper read another's orders.
READS: Tuple[Request, ...] = (
    Request("A shopper (Jessica) reads the return policy", SHOPPER, "get_return_policy", {},
            ALLOW),
    Request("A shopper (Jessica) reads her own orders", SHOPPER, "get_orders",
            {"customer_id": "CUST-JESSICA"}, ALLOW),
    Request("Nadia checks stock", NADIA, "check_stock", {"product_query": "Wabi-Sabi Bowl"},
            ALLOW),
    Request("A shopper (Jessica) reads Theo's orders", SHOPPER, "get_orders",
            {"customer_id": "CUST-THEO"}, DENY),
)
REQUESTS: Tuple[Request, ...] = MATRIX + MORE + READS

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
    ("one customer only",
     "context.input has amount_cents && context.input.amount_cents <= 10000 && "
     'context.input.customer_id == "CUST-JESSICA"'),
    ("a lower bound, >= 5000",
     "context.input has amount_cents && context.input.amount_cents >= 5000 && "
     "context.input.amount_cents <= 10000"),
)
# The one wrong rule that changes the head: your unless block over every action.
WIDENED = "your unless block over every action, not only give_store_credit"
_CREDIT_ACTION_CLAUSE = f'action == AgentCore::Action::"{GIVE_STORE_CREDIT_ACTION}"'


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


def policy_count(rule: str) -> Optional[int]:
    """How many policies Cedar parses from ``rule``; ``None`` when it does not parse."""
    import cedarpy

    try:
        parsed = json.loads(cedarpy.policies_to_json_str(rule))
    except Exception:  # noqa: BLE001 - the matrix reports a rule Cedar rejects
        return None
    return len(parsed.get("staticPolicies") or {}) + len(parsed.get("templates") or {})


def same_rule(left: str, right: str) -> bool:
    """Whether two statements are the same Cedar, comments and spacing aside."""
    return " ".join(cedar_code(left).split()) == " ".join(cedar_code(right).split())


def _policy_text(policies: Sequence[Tuple[str, str]]) -> str:
    return "\n".join(f'@id("{name}")\n{statement}' for name, statement in policies)


def policy_head(text: str) -> Optional[str]:
    """Everything before the final ``unless`` block, comments and spacing aside.

    ``None`` when the policy has no final ``unless`` block.
    """
    try:
        head, _tail = _split_unless(text)
    except ValueError:
        return None
    return " ".join(head.split())


def widen_action(rule: str) -> str:
    """``rule`` with its action scope removed, so the forbid covers every action."""
    head, tail = _split_unless(rule)
    return head.replace(_CREDIT_ACTION_CLAUSE, "action") + tail


def mutants(rule: str) -> List[Tuple[str, str]]:
    """The wrong rules, each built from yours: five unless blocks and one widened head."""
    built = [(label, with_unless(rule, body)) for label, body in MUTATIONS]
    return built + [(WIDENED, widen_action(rule))]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@dataclass
class Decision:
    decision: str
    decided_by: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def decide(policies: Sequence[Tuple[str, str]], schema: Dict[str, Any], caller: Caller,
           action: str, tool_input: Dict[str, Any],
           gateway_arn: str = LOCAL_GATEWAY_ARN) -> Decision:
    """One Cedar authorization of ``caller`` calling ``action`` with ``tool_input``."""
    import cedarpy

    request = {
        "principal": {"type": "AgentCore::OAuthUser", "id": caller.principal_id},
        "action": {"type": "AgentCore::Action", "id": action},
        "resource": {"type": "AgentCore::Gateway", "id": gateway_arn},
        "context": {"input": dict(tool_input)},
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
    rows: List[Tuple[Request, Decision]]

    @property
    def wrong(self) -> List[Tuple[Request, Decision]]:
        return [row for row in self.rows if row[1].decision != row[0].want or row[1].errors]

    @property
    def passed(self) -> bool:
        return not self.errors and not self.wrong

    def decision_for(self, caller: Caller, cents: int) -> Optional[Decision]:
        """The decision on ``caller``'s credit of ``cents``, if the matrix has one."""
        return next((d for r, d in self.rows if r.caller is caller and r.cents == cents), None)


def assess(rule: Optional[str], schema: Dict[str, Any],
           baseline: Sequence[Tuple[str, str]]) -> Assessment:
    """The matrix for the baseline plus ``rule`` (``None`` leaves the rule out)."""
    policies = list(baseline) + ([(CREDIT_LIMIT_POLICY, rule)] if rule is not None else [])
    errors = validation_errors(policies, schema)
    if errors:
        return Assessment(errors, [])
    rows = [(request, decide(policies, schema, request.caller, request.action,
                             request.tool_input))
            for request in REQUESTS]
    return Assessment([], rows)


@dataclass
class LocalResult:
    finding: check.Finding
    table: List[List[str]]


def _first_wrong(assessment: Assessment) -> str:
    if assessment.errors:
        return "Cedar rejects it: " + assessment.errors[0][:120]
    request, got = assessment.wrong[0]
    return f"{request.label} reads {got.decision}, expected {request.want}"


def _next_step(assessment: Assessment) -> str:
    if assessment.errors:
        return "fix the syntax or the attribute name: Cedar must accept the rule before it decides."
    wrong = assessment.wrong
    if any(request.tool != "give_store_credit" for request, _d in wrong):
        return ("your rule reaches tools it does not govern: keep the action "
                "give_store_credit and edit only the unless block.")
    missed = {(request.caller.label, request.cents) for request, _d in wrong}
    if ("Nadia", PROBE_CENTS) in missed or ("Another staff member", PROBE_CENTS) in missed:
        return ("your rule lets an over-limit credit through: true, staff-only, or the wrong unit "
                "lets 10001 cents pass.")
    if ("Nadia", LIMIT_CENTS) in missed and ("Nadia", 9999) not in missed:
        return "your comparison excludes the limit: 10000 cents must pass."
    return "your rule denies an in-limit credit: compare amount_cents, in cents, with 10000."


def _cell(assessment: Assessment, index: int) -> str:
    if assessment.errors:
        return "error"
    decision = assessment.rows[index][1]
    return decision.decision + (" (error)" if decision.errors else "")


def _table(alone: Assessment, starter: Assessment, yours: Assessment) -> List[List[str]]:
    rows = []
    for i, request in enumerate(REQUESTS):
        matches = (not yours.errors and yours.rows[i][1].decision == request.want
                   and not yours.rows[i][1].errors)
        rows.append([request.label, _cell(alone, i), _cell(starter, i), _cell(yours, i),
                     request.want, "matches" if matches else "differs"])
    return rows


def _decided(decision: Optional[Decision]) -> str:
    if decision is None:
        return "not evaluated"
    by = ", ".join(decision.decided_by) or "no policy (default deny)"
    return f"{decision.decision}, decided by {by}"


_LOCAL_TITLE = "your rule limits one credit to $100"
_LOCAL_EXPECTED = ("Cedar accepts the rule, the file holds one policy and the lines before its "
                   "unless block are the starter's; shopper $100 DENY, Nadia 1, 9999 and 10000 "
                   "cents ALLOW, 10001 DENY, the same for a second staff member and other "
                   "customers; a shopper's return policy and own orders, and a staff stock "
                   "check, stay ALLOW, and another customer's orders stay DENY; the eight "
                   "wrong rules are caught; without your rule Nadia's 10001 cents is allowed")


def _local_evidence(rule_text: str, *, rule: str, head_kept: bool, policies: Optional[int],
                    yours: Assessment,
                    caught: Sequence[Tuple[str, Assessment]], alone: Assessment,
                    baseline: Sequence[Tuple[str, str]], tools: int) -> List[str]:
    digest = hashlib.sha256(rule.encode("utf-8")).hexdigest()
    evidence = [
        f"{CREDIT_LIMIT_SOURCE} sha256:{digest[:16]}, unless {{ {unless_body(rule_text)} }}",
        "policy head: " + ("the starter's, unchanged" if head_kept
                           else "differs from the starter's (principal, action or resource)"),
        "policies in the file: " + (str(policies) if policies is not None
                                    else "Cedar cannot parse it"),
        f"evaluated with Cedar beside {len(baseline)} baseline policies "
        f"({', '.join(name for name, _ in baseline)}) and the Gateway schema for "
        f"{tools} published tools",
    ]
    if not yours.errors:
        evidence.append(f"Nadia at {PROBE_CENTS} cents: "
                        f"{_decided(yours.decision_for(NADIA, PROBE_CENTS))}")
    evidence += [f"wrong rule {label}: {'caught' if not m.passed else 'NOT caught'}, "
                 f"{_first_wrong(m) if not m.passed else 'the matrix passed it'}"
                 for label, m in caught]
    alone_over = alone.decision_for(NADIA, PROBE_CENTS)
    evidence.append("without your rule, Nadia at 10001 cents: "
                    + (_decided(alone_over) if alone_over and alone_over.decided_by
                       else alone_over.decision if alone_over else "not evaluated"))
    return evidence


def _local_state(*, unchanged: bool, head_kept: bool, extra_policies: bool, yours: Assessment,
                 escaped: List[str], counterfactual_holds: bool) -> Tuple[str, str]:
    """The verdict and the next step, in the order the check reads them."""
    if unchanged:
        return check.NOT_YET, "edit the final unless block, then run this again."
    if not head_kept:
        return check.CONTRADICTED, ("edit only the final unless block: the lines before it (the "
                                    "principal, the give_store_credit action and the Gateway) "
                                    "stay as the starter wrote them.")
    if extra_policies:
        return check.CONTRADICTED, ("keep one policy in the file, the forbid: anything after its "
                                    "unless block would deploy beside your rule.")
    if yours.passed and not escaped and counterfactual_holds:
        return check.PROVED, ""
    if escaped or not counterfactual_holds:
        return check.UNCHECKED, ("the check itself is not sound here: a wrong rule passed or the "
                                 "baseline alone denies 10001 cents. Report it; do not change "
                                 "your rule for it.")
    return check.CONTRADICTED, _next_step(yours)


def _no_unless_block(rule_text: str) -> LocalResult:
    finding = check.Finding("4A", _LOCAL_TITLE, check.CONTRADICTED, _LOCAL_EXPECTED,
                            "the policy has no final unless block",
                            [f"{CREDIT_LIMIT_SOURCE} sha256:"
                             f"{hashlib.sha256(rule_text.encode('utf-8')).hexdigest()[:16]}"],
                            "restore the starter with cp workshop/starters/"
                            "workshop_credit_limit.cedar policies/workshop_credit_limit.cedar, "
                            "then edit only its final unless block.")
    return LocalResult(finding, [])


def local_check(rule_text: str, starter_text: str) -> LocalResult:
    """Part 1: the head, one policy, the matrix, the eight wrong rules and the counterfactual."""
    if policy_head(rule_text) is None:
        return _no_unless_block(rule_text)
    schema, baseline = gateway_cedar_schema(), baseline_set()
    rule = render_rule(rule_text)
    yours = assess(rule, schema, baseline)
    alone = assess(None, schema, baseline)
    caught = [(label, assess(mutant, schema, baseline)) for label, mutant in mutants(rule)]
    escaped = [label for label, mutant in caught if mutant.passed]
    head_kept = policy_head(rule_text) == policy_head(starter_text)
    policies = policy_count(rule)
    extra_policies = policies is not None and policies != 1
    table = _table(alone, assess(render_rule(starter_text), schema, baseline), yours)
    over_limit_alone = alone.decision_for(NADIA, PROBE_CENTS)
    counterfactual_holds = over_limit_alone is not None and over_limit_alone.decision == ALLOW

    observed = (f"{sum(1 for row in table if row[-1] == 'matches')} of {len(table)} decisions "
                f"match; {len(caught) - len(escaped)} of {len(caught)} wrong rules caught; "
                "without your rule Nadia's 10001 cents is "
                f"{over_limit_alone.decision if over_limit_alone else 'not evaluated'}")
    if yours.errors:
        observed = f"Cedar rejects your rule: {yours.errors[0][:160]}"
    if extra_policies:
        observed = f"your file holds {policies} policies, not one; {observed}"
    if not head_kept:
        observed = f"your edit changes the lines before the unless block; {observed}"
    state, next_step = _local_state(
        unchanged=rule_text == starter_text, head_kept=head_kept,
        extra_policies=extra_policies, yours=yours, escaped=escaped,
        counterfactual_holds=counterfactual_holds)
    evidence = _local_evidence(
        rule_text, rule=rule, head_kept=head_kept, policies=policies, yours=yours,
        caught=caught, alone=alone, baseline=baseline,
        tools=len(schema["AgentCore"]["actions"]) - 2)
    return LocalResult(check.Finding("4A", _LOCAL_TITLE, state, _LOCAL_EXPECTED, observed,
                                     evidence, next_step), table)


# ---------------------------------------------------------------------------
# Part 2: the deployed rule and one over-limit credit through the Gateway
# ---------------------------------------------------------------------------

PROBE_ROWS_SQL = """
SELECT (SELECT count(*) FROM pellier.tool_audit
         WHERE args->>'idempotency_key' = %(key)s) AS audit_rows,
       (SELECT count(*) FROM pellier.store_credits
         WHERE idempotency_key = %(key)s) AS credit_rows;
"""

# The check confirms its own probe. No person approves it, so the decision is
# recorded under the check's name, never a staff member's.
_CONFIRM_PROBE_SQL = """
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
MANAGED_EXPECTED = ("the deployed workshop_credit_limit is your file; the check's 10001-cent "
                    "credit, sent with Nadia's token, is a Cedar denial, and its key leaves 0 "
                    "tool_audit and 0 store_credits rows")


def _runner(conn: Any) -> Any:
    def run(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall()) if cur.description else []
    return run


def ensure_probe_review(conn: Any, *, staff_sub: str) -> Dict[str, Any]:
    """The isolated over-limit review, opened once and confirmed by this check.

    ``staff_sub`` is the verified subject of the token the call is sent with
    (Nadia's); it is recorded as who the request ran as. The confirmation is
    the check's own, under ``POLICY_CHECK_DECIDER``: no person approved it.
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
        cur.execute(_CONFIRM_PROBE_SQL, (POLICY_CHECK_DECIDER, POLICY_CHECK_DECIDER, review.id))
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


def _managed_finding(state: str, observed: str, evidence: List[str],
                     next_step: str = "") -> check.Finding:
    return check.Finding("4A", _MANAGED_TITLE, state, MANAGED_EXPECTED, observed, evidence,
                         next_step)


def _deployed_rule_gap(deployed: Optional[str], local_rule: str, local_proved: bool,
                       evidence: List[str]) -> Optional[check.Finding]:
    """Why no over-limit call may count yet, or ``None`` when the deployed rule is yours."""
    if deployed is None:
        return _managed_finding(check.CONTRADICTED,
                                f"{CREDIT_LIMIT_POLICY} is not on the policy engine", evidence,
                                "provisioning deploys the starter; ask for the environment to "
                                "be reprovisioned.")
    if not same_rule(deployed, local_rule):
        return _managed_finding(check.NOT_YET, "the deployed rule is not your file yet", evidence,
                                'deploy it: python3 scripts/provision_agentcore_end_to_end.py '
                                '--repo-path "$PWD" --mode participant')
    if not local_proved:
        return _managed_finding(check.NOT_YET, "your rule is deployed but did not pass Part 1",
                                evidence, "fix the rule until Part 1 passes, then deploy it again.")
    return None


def _call_outcome(payload: Dict[str, Any], rows: Dict[str, int],
                  evidence: List[str]) -> check.Finding:
    """The verdict on one over-limit call from the Gateway's answer and the rows its key left."""
    if payload.get("outcome") == "allow" or rows["credit_rows"] or rows["audit_rows"]:
        return _managed_finding(check.CONTRADICTED, "the over-limit credit got past Cedar",
                                evidence, "Part 1 and the deployed rule disagree with the Gateway; "
                                          "read the deployed statement and the enforcement mode "
                                          "(scripts/policy_mode.py).")
    if payload.get("outcome") != "deny" or not payload.get("cedar_denial"):
        return _managed_finding(check.UNCHECKED,
                                "the call failed for another reason, so it says nothing about "
                                "Cedar", evidence,
                                "a 401, a validation failure or a transport error is not a policy "
                                "decision; read the Gateway's words above.")
    # The starter denies 10001 cents too, so a DENY read while the update is
    # still propagating cannot tell the two apart on its own.
    evidence.append("the starter denies 10001 cents too, so this DENY alone cannot tell your rule "
                    "from a starter still propagating; Jessica's $100.00 credit, which only your "
                    "rule allows, is the other half (python3 scripts/workshop_evidence.py, 4A)")
    return _managed_finding(check.PROVED, "Cedar denied the over-limit credit before the tool "
                                          "ran; its key left no row", evidence)


def judge_managed(*, deployed: Optional[str], local_rule: str, local_proved: bool,
                  payload: Optional[Dict[str, Any]], rows: Optional[Dict[str, int]],
                  review: Optional[Dict[str, Any]], engine: Dict[str, Any],
                  failure: str = "") -> check.Finding:
    """Part 2's verdict from what the control plane, the Gateway and the tables said."""
    policy_id = (engine.get("policy_ids") or {}).get(CREDIT_LIMIT_POLICY, "unknown")
    evidence = [f"policy {CREDIT_LIMIT_POLICY} {policy_id}, policy set "
                f"{str(engine.get('policy_digest') or 'unread')[:23]}, read just before the call"]
    gap = _deployed_rule_gap(deployed, local_rule, local_proved, evidence)
    if gap is not None:
        return gap
    if payload is None or review is None or rows is None:
        return _managed_finding(check.UNCHECKED, "the over-limit call could not be made",
                                evidence + ([failure] if failure else []),
                                "run this again on the workshop box; the reason is above.")
    evidence += [
        f"review {review['id']} for {PROBE_CUSTOMER}, {PROBE_CENTS} cents, covers no order, "
        "opened and confirmed by the Lab 4 policy check (probe data)",
        f"idempotency key {review['idempotency_key']}",
        "Gateway diagnostic, verbatim: "
        f"{str(payload.get('error') or payload.get('result') or '')[:160]}",
        f"tool_audit rows {rows['audit_rows']}, store_credits rows {rows['credit_rows']} "
        "for that key",
    ]
    return _call_outcome(payload, rows, evidence)


def _managed_environment() -> Tuple[str, str, Dict[str, Any]]:
    """The Gateway URL and ARN, and the policy engine's state for the credit action."""
    import anyio
    from gateway_client import _load_env, _require

    _load_env()
    gateway_url = _require("AGENTCORE_GATEWAY_URL")
    gateway_arn = _require("AGENTCORE_GATEWAY_ARN")
    from services import managed_policy

    engine = anyio.run(managed_policy.engine_state_for_action, GIVE_STORE_CREDIT_ACTION)
    if engine is None:
        raise RuntimeError("AGENTCORE_POLICY_ENGINE_ID is not set")
    return gateway_url, gateway_arn, engine


def send_probe(cfg: Dict[str, str], gateway_url: str,
               engine: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, int]]:
    """Open the over-limit review, send its credit with Nadia's token, store the answer.

    Returns the review, the classified Gateway answer and the rows its key left.
    """
    import anyio
    from gateway_client import _token_from_cognito, _verified_identity
    from gateway_policy_probe import _call_tool, classify_call

    token = _token_from_cognito("nadia")
    identity = _verified_identity(token)
    with check.connect(cfg) as conn:
        review = ensure_probe_review(conn, staff_sub=identity["verified_subject"])
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
    return review, payload, rows


def managed_check(
    local: LocalResult, rule_text: str, cfg: Optional[Dict[str, str]],
) -> check.Finding:
    """Part 2 on the workshop box; UNCHECKED where no Gateway is provisioned."""
    try:
        gateway_url, gateway_arn, engine = _managed_environment()
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - reported as UNCHECKED
        return _managed_finding(check.UNCHECKED, "the managed environment is not configured here",
                                [f"{type(exc).__name__}: {str(exc)[:160]}"],
                                "run this on the workshop box, where the Gateway is provisioned.")
    common: Dict[str, Any] = {
        "deployed": (engine.get("statements") or {}).get(CREDIT_LIMIT_POLICY),
        "local_rule": render_rule(rule_text, gateway_arn),
        "local_proved": local.finding.state == check.PROVED, "engine": engine,
    }
    if common["deployed"] is None or not same_rule(common["deployed"], common["local_rule"]) \
            or not common["local_proved"]:
        return judge_managed(payload=None, rows=None, review=None, **common)
    if cfg is None:
        return judge_managed(payload=None, rows=None, review=None,
                             failure=check.missing_settings_reason(), **common)
    try:
        review, payload, rows = send_probe(cfg, gateway_url, engine)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - the reason is the finding
        return judge_managed(payload=None, rows=None, review=None,
                             failure=f"{type(exc).__name__}: {str(exc)[:160]}", **common)
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
    if local.table:
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
