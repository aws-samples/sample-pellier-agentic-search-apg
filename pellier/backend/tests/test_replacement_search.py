"""Replacement Search: grounding, hard constraints, and what "in stock" means.

The assertions worth having are the ones a demo cannot show. That an operator's
$100 ceiling survives reranking. That an ambiguous item reference does not become a
coin flip. That "in stock" is refused by the aggregate cache and answered by the
ledger. That an unverified availability never turns into "out of stock", and a
reranker can reorder valid candidates but never resurrect an invalid one.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional, Sequence

import pytest

from services import inventory_evidence as INV
from services import replacement_search as RS


# ---------------------------------------------------------------------------
# Fixtures: a fake Aurora that behaves like the real driver
# ---------------------------------------------------------------------------

def _order_row(
    order_id: int, product_id: str, name: str, category: str, price: float,
    *, brand: str = "Pellier Home", tags: Sequence[str] = ("ceramic", "home"),
) -> Dict[str, Any]:
    return {
        "order_id": order_id, "product_id": product_id, "name": name,
        "category": category, "price": price, "quantity": 1, "brand": brand,
        "color": "sand", "description": f"{name} description", "tags": list(tags),
        "img_url": f"/products/{product_id}.png", "placed_at": None,
    }


class FakeDb:
    """Returns MAPPINGS, not tuples: the pool configures `dict_row`.

    An earlier revision of `inventory_evidence` indexed rows positionally and passed
    every test against a tuple-based fake, then would have raised `KeyError: 0` on its
    first live call. A fake looser than the real driver is worse than no fake.
    """

    def __init__(
        self,
        *,
        orders: Optional[List[Dict[str, Any]]] = None,
        inventory: Optional[List[Dict[str, Any]]] = None,
        fail: bool = False,
    ) -> None:
        self.orders = orders if orders is not None else []
        self.inventory = inventory or []
        self.fail = fail
        self.statements: List[str] = []

    def get_connection(self):
        return _Conn(self)


class _Cur:
    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self._rows: List[Dict[str, Any]] = []

    async def execute(self, sql: str, params: Any = ()) -> None:
        flat = " ".join(sql.split())
        self.db.statements.append(flat)
        if self.db.fail:
            raise RuntimeError("connection reset")
        if "FROM pellier.orders" in flat:
            self._rows = list(self.db.orders)
        elif "pellier.warehouse_balance" in flat:
            wanted = set(params["product_ids"]) if isinstance(params, dict) else set()
            self._rows = [r for r in self.db.inventory if r["product_id"] in wanted]
        else:  # pragma: no cover - an unmodelled statement is a test bug
            raise AssertionError(f"unexpected SQL: {flat[:90]}")

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None

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


POUR_OVER = _order_row(306, "31", "Stoneware Pour-Over Set", "Home Decor", 165.0,
                       tags=("ceramic", "home", "slow", "artisanal"))
CATCHALL = _order_row(315, "41", "Coral Lacquer Catchall", "Home Decor", 325.36,
                      brand="Pellier Maison", tags=("home", "gift"))
ROBE = _order_row(316, "42", "Luxury Bath Robe, Sage", "Home Decor", 107.3)


def _inventory_row(
    product_id: str, *, has_ledger: bool, locations: Optional[List[Dict[str, Any]]],
    aggregate_cache: Optional[int] = 50, aggregate_ledger: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "product_id": product_id,
        "has_ledger": has_ledger,
        "locations": locations,
        "aggregate_cache": aggregate_cache,
        "aggregate_ledger": aggregate_ledger,
    }


def _loc(warehouse: str, cache: int, ledger: int) -> Dict[str, Any]:
    return {
        "warehouseId": warehouse, "cacheQuantity": cache, "ledgerQuantity": ledger,
        "displayName": warehouse, "city": "Somewhere",
        "shipWindowMin": 1, "shipWindowMax": 2,
    }


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_order_item_is_established_by_aurora_not_by_the_request() -> None:
    """The request may name a product; the price and id come from the order line."""
    db = FakeDb(orders=[CATCHALL, POUR_OVER])
    grounding = await RS.resolve_order_item(
        db, customer_id="CUST-JESSICA",
        # A wrong price in the request must not survive into the plan.
        request="Find a replacement for the Stoneware Pour-Over Set, it was $9.99.",
    )
    assert grounding.item is not None
    assert grounding.item.product_id == "31"
    assert grounding.item.price == 165.0
    assert grounding.item.order_id == 306


@pytest.mark.asyncio
async def test_an_explicit_order_number_wins() -> None:
    db = FakeDb(orders=[CATCHALL, POUR_OVER])
    grounding = await RS.resolve_order_item(
        db, customer_id="CUST-JESSICA", request="For order #315 find a replacement."
    )
    assert grounding.item is not None and grounding.item.order_id == 315
    assert "315" in grounding.matched_on


@pytest.mark.asyncio
async def test_an_ambiguous_reference_is_not_guessed() -> None:
    """Two order lines fitting equally well is a question, not a coin flip."""
    wool_a = _order_row(1, "51", "Camel Wool Overcoat", "Apparel", 895.0)
    wool_b = _order_row(2, "45", "Tailored Wool Blazer", "Apparel", 346.38)
    db = FakeDb(orders=[wool_a, wool_b])
    grounding = await RS.resolve_order_item(
        db, customer_id="CUST-CATHERINE", request="Find a replacement for her wool piece."
    )
    assert grounding.item is None
    assert grounding.ambiguous is True
    assert {c.product_id for c in grounding.candidates} == {"51", "45"}


@pytest.mark.asyncio
async def test_an_unnarrowed_request_reports_the_assumption_it_made() -> None:
    db = FakeDb(orders=[CATCHALL, POUR_OVER])
    grounding = await RS.resolve_order_item(
        db, customer_id="CUST-JESSICA", request="Find her a replacement."
    )
    assert grounding.item is not None and grounding.item.order_id == 315
    # The operator can see WHAT was assumed rather than having to infer it.
    assert grounding.matched_on == "most recent order"


@pytest.mark.asyncio
async def test_no_order_history_is_reported_not_invented() -> None:
    grounding = await RS.resolve_order_item(
        FakeDb(orders=[]), customer_id="CUST-NEW", request="Find a replacement."
    )
    assert grounding.item is None and grounding.reason == "no_order_history"


@pytest.mark.asyncio
async def test_a_read_failure_is_not_an_empty_order_history() -> None:
    grounding = await RS.resolve_order_item(
        FakeDb(fail=True), customer_id="CUST-JESSICA", request="Find a replacement."
    )
    assert grounding.reason == "order_history_unavailable"


# ---------------------------------------------------------------------------
# Hard vs soft
# ---------------------------------------------------------------------------

def _plan(request: str, extracted: Dict[str, Any], item: Any = None) -> Any:
    return RS.build_replacement_plan(
        original=RS._order_item(item or POUR_OVER), request=request, extracted=extracted
    )


def test_an_explicit_operator_ceiling_is_authoritative() -> None:
    plan = _plan("find a replacement under $80", {"price_max_usd": 80})
    assert plan.search_plan.hard.price_max_usd == 80.0
    assert plan.price_ceiling_source == "operator_explicit"


def test_a_derived_price_band_is_declared_as_a_heuristic() -> None:
    """Not an unexplained ±20% rule: the multiplier is named and reported."""
    plan = _plan("find a similar replacement", {})
    assert plan.price_ceiling_source == "similar_price_heuristic"
    assert plan.search_plan.hard.price_max_usd == round(
        165.0 * RS.SIMILAR_PRICE_CEILING_MULTIPLIER, 2
    )
    described = " ".join(plan.describe_hard_controls())
    assert "similar-price heuristic" in described, (
        "a heuristic was presented as business policy"
    )


def test_an_inferred_preference_stays_soft(completed_search_plan) -> None:
    """A model-proposed taste tag may shape ranking; it may not gate validity."""
    plan = _plan("something similar", {"tags": ["ceramic", "artisanal"]})
    assert plan.search_plan.soft.tags == ("ceramic", "artisanal")
    # The hard set contains only what Aurora established — the original's category.
    assert plan.search_plan.hard.categories == ("Home Decor",)
    assert "ceramic" not in " ".join(plan.describe_hard_controls())
    # And the tag predicate is droppable by the relaxation ladder, unlike the rest.
    widened = plan.search_plan.relaxation_ladder()[-1]
    assert widened.soft.tags == ()
    assert widened.hard.categories == ("Home Decor",)
    assert widened.hard.price_max_usd == plan.search_plan.hard.price_max_usd


def test_the_original_category_is_hard_because_aurora_established_it() -> None:
    plan = _plan("find a replacement", {})
    assert plan.search_plan.hard.categories == ("Home Decor",)


def test_a_replacement_is_never_the_item_it_replaces() -> None:
    plan = _plan("find a replacement", {})
    clauses, params = RS.compile_replacement_predicates(plan)
    assert any('"productId" <> %s' in c for c in clauses)
    assert "31" in [str(p) for p in params]


# ---------------------------------------------------------------------------
# "In stock" has to mean something
# ---------------------------------------------------------------------------

def test_an_availability_request_is_recognised_from_either_source() -> None:
    assert RS.requires_reconciled_availability("find an in-stock option", {}) is True
    assert RS.requires_reconciled_availability("find one", {"in_stock_only": True}) is True
    assert RS.requires_reconciled_availability("find one", {}) is False


def test_the_aggregate_cache_can_never_satisfy_an_in_stock_request() -> None:
    """The load-bearing test for this workflow.

    `SearchPlan.compile_predicates` renders `in_stock_only` as a bare `quantity > 0`
    on `product_catalog.quantity` — the aggregate cache, which carries a seed constant
    for 960 of 1,000 rows. If that predicate ever reappears here, "in stock" stops
    meaning anything.
    """
    plan = _plan("find an in-stock replacement", {"in_stock_only": True})
    assert plan.availability_requirement == RS.AVAILABILITY_RECONCILED
    # Forced off in the SearchPlan so it cannot compile the cache predicate.
    assert plan.search_plan.hard.in_stock_only is False

    clauses, _params = RS.compile_replacement_predicates(plan)
    assert "quantity > 0" not in clauses, "the aggregate cache satisfied 'in stock'"
    # And the ledger predicate IS there, reading the migration 013 views.
    joined = " ".join(clauses)
    assert "pellier.warehouse_balance" in joined
    assert "pellier.warehouse_inventory" in joined


def test_availability_is_absent_from_the_predicates_when_not_requested() -> None:
    plan = _plan("find something similar", {})
    clauses, _params = RS.compile_replacement_predicates(plan)
    assert "pellier.warehouse_balance" not in " ".join(clauses)


def test_hard_constraints_reach_retrieval_rather_than_a_post_filter() -> None:
    """A post-filter makes the result short; a hard predicate makes it correct."""
    import inspect

    source = inspect.getsource(RS.find_replacements)
    assert "hard_clauses=hard_clauses" in source
    # And the reranker runs after retrieval, over an already-valid pool.
    assert source.index("hard_clauses=hard_clauses") < source.index("rerank(")


# ---------------------------------------------------------------------------
# Inventory: the ledger decides
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_reconciled_product_reports_the_ledger_quantity() -> None:
    db = FakeDb(inventory=[
        _inventory_row("31", has_ledger=True,
                       locations=[_loc("BK-01", 19, 19), _loc("ATX-02", 15, 15)],
                       aggregate_cache=50, aggregate_ledger=34),
    ])
    ev = await INV.resolve_inventory(db, "31")
    assert ev.status == INV.RECONCILED_IN_STOCK
    assert ev.available_quantity == 34
    assert ev.authority == INV.AUTHORITY_LEDGER
    assert ev.reconciled_to_ledger is True
    assert ev.supports_availability_claim is True
    # The stale aggregate cache is carried, not resolved.
    assert ev.aggregate_cache_stale is True
    assert ev.catalog_cache_quantity == 50 and ev.catalog_ledger_quantity == 34


@pytest.mark.asyncio
async def test_a_cache_only_reading_is_observed_and_not_verified() -> None:
    db = FakeDb(inventory=[
        _inventory_row("9", has_ledger=False, locations=[_loc("BK-01", 7, 0)]),
    ])
    ev = await INV.resolve_inventory(db, "9")
    assert ev.status == INV.OBSERVED_IN_STOCK
    assert ev.authority == INV.AUTHORITY_CACHE
    assert ev.reconciled_to_ledger is False
    # It may be reported, but it does not license an availability claim.
    assert ev.supports_availability_claim is False
    assert ev.supports_observed_claim is True
    assert "not reconciled" in INV.describe_availability(ev)


@pytest.mark.asyncio
async def test_a_disagreement_is_preserved_rather_than_resolved() -> None:
    db = FakeDb(inventory=[
        _inventory_row("21", has_ledger=True,
                       locations=[_loc("BK-01", 14, 14), _loc("ATX-02", 13, 9)]),
    ])
    ev = await INV.resolve_inventory(db, "21")
    assert ev.status == INV.LEDGER_CACHE_DISAGREEMENT
    # Neither side is silently preferred, and no quantity is offered.
    assert ev.available_quantity is None
    assert ev.supports_availability_claim is False
    assert ev.disagreements == [
        {"warehouseId": "ATX-02", "cacheQuantity": 13, "ledgerQuantity": 9}
    ]
    assert "disagree" in INV.describe_availability(ev)


@pytest.mark.asyncio
async def test_no_ledger_evidence_is_neither_in_stock_nor_out_of_stock() -> None:
    """960 of 1,000 catalog rows are in this state. Both wrong answers are tempting."""
    db = FakeDb(inventory=[
        _inventory_row("41", has_ledger=False, locations=None, aggregate_cache=50),
    ])
    ev = await INV.resolve_inventory(db, "41")
    assert ev.status == INV.NOT_VERIFIED
    assert ev.available_quantity is None, "a seed constant became a stock number"
    assert ev.status != INV.OBSERVED_OUT_OF_STOCK, "missing evidence became zero stock"
    assert ev.supports_availability_claim is False
    # The aggregate column is reported, and labelled as a cache.
    assert ev.catalog_cache_quantity == 50


@pytest.mark.asyncio
async def test_a_read_failure_is_not_zero_stock() -> None:
    ev = await INV.resolve_inventory(FakeDb(fail=True), "31")
    assert ev.status == INV.NOT_VERIFIED
    assert ev.available_quantity is None
    assert ev.source == "unavailable"


@pytest.mark.asyncio
async def test_many_products_resolve_in_one_round_trip() -> None:
    db = FakeDb(inventory=[
        _inventory_row("31", has_ledger=True, locations=[_loc("BK-01", 5, 5)]),
        _inventory_row("37", has_ledger=True, locations=[_loc("BK-01", 3, 3)]),
    ])
    batch = await INV.resolve_inventory_many(db, ["31", "37", "999"])
    assert len(db.statements) == 1, "one query per product would be N round trips"
    assert batch["31"].status == INV.RECONCILED_IN_STOCK
    assert batch["37"].status == INV.RECONCILED_IN_STOCK
    # A product the query returned nothing for is still answered, honestly.
    assert batch["999"].status == INV.NOT_VERIFIED


def test_the_reconciled_predicate_reads_the_migration_views() -> None:
    """Derived from migration 013's own views, not a hand-rolled sum(delta)."""
    sql = " ".join(INV.RECONCILED_AVAILABLE_SQL.split())
    assert "pellier.warehouse_balance" in sql
    assert "sum(" not in sql.lower(), "the derivation was re-implemented"
    assert 'product_catalog."productId"' in sql


def test_the_ledger_is_the_source_of_truth_per_the_migration() -> None:
    """The claim this module rests on, checked against the migration itself."""
    migration = pathlib.Path(
        "../../scripts/migrations/013_inventory_ledger.sql"
    ).resolve()
    text = migration.read_text()
    assert "The ledger is the source of" in text
    # And the two views this module reads exist there.
    assert "CREATE OR REPLACE VIEW pellier.warehouse_balance" in text
    assert "CREATE OR REPLACE VIEW pellier.catalog_balance" in text


# ---------------------------------------------------------------------------
# Read-only
# ---------------------------------------------------------------------------

def test_replacement_search_performs_no_write() -> None:
    import inspect

    source = inspect.getsource(RS)
    for forbidden in ("INSERT", "UPDATE ", "DELETE", "propose_review",
                      "initiate_return(", "issue_credit(", "reserve"):
        assert forbidden not in source, f"replacement search references {forbidden}"


def test_no_external_search_service_is_introduced() -> None:
    import inspect

    source = inspect.getsource(RS).lower()
    for forbidden in ("opensearch", "elasticsearch", "pinecone", "weaviate",
                      "dynamodb", "redis", "algolia"):
        assert forbidden not in source, f"an external search backend appeared: {forbidden}"
    # And the Aurora mechanisms it does compose.
    assert "hybrid_search" in inspect.getsource(RS)
    assert "search_plan" in inspect.getsource(RS)


def test_no_upgrade_role_is_claimed() -> None:
    """`tier` is 1 for all 1,000 rows, so nothing establishes an upgrade."""
    assert not hasattr(RS, "ROLE_UPGRADE")
    assert RS.ROLE_BEST_MATCH == "best_match"
    assert RS.ROLE_ALTERNATIVE == "alternative"


# ---------------------------------------------------------------------------
# The pipeline: partition, cap, and what reranking may not do
# ---------------------------------------------------------------------------

def _candidate(pid: str, name: str, price: float, **extra: Any) -> Dict[str, Any]:
    row = {
        "product_id": pid, "name": name, "price": price, "brand": "Pellier Home",
        "category": "Home Decor", "description": f"{name} description",
        "img_url": f"/products/{pid}.png", "tags": ["ceramic", "home"],
        "rrf_score": 0.03,
    }
    row.update(extra)
    return row


def _wire_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    candidates: List[Dict[str, Any]],
    inventory: Dict[str, Any],
    rerank: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Stub retrieval, reranking and inventory so the pipeline itself is under test."""
    seen: Dict[str, Any] = {}

    class _Embeddings:
        def embed_query(self, _query: str) -> List[float]:
            return [0.0] * 1024

    class _Hybrid:
        def __init__(self, _db: Any) -> None:
            pass

        async def search(self, **kwargs: Any) -> List[Dict[str, Any]]:
            seen["hard_clauses"] = list(kwargs.get("hard_clauses") or [])
            return list(candidates)

    class _Rerank:
        def rerank(self, **kwargs: Any) -> List[Dict[str, Any]]:
            seen["rerank_query"] = kwargs.get("query")
            if rerank is not None:
                return rerank
            return [
                {"index": i, "relevance_score": 1.0 - i * 0.1}
                for i in range(len(candidates))
            ]

    async def _resolve_many(_db: Any, product_ids: Sequence[str]) -> Dict[str, Any]:
        seen["reconciled_for"] = list(product_ids)
        return {pid: inventory[pid] for pid in product_ids if pid in inventory}

    from services import embeddings as EMB
    from services import hybrid_search as HS
    from services import inventory_evidence as IE
    from services import rerank as RR

    monkeypatch.setattr(EMB, "EmbeddingService", _Embeddings)
    monkeypatch.setattr(HS, "HybridSearch", _Hybrid)
    monkeypatch.setattr(RR, "get_rerank_service", lambda: _Rerank())
    monkeypatch.setattr(IE, "resolve_inventory_many", _resolve_many)
    return seen


def _reconciled(pid: str, qty: int = 12) -> INV.InventoryEvidence:
    return INV.InventoryEvidence(
        product_id=pid, status=INV.RECONCILED_IN_STOCK, available_quantity=qty,
        scope=INV.SCOPE_WAREHOUSE, locations=[{"warehouseId": "BK-01", "quantity": qty}],
        authority=INV.AUTHORITY_LEDGER, reconciled_to_ledger=True,
    )


def _unverified(pid: str) -> INV.InventoryEvidence:
    return INV.InventoryEvidence(product_id=pid, status=INV.NOT_VERIFIED)


@pytest.mark.asyncio
async def test_only_reconciled_candidates_are_offered_as_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [
        _candidate("37", "Wabi-Sabi Bowl", 65.0),
        _candidate("60", "Blown Glass Decanter", 210.0),
    ]
    _wire_pipeline(monkeypatch, candidates=candidates, inventory={
        "37": _reconciled("37", 50), "60": _unverified("60"),
    })
    plan = _plan("find a replacement", {})
    result = await RS.find_replacements(FakeDb(), plan)

    assert [r.product_id for r in result.available] == ["37"]
    assert [r.product_id for r in result.close_matches] == ["60"]
    # And a close match never carries the leading role.
    assert result.available[0].role == RS.ROLE_BEST_MATCH
    assert all(r.role == RS.ROLE_ALTERNATIVE for r in result.close_matches)


@pytest.mark.asyncio
async def test_at_most_three_recommendations_are_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator recommendation, not a product grid.

    Regression: the close-match slice read `remaining or _MAX_RECOMMENDATIONS`, so the
    zero case — three available already — fell back to three and produced six cards.
    """
    candidates = [_candidate(str(i), f"Option {i}", 50.0 + i) for i in range(6)]
    inventory = {str(i): _reconciled(str(i)) for i in range(4)}
    inventory.update({str(i): _unverified(str(i)) for i in (4, 5)})
    _wire_pipeline(monkeypatch, candidates=candidates, inventory=inventory)
    plan = _plan("find a replacement", {})
    result = await RS.find_replacements(FakeDb(), plan)

    assert len(result.available) == 3
    assert result.close_matches == []
    assert len(result.available) + len(result.close_matches) <= 3


@pytest.mark.asyncio
async def test_reconciled_count_is_measured_before_the_display_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: "3 of 12 reconciled" was really "3 shown of 12 reranked"."""
    candidates = [_candidate(str(i), f"Option {i}", 50.0) for i in range(5)]
    _wire_pipeline(monkeypatch, candidates=candidates,
                   inventory={str(i): _reconciled(str(i)) for i in range(5)})
    result = await RS.find_replacements(FakeDb(), _plan("find a replacement", {}))
    assert result.reconciled_count == 5
    assert len(result.available) == 3


@pytest.mark.asyncio
async def test_reranking_reorders_valid_candidates_and_resurrects_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reranker sees only what SQL already admitted.

    Its index list projects the candidate pool; an out-of-range index — a wrong
    reranker, a shifted pool — is dropped rather than admitting an unknown row.
    """
    candidates = [
        _candidate("37", "Wabi-Sabi Bowl", 65.0),
        _candidate("36", "Ceramic Tumblers", 78.0),
    ]
    seen = _wire_pipeline(
        monkeypatch, candidates=candidates,
        inventory={"37": _reconciled("37"), "36": _reconciled("36")},
        # Reversed order, plus an index that does not exist in the pool.
        rerank=[{"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.4},
                {"index": 99, "relevance_score": 0.99}],
    )
    result = await RS.find_replacements(FakeDb(), _plan("find a replacement", {}))

    assert [r.product_id for r in result.available] == ["36", "37"], "not reordered"
    assert len(result.available) == 2, "an out-of-pool index was admitted"
    # The soft signal is what the reranker scores against, not the hard constraints.
    assert seen["rerank_query"]


@pytest.mark.asyncio
async def test_a_reranker_failure_degrades_order_not_correctness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [_candidate("37", "Wabi-Sabi Bowl", 65.0)]
    _wire_pipeline(monkeypatch, candidates=candidates,
                   inventory={"37": _reconciled("37")}, rerank=[])
    result = await RS.find_replacements(FakeDb(), _plan("find a replacement", {}))
    assert result.rerank_applied is False
    assert [r.product_id for r in result.available] == ["37"]


@pytest.mark.asyncio
async def test_a_price_ceiling_survives_reranking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ceiling is SQL, so a reranker cannot promote something over it.

    Asserted through the predicate that reached retrieval rather than by filtering
    afterwards: a post-rerank check would pass even if the pool were wrong.
    """
    seen = _wire_pipeline(
        monkeypatch, candidates=[_candidate("37", "Wabi-Sabi Bowl", 65.0)],
        inventory={"37": _reconciled("37")},
    )
    plan = _plan("find a replacement under $80", {"price_max_usd": 80})
    await RS.find_replacements(FakeDb(), plan)

    # Asserted on what reached retrieval. A fake pool cannot demonstrate SQL
    # filtering, so proving "no result exceeds the ceiling" against one would be
    # circular — the real check is that the bound predicate is in the query, which
    # live Aurora then enforces.
    assert "price <= %s" in seen["hard_clauses"]
    _clauses, params = RS.compile_replacement_predicates(plan)
    assert 80.0 in params, "the ceiling travelled as a bound parameter"


@pytest.mark.asyncio
async def test_sparse_coverage_is_reported_as_coverage_not_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_pipeline(monkeypatch, candidates=[_candidate("60", "Decanter", 210.0)],
                   inventory={"60": _unverified("60")})
    result = await RS.find_replacements(FakeDb(), _plan("find a replacement", {}))
    assert result.available == []
    assert len(result.close_matches) == 1
    assert "ledger" in result.coverage_note
    assert "40 of 1,000" in result.coverage_note


@pytest.mark.asyncio
async def test_an_empty_pool_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_pipeline(monkeypatch, candidates=[], inventory={})
    result = await RS.find_replacements(FakeDb(), _plan("find a replacement", {}))
    assert result.available == [] and result.close_matches == []
    assert "hard constraints" in result.coverage_note


@pytest.mark.asyncio
async def test_fit_reasons_are_structural_and_checkable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Facts about two catalog rows, not taste claims about a person."""
    _wire_pipeline(
        monkeypatch,
        candidates=[_candidate("37", "Wabi-Sabi Bowl", 65.0,
                               tags=["ceramic", "home", "artisanal"])],
        inventory={"37": _reconciled("37")},
    )
    result = await RS.find_replacements(FakeDb(), _plan("find a replacement", {}))
    reasons = " ".join(result.available[0].fit_reasons).lower()
    assert "same category" in reasons
    assert "below the $165.00 paid" in reasons
    assert "shares catalog tags" in reasons
    for invented in ("eco-conscious", "minimalist", "luxury", "loves", "prefers"):
        assert invented not in reasons


@pytest.mark.asyncio
async def test_the_narrative_and_the_card_cannot_disagree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One object, one availability field. The reference bug made structurally impossible."""
    _wire_pipeline(monkeypatch, candidates=[_candidate("37", "Wabi-Sabi Bowl", 65.0)],
                   inventory={"37": _reconciled("37", 41)})
    result = await RS.find_replacements(FakeDb(), _plan("find a replacement", {}))
    payload = result.available[0].to_payload()
    # The sentence a surface prints and the structured status come from one source.
    assert payload["availabilitySentence"] == INV.describe_availability(
        result.available[0].inventory
    )
    assert payload["inventoryEvidence"]["availableQuantity"] == 41
    assert "41 units" in payload["availabilitySentence"]


@pytest.mark.asyncio
async def test_a_thin_strict_pass_widens_preferences_but_not_constraints(
    monkeypatch: pytest.MonkeyPatch,
    completed_search_plan,
) -> None:
    """Regression: a proposed tag gated validity and returned nothing.

    Replacing a suede boot found zero candidates, because the extractor proposed
    ceramic-ish tags and no Footwear row carried them. A preference is not a
    correctness boundary, so the ladder widens it — and every rung keeps the price
    ceiling, the category and the availability requirement.
    """
    calls: List[List[str]] = []

    class _Hybrid:
        def __init__(self, _db: Any) -> None:
            pass

        async def search(self, **kwargs: Any) -> List[Dict[str, Any]]:
            clauses = list(kwargs.get("hard_clauses") or [])
            calls.append(clauses)
            # The strict rung (tags applied) finds nothing; the widened one finds five.
            if any("tags ?|" in c for c in clauses):
                return []
            return [_candidate(str(i), f"Option {i}", 60.0) for i in range(5)]

    class _Embeddings:
        def embed_query(self, _q: str) -> List[float]:
            return [0.0] * 1024

    class _Rerank:
        def rerank(self, **kwargs: Any) -> List[Dict[str, Any]]:
            return [{"index": i, "relevance_score": 1.0 - i * 0.1} for i in range(5)]

    async def _resolve(_db: Any, pids: Sequence[str]) -> Dict[str, Any]:
        return {pid: _reconciled(pid) for pid in pids}

    from services import embeddings as EMB
    from services import hybrid_search as HS
    from services import inventory_evidence as IE
    from services import rerank as RR

    monkeypatch.setattr(EMB, "EmbeddingService", _Embeddings)
    monkeypatch.setattr(HS, "HybridSearch", _Hybrid)
    monkeypatch.setattr(RR, "get_rerank_service", lambda: _Rerank())
    monkeypatch.setattr(IE, "resolve_inventory_many", _resolve)

    plan = _plan("find an in-stock replacement",
                 {"tags": ["ceramic", "artisanal"], "in_stock_only": True})
    result = await RS.find_replacements(FakeDb(), plan)

    assert len(calls) == 2, "the ladder did not widen after a thin strict pass"
    assert len(result.available) == 3
    # What was widened is on the record.
    assert result.relaxations and result.relaxations[0]["step"] == "drop_tags"

    # And the widened rung still carries every hard constraint.
    widened = calls[1]
    assert any("price <= %s" in c for c in widened)
    assert any("category = ANY(%s)" in c for c in widened)
    assert any("pellier.warehouse_balance" in c for c in widened)
    assert any('"productId" <> %s' in c for c in widened)
    assert not any("tags ?|" in c for c in widened)


@pytest.mark.asyncio
async def test_a_sufficient_strict_pass_does_not_widen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [_candidate(str(i), f"Option {i}", 60.0) for i in range(6)]
    _wire_pipeline(monkeypatch, candidates=candidates,
                   inventory={str(i): _reconciled(str(i)) for i in range(6)})
    plan = _plan("find a replacement", {"tags": ["ceramic"]})
    def unexpected_fallback(_self):
        pytest.fail("A sufficient strict result must not construct the fallback")
    monkeypatch.setattr(type(plan.search_plan), "relaxation_ladder", unexpected_fallback)
    result = await RS.find_replacements(FakeDb(), plan)
    assert result.relaxations == [], "a sufficient strict pass was widened anyway"


@pytest.mark.asyncio
async def test_an_explicit_availability_request_admits_only_reconciled_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second gate on the same rule the SQL predicate enforces."""
    candidates = [
        _candidate("60", "Blown Glass Decanter", 210.0),
        _candidate("37", "Wabi-Sabi Bowl", 65.0),
    ]
    _wire_pipeline(monkeypatch, candidates=candidates, inventory={
        "60": _unverified("60"), "37": _reconciled("37"),
    })
    plan = _plan("find an in-stock replacement", {"in_stock_only": True})
    result = await RS.find_replacements(FakeDb(), plan)

    assert [r.product_id for r in result.available] == ["37"]
    assert result.close_matches == [], (
        "an unverified option was offered against an explicit availability request"
    )


@pytest.mark.asyncio
async def test_without_an_availability_request_the_best_ranked_options_are_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filling the cap with reconciled options first hid the best-ranked option.

    Nothing is claimed that the evidence does not support: each card carries its own
    availability state, and the two groups are headed differently.
    """
    candidates = [
        _candidate("60", "Blown Glass Decanter", 210.0),
        _candidate("44", "Travertine Wall Clock", 248.0),
        _candidate("37", "Wabi-Sabi Bowl", 65.0),
        _candidate("23", "Ceramic Ring Dish", 35.0),
    ]
    _wire_pipeline(monkeypatch, candidates=candidates, inventory={
        "60": _unverified("60"), "44": _unverified("44"),
        "37": _reconciled("37"), "23": _reconciled("23"),
    })
    result = await RS.find_replacements(FakeDb(), _plan("find a replacement", {}))

    # Three cards from the top of the rerank order, not three reconciled ones.
    assert len(result.available) + len(result.close_matches) == 3
    assert [r.product_id for r in result.close_matches] == ["60", "44"]
    assert [r.product_id for r in result.available] == ["37"]
    # The best match is the top-ranked option an operator can actually promise.
    assert result.available[0].role == RS.ROLE_BEST_MATCH
    assert all(r.role == RS.ROLE_ALTERNATIVE for r in result.close_matches)


@pytest.mark.asyncio
async def test_nothing_reconciled_yields_no_best_match_and_a_coverage_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_pipeline(monkeypatch, candidates=[_candidate("60", "Decanter", 210.0)],
                   inventory={"60": _unverified("60")})
    result = await RS.find_replacements(FakeDb(), _plan("find a replacement", {}))
    assert result.available == []
    # No card claims to be the recommendation when none can be promised.
    assert all(r.role == RS.ROLE_ALTERNATIVE for r in result.close_matches)
    assert "40 of 1,000" in result.coverage_note


@pytest.mark.asyncio
async def test_the_concierge_composes_the_parts_without_the_shared_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deliberate divergence, pinned so it stays a decision rather than a drift.

    ``services.planned_hybrid_retrieval.execute_search_plan`` is the shopper
    surfaces' one executor. This pipeline does not run it: it adds two hard
    predicates the executor has no contract for, breaks its ladder on candidate
    count before reranking rather than on returned count after it, and offers
    the reranker every candidate. The module docstring records the reasoning.
    If this test ever fails, the reasoning changed and the docstring is stale.
    """
    from services import planned_hybrid_retrieval as PHR

    async def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            "find_replacements ran the shared executor; update the docstring "
            "in services/replacement_search.py or route it deliberately"
        )

    monkeypatch.setattr(PHR, "execute_search_plan", _forbidden)
    seen = _wire_pipeline(
        monkeypatch,
        candidates=[_candidate("37", "Wabi-Sabi Bowl", 65.0)],
        inventory={"37": _reconciled("37")},
    )

    result = await RS.find_replacements(FakeDb(), _plan("find a replacement", {}))

    assert [r.product_id for r in result.available] == ["37"]
    # The replacement-specific predicate the shared executor cannot express.
    assert any("<> %s" in clause for clause in seen["hard_clauses"])
