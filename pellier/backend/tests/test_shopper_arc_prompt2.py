"""PROMPT 2 — the shopper arc: Marco → Anna → Theo as one journey.

Tests behaviour and instruction contracts, not prose formatting. Model output is
generated, so what is asserted here is the deterministic scaffolding that makes
the story possible: which tool runs, which fields it can read, and — for Theo —
that no privileged write can occur from the shopper conversation at all.

The Theo assertions matter most. Prompt 2's whole point is that Pellier reaches
the consequential-action boundary and stops. That must be enforced by
architecture rather than by a prompt asking the model nicely, so the tests read
the rail guard, not the wording.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "pellier" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# ---------------------------------------------------------------------------
# MARCO — GROUND. Live truth, including fulfilment timing.
# ---------------------------------------------------------------------------

def test_marco_canonical_question_asks_about_fulfilment_timing() -> None:
    """The strengthened question is two halves answered by one tool call.

    Aurora provides warehouse quantity and dispatch timing. It does not
    establish a delivery date without destination and carrier evidence.
    """
    prompt = (BACKEND / "agents" / "inventory_agent.py").read_text()
    assert "Brooklyn" in prompt and "what ship window is recorded?" in prompt
    assert "check_inventory(product_query='Hadley Linen Shirt')" in prompt
    assert "A dispatch window does not establish an arrival date" in prompt
    assert "time-to-doorstep" not in prompt and "day arrival" not in prompt


def test_marco_tool_reads_the_ship_window_from_aurora() -> None:
    logic = (BACKEND / "services" / "business_logic.py").read_text()
    # Per-warehouse breakdown must carry both the count and the window.
    assert "ship_window_min" in logic and "ship_window_max" in logic
    assert "w.display_name" in logic and "wi.quantity" in logic


def test_marco_answer_rules_require_warehouse_count_and_ship_window() -> None:
    """All three, or the answer is not grounded in what the tool returned."""
    prompt = (BACKEND / "agents" / "inventory_agent.py").read_text()
    assert "ship window" in prompt.lower()
    assert "total_units" in prompt
    assert "BK-01" in prompt


def test_marco_quantity_is_never_hard_coded_in_the_prompt() -> None:
    """Prompt 1 observed 20 units. That is evidence, not a fixture.

    A literal count in the instructions would have the agent assert a number
    Aurora may no longer agree with.
    """
    prompt = (BACKEND / "agents" / "inventory_agent.py").read_text()
    # The prompt's illustrative examples use deliberately different numbers so
    # no single value can read as the real one.
    assert "20 of the Hadley" not in prompt
    assert "quantity" in prompt  # it reads the field instead


# ---------------------------------------------------------------------------
# ANNA — RETRIEVE. Four strategies, and honest filter ownership.
# ---------------------------------------------------------------------------

def test_anna_four_strategies_are_all_present() -> None:
    app = (BACKEND / "app.py").read_text()
    for strategy in ("vector", "hybrid", "rerank", "agentic"):
        assert f'"{strategy}"' in app or f"'{strategy}'" in app, strategy


def test_anna_agentic_row_extracts_both_hard_constraints() -> None:
    """The hard filters are the whole point of the fourth row."""
    app = (BACKEND / "app.py").read_text()
    assert '"priceMaxUsd"' in app
    assert '"inStockOnly"' in app
    assert '"softSignal"' in app


def test_anna_uses_modeled_cost_field_not_cost_model() -> None:
    """`costModel` never existed; asserting it would encode a false claim."""
    app = (BACKEND / "app.py").read_text()
    assert '"modeledCostPerThousandUsd"' in app
    assert '"costModel"' not in app


def test_anna_observed_ms_is_presented_as_an_observation() -> None:
    """One run is not a benchmark, and the endpoint says so."""
    app = (BACKEND / "app.py").read_text()
    assert '"observedMs"' in app
    assert "durations are observations" in app


# ---------------------------------------------------------------------------
# THEO — ACT. The boundary, enforced by architecture.
# ---------------------------------------------------------------------------

def test_theo_shopper_rail_cannot_execute_the_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The governed format refuses the write in-process. Deterministically.

    This is the load-bearing assertion of Prompt 2. If `initiate_return` ever
    became servable on the shopper rail, Pellier would complete a privileged
    business mutation from a chat turn with no human confirmation and no Cedar
    evaluation.

    The gate is format-scoped on purpose: `requires_managed_rail` returns False
    unless WORKSHOP_FORMAT is "governed". The builders format deliberately runs
    the write in-process, so the format is set explicitly here rather than
    inherited from the environment.
    """
    from services import execution_rail

    monkeypatch.setattr(
        execution_rail.settings, "WORKSHOP_FORMAT", "governed", raising=False
    )

    assert execution_rail.requires_managed_rail("initiate_return") is True
    assert execution_rail.requires_managed_rail("issue_credit") is True
    # A read must NOT be gated, or the shopper arc breaks for Marco and Anna.
    assert execution_rail.requires_managed_rail("check_inventory") is False
    assert execution_rail.requires_managed_rail("search_products") is False


def test_the_boundary_is_scoped_to_the_governed_format() -> None:
    """Stated as its own fact, because it decides where the arc applies.

    On the builders format the shopper rail completes the return in-process.
    Prompt 2's "stop at the boundary" behaviour is a governed-branch property,
    not a universal one.
    """
    from services import execution_rail

    original = getattr(execution_rail.settings, "WORKSHOP_FORMAT", "")
    try:
        execution_rail.settings.WORKSHOP_FORMAT = "builders"
        assert execution_rail.requires_managed_rail("initiate_return") is False
    finally:
        execution_rail.settings.WORKSHOP_FORMAT = original


def test_theo_return_tool_checks_the_rail_before_touching_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard must run first, not after a partial write.

    Scope note, added in Prompt 3: `_db_service` is the handle every *business*
    write goes through, and this asserts the refusal path never reaches it. The
    refusal branch does now open a durable operator review, which is workflow
    state written through a separate pool reference in `services.operator_review`
    after the guard has already decided to refuse. That is deliberately not what
    this tripwire guards, and `test_operator_review` asserts the separation from
    the other side.
    """
    from services import agent_tools

    from services import execution_rail

    monkeypatch.setattr(
        execution_rail.settings, "WORKSHOP_FORMAT", "governed", raising=False
    )

    called: list[str] = []

    class Tripwire:
        def __getattr__(self, name: str):  # pragma: no cover - must not run
            called.append(name)
            raise AssertionError(
                f"the database was touched ({name}) despite the managed-rail guard"
            )

    monkeypatch.setattr(agent_tools, "_db_service", Tripwire())

    raw = agent_tools.initiate_return._tool_func(
        customer_id="theo",
        product_id=37,
        reason="damaged",
        idempotency_key="prompt2-boundary-probe",
    )

    import json

    envelope = json.loads(raw)
    assert envelope["error"] == "managed_rail_required"
    assert envelope["tool"] == "initiate_return"
    assert called == [], "no database attribute may be reached"


def test_theo_credit_tool_is_gated_on_the_same_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import agent_tools

    from services import execution_rail

    monkeypatch.setattr(
        execution_rail.settings, "WORKSHOP_FORMAT", "governed", raising=False
    )
    import json

    envelope = json.loads(
        agent_tools.issue_credit._tool_func(
            customer_id="CUST-THEO",
            amount_cents=2500,
            reason="probe",
            idempotency_key="prompt2-credit-probe",
        )
    )
    assert envelope["error"] == "managed_rail_required"


def test_theo_agent_is_told_the_boundary_is_not_a_failure() -> None:
    """`managed_rail_required` previously reached the model with no guidance.

    The Customer Service Agent was still instructed to announce a completed write, so
    the shopper could plausibly be told the return was filed when nothing had
    happened.
    """
    prompt = (BACKEND / "agents" / "customer_service_agent.py").read_text()
    assert "managed_rail_required" in prompt
    assert "operator-review-boundary" in prompt
    assert "prepared" in prompt.lower()


def test_theo_agent_may_not_claim_the_return_completed() -> None:
    """Each forbidden claim is named, because a vague rule is not a rule."""
    prompt = (BACKEND / "agents" / "customer_service_agent.py").read_text()
    flat = " ".join(prompt.split())
    for forbidden in ("refund", "credit", "replacement", "policy approved"):
        assert forbidden in flat, f"the prompt does not forbid claiming: {forbidden}"
    assert "must NOT say" in flat


def test_theo_boundary_does_not_leak_system_vocabulary_to_the_shopper() -> None:
    """The shopper hears a prepared request, not a rail name."""
    prompt = (BACKEND / "agents" / "customer_service_agent.py").read_text()
    flat = " ".join(prompt.split())
    assert "Never show the shopper" in flat
    for internal in ("managed_rail_required", "gateway-mcp", "Cedar"):
        assert internal in flat, f"{internal} should be named as internal-only"


def test_theo_boundary_does_not_reuse_the_stylist_escalation() -> None:
    """`escalate_to_human` routes to a stylist for cases policy will not cover.

    Theo's return IS covered — damaged is canonical and he owns the piece. Using
    the stylist handoff would send a governed action to the wrong destination and
    describe it as a policy exception.
    """
    prompt = (BACKEND / "agents" / "customer_service_agent.py").read_text()
    flat = " ".join(prompt.split())
    assert "Do NOT use escalate_to_human for a return that simply needs operator" in flat

    tools = (BACKEND / "services" / "agent_tools.py").read_text()
    # And the tool itself still means what it meant: a UI handoff, no write.
    assert '"channel": "stylist"' in tools
    assert "No products, no audit row" in tools


# ---------------------------------------------------------------------------
# Scope guard — Prompt 2 must not build Prompt 3
# ---------------------------------------------------------------------------

def test_prompt_2_did_not_create_an_operator_case_model() -> None:
    """The case model belongs to Prompt 3, with real durable state.

    A frontend-only "case" invented so the transition looks finished would be
    exactly the forked business truth the arc forbids.
    """
    migrations = sorted((REPO / "scripts" / "migrations").glob("*.sql"))
    for path in migrations:
        sql = path.read_text()
        assert "CREATE TABLE IF NOT EXISTS pellier.operator_cases" not in sql, path.name
        assert "CREATE TABLE IF NOT EXISTS pellier.cases" not in sql, path.name

    frontend = REPO / "pellier" / "frontend" / "src"
    stray = [
        p.relative_to(frontend).as_posix()
        for p in frontend.rglob("*.ts*")
        if p.name.lower() in {"cases.ts", "case.ts", "operatorcase.ts", "casemodel.ts"}
    ]
    assert not stray, f"a case model appeared ahead of Prompt 3: {stray}"


def test_prompt_2_added_no_new_privileged_mutation() -> None:
    """The mutation set is exactly the three that already existed."""
    from services.agentcore_gateway import mutation_tool_names

    assert sorted(mutation_tool_names()) == [
        "initiate_return",
        "issue_credit",
        "restock_inventory",
    ]


def test_prompt_2_did_not_mint_a_second_correlation_identifier() -> None:
    schemas = (REPO / "scripts" / "deploy" / "gateway_tool_schemas.py").read_text()
    assert "turn_id" in schemas
    for rival in ("case_id", "correlation_id", "review_id"):
        assert rival not in schemas, f"a rival correlation key appeared: {rival}"
