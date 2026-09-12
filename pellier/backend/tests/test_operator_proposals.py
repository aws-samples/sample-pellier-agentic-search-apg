"""Governed proposals: preparing is not authorizing, and confirming is not executing.

The assertions that matter here are all refusals. That a recommendation does not open
a review. That an exploratory question acquires no side effect. That the browser
cannot name the customer and the model cannot name the product. That a reason is
refused rather than guessed, because a human is bound to it. And that no path from
this surface reaches a governed write.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

import pytest

from services import operator_proposals as PROP
from services import operator_review as RV


def _code_only(target: Any) -> str:
    """Source with comment lines dropped. Works for a module or a function.

    Scanning raw source made three of these tests trip on their own prose: the module
    explains that `ALLOWED_REASONS` mirrors `BusinessLogic.initiate_return`'s
    allow-list, the replacement stage says "a model proposed it", and the investigate
    stage names "Review prepared" in a comment above the guard that emits it. A
    substring match read all three as code.
    """
    lines = []
    for line in inspect.getsource(target).splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        lines.append(line.split("  # ")[0])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Intent: the operator asks, the model does not
# ---------------------------------------------------------------------------

def test_explicit_consequential_intent_is_required() -> None:
    prepares = (
        "Prepare the damaged-item return for review.",
        "Set up a return for this damaged item.",
        "Help me initiate the return.",
        "Start a return for the damaged bottle.",
        "Log the return for review.",
    )
    recommends_only = (
        "What should we do?",
        "Investigate what happened.",
        "Summarize the options.",
        "Find a replacement.",
        "Is a return appropriate here?",
        "A return may be the right outcome.",
    )
    for request in prepares:
        assert PROP.classify_action_intent(request) is not None, request
    for request in recommends_only:
        assert PROP.classify_action_intent(request) is None, request


def test_a_model_recommendation_cannot_open_a_review() -> None:
    """Intent is read from the operator's words, and nothing else reaches the classifier."""
    signature = inspect.signature(PROP.classify_action_intent)
    assert list(signature.parameters) == ["request"], (
        "the intent classifier accepts something other than the operator's request"
    )
    # The most emphatic possible model recommendation, as an operator question.
    assert PROP.classify_action_intent(
        "The evidence strongly supports initiating a return immediately. Do you agree?"
    ) is None


def test_the_intent_classifier_is_deterministic_not_a_model_call() -> None:
    source = _code_only(PROP.classify_action_intent)
    for forbidden in ("bedrock", "converse", "invoke_model", "synthesize"):
        assert forbidden not in source.lower()


# ---------------------------------------------------------------------------
# Reason: normalised, never inferred
# ---------------------------------------------------------------------------

def test_a_canonical_reason_the_operator_typed_wins() -> None:
    for canonical in PROP.ALLOWED_REASONS:
        assert PROP.normalize_reason(f"prepare the {canonical} return") == canonical


def test_operator_phrasing_maps_to_a_canonical_reason() -> None:
    assert PROP.normalize_reason("the bottle arrived under-filled") == "not_as_described"
    assert PROP.normalize_reason("it does not fit") == "wrong_size"
    assert PROP.normalize_reason("she changed her mind") == "changed_mind"
    assert PROP.normalize_reason("the vase is broken") == "damaged"


def test_every_mapped_reason_is_one_the_write_path_accepts() -> None:
    """A reason outside the allow-list would prepare an action that can never run."""
    from services.business_logic import BusinessLogic

    allowed_in_write = inspect.getsource(BusinessLogic.initiate_return)
    for canonical in PROP.ALLOWED_REASONS:
        assert f'"{canonical}"' in allowed_in_write, canonical
    for _phrase, canonical in PROP._REASON_PHRASES:
        assert canonical in PROP.ALLOWED_REASONS, canonical


def test_an_unstated_reason_is_not_guessed() -> None:
    assert PROP.normalize_reason("prepare the return for review") == ""
    assert PROP.normalize_reason("") == ""


# ---------------------------------------------------------------------------
# Capability gating
# ---------------------------------------------------------------------------

def test_a_deliberately_unpublished_capability_gets_no_review() -> None:
    assert PROP.capability_blocks_proposal(
        {"state": "not_enabled", "reason": "capability_not_published"}
    ) is True


def test_a_closed_rail_still_allows_a_review() -> None:
    """A review is workflow state. A published capability with a closed rail is
    exactly the case where preparing a decision is legitimate."""
    assert PROP.capability_blocks_proposal(
        {"state": "temporarily_unavailable", "reason": "governed_action_unavailable"}
    ) is False


def test_an_unreadable_capability_is_not_treated_as_absence() -> None:
    """A control plane that could not answer is not evidence a capability is gone."""
    assert PROP.capability_blocks_proposal(None) is False
    assert PROP.capability_blocks_proposal({"state": "capability_state_unverified"}) is False


def test_execution_affordance_fails_closed() -> None:
    for capability, executable in (
        ({"state": "available"}, True),
        ({"state": "temporarily_unavailable"}, False),
        ({"state": "not_enabled"}, False),
        ({"state": "capability_state_unverified"}, False),
        (None, False),
    ):
        assert PROP._execution_capability(capability)["executable"] is executable


def test_review_required_is_a_known_gate_not_an_unknown_capability() -> None:
    capability = {"state": "review_required", "reason": "human_review_required"}
    assert PROP._execution_capability(capability)["executable"] is False
    assert PROP.describe_execution(capability) == (
        "Human confirmation is required before requesting governed execution."
    )


# ---------------------------------------------------------------------------
# Material arguments: Aurora establishes every business reference
# ---------------------------------------------------------------------------

def _order_row(order_id: int, product_id: str, name: str, price: float) -> Dict[str, Any]:
    return {
        "order_id": order_id, "product_id": product_id, "name": name,
        "category": "Beauty", "price": price, "quantity": 1, "brand": "Pellier Parfum",
        "color": "", "description": f"{name} description", "tags": [],
        "img_url": f"/products/{product_id}.png", "placed_at": None,
    }


class FakeDb:
    """Mappings, not tuples: the pool configures `dict_row`."""

    def __init__(self, *, orders: Optional[List[Dict[str, Any]]] = None,
                 review_turn: str = "", review_id: Optional[int] = 99) -> None:
        self.orders = orders if orders is not None else []
        self.review_turn = review_turn
        self.review_id = review_id
        self.statements: List[str] = []

    def get_connection(self):
        return _Conn(self)

    async def fetch_one(self, sql: str, *params: Any) -> Optional[Dict[str, Any]]:
        flat = " ".join(sql.split())
        self.statements.append(flat)
        if "source_turn_id FROM pellier.approvals" in flat:
            return {"source_turn_id": self.review_turn}
        raise AssertionError(f"unexpected fetch_one: {flat[:80]}")


class _Cur:
    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self._rows: List[Dict[str, Any]] = []

    async def execute(self, sql: str, params: Any = ()) -> None:
        flat = " ".join(sql.split())
        self.db.statements.append(flat)
        if "FROM pellier.orders" in flat:
            self._rows = list(self.db.orders)
        else:  # pragma: no cover
            raise AssertionError(f"unexpected SQL: {flat[:80]}")

    async def fetchall(self):
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Conn:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    def cursor(self):
        return _Cur(self.db)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


VETIVER = _order_row(325, "47", "Vetiver Quietude", 186.0)
ROSE = _order_row(344, "56", "Rose Absolute Body Oil", 118.0)

OPEN_RAIL = {"state": "temporarily_unavailable", "reason": "governed_action_unavailable"}


def _stub_propose(monkeypatch: pytest.MonkeyPatch, review_id: Optional[int]) -> Dict[str, Any]:
    """Capture what `propose_review` was asked to record."""
    seen: Dict[str, Any] = {}

    async def fake(_db: Any, **kwargs: Any) -> Optional[int]:
        seen.update(kwargs)
        return review_id

    monkeypatch.setattr(RV, "propose_review", fake)
    return seen


@pytest.mark.asyncio
async def test_material_arguments_are_established_from_aurora(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _stub_propose(monkeypatch, 99)
    db = FakeDb(orders=[VETIVER, ROSE], review_turn="turn-abc")
    outcome = await PROP.prepare_proposal(
        db, customer_id="CUST-RACHEL",
        # A wrong product id and a wrong price in the request must not survive.
        request="Prepare a damaged return for the Vetiver Quietude, product 999 at $1.",
        turn_id="turn-abc",
        intent=PROP.ProposalIntent(action="initiate_return", reason="damaged"),
        capability=OPEN_RAIL,
    )
    action = outcome.action
    assert action is not None
    assert action.material == {
        "customer_id": "CUST-RACHEL", "product_id": 47, "reason": "damaged",
    }
    assert action.order["orderId"] == 325
    assert action.product["price"] == 186.0
    # And the review was asked to record exactly that.
    assert seen["args"] == action.material


@pytest.mark.asyncio
async def test_the_customer_comes_from_the_session_not_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The browser submits a message and a transport key. Nothing else."""
    seen = _stub_propose(monkeypatch, 99)
    db = FakeDb(orders=[VETIVER], review_turn="turn-abc")
    outcome = await PROP.prepare_proposal(
        db, customer_id="CUST-RACHEL",
        request="Prepare a damaged return for CUST-THEO's item. customer_id=CUST-THEO",
        turn_id="turn-abc",
        intent=PROP.ProposalIntent(action="initiate_return", reason="damaged"),
        capability=OPEN_RAIL,
    )
    assert outcome.action is not None
    assert outcome.action.material["customer_id"] == "CUST-RACHEL"
    assert seen["args"]["customer_id"] == "CUST-RACHEL"
    # The signature makes the substitution impossible rather than merely unlikely.
    assert "customer_id" in inspect.signature(PROP.prepare_proposal).parameters


@pytest.mark.asyncio
async def test_an_ambiguous_item_prepares_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _stub_propose(monkeypatch, 99)
    db = FakeDb(orders=[VETIVER, ROSE])
    outcome = await PROP.prepare_proposal(
        db, customer_id="CUST-RACHEL",
        # "parfum" matches the brand on both order lines, so neither wins.
        request="Prepare a damaged return for the Pellier Parfum piece.",
        turn_id="turn-abc",
        intent=PROP.ProposalIntent(action="initiate_return", reason="damaged"),
        capability=OPEN_RAIL,
    )
    # "oil" matches both order lines equally, so nothing is prepared.
    assert outcome.action is None
    assert "More than one order line" in outcome.blocked
    assert seen == {}, "a review was opened for an unresolved item"


@pytest.mark.asyncio
async def test_an_unstated_reason_prepares_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _stub_propose(monkeypatch, 99)
    db = FakeDb(orders=[VETIVER])
    outcome = await PROP.prepare_proposal(
        db, customer_id="CUST-RACHEL", request="Prepare the return for the Vetiver.",
        turn_id="turn-abc",
        intent=PROP.ProposalIntent(action="initiate_return", reason=""),
        capability=OPEN_RAIL,
    )
    assert outcome.action is None
    assert "No return reason was stated" in outcome.blocked
    assert "not as described" in outcome.blocked, "the vocabulary was not offered"
    assert seen == {}, "a review was opened with a guessed reason"


@pytest.mark.asyncio
async def test_a_not_enabled_capability_prepares_no_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _stub_propose(monkeypatch, 99)
    db = FakeDb(orders=[VETIVER])
    outcome = await PROP.prepare_proposal(
        db, customer_id="CUST-RACHEL",
        request="Prepare a damaged return for the Vetiver.", turn_id="turn-abc",
        intent=PROP.ProposalIntent(action="initiate_return", reason="damaged"),
        capability={"state": "not_enabled", "reason": "capability_not_published"},
    )
    assert outcome.action is not None
    assert outcome.action.state == PROP.STATE_NOT_ENABLED
    assert outcome.action.review_id is None
    assert outcome.action.action_hash == "", "a fingerprint was published with no review"
    assert seen == {}, "a review was opened for an unpublished capability"


@pytest.mark.asyncio
async def test_a_failed_review_does_not_discard_the_investigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No fake reviewId, and the established action still reaches the operator."""
    _stub_propose(monkeypatch, None)
    db = FakeDb(orders=[VETIVER])
    outcome = await PROP.prepare_proposal(
        db, customer_id="CUST-RACHEL",
        request="Prepare a damaged return for the Vetiver.", turn_id="turn-abc",
        intent=PROP.ProposalIntent(action="initiate_return", reason="damaged"),
        capability=OPEN_RAIL,
    )
    assert outcome.action is not None
    assert outcome.action.state == PROP.STATE_COULD_NOT_PREPARE
    assert outcome.action.review_id is None
    assert outcome.blocked == "", "a review failure discarded the investigation"


@pytest.mark.asyncio
async def test_an_already_open_review_is_reported_not_claimed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migration 020's partial unique index resolved this to another turn's review.

    That row's lineage belongs to the turn that opened it, so this turn reports the
    resolution instead of asserting authorship it does not have.
    """
    _stub_propose(monkeypatch, 36)
    db = FakeDb(orders=[VETIVER], review_turn="turn-the-first-one")
    outcome = await PROP.prepare_proposal(
        db, customer_id="CUST-RACHEL",
        request="Prepare a damaged return for the Vetiver.", turn_id="turn-a-later-one",
        intent=PROP.ProposalIntent(action="initiate_return", reason="damaged"),
        capability=OPEN_RAIL,
    )
    assert outcome.action is not None
    assert outcome.action.state == PROP.STATE_REVIEW_ALREADY_OPEN
    assert outcome.action.review_id == 36
    assert outcome.action.review_source_turn_id == "turn-the-first-one"


@pytest.mark.asyncio
async def test_the_turn_id_travels_unchanged_into_the_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One correlation family: session -> turn -> review -> execution -> evidence."""
    seen = _stub_propose(monkeypatch, 99)
    db = FakeDb(orders=[VETIVER], review_turn="turn-exact")
    await PROP.prepare_proposal(
        db, customer_id="CUST-RACHEL",
        request="Prepare a damaged return for the Vetiver.", turn_id="turn-exact",
        intent=PROP.ProposalIntent(action="initiate_return", reason="damaged"),
        capability=OPEN_RAIL,
    )
    assert seen["source_turn_id"] == "turn-exact", "the turn id was transformed"


# ---------------------------------------------------------------------------
# The fingerprint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_action_hash_is_the_canonical_write_path_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One hash format. A Concierge-specific one could never be compared to a write."""
    from services.business_logic import write_request_hash

    _stub_propose(monkeypatch, 99)
    db = FakeDb(orders=[VETIVER], review_turn="turn-abc")
    outcome = await PROP.prepare_proposal(
        db, customer_id="CUST-RACHEL",
        request="Prepare a damaged return for the Vetiver.", turn_id="turn-abc",
        intent=PROP.ProposalIntent(action="initiate_return", reason="damaged"),
        capability=OPEN_RAIL,
    )
    assert outcome.action is not None
    assert outcome.action.action_hash == write_request_hash(
        "initiate_return", customer_id="CUST-RACHEL", product_id=47, reason="damaged",
    )
    # And the same value the review substrate would compute.
    assert outcome.action.action_hash == RV.action_fingerprint(
        "initiate_return", outcome.action.material
    )


def test_the_displayed_material_is_exactly_what_the_fingerprint_covers() -> None:
    """A field shown but unfingerprinted could change under an approved review."""
    assert set(RV.MATERIAL_PARAMETERS["initiate_return"]) == {
        "customer_id", "product_id", "reason",
    }


@pytest.mark.asyncio
async def test_changed_material_produces_a_different_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which is what makes a stale confirmation refuse with `parameters_changed`."""
    _stub_propose(monkeypatch, 99)
    hashes = set()
    for reason in ("damaged", "not_as_described"):
        db = FakeDb(orders=[VETIVER], review_turn="turn-abc")
        outcome = await PROP.prepare_proposal(
            db, customer_id="CUST-RACHEL",
            request="Prepare the return for the Vetiver.", turn_id="turn-abc",
            intent=PROP.ProposalIntent(action="initiate_return", reason=reason),
            capability=OPEN_RAIL,
        )
        hashes.add(outcome.action.action_hash)
    assert len(hashes) == 2, "two different mutations share one fingerprint"


# ---------------------------------------------------------------------------
# No execution path
# ---------------------------------------------------------------------------

def test_proposals_reach_only_the_review_substrate() -> None:
    code = _code_only(PROP)
    for forbidden in (
        "BusinessLogic(", "issue_credit(", "escalate_to_human(",
        "invoke_tool", "gateway_invoke", "invoke_gateway", "execute_review",
        "managed_rail", "principal_session",
        "INSERT INTO pellier.returns", "UPDATE pellier.warehouse_inventory",
        "UPDATE pellier.product_catalog", "INSERT INTO pellier.store_credits",
    ):
        assert forbidden not in code, f"proposals reference {forbidden}"
    # The single consequential-path call, and the only write it can reach.
    assert "propose_review" in code
    assert "INSERT INTO pellier.approvals" not in code, (
        "proposals write approvals directly instead of through propose_review"
    )


def test_only_initiate_return_is_proposable_in_this_phase() -> None:
    assert PROP.PROPOSABLE_ACTIONS == ("initiate_return",)
    # `issue_credit` is reviewable in the substrate but its capability is not
    # published, so this phase never proposes it.
    assert "issue_credit" in RV.REVIEWABLE_ACTIONS
    assert "issue_credit" not in PROP.PROPOSABLE_ACTIONS


def test_a_proposal_is_not_an_outcome() -> None:
    """An episode records a resolution. Preparing a decision is not one."""
    code = _code_only(PROP)
    assert "store_episode" not in code
    assert "operator_episodes" not in code


# ---------------------------------------------------------------------------
# Only one workflow may propose
# ---------------------------------------------------------------------------

def test_only_the_investigation_workflow_may_propose() -> None:
    """An exploratory search must not acquire a side effect."""
    from services import operator_concierge as ORCH

    staged = set(ORCH._CONTEXT_STAGES)
    assert ORCH.WORKFLOW_INVESTIGATE in staged
    # The other three reach no proposal code at all.
    for read_only in (ORCH.WORKFLOW_CLIENT_SUMMARY, ORCH.WORKFLOW_DRAFT_NOTE):
        assert read_only not in staged
    # Replacement HAS a stage, but a retrieval one — it must not import proposals.
    replacement_stage = _code_only(ORCH._replacement_context)
    assert "operator_proposals" not in replacement_stage
    assert "propose_review" not in replacement_stage
    assert "prepare_proposal" not in replacement_stage


def test_a_consequential_request_routes_to_the_investigation_workflow() -> None:
    from services import operator_concierge as ORCH

    for request in (
        "Prepare the damaged-item return for review.",
        "Set up a return for this damaged item.",
        "Help me initiate the return.",
    ):
        assert ORCH.classify_workflow(request) == ORCH.WORKFLOW_INVESTIGATE, request


def test_asking_for_copy_about_a_return_is_still_a_draft() -> None:
    from services import operator_concierge as ORCH

    request = "Draft a note about preparing the return."
    assert ORCH.classify_workflow(request) == ORCH.WORKFLOW_DRAFT_NOTE
    # And a draft turn reaches no stage, so no review can be created from it.
    assert ORCH.WORKFLOW_DRAFT_NOTE not in ORCH._CONTEXT_STAGES


def test_the_capability_read_is_not_reported_as_a_policy_decision() -> None:
    """Reading which capabilities exist is not asking Policy to authorize anything.

    Listing AgentCore Policy as a participating source here would imply an
    authorization decision that has not happened.
    """
    from services import operator_concierge as ORCH

    assert ORCH.SOURCE_POLICY_PLANE == "AgentCore control plane"
    assert "Policy" not in ORCH.SOURCE_POLICY_PLANE.replace("control plane", "")
    assert "SOURCE_POLICY_PLANE" in _code_only(ORCH._investigate_context)


def test_review_prepared_is_only_emitted_when_a_review_exists() -> None:
    """No fake action progress."""
    from services import operator_concierge as ORCH

    stage = _code_only(ORCH._investigate_context)
    prepared = stage.index('"Review prepared"')
    guard = stage.index("if action.review_id is not None:")
    assert guard < prepared, "the step is emitted before the review is checked"
    assert '"No review prepared"' in stage


# ---------------------------------------------------------------------------
# Review state: no axis derives another
# ---------------------------------------------------------------------------

def test_a_pending_proposal_asserts_nothing_beyond_the_human_axis() -> None:
    from routes.operator import _assurance

    axes = _assurance("confirmation_required")
    assert axes == {
        "human": "CONFIRMATION_REQUIRED", "policy": "PENDING",
        "aurora": "NOT_EVALUATED", "evidence": "PENDING",
    }


def test_a_confirmation_does_not_become_an_authorization() -> None:
    """The showpiece state. A person said yes; nothing else has happened."""
    from routes.operator import _assurance

    axes = _assurance("confirmed")
    assert axes["human"] == "CONFIRMED"
    assert axes["policy"] == "PENDING", "a confirmation fabricated a policy ALLOW"
    assert axes["aurora"] == "NOT_EVALUATED", "a confirmation fabricated an RLS pass"
    assert axes["evidence"] == "PENDING", "a confirmation fabricated a receipt"


def test_a_decline_is_not_a_policy_deny() -> None:
    from routes.operator import _assurance

    axes = _assurance("declined")
    assert axes["human"] == "DECLINED"
    assert axes["policy"] == "NOT_EVALUATED", "a human decline was labelled a policy DENY"
    assert axes["aurora"] == "NOT_REACHED"
    assert axes["evidence"] == "NO_EXECUTION"


def test_confirming_a_review_does_not_execute_it() -> None:
    """The load-bearing separation. `decide_review` records a decision, full stop."""
    source = _code_only(RV.decide_review)
    for forbidden in ("BusinessLogic", "initiate_return(", "issue_credit(",
                      "invoke", "execute", "principal_session"):
        assert forbidden not in source, f"confirmation reaches {forbidden}"
    # It writes one row's workflow state and returns.
    assert "UPDATE pellier.approvals" in inspect.getsource(RV)


def test_a_confirmation_is_bound_to_the_parameters_it_was_shown() -> None:
    source = _code_only(RV.decide_review)
    assert "action_hash_required" in source
    assert "parameters_changed" in source
    # Constant-time comparison, same as the commerce confirmation path.
    assert "compare_digest" in source
    # And the stored args are re-fingerprinted, so a row whose hash and args disagree
    # is refused rather than trusted.
    assert "stored_parameters_invalid" in source


def test_the_concierge_supplies_its_own_recommendation() -> None:
    """The shopper-rail default states facts a Concierge proposal has not established.

    `_default_recommendation` is written for Theo's damaged return: it names a
    2500-cent courtesy credit and cites a previous damaged piece. Neither is
    established for an operator-prepared action, so the Concierge supplies its own.
    """
    theo_default = RV._default_recommendation(
        "initiate_return", {"reason": "damaged"}
    )
    assert "damaged on arrival" in theo_default["rationale"]

    item = type("Item", (), {"name": "Vetiver Quietude", "order_id": 325})()
    ours = PROP._recommendation_for(
        item, PROP.ProposalIntent(action="initiate_return", reason="not_as_described")
    )
    assert "not as described" in ours["rationale"]
    assert "damaged on arrival" not in ours["rationale"]
    # No entitlement, no invented amount, no availability claim.
    assert "secondarySuggestion" not in ours
    for invented in ("courtesy credit", "2500", "previous", "entitlement", "available"):
        assert invented not in ours["rationale"].lower()


def test_a_review_headline_cannot_name_a_reason_the_review_lacks() -> None:
    """The console mapped every `initiate_return` to "File a damaged return"."""
    import pathlib

    source = pathlib.Path(
        "../frontend/src/operator/surfaces/ReviewRecord.tsx"
    ).read_text()
    assert "initiate_return: 'File a damaged return'" not in source
    assert "function actionTitle(" in source
    assert "parameters.reason" in source


def test_absent_warehouse_rows_are_not_reported_as_zero_stock() -> None:
    """"No replacement stock is available right now" for a product with no rows at
    all states an inventory fact the database never established."""
    import pathlib

    route = pathlib.Path("routes/operator.py").read_text()
    assert '"availabilityVerified": bool(warehouses)' in route
    surface = pathlib.Path(
        "../frontend/src/operator/surfaces/ReviewRecord.tsx"
    ).read_text()
    assert "availabilityVerified === false" in surface
    assert "Replacement availability is not verified" in surface


# ---------------------------------------------------------------------------
# The shopper-rail recommendation must name the reason it actually has
# ---------------------------------------------------------------------------

def test_theos_canonical_damaged_wording_is_unchanged() -> None:
    """The one case that must read exactly as it always has."""
    rec = RV._default_recommendation("initiate_return", {"reason": "damaged"})
    assert rec["rationale"] == (
        "The client owns this piece and reported it damaged on arrival, "
        "which is a canonical return reason."
    )
    # Damage alone proves no previous incident or discretionary credit amount.
    assert "secondarySuggestion" not in rec


def test_a_non_damaged_return_never_claims_damage() -> None:
    for reason in ("wrong_size", "not_as_described", "changed_mind", "other"):
        rec = RV._default_recommendation("initiate_return", {"reason": reason})
        assert "damaged" not in rec["rationale"], reason
        assert "damage" not in rec["rationale"], reason
        # Nor does it inherit a history claim that belongs to one client.
        assert "secondarySuggestion" not in rec, reason


def test_each_canonical_reason_has_its_own_clause() -> None:
    clauses = {
        reason: RV._default_recommendation(
            "initiate_return", {"reason": reason}
        )["rationale"]
        for reason in PROP.ALLOWED_REASONS
    }
    assert len(set(clauses.values())) == len(PROP.ALLOWED_REASONS), (
        f"two reasons share a rationale: {clauses}"
    )
    assert "not as described" in clauses["not_as_described"]
    assert "size is wrong" in clauses["wrong_size"]


def test_an_absent_or_unknown_reason_gets_the_neutral_clause() -> None:
    """Stating the wrong reason is worse than stating none."""
    for args in ({}, {"reason": ""}, {"reason": "vibes"}):
        rec = RV._default_recommendation("initiate_return", args)
        assert rec["rationale"] == (
            "The client owns this piece and asked to return the piece, "
            "which is a canonical return reason."
        )
        assert "damaged" not in rec["rationale"]


def test_every_reason_the_write_path_accepts_has_a_clause() -> None:
    for reason in PROP.ALLOWED_REASONS:
        assert reason in RV._REASON_CLAUSES, reason
