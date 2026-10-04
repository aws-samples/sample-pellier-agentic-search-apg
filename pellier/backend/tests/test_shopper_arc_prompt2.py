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
    prompt = (BACKEND / "agents" / "stock_agent.py").read_text()
    assert "Brooklyn" in prompt and "what ship window is recorded?" in prompt
    assert "check_stock(product_query='Hadley Linen Shirt')" in prompt
    assert "A dispatch window does not establish an arrival date" in prompt
    assert "time-to-doorstep" not in prompt and "day arrival" not in prompt


def test_marco_tool_reads_the_ship_window_from_aurora() -> None:
    logic = (BACKEND / "services" / "store_tools.py").read_text()
    # Per-warehouse breakdown must carry both the count and the window.
    assert "ship_window_min" in logic and "ship_window_max" in logic
    assert "w.display_name" in logic and "wi.quantity" in logic


def test_marco_answer_rules_require_warehouse_count_and_ship_window() -> None:
    """All three, or the answer is not grounded in what the tool returned."""
    prompt = (BACKEND / "agents" / "stock_agent.py").read_text()
    assert "ship window" in prompt.lower()
    assert "total_units" in prompt
    assert "BK-01" in prompt


def test_marco_quantity_is_never_hard_coded_in_the_prompt() -> None:
    """Prompt 1 observed 20 units. That is evidence, not a fixture.

    A literal count in the instructions would have the agent assert a number
    Aurora may no longer agree with.
    """
    prompt = (BACKEND / "agents" / "stock_agent.py").read_text()
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

def test_theo_shopper_rail_cannot_execute_the_credit() -> None:
    """No shopper agent can reach the credit write. Structurally.

    This is the load-bearing assertion of Prompt 2. The in-process wrapper for
    `give_store_credit` does not exist, so no specialist can bind it and a chat
    turn cannot complete a privileged business mutation without a person and a
    Cedar evaluation. The Operator reaches the write only through
    `services.governed_execution`, which selects the rail itself.
    """
    import inspect

    from agents import shopping_agent, stock_agent, support_agent
    from services import agent_tools, governed_execution

    assert not hasattr(agent_tools, "give_store_credit")
    for module in (shopping_agent, stock_agent, support_agent):
        assert "give_store_credit" not in inspect.getsource(module), module.__name__
    assert "store_tools.give_store_credit" in inspect.getsource(governed_execution)


def _support_prompt() -> str:
    from agents.support_agent import _SUPPORT_SYSTEM_PROMPT

    return " ".join(_SUPPORT_SYSTEM_PROMPT.split())


def test_theo_agent_hands_a_credit_request_to_a_person() -> None:
    """The Support agent asks for a credit; a person decides it.

    The prompt names the handoff tool, the amount argument, and the fact that
    nothing changes until a person confirms.
    """
    flat = _support_prompt()
    assert "ask_a_person" in flat
    assert "store_credit_cents" in flat
    assert "A person reviews every credit before anything changes" in flat
    assert "nothing has changed yet" in flat


def test_theo_agent_may_not_claim_the_return_completed() -> None:
    """The forbidden claim is named, because a vague rule is not a rule."""
    flat = _support_prompt()
    assert (
        "never say a refund, return or credit was made unless a tool result says so"
        in flat
    )
    assert "do not promise a timeframe or an outcome" in flat


def test_theo_boundary_does_not_leak_system_vocabulary_to_the_shopper() -> None:
    """The shopper hears a prepared request, not a rail name."""
    flat = _support_prompt()
    assert "Never show the shopper a tool name, a status code" in flat
    for internal in ("Cedar", "rail"):
        assert internal in flat, f"{internal} should be named as internal-only"


def test_the_support_agent_never_binds_the_credit_tool() -> None:
    """A credit is requested through `ask_a_person`, never written by the agent.

    `give_store_credit` is bound to no agent; it runs only for a review a person
    confirmed. Binding it would put the money-moving write back inside the chat.
    """
    from agents import support_agent

    source = (BACKEND / "agents" / "support_agent.py").read_text()
    assert "give_store_credit" not in source
    bound = {
        getattr(getattr(tool, "__wrapped__", tool), "__name__", "")
        for tool in (
            support_agent.get_orders,
            support_agent.get_return_policy,
            support_agent.get_tickets,
            support_agent.ask_a_person,
        )
    }
    assert "give_store_credit" not in bound


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


def test_the_only_privileged_mutation_is_the_operator_store_credit() -> None:
    """The mutation set is one tool, and no agent binds it."""
    from services.agentcore_gateway import mutation_tool_names

    assert sorted(mutation_tool_names()) == ["give_store_credit"]


def test_prompt_2_did_not_mint_a_second_correlation_identifier() -> None:
    schemas = (REPO / "scripts" / "deploy" / "gateway_tool_schemas.py").read_text()
    assert "turn_id" in schemas
    for rival in ("case_id", "correlation_id", "review_id"):
        assert rival not in schemas, f"a rival correlation key appeared: {rival}"
