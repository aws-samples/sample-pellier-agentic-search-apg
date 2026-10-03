"""PROMPT 1 — the frozen contract for the Marco → Anna → Theo arc.

This is the fixture map, expressed as assertions rather than prose, so the
relationships the whole arc depends on cannot drift while later stages are built.

Prompt 3 introduces a genuinely new Operator case object. Once that exists it
becomes tempting to bend the data model around whatever the UI needs, which is
why the authoritative relationships are pinned here first.

Every identifier below was verified against the live `dat4xx-labs-test` Aurora
cluster before being written down. These tests read the seed sources rather than
the database, so they run offline in CI and still fail if a canonical row is
renamed or removed.

What is deliberately NOT asserted here:

* live quantities — inventory moves during a workshop, so pinning `20` would
  make the suite fail for a legitimate reason;
* `turn_id` values — minted per request;
* anything about a case model, which does not exist yet.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO / "scripts" / "migrations"
BACKEND = REPO / "pellier" / "backend"


# ---------------------------------------------------------------------------
# The frozen fixture map. One place, machine-readable.
# ---------------------------------------------------------------------------

ARC = {
    "marco": {
        "persona_id": "marco",
        "customer_id": "CUST-MARCO",
        "membership": "maison",
        "product_id": 2,
        "product_name": "Hadley Linen Shirt",
        "warehouse_id": "BK-01",
        "warehouse_city": "Brooklyn, NY",
        "tool": "check_inventory",
        "question": "How many Hadley Linen Shirts are available at the Brooklyn warehouse, and what ship window is recorded?",
    },
    "anna": {
        "persona_id": "anna",
        "customer_id": "CUST-ANNA",
        "membership": "circle",
        "query": "A housewarming gift under $100 that is in stock",
        "price_max_usd": 100,
        "in_stock_only": True,
        "tools": ("search_products", "search_products_hybrid"),
        "strategy_endpoint": "/api/observatory/search-strategies/compare",
    },
    "theo": {
        "persona_id": "theo",
        # Both resolve in authoritative order history; the shopper prompt
        # never supplies either value as an identity claim.
        "customer_ids": ("CUST-THEO", "theo"),
        "membership": "registered",
        "spend_12mo": 940.00,
        "product_id": 37,
        "product_name": "Wabi-Sabi Bowl",
        "reason": "damaged",
        "tools": ("initiate_return", "issue_credit"),
        "question": "My Wabi-Sabi Bowl arrived chipped. Please help me return it.",
    },
}

OPERATOR_READ_APIS = (
    "/api/operator/clients",
    "/api/operator/clients/{client_id}",
)
OPERATOR_WRITE_APIS = (
    "/api/operator/reviews/{review_id}/execute",
)

# `turn_id` stays the only correlation identifier. No second one may appear.
CORRELATION_KEY = "turn_id"


def _load_seed_module():
    name = "seed_catalog_for_arc_contract"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, REPO / "scripts" / "seed_pellier_catalog.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


def _catalog_by_id():
    return {p.productId: p for p in _load_seed_module().load_catalog()}


# ---------------------------------------------------------------------------
# MARCO — GROUND
# ---------------------------------------------------------------------------

def test_marco_product_is_canonical() -> None:
    product = _catalog_by_id()[ARC["marco"]["product_id"]]
    assert product.name == ARC["marco"]["product_name"]
    # Marco's turn is an apparel stock question; the persona bucket matters for
    # the personalized grid, so a re-bucketing would change his story.
    assert product.persona == "fresh"


def test_marco_warehouse_and_ship_window_exist_in_the_schema() -> None:
    """The strengthened question asks whether it can still ship in time.

    That is only answerable because the warehouse dimension carries a ship
    window. If those columns go, Marco's turn silently degrades to "in stock".
    """
    sql = (MIGRATIONS / "006_warehouse_inventory.sql").read_text()
    assert "ship_window_min" in sql and "ship_window_max" in sql
    assert ARC["marco"]["warehouse_id"] in sql, "BK-01 is not seeded"

    logic = (BACKEND / "services" / "business_logic.py").read_text()
    # check_inventory must actually read the window, not just the quantity.
    assert "ship_window_min" in logic and "ship_window_max" in logic


def test_marco_tool_is_the_lab_one_build_target() -> None:
    tools = (BACKEND / "services" / "agent_tools.py").read_text()
    assert f"def {ARC['marco']['tool']}(" in tools
    # The guided exercise markers name the same tool.
    assert "WORKSHOP - Inventory Agent - check_inventory: START" in tools


# ---------------------------------------------------------------------------
# ANNA — RETRIEVE
# ---------------------------------------------------------------------------

def test_anna_query_has_a_real_mixed_constraint_pool() -> None:
    """Her query is only interesting if products actually satisfy both bounds.

    An empty or near-empty pool makes every strategy look identical, which
    destroys the comparison the lab is built on.
    """
    catalog = _load_seed_module().load_catalog()
    affordable = [
        p for p in catalog
        if p.price <= ARC["anna"]["price_max_usd"]
    ]
    assert len(affordable) >= 10, (
        f"only {len(affordable)} curated products are within "
        f"${ARC['anna']['price_max_usd']}; the four strategies would not diverge"
    )


def test_anna_strategy_endpoint_exposes_the_four_strategies() -> None:
    app = (BACKEND / "app.py").read_text()
    assert ARC["anna"]["strategy_endpoint"] in app

    # The exact response keys the participant compares. `costModel` was the
    # name in an earlier draft of the arc and does not exist.
    for key in ("observedMs", "modeledCostPerThousandUsd", "extractedFilters"):
        assert f'"{key}"' in app, f"strategy response is missing {key}"
    assert '"costModel"' not in app

    # Agentic extraction keys, camelCase at the API boundary.
    for key in ("priceMaxUsd", "inStockOnly", "softSignal"):
        assert f'"{key}"' in app, f"extractedFilters is missing {key}"


def test_anna_rerank_model_is_cohere_3_5() -> None:
    rerank = (BACKEND / "services" / "rerank.py").read_text()
    assert "cohere.rerank-v3-5:0" in rerank


# ---------------------------------------------------------------------------
# THEO — ACT
# ---------------------------------------------------------------------------

def test_theo_product_is_canonical() -> None:
    product = _catalog_by_id()[ARC["theo"]["product_id"]]
    assert product.name == ARC["theo"]["product_name"]


def test_theo_owns_the_bowl_under_both_customer_ids() -> None:
    """`initiate_return` checks ownership in SQL before it writes.

    The live prompt passes the bare id `theo`, so the order must exist under the
    alias as well as the canonical id or the write path fails with "product not
    found in your orders".
    """
    sql = (MIGRATIONS / "003_persona_seed.sql").read_text()
    for customer_id in ARC["theo"]["customer_ids"]:
        assert (
            f"('{customer_id}', '{ARC['theo']['product_id']}'" in sql
        ), f"{customer_id} has no seeded {ARC['theo']['product_name']} order"


def test_theo_is_registered_and_that_is_intentional() -> None:
    """Product design, not missing seed data.

    A courtesy credit for a Maison client is a formality; the same credit for the
    lowest rung is a judgment call, which is the decision the governance lesson
    needs. Promoting Theo to make the scenario easier would remove the point.
    """
    sql = (MIGRATIONS / "018_client_book.sql").read_text()
    assert (
        "UPDATE pellier.customers SET membership = 'registered', spend_12mo =  940.00 "
        "WHERE id = 'CUST-THEO';" in sql
    )
    assert "platinum" not in sql.lower(), "Pellier's ladder has no platinum rung"


def test_theo_damage_reason_is_in_the_canonical_set() -> None:
    logic = (BACKEND / "services" / "business_logic.py").read_text()
    assert f'"{ARC["theo"]["reason"]}"' in logic


def test_theo_tools_exist_and_are_governed_writes() -> None:
    sys.path.insert(0, str(BACKEND)) if str(BACKEND) not in sys.path else None
    from services.agentcore_gateway import mutation_tool_names

    mutations = set(mutation_tool_names())
    for tool in ARC["theo"]["tools"]:
        assert tool in mutations, f"{tool} is not classified as a mutation"


# ---------------------------------------------------------------------------
# Operator bridge — the APIs that let both channels see one client
# ---------------------------------------------------------------------------

def test_operator_read_and_write_apis_are_registered() -> None:
    route = (BACKEND / "routes" / "operator.py").read_text()
    for path in OPERATOR_READ_APIS:
        # The router carries the prefix, so match the suffix.
        suffix = path.replace("/api/operator", "")
        assert f'"{suffix}"' in route, f"{path} is not defined"
    for path in OPERATOR_WRITE_APIS:
        suffix = path.replace("/api/operator", "")
        assert f'"{suffix}"' in route, f"{path} is not defined"

    app = (BACKEND / "app.py").read_text()
    assert "app.include_router(operator_router)" in app, (
        "the operator router is imported but never mounted — the routes 404"
    )


def test_every_operator_route_is_one_authorization_boundary() -> None:
    """Reads included. This test asserted the opposite, which is how it survived.

    "The desk must not be a blank 401" was the stated reason `GET` needed no token, and it
    is a real workshop-reliability concern. It is outweighed by what the reads return:
    `GET /clients` enumerates every client's standing, preferences and order history, and
    `GET /reviews/{id}` returns the governance verdicts and their lineage. Reliability
    comes from seeding the operator group deterministically, not from anonymous access to
    customer data.

    Asserted against the router's real dependency graph rather than the source text. An
    earlier version split the file on a comment marker and tripped over the word
    `require_operator` in the module docstring, which proves nothing either way about
    what the handlers actually depend on.
    """
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from routes.operator import router
    from services.auth import require_operator

    def gated(route) -> bool:
        """True when `require_operator` is in the route's resolved dependency graph.

        The dependency is declared once on the `APIRouter`, and FastAPI flattens router
        dependencies into every route's `dependant`, so this sees router-level and
        handler-level declarations alike. That is the point: a new route inherits the
        boundary instead of being forgotten.
        """
        return any(
            dep.call is require_operator
            for dep in route.dependant.dependencies
        )

    assert router.routes, "the operator router has no routes"
    for route in router.routes:
        assert gated(route), (
            f"{route.path} is reachable without require_operator. Every route on this "
            "prefix is one boundary: anonymous is 401, an authenticated shopper is 403, "
            "and only the operator group gets through."
        )


def test_the_operator_surface_does_not_fork_business_truth() -> None:
    """A case may hold references and workflow state, never business truth.

    Membership, order state, and return status are resolved from Aurora on read.
    A committed frontend copy of the client book would be the exact "UI state is
    not proof" mistake, so its absence is asserted rather than assumed.
    """
    data_dir = REPO / "pellier" / "frontend" / "src" / "data"
    forked = [
        p.name for p in data_dir.glob("*.ts")
        if p.name in {"clientBook.ts", "clients.ts", "cases.ts"}
    ]
    assert not forked, (
        f"frontend fixtures duplicating backend business truth: {forked}"
    )


# ---------------------------------------------------------------------------
# Identity and correlation
# ---------------------------------------------------------------------------

def test_turn_id_is_the_only_correlation_identifier() -> None:
    """Do not mint a second one.

    A rival correlation key means two incompatible reconstructions of the same
    turn, and no way to tell which is authoritative.
    """
    schemas = (REPO / "scripts" / "deploy" / "gateway_tool_schemas.py").read_text()
    assert CORRELATION_KEY in schemas

    rivals = ("correlation_id", "trace_id_v2", "case_correlation_id", "request_uuid")
    for name in rivals:
        assert name not in schemas, f"a second correlation identifier appeared: {name}"


def test_membership_is_stored_on_the_customer_not_derived_per_request() -> None:
    """Policy must read a stable, auditable value."""
    sql = (MIGRATIONS / "018_client_book.sql").read_text()
    assert "ADD COLUMN IF NOT EXISTS membership TEXT" in sql
    assert "ADD COLUMN IF NOT EXISTS spend_12mo" in sql


def test_the_arc_fixture_map_is_serialisable() -> None:
    """The map is the deliverable, so it must be machine-readable."""
    payload = json.loads(json.dumps(ARC, default=list))
    assert set(payload) == {"marco", "anna", "theo"}
    assert payload["theo"]["membership"] == "registered"
    assert payload["marco"]["warehouse_id"] == "BK-01"
    assert payload["anna"]["price_max_usd"] == 100
