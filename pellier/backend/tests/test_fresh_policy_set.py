"""What a FRESH workshop provision would publish and authorize.

Nothing asserted the fresh renderer's output once, so it drifted a long way from the
validated live contract without a single test going red. These tests parse the GENERATED
Cedar. They do not re-implement a second policy model, and they never assert a count
alone: a count passes while the names are wrong.

The contract: nine tools on one Gateway target, `pellier-store-tools`. The starter defers
`get_tickets` until Lab 3A, so eight are published first and nine after. The Lab 4 rule
(an amount limit on `give_store_credit`) is the participant's, never the baseline's.
"""

from __future__ import annotations

import importlib
import os
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Set

import pytest

sys.path.insert(0, os.path.abspath("../../scripts/deploy"))
sys.path.insert(0, os.path.abspath("../../scripts"))

from gateway_tool_schemas import (  # noqa: E402
    TOOL_SCHEMAS,
    WORKSHOP_DEFERRED_TOOLS,
    canonical_tool_names,
    schema_for,
    workshop_published_tools,
    workshop_target_tools,
)
from render_agentcore_project import baseline_policies  # noqa: E402

lab4 = importlib.import_module("lab4_policy_check")

STORE = "pellier-store-tools"
CREDIT_ACTION = f"{STORE}___give_store_credit"
CUSTOMER_READ_POLICIES = {
    "get_orders_owner_only": f"{STORE}___get_orders",
    "get_tickets_owner_only": f"{STORE}___get_tickets",
}
# A syntactically valid ARN; policies render only after the Gateway exists.
GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/test-gw"
CUSTOMER_CLAIM = "custom:customer_id"
STAFF_CLAIM = "custom:staff_scope"

# The nine tools, and the eight this workshop iteration publishes first. Written out ONCE,
# here, so a change to the derived contract has to be acknowledged in a test rather than
# absorbed silently.
EXPECTED_CANONICAL: Set[str] = {
    "search_products", "browse_department", "compare_products", "check_stock",
    "get_orders", "get_return_policy", "get_tickets", "give_store_credit", "ask_a_person",
}
EXPECTED_PUBLISHED: Set[str] = EXPECTED_CANONICAL - {"get_tickets"}
SHOPPER_SAFE: Set[str] = {
    "search_products", "browse_department", "compare_products", "check_stock",
    "get_return_policy", "ask_a_person",
}

EXPECTED_TARGETS: Dict[str, Set[str]] = {STORE: EXPECTED_PUBLISHED}

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


def test_the_workshop_publishes_exactly_the_expected_eight() -> None:
    assert workshop_published_tools() == EXPECTED_PUBLISHED


def test_the_deferred_set_is_the_lab_three_read() -> None:
    """`give_store_credit` is published for staff; `get_tickets` waits for Task 3A."""
    assert WORKSHOP_DEFERRED_TOOLS == {"get_tickets"}


def test_the_published_set_is_derived_not_hand_copied() -> None:
    """Catalogue minus deferred. A second literal list would drift on the next tool."""
    assert workshop_published_tools() == canonical_tool_names() - WORKSHOP_DEFERRED_TOOLS
    assert canonical_tool_names() == EXPECTED_CANONICAL
    assert len(canonical_tool_names()) == 9
    assert len(workshop_published_tools()) == 8


def test_every_published_name_is_unique() -> None:
    names = [t["name"] for c in TOOL_SCHEMAS.values() for t in c["tools"]]
    assert len(names) == len(set(names)), "a tool name is declared twice"


def test_target_assignment_is_exact() -> None:
    assert {k: set(v) for k, v in workshop_target_tools().items()} == EXPECTED_TARGETS


def test_no_retired_name_is_published() -> None:
    assert workshop_published_tools() & RETIRED == set()


def test_no_deferred_name_is_published() -> None:
    assert workshop_published_tools() & WORKSHOP_DEFERRED_TOOLS == set()


def test_the_store_target_publishes_eight_and_the_full_catalogue_nine() -> None:
    """`get_tickets` lives on this target and must not ship before Lab 3A."""
    served = [t["name"] for t in schema_for("store", workshop=True)]
    assert set(served) == EXPECTED_PUBLISHED
    full = [t["name"] for t in schema_for("store", workshop=False)]
    assert set(full) - set(served) == {"get_tickets"}
    assert len(full) == 9


def test_there_is_exactly_one_gateway_target() -> None:
    assert list(TOOL_SCHEMAS) == ["store"]
    assert TOOL_SCHEMAS["store"]["target_name"] == STORE


# ---------------------------------------------------------------------------
# The policy set: exact names, effects, actions, conditions
# ---------------------------------------------------------------------------


def test_the_fresh_policy_set_is_exactly_the_named_baseline_and_scoped_reads() -> None:
    """Exact set, never a count: a count passes while the names are wrong."""
    assert set(_by_name()) == {
        "baseline_permit_workshop_tools",
        "get_orders_owner_only",
        "give_store_credit_staff_scope",
    }


def _policies_after_lab_three(monkeypatch) -> Dict[str, dict]:
    """The baseline once Task 3A has published `get_tickets` as well."""
    import render_agentcore_project

    monkeypatch.setattr(
        render_agentcore_project,
        "workshop_target_tools",
        lambda: {STORE: tuple(t["name"] for t in TOOL_SCHEMAS["store"]["tools"])},
    )
    return {p["name"]: p for p in baseline_policies(gateway_arn=GATEWAY_ARN)}


def test_publishing_get_tickets_adds_its_owner_only_permit(monkeypatch) -> None:
    """Task 3A publishes `get_tickets`; its owner-only permit lands in the same deploy."""
    assert set(_policies_after_lab_three(monkeypatch)) == {
        "baseline_permit_workshop_tools",
        *CUSTOMER_READ_POLICIES,
        "give_store_credit_staff_scope",
    }


def test_every_policy_action_exists_in_the_published_schema() -> None:
    """A policy naming an unpublished action does not deploy at all.

    Measured against the live engine and recorded in
    the renderer's policy notes: `FAIL_ON_ANY_FINDINGS` rejects
    `unrecognized action AgentCore::Action::"..."` for any id absent from the live Gateway
    schema, and `UPDATE_FAILED` does not roll the stored definition back.

    A policy naming a deferred tool would fail the whole policy on a fresh provision.
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
    type-check, which is why the baseline allow-list names six at once.
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

    staff = _norm(_by_name()["give_store_credit_staff_scope"]["statement"])
    assert staff.startswith("permit (principal is AgentCore::OAuthUser,")
    assert f'principal.hasTag("{STAFF_CLAIM}")' in staff
    assert f'principal.getTag("{STAFF_CLAIM}") == "returns"' in staff
    for policy in _policies():
        assert OPERATOR_GROUP not in policy["statement"], policy["name"]
        assert "cognito:groups" not in policy["statement"], policy["name"]


def test_the_two_authority_boundaries_are_recorded_where_they_are_enforced() -> None:
    """Operator authority is enforced twice, and each place says so."""
    renderer = pathlib.Path(
        os.path.abspath("../../scripts/deploy/render_agentcore_project.py")
    ).read_text(encoding="utf-8")
    assert "give_store_credit_staff_scope" in renderer
    assert "authorizes a person, not a service" in renderer

    auth = pathlib.Path(
        os.path.abspath("../../pellier/backend/services/auth.py")
    ).read_text(encoding="utf-8")
    assert "custom:staff_scope" in auth


def test_give_store_credit_is_published_for_staff_and_unreachable_by_a_shopper() -> None:
    """Published, so the operator desk can execute an approved credit through the
    Gateway with the operator's own token; permitted only under the staff scope
    claim; named by no shopper permit, so a shopper token is denied by default.
    The staff permit carries no amount condition: the amount limit is Lab 4's forbid.
    """
    assert "give_store_credit" not in WORKSHOP_DEFERRED_TOOLS
    published = {
        tool for tools in workshop_target_tools().values() for tool in tools
    }
    assert "give_store_credit" in published
    naming = [p for p in _policies() if CREDIT_ACTION in _actions(p["statement"])]
    assert [p["name"] for p in naming] == ["give_store_credit_staff_scope"]
    statement = naming[0]["statement"]
    assert statement.lstrip().startswith("permit")
    assert 'principal.getTag("custom:staff_scope") == "returns"' in statement
    assert "custom:customer_id" not in statement
    assert "amount_cents" not in statement


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


def test_the_baseline_permits_exactly_the_six_shopper_safe_reads() -> None:
    """Customer-scoped reads and the credit never sit in the unconditional permit."""
    expected = {f"{STORE}___{tool}" for tool in SHOPPER_SAFE}
    actual = set(_actions(_by_name()["baseline_permit_workshop_tools"]["statement"]))
    assert actual == expected
    assert len(actual) == 6
    assert not any("give_store_credit" in action for action in actual), (
        "the unconditional catalogue permit must never reach the staff-only credit"
    )
    assert not any(
        tool in action for action in actual for tool in ("get_orders", "get_tickets")
    )


def test_the_baseline_is_unconditional() -> None:
    statement = _by_name()["baseline_permit_workshop_tools"]["statement"]
    assert "when {" not in statement
    assert "unless {" not in statement


def test_there_is_no_forbid_in_the_fresh_baseline() -> None:
    """Forbid wins over permit, so a baseline forbid could silently block staff.

    Every restriction is expressed as a condition on a permit; the only forbid in
    the workshop is the one the participant writes in Lab 4, the amount limit on
    `give_store_credit`.
    """
    for policy in _policies():
        assert not _norm(policy["statement"]).startswith("forbid"), policy["name"]


def test_sensitive_gateway_reads_are_permitted_only_to_the_claimed_customer(monkeypatch) -> None:
    """Direct Gateway invocation must not turn a customer_id into authority."""
    policies = _policies_after_lab_three(monkeypatch)
    for name, action in CUSTOMER_READ_POLICIES.items():
        statement = _norm(policies[name]["statement"])
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


def test_no_fresh_policy_contains_the_lab_four_amount_rule() -> None:
    """The load-bearing assertion of this file.

    The amount limit on `give_store_credit` is the Lab 4 exercise. A baseline that
    already contains it makes the exercise semantically false: the over-limit DENY the
    participant is meant to create already happens, and a broken participant policy
    would be masked.
    """
    for policy in _policies():
        statement = policy["statement"]
        assert "amount_cents" not in statement, policy["name"]
        assert "context.input has amount_cents" not in statement, policy["name"]
        assert not _norm(statement).startswith("forbid"), policy["name"]


def test_no_fresh_policy_names_a_persona_customer() -> None:
    for policy in _policies():
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
    assert "NO amount condition on purpose" in doc
    assert "Lab 4" in doc
    assert "teaching baseline" in doc


# ---------------------------------------------------------------------------
# Evaluated authorization outcomes
# ---------------------------------------------------------------------------


SHOPPER = {CUSTOMER_CLAIM: "CUST-MARCO"}
STAFF = {STAFF_CLAIM: "returns"}
STRANGER: Dict[str, str] = {}
SCHEMA = lab4.gateway_cedar_schema()


def _credit(cents: int) -> Dict[str, object]:
    """A schema-valid `give_store_credit` input for Marco's account."""
    return {"customer_id": "CUST-MARCO", "amount_cents": cents,
            "reason": "fresh policy test", "idempotency_key": "fresh-policy-test"}


def _schema_for(action: str, inp: Dict[str, object]) -> Optional[Dict[str, Any]]:
    """The Gateway's Cedar schema when the request is well formed, else none.

    A request on a published action with every required input is validated
    against the schema, so its DENY is Cedar's decision on a request the Gateway
    could send. An undeclared action (deferred `get_tickets`, a future tool) or an
    input missing a required attribute would only fail schema validation, which
    proves nothing about the policies; those are evaluated without a schema, so
    what decides is Cedar's default deny or the policy's own `has` guard.
    """
    declared = SCHEMA["AgentCore"]["actions"].get(action)
    if declared is None:
        return None
    attributes = declared["appliesTo"]["context"]["attributes"]["input"]["attributes"]
    missing = [name for name, spec in attributes.items() if spec["required"] and name not in inp]
    return None if missing else SCHEMA


def _decide(
    action: str,
    inp: Dict[str, object] | None = None,
    *,
    claims: Dict[str, str] = SHOPPER,
    extra: List[str] | None = None,
) -> str:
    """Authorize one call with the Cedar engine, through the Lab 4 checker's `decide`.

    The policy set is the generated baseline plus any `extra` statements. Cedar
    is default-deny and forbid wins. A diagnostic error fails the test, so a
    malformed request can never pass as a DENY.
    """
    inp = dict(inp or {})
    policies = [(p["name"], p["statement"]) for p in _policies()]
    policies += [(f"extra-{i}", text) for i, text in enumerate(extra or [])]
    caller = lab4.Caller("test principal", "test-principal", dict(claims))
    decision = lab4.decide(policies, _schema_for(action, inp), caller, action, inp,
                           gateway_arn=GATEWAY_ARN)
    assert not decision.errors, decision.errors
    return decision.decision


@pytest.mark.parametrize(("who", "action", "inp", "expected"), [
    ("stranger", f"{STORE}___check_stock", {"product_query": "linen shirt"}, "ALLOW"),
    ("shopper", f"{STORE}___search_products", {"query": "linen"}, "ALLOW"),
    ("shopper", f"{STORE}___ask_a_person", {"reason": "a person, please"}, "ALLOW"),
    ("shopper", f"{STORE}___get_orders", {"customer_id": "CUST-MARCO"}, "ALLOW"),
    ("shopper", f"{STORE}___get_orders", {"customer_id": "CUST-THEO"}, "DENY"),
    ("shopper", f"{STORE}___get_orders", {}, "DENY"),
    ("staff", f"{STORE}___get_orders", {"customer_id": "CUST-MARCO"}, "DENY"),
    ("stranger", f"{STORE}___get_orders", {"customer_id": "CUST-MARCO"}, "DENY"),
    ("shopper", f"{STORE}___get_tickets", {"customer_id": "CUST-MARCO"}, "DENY"),
    ("shopper", CREDIT_ACTION, _credit(500), "DENY"),
    ("staff", CREDIT_ACTION, _credit(500), "ALLOW"),
    ("staff", CREDIT_ACTION, _credit(50000), "ALLOW"),
    ("stranger", CREDIT_ACTION, _credit(500), "DENY"),
    ("shopper", f"{STORE}___some_future_tool", {}, "DENY"),
])
def test_the_fresh_authorization_matrix(who: str, action: str, inp, expected: str) -> None:
    claims = {"shopper": SHOPPER, "staff": STAFF, "stranger": STRANGER}[who]
    assert _decide(action, inp, claims=claims) == expected


def test_a_future_published_tool_is_denied_by_default() -> None:
    for future in ("get_tickets", "anything_at_all"):
        action = f"{STORE}___{future}"
        assert _decide(action, None) == "DENY", future
        assert _decide(action, {"customer_id": "CUST-MARCO"}) == "DENY", future


# ---------------------------------------------------------------------------
# Lab 4: before and after the participant's own Policy work
# ---------------------------------------------------------------------------

CHALLENGE = pathlib.Path("../../policies/workshop_credit_limit.cedar")
STARTER = pathlib.Path("../../workshop/starters/workshop_credit_limit.cedar")
SOLUTION = pathlib.Path(
    "../../solutions/the-concierge/policies/workshop_credit_limit.cedar")
OVER_LIMIT = _credit(25000)
WITHIN_LIMIT = _credit(10000)


def _solution_statement() -> str:
    """The reference rule, comments dropped, ARN placeholder filled in."""
    lines = [
        line for line in SOLUTION.read_text().splitlines()
        if not line.strip().startswith("//")
    ]
    return "\n".join(lines).replace("${PELLIER_GATEWAY_ARN}", GATEWAY_ARN)


def test_the_challenge_file_ships_unsolved() -> None:
    """`unless { false }` denies every credit, staff included: the honest starting state."""
    body = CHALLENGE.read_text()
    assert re.search(r"unless\s*\{\s*false\s*\}", body)
    assert "getTag(" not in body
    assert "CUST-MARCO" not in body
    assert "amount_cents <=" not in body


def test_the_live_challenge_file_is_byte_identical_to_the_starter() -> None:
    assert CHALLENGE.read_bytes() == STARTER.read_bytes()


def test_the_solution_file_contains_the_amount_limit() -> None:
    body = SOLUTION.read_text()
    assert "context.input has amount_cents" in body
    assert "context.input.amount_cents <= 10000" in body
    assert "principal.getTag(" not in body, "the reference is an amount rule, not an identity match"


def test_before_the_solution_an_over_limit_credit_is_permitted() -> None:
    """The baseline staff permit has no amount condition, so $250 is ALLOWed until the
    participant writes the forbid; otherwise they would have nothing to discover.
    """
    assert _decide(CREDIT_ACTION, OVER_LIMIT, claims=STAFF) == "ALLOW"


def test_the_starter_forbid_blocks_every_credit() -> None:
    """`unless { false }` never admits a credit, so the unsolved rule denies staff."""
    rule = [CHALLENGE.read_text().replace("${PELLIER_GATEWAY_ARN}", GATEWAY_ARN)]
    assert _decide(CREDIT_ACTION, WITHIN_LIMIT, claims=STAFF, extra=rule) == "DENY"


def test_after_the_solution_the_over_limit_credit_is_denied() -> None:
    """The reference forbid's `unless` fails above $100, so Cedar denies the $250 credit,
    while a credit within the limit still passes the staff permit.
    """
    rule = [_solution_statement()]
    assert _decide(CREDIT_ACTION, OVER_LIMIT, claims=STAFF, extra=rule) == "DENY"
    assert _decide(CREDIT_ACTION, WITHIN_LIMIT, claims=STAFF, extra=rule) == "ALLOW"
    assert _decide(CREDIT_ACTION, {"customer_id": "CUST-MARCO"}, claims=STAFF, extra=rule) == "DENY"
    assert _decide(CREDIT_ACTION, WITHIN_LIMIT, claims=SHOPPER, extra=rule) == "DENY"


def test_the_participant_files_name_the_canonical_action() -> None:
    for path in (CHALLENGE, SOLUTION):
        body = path.read_text()
        assert f'"{CREDIT_ACTION}"' in body, path.name


# ---------------------------------------------------------------------------
# One contract, three declarations: they must reconcile
# ---------------------------------------------------------------------------


def test_the_application_catalogue_reconciles_with_the_workshop_contract() -> None:
    """The application's tier map and the Gateway schemas name the same nine tools.

    Three places name the tool set and each has a different job:

        agent_tools.py @tool          what the process can execute
        GATEWAY_TOOL_TIERS            the application's view of the Gateway catalogue
        workshop_published_tools()    what a fresh workshop provision publishes (8, 9 after Lab 3A)

    Asserted as a DERIVED relationship rather than a fourth literal list, so adding a
    tool has to be classified once and cannot drift here.
    """
    import os as _os
    import sys as _sys

    backend = _os.path.abspath(".")
    if backend not in _sys.path:
        _sys.path.insert(0, backend)
    from services.agentcore_gateway import GATEWAY_TARGET, GATEWAY_TOOL_TIERS

    catalogue = set(GATEWAY_TOOL_TIERS)
    assert catalogue == canonical_tool_names(), (
        "the application catalogue and the Gateway schemas disagree: "
        f"{sorted(catalogue ^ canonical_tool_names())}"
    )
    assert catalogue - WORKSHOP_DEFERRED_TOOLS == workshop_published_tools()
    assert GATEWAY_TARGET == STORE


def test_the_readiness_map_names_every_baseline_policy() -> None:
    """The doc that tells a maintainer what ships must not drift from what ships.

    A prose table nobody checks is a claim, not a contract. The renderer produces
    three policies on the starter (four after Lab 3A publishes `get_tickets`).
    """
    readiness = (
        pathlib.Path(__file__).resolve().parents[3]
        / "docs"
        / "AGENTCORE-READINESS.md"
    )
    text = readiness.read_text(encoding="utf-8")
    rendered = set(_by_name())

    section = text.split("## Baseline authorization on a fresh stack", 1)[1]
    section = section.split("\n## ", 1)[0]

    for name in rendered:
        assert f"`{name}`" in section, (
            f"{name} is rendered onto a fresh stack but absent from the readiness "
            "map's baseline table"
        )
    documented = set(re.findall(r"^\| `([a-z0-9_]+)` \|", section, re.M))
    assert documented == rendered, (
        f"readiness table and renderer disagree: "
        f"only in doc {documented - rendered}, only in code {rendered - documented}"
    )
    assert f"{len(rendered)} policies" in section.lower()
