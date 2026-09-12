"""What a FRESH workshop provision would publish and authorize.

The audit gap this closes
-------------------------

Nothing asserted the fresh renderer's output, so it drifted a long way from the
validated live contract without a single test going red:

  * 18 policies instead of 3;
  * a `permit_<tool>` per read tool instead of one exact allow-list;
  * the actor/customer OWNERSHIP condition pre-installed on `initiate_return` — which is
    the Lab 4 challenge, so a fresh stack shipped the participant's answer and step 3's
    DENY fired before they wrote anything;
  * `get_ticket_history` published while it is deferred, or `issue_credit` reachable by a shopper.

These tests parse the GENERATED Cedar. They do not re-implement a second policy model,
and they never assert a count alone: a count passes while the names are wrong.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
from typing import Dict, List, Set

import pytest

sys.path.insert(0, os.path.abspath("../../scripts/deploy"))

from gateway_tool_schemas import (  # noqa: E402
    TOOL_SCHEMAS,
    WORKSHOP_DEFERRED_TOOLS,
    canonical_tool_names,
    schema_for,
    workshop_published_tools,
    workshop_target_tools,
)
from render_agentcore_project import baseline_policies  # noqa: E402

EXPERIENCE = "pellier-concierge-experience-target"
RETURN_ACTION = f"{EXPERIENCE}___initiate_return"
RECOMMENDATION = "pellier-curation-recommendation-target"
CUSTOMER_READ_POLICIES = {
    "get_customer_preferences_owner_only": (
        f"{RECOMMENDATION}___get_customer_preferences"
    ),
    "get_audit_trail_owner_only": f"{RECOMMENDATION}___get_audit_trail",
}
# A syntactically valid ARN; policies render only after the Gateway exists.
GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/test-gw"
CUSTOMER_CLAIM = "custom:customer_id"
STAFF_CLAIM = "custom:staff_scope"

# The exact 14 this workshop iteration publishes. Written out ONCE, here, so a change to
# the derived contract has to be acknowledged in a test rather than absorbed silently.
EXPECTED_PUBLISHED: Set[str] = {
    "search_products", "search_products_hybrid", "browse_category", "check_inventory",
    "get_low_stock",
    "get_price_analysis", "compare_products",
    "get_customer_preferences", "get_audit_trail", "get_trending_products",
    "get_return_policy", "get_related_products",
    "initiate_return", "escalate_to_human",
    "issue_credit", "replace_damaged_item",
}

EXPECTED_TARGETS: Dict[str, Set[str]] = {
    "pellier-discovery-search-target": {
        "search_products", "search_products_hybrid", "browse_category",
        "check_inventory", "get_low_stock",
    },
    "pellier-value-pricing-target": {"get_price_analysis", "compare_products"},
    "pellier-curation-recommendation-target": {
        "get_customer_preferences", "get_audit_trail", "get_trending_products",
        "get_return_policy", "get_related_products",
    },
    "pellier-concierge-experience-target": {"initiate_return", "escalate_to_human", "issue_credit", "replace_damaged_item"},
}

RETIRED = {
    "floor_check", "running_low", "restock_shelf", "process_return", "find_pieces",
    "find_pieces_hybrid", "whats_trending", "price_intelligence", "explore_collection",
    "side_by_side", "returns_and_care", "style_match", "preference_snapshot",
    "trace_receipt", "escalate_to_stylist",
}


def _policies() -> List[dict]:
    return baseline_policies(gateway_arn=GATEWAY_ARN)


def _by_name() -> Dict[str, dict]:
    return {p["name"]: p for p in _policies()}


def _actions(statement: str) -> List[str]:
    return re.findall(r'AgentCore::Action::"([^"]+)"', statement)


def _norm(statement: str) -> str:
    return " ".join(statement.split())


# ---------------------------------------------------------------------------
# Publication: the exact set, not the count
# ---------------------------------------------------------------------------


def test_the_workshop_publishes_exactly_the_expected_fifteen() -> None:
    assert workshop_published_tools() == EXPECTED_PUBLISHED


def test_the_deferred_set_is_restock_and_the_lab_three_read() -> None:
    """`issue_credit` is published for staff; restock waits for the desk's own route."""
    assert WORKSHOP_DEFERRED_TOOLS == {"restock_inventory", "get_ticket_history"}


def test_the_published_set_is_derived_not_hand_copied() -> None:
    """Catalogue minus deferred. A second literal list would drift on the next tool."""
    assert workshop_published_tools() == canonical_tool_names() - WORKSHOP_DEFERRED_TOOLS
    assert len(canonical_tool_names()) == 18
    assert len(workshop_published_tools()) == 16


def test_every_published_name_is_unique() -> None:
    names = [t["name"] for c in TOOL_SCHEMAS.values() for t in c["tools"]]
    assert len(names) == len(set(names)), "a tool name is declared twice"


def test_target_assignment_is_exact() -> None:
    assert {k: set(v) for k, v in workshop_target_tools().items()} == EXPECTED_TARGETS


def test_no_retired_name_is_published() -> None:
    assert workshop_published_tools() & RETIRED == set()


def test_no_deferred_name_is_published() -> None:
    assert workshop_published_tools() & WORKSHOP_DEFERRED_TOOLS == set()


def test_the_experience_target_publishes_the_three_governed_actions() -> None:
    """`get_ticket_history` lives on this target and must not ship before Lab 3a."""
    served = [t["name"] for t in schema_for("experience", workshop=True)]
    assert served == ["initiate_return", "issue_credit", "escalate_to_human", "replace_damaged_item"]
    full = [t["name"] for t in schema_for("experience", workshop=False)]
    assert set(full) - set(served) == {"get_ticket_history"}


# ---------------------------------------------------------------------------
# The policy set: exact names, effects, actions, conditions
# ---------------------------------------------------------------------------


def test_the_fresh_policy_set_is_exactly_the_named_baseline_and_scoped_reads() -> None:
    """Exact set, never a count: a count passes while the names are wrong."""
    assert set(_by_name()) == {
        "baseline_permit_workshop_tools",
        *CUSTOMER_READ_POLICIES,
        "initiate_return_shopper_damaged",
        "initiate_return_staff_scope",
        "issue_credit_staff_scope",
        "replace_damaged_item_staff_scope",
    }


def test_every_policy_action_exists_in_the_published_schema() -> None:
    """A policy naming an unpublished action does not deploy at all.

    Measured against the live engine and recorded in
    `scripts/migrate_gateway_vocabulary.py`: `FAIL_ON_ANY_FINDINGS` rejects
    `unrecognized action AgentCore::Action::"..."` for any id absent from the live Gateway
    schema, and `UPDATE_FAILED` does not roll the stored definition back.

    Nothing compared policy actions against the published set until a policy was written
    naming the deferred `issue_credit`, on the reasoning that gating a deferred tool
    "closes the publication window in advance". It would have failed the whole policy on a
    fresh provision.
    """
    published = {
        f"{target}___{tool}"
        for target, tools in workshop_target_tools().items()
        for tool in tools
    }
    for policy in _policies():
        for action in _actions(policy["statement"]):
            assert action in published, (
                f"{policy['name']} names {action}, which a fresh Gateway does not "
                f"publish. Deferred tools: {sorted(WORKSHOP_DEFERRED_TOOLS)}"
            )


def test_every_conditional_policy_pins_one_action() -> None:
    """A conditional policy must use `action ==`, never `action in [...]`.

    The second measured failure. Widening the action set widens the scope the validator
    type-checks the condition against, and the condition is not valid for sibling action
    types such as `Mcp`, `CallTool` and `InvokeLLM`.

    Unconditional policies may use `action in [...]` freely: there is no condition to
    type-check, which is why the baseline allow-list names eleven at once.
    """
    for policy in _policies():
        statement = policy["statement"]
        if not (("when {" in statement) or ("unless {" in statement)):
            continue
        assert "action in [" not in statement, (
            f"{policy['name']} is conditional and uses `action in [...]`; pin it to a "
            "single `action ==` id or split it into one policy per action"
        )
        assert len(_actions(statement)) == 1, (
            f"{policy['name']} is conditional and names "
            f"{len(_actions(statement))} actions"
        )


def test_staff_authority_is_a_scope_claim_never_a_group_name() -> None:
    """Staff authority is positively verified, and it is not a Cognito group literal.

    The pre-token trigger stamps `custom:staff_scope` from operator group membership,
    so the policy reads a string claim the engine is proven to expose as a tag. A
    policy reading `cognito:groups` directly would depend on an array-claim tag
    representation nobody validated, and naming the group in Cedar would couple
    the policy to pool administration.
    """
    from services.auth import OPERATOR_GROUP

    staff = _norm(_by_name()["initiate_return_staff_scope"]["statement"])
    assert staff.startswith("permit (principal is AgentCore::OAuthUser,")
    assert f'principal.hasTag("{STAFF_CLAIM}")' in staff
    assert f'principal.getTag("{STAFF_CLAIM}") == "returns"' in staff
    assert "reason" not in staff, "a resolved dispute is not a damaged-goods return"
    for policy in _policies():
        assert OPERATOR_GROUP not in policy["statement"], policy["name"]
        assert "cognito:groups" not in policy["statement"], policy["name"]


def test_the_two_authority_boundaries_are_recorded_where_they_are_enforced() -> None:
    """Operator authority is enforced twice, and each place says so."""
    renderer = pathlib.Path(
        os.path.abspath("../../scripts/deploy/render_agentcore_project.py")
    ).read_text(encoding="utf-8")
    assert "initiate_return_staff_scope" in renderer
    assert "authorizes a person, not a service" in renderer

    auth = pathlib.Path(
        os.path.abspath("../../pellier/backend/services/auth.py")
    ).read_text(encoding="utf-8")
    assert "custom:staff_scope" in auth


def test_issue_credit_is_published_for_staff_and_unreachable_by_a_shopper() -> None:
    """Published, so the operator desk can execute an approved credit through the
    Gateway with the operator's own token; permitted only under the staff scope
    claim; named by no shopper permit, so a shopper token is denied by default.
    """
    assert "issue_credit" not in WORKSHOP_DEFERRED_TOOLS
    published = {
        tool for tools in workshop_target_tools().values() for tool in tools
    }
    assert "issue_credit" in published
    naming = [p for p in _policies() if f"{EXPERIENCE}___issue_credit" in _actions(p["statement"])]
    assert [p["name"] for p in naming] == ["issue_credit_staff_scope"]
    statement = naming[0]["statement"]
    assert statement.lstrip().startswith("permit")
    assert 'principal.getTag("custom:staff_scope") == "returns"' in statement
    assert "custom:customer_id" not in statement


def test_every_policy_is_active_and_validated_strictly() -> None:
    for policy in _policies():
        assert policy["enforcementMode"] == "ACTIVE", policy["name"]
        assert policy["validationMode"] == "FAIL_ON_ANY_FINDINGS", policy["name"]


def test_the_baseline_is_an_exact_allow_list_not_a_wildcard() -> None:
    """A wildcard hands every future published tool a permit the moment it appears."""
    statement = _by_name()["baseline_permit_workshop_tools"]["statement"]
    assert "action in [" in statement
    assert not re.search(r"permit\s*\(\s*principal,\s*action\s*,", _norm(statement))
    # And no target Action Group, whose membership compiles at policy-save time.
    assert 'action in AgentCore::Action::"pellier-' not in statement


def test_the_baseline_permits_exactly_the_eleven_catalogue_reads() -> None:
    """Customer-scoped reads and writes never sit in the unconditional permit."""
    expected = {
        f"{target}___{tool}"
        for target, tools in EXPECTED_TARGETS.items()
        for tool in tools
        if tool not in {
            "initiate_return", "restock_inventory", "issue_credit", "replace_damaged_item",
            "get_customer_preferences", "get_audit_trail",
        }
    }
    actual = set(_actions(_by_name()["baseline_permit_workshop_tools"]["statement"]))
    assert actual == expected
    assert len(actual) == 11
    assert not any("issue_credit" in action for action in actual), (
        "the unconditional catalogue permit must never reach the staff-only credit"
    )


def test_the_baseline_is_unconditional() -> None:
    statement = _by_name()["baseline_permit_workshop_tools"]["statement"]
    assert "when {" not in statement
    assert "unless {" not in statement


def test_the_return_permits_name_the_canonical_action_only() -> None:
    for name in ("initiate_return_shopper_damaged", "initiate_return_staff_scope"):
        actions = _actions(_by_name()[name]["statement"])
        assert actions == [RETURN_ACTION], name
        assert "process_return" not in _by_name()[name]["statement"], name


def test_the_shopper_return_permit_requires_a_customer_claim_and_damaged() -> None:
    """A token with no customer claim cannot file a return, whatever the reason.

    The ownership binding is deliberately absent here; that is Lab 4.
    """
    permit = _norm(_by_name()["initiate_return_shopper_damaged"]["statement"])
    assert permit.startswith("permit (principal is AgentCore::OAuthUser,")
    assert f'principal.hasTag("{CUSTOMER_CLAIM}")' in permit
    assert 'context.input has reason && context.input.reason == "damaged"' in permit


def test_there_is_no_forbid_in_the_fresh_baseline() -> None:
    """Forbid wins over permit, so a baseline forbid could silently block staff.

    Every restriction is expressed as a condition on a permit; the only forbid in
    the workshop is the one the participant writes in Lab 4, scoped by `when` to
    principals carrying a customer claim.
    """
    for policy in _policies():
        assert not _norm(policy["statement"]).startswith("forbid"), policy["name"]


def test_sensitive_gateway_reads_are_permitted_only_to_the_claimed_customer() -> None:
    """Direct Gateway invocation must not turn a customer_id into authority."""
    for name, action in CUSTOMER_READ_POLICIES.items():
        statement = _norm(_by_name()[name]["statement"])
        assert statement.startswith("permit (principal is AgentCore::OAuthUser,"), name
        assert f'AgentCore::Action::"{action}"' in statement, name
        assert f'principal.hasTag("{CUSTOMER_CLAIM}")' in statement, name
        assert "context.input has customer_id" in statement, name
        assert (
            f'principal.getTag("{CUSTOMER_CLAIM}") == context.input.customer_id'
            in statement
        ), name
        assert "username" not in statement, name
        assert "CUST-" not in statement, name


def test_every_policy_is_typed_and_pinned_to_the_gateway_arn() -> None:
    """Untyped `hasTag` rules fail validation; `resource is` fails for pinned actions.

    Both were rejected by the live analyzer on 2026-09-09: an IAM principal has no
    tags, so an untyped conditional rule reads as denying every request, and a
    tool-specific policy must constrain the resource to one Gateway ARN.
    """
    for policy in _policies():
        statement = _norm(policy["statement"])
        assert "principal is AgentCore::OAuthUser" in statement, policy["name"]
        assert f'resource == AgentCore::Gateway::"{GATEWAY_ARN}"' in statement, policy["name"]
        assert "resource is AgentCore::Gateway" not in statement, policy["name"]


def test_policies_cannot_render_without_the_gateway_arn() -> None:
    with pytest.raises(SystemExit, match="Gateway ARN"):
        baseline_policies(gateway_arn="")


def test_an_authenticated_stranger_may_only_read_the_catalogue() -> None:
    """A token with neither claim matches exactly one permit."""
    unconditional = [
        policy["name"]
        for policy in _policies()
        if "hasTag(" not in policy["statement"]
    ]
    assert unconditional == ["baseline_permit_workshop_tools"]


# ---------------------------------------------------------------------------
# The Lab 4 challenge must NOT be pre-installed
# ---------------------------------------------------------------------------


def test_no_fresh_policy_contains_the_lab_four_ownership_condition() -> None:
    """The load-bearing assertion of this file.

    Binding the customer claim to `context.input.customer_id` on the return action is
    the Lab 4 exercise. A baseline that already contains it makes the exercise semantically false:
    the cross-customer DENY the participant is meant to create already happens.

    The assertion is the BINDING, not the mere presence of a tag read. It used to be
    "`getTag` appears nowhere", which was a proxy that broke the moment the baseline needed
    a legitimate, unrelated tag check: the operator-group forbid reads
    `cognito:groups`, which has nothing to do with the participant's exercise. A proxy that
    forbids a whole Cedar feature blocks correct policies as readily as incorrect ones.
    """
    for policy in _policies():
        statement = policy["statement"]
        name = policy["name"]
        if RETURN_ACTION not in _actions(statement):
            continue
        assert f'getTag("{CUSTOMER_CLAIM}")' not in statement, name
        assert 'getTag("username")' not in statement, name
        assert "context.input.customer_id" not in statement, name
        assert "context.input has customer_id" not in statement, name


def test_no_fresh_policy_names_a_persona_customer() -> None:
    for policy in _policies():
        if RETURN_ACTION not in _actions(policy["statement"]):
            continue
        for persona in (
            "CUST-MARCO",
            "CUST-ANNA",
            "CUST-THEO",
            "CUST-JESSICA",
            '"marco"',
            '"anna"',
            '"theo"',
            '"jessica"',
        ):
            assert persona not in policy["statement"], f"{policy['name']} / {persona}"


def test_the_renderer_documents_the_omission_as_deliberate() -> None:
    """So a later 'hardening' pass cannot re-add the challenge as an oversight."""
    doc = baseline_policies.__doc__ or ""
    assert "absent on purpose" in doc
    assert "Lab 4" in doc
    assert "teaching baseline" in doc


# ---------------------------------------------------------------------------
# Evaluated authorization outcomes
# ---------------------------------------------------------------------------


SHOPPER = {CUSTOMER_CLAIM: "CUST-MARCO"}
STAFF = {STAFF_CLAIM: "returns"}
STRANGER: Dict[str, str] = {}


def _conditions_hold(body: str, claims: Dict[str, str], inp: Dict[str, str]) -> bool:
    """Whether one `when`/`unless` body holds for this principal and input.

    A deliberately small model of the conditions the baseline and the Lab 4 rule
    actually use: the `false` literal, claim presence, claim-to-input equality, a
    literal scope, input presence, and the reason. Anything a policy starts using
    that this does not model must be added here, so a new condition cannot pass
    by being ignored.
    """
    body = " ".join(body.split())
    if not body:
        return True
    if body == "false":
        return False
    if f'principal.hasTag("{CUSTOMER_CLAIM}")' in body and CUSTOMER_CLAIM not in claims:
        return False
    if f'principal.hasTag("{STAFF_CLAIM}")' in body and STAFF_CLAIM not in claims:
        return False
    if "context.input has customer_id" in body and "customer_id" not in inp:
        return False
    if f'principal.getTag("{CUSTOMER_CLAIM}") == context.input.customer_id' in body:
        if claims.get(CUSTOMER_CLAIM) != inp.get("customer_id"):
            return False
    scope = re.search(rf'principal\.getTag\("{STAFF_CLAIM}"\) == "([a-z_-]+)"', body)
    if scope and claims.get(STAFF_CLAIM) != scope.group(1):
        return False
    if 'context.input.reason == "damaged"' in body and inp.get("reason") != "damaged":
        return False
    return True


def _statement_applies(statement: str, claims: Dict[str, str], inp: Dict[str, str]) -> bool:
    """A permit or forbid applies when its `when` holds and its `unless` does not."""
    when = re.search(r"when\s*\{(.*?)\}", statement, re.DOTALL)
    unless = re.search(r"unless\s*\{(.*?)\}", statement, re.DOTALL)
    if not _conditions_hold(when.group(1) if when else "", claims, inp):
        return False
    if unless and _conditions_hold(unless.group(1), claims, inp):
        return False
    return True


def _decide(
    action: str,
    inp: Dict[str, str] | None = None,
    *,
    claims: Dict[str, str] = SHOPPER,
    extra: List[str] | None = None,
) -> str:
    """Evaluate the generated statements. Cedar is default-deny and forbid wins."""
    inp = inp or {}
    permits, forbids = [], []
    statements = [(p["name"], p["statement"]) for p in _policies()]
    statements += [(f"extra-{i}", text) for i, text in enumerate(extra or [])]
    for name, statement in statements:
        if action not in _actions(statement):
            continue
        if not _statement_applies(statement, claims, inp):
            continue
        effect = " ".join(
            line for line in statement.splitlines() if not line.strip().startswith("//")
        ).lstrip()
        (forbids if effect.startswith("forbid") else permits).append(name)
    if forbids:
        return "DENY"
    return "ALLOW" if permits else "DENY"


RETURN_DAMAGED = {"customer_id": "CUST-THEO", "reason": "damaged"}


@pytest.mark.parametrize(("who", "action", "inp", "expected"), [
    ("shopper", RETURN_ACTION, RETURN_DAMAGED, "ALLOW"),
    ("shopper", RETURN_ACTION, {"customer_id": "CUST-THEO", "reason": "not_as_described"}, "DENY"),
    ("shopper", RETURN_ACTION, {"customer_id": "CUST-THEO", "reason": "changed_mind"}, "DENY"),
    ("shopper", RETURN_ACTION, {"customer_id": "CUST-THEO"}, "DENY"),
    ("staff", RETURN_ACTION, {"customer_id": "CUST-THEO", "reason": "changed_mind"}, "ALLOW"),
    ("staff", RETURN_ACTION, RETURN_DAMAGED, "ALLOW"),
    ("stranger", RETURN_ACTION, RETURN_DAMAGED, "DENY"),
    ("shopper", "pellier-discovery-search-target___restock_inventory", {}, "DENY"),
    ("staff", "pellier-discovery-search-target___restock_inventory", {}, "DENY"),
    ("stranger", "pellier-discovery-search-target___check_inventory", {}, "ALLOW"),
    ("shopper", f"{EXPERIENCE}___escalate_to_human", {}, "ALLOW"),
    ("shopper", f"{RECOMMENDATION}___get_customer_preferences", {"customer_id": "CUST-MARCO"}, "ALLOW"),
    ("shopper", f"{RECOMMENDATION}___get_customer_preferences", {"customer_id": "CUST-THEO"}, "DENY"),
    ("staff", f"{RECOMMENDATION}___get_customer_preferences", {"customer_id": "CUST-MARCO"}, "DENY"),
    ("stranger", f"{RECOMMENDATION}___get_audit_trail", {"customer_id": "CUST-MARCO"}, "DENY"),
    ("shopper", f"{EXPERIENCE}___issue_credit", {}, "DENY"),
    ("staff", f"{EXPERIENCE}___issue_credit", {}, "ALLOW"),
    ("stranger", f"{EXPERIENCE}___issue_credit", {}, "DENY"),
    ("shopper", f"{EXPERIENCE}___get_ticket_history", {"customer_id": "CUST-MARCO"}, "DENY"),
    ("shopper", f"{EXPERIENCE}___some_future_tool", {}, "DENY"),
])
def test_the_fresh_authorization_matrix(who: str, action: str, inp, expected: str) -> None:
    claims = {"shopper": SHOPPER, "staff": STAFF, "stranger": STRANGER}[who]
    assert _decide(action, inp, claims=claims) == expected


def test_restock_inventory_is_off_the_shopper_gateway_and_has_no_permit() -> None:
    """Restock is an operator capability. Not published, so no action id; and no
    permit names it either, so a future publication is still denied by default.
    """
    action = "pellier-discovery-search-target___restock_inventory"
    matching = [
        p["name"] for p in _policies()
        if action in _actions(p["statement"])
        and not p["statement"].lstrip().startswith("forbid")
    ]
    assert matching == []
    assert "restock_inventory" not in workshop_published_tools()
    assert "restock_inventory" in canonical_tool_names(), "the tool still exists for the desk"


def test_a_future_published_tool_is_denied_by_default() -> None:
    for future in ("get_ticket_history", "anything_at_all"):
        action = f"{EXPERIENCE}___{future}"
        assert _decide(action, None) == "DENY", future
        assert _decide(action, "damaged") == "DENY", future


# ---------------------------------------------------------------------------
# Lab 4: before and after the participant's own Policy work
# ---------------------------------------------------------------------------

CHALLENGE = pathlib.Path("../../policies/workshop_identity_match_forbid.cedar")
SOLUTION = pathlib.Path(
    "../../solutions/the-concierge/policies/identity_match_forbid.cedar")


def _solution_statement() -> str:
    """The participant's completed rule, comments dropped, ARN placeholder filled in."""
    lines = [
        line for line in SOLUTION.read_text().splitlines()
        if not line.strip().startswith("//")
    ]
    return "\n".join(lines).replace("${PELLIER_GATEWAY_ARN}", GATEWAY_ARN)


def test_the_challenge_file_ships_unsolved() -> None:
    """`unless { false }` denies every shopper return, the honest starting state."""
    body = CHALLENGE.read_text()
    assert re.search(r"unless\s*\{\s*false\s*\}", body)
    assert "getTag(" not in body
    assert "CUST-MARCO" not in body


def test_the_solution_file_contains_the_ownership_binding() -> None:
    body = SOLUTION.read_text()
    assert f'principal.hasTag("{CUSTOMER_CLAIM}")' in body
    assert "context.input has customer_id" in body
    assert f'principal.getTag("{CUSTOMER_CLAIM}") == context.input.customer_id' in body


def test_before_the_solution_a_cross_customer_return_is_permitted() -> None:
    """Case F. Marco's token, Theo's damaged return.

    This must ALLOW on the fresh baseline, or the participant has nothing to discover.
    """
    assert _decide(RETURN_ACTION, RETURN_DAMAGED, claims=SHOPPER) == "ALLOW"
    for policy in _policies():
        if RETURN_ACTION not in _actions(policy["statement"]):
            continue
        assert f'getTag("{CUSTOMER_CLAIM}")' not in policy["statement"]


def test_after_the_solution_the_cross_customer_return_is_denied() -> None:
    """Case G. The same call, with the participant's rule added.

    The forbid's `unless` fails for Marco's token and Theo's customer id, so Cedar
    denies, while the owner's own damaged return still passes and staff, who carry
    no customer claim, are untouched by the forbid.
    """
    rule = [_solution_statement()]
    assert _decide(RETURN_ACTION, RETURN_DAMAGED, claims=SHOPPER, extra=rule) == "DENY"
    own = {"customer_id": "CUST-MARCO", "reason": "damaged"}
    assert _decide(RETURN_ACTION, own, claims=SHOPPER, extra=rule) == "ALLOW"
    assert _decide(RETURN_ACTION, RETURN_DAMAGED, claims=STAFF, extra=rule) == "ALLOW"
    assert _decide(RETURN_ACTION, RETURN_DAMAGED, claims=STRANGER, extra=rule) == "DENY"


def test_the_solution_names_the_canonical_action() -> None:
    for path in (CHALLENGE, SOLUTION):
        body = path.read_text()
        assert "___initiate_return" in body, path.name
        assert "___process_return" not in body, path.name


# ---------------------------------------------------------------------------
# One contract, three declarations: they must reconcile
# ---------------------------------------------------------------------------


def test_the_application_catalogue_reconciles_with_the_workshop_contract() -> None:
    """The local MCP catalog and managed workshop subset have distinct roles.

    Three places name the tool set and each has a different job:

        agent_tools.py @tool          what the process can execute (17)
        LOCAL_MCP_TOOL_NAMES          local in-process / MCP catalog (17)
        workshop_published_tools()    what a fresh workshop provision publishes (15, 16 after Lab 3a)

    Asserted as a DERIVED relationship rather than a fourth literal list, so adding a
    tool has to be classified once and cannot drift here.
    """
    import os as _os
    import sys as _sys

    backend = _os.path.abspath(".")
    if backend not in _sys.path:
        _sys.path.insert(0, backend)
    from services.agentcore_gateway import LOCAL_MCP_TOOL_NAMES, GATEWAY_ONLY_OPERATOR_TOOLS

    catalogue = set(LOCAL_MCP_TOOL_NAMES) | GATEWAY_ONLY_OPERATOR_TOOLS
    assert catalogue == canonical_tool_names(), (
        "the application catalogue and the Gateway schemas disagree: "
        f"{sorted(catalogue ^ canonical_tool_names())}"
    )
    assert catalogue - WORKSHOP_DEFERRED_TOOLS == workshop_published_tools()
    assert len(LOCAL_MCP_TOOL_NAMES) == len(set(LOCAL_MCP_TOOL_NAMES)), "a name is listed twice"

def test_the_handoff_contract_names_every_baseline_policy() -> None:
    """The doc that tells a facilitator what ships must not drift from what ships.

    ``docs/HANDOFF-SOURCE-CONTRACT.md`` listed three policies while the renderer
    defined five; the two ``*_identity_scope`` guards were missing, which is
    exactly the pair that decides whether the managed customer-read boundary is
    attributed to Cedar or blanket-credited to Row-Level Security. A prose table
    nobody checks is a claim, not a contract.
    """
    handoff = (
        pathlib.Path(__file__).resolve().parents[3]
        / "docs"
        / "HANDOFF-SOURCE-CONTRACT.md"
    )
    text = handoff.read_text(encoding="utf-8")
    rendered = set(_by_name())

    section = text.split("## Baseline authorization on a fresh stack", 1)[1]
    section = section.split("\n## ", 1)[0]

    for name in rendered:
        assert f"`{name}`" in section, (
            f"{name} is rendered onto a fresh stack but absent from the handoff "
            "contract's baseline table"
        )
    documented = set(re.findall(r"^\| `([a-z0-9_]+)` \|", section, re.M))
    assert documented == rendered, (
        f"handoff table and renderer disagree: "
        f"only in doc {documented - rendered}, only in code {rendered - documented}"
    )
    assert f"{len(rendered)} policies" in section.lower() or (
        "five policies" in section.lower() and len(rendered) == 5
    ), "the table's stated count must match the number of rendered policies"
