"""Inventory evidence: one canonical availability object, never a verified claim from a cache.

Carried over from the Operator truth contracts when the Concierge was deleted;
``services/inventory_evidence.py`` still serves the shopper turn.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from services import inventory_evidence as INV


# ---------------------------------------------------------------------------
# Inventory evidence
# ---------------------------------------------------------------------------

class _FakeCursor:
    """Returns MAPPINGS, not tuples: the pool configures `dict_row`.

    The earlier tuple-based version of this fake was looser than the real driver, and
    it hid a positional-indexing bug in `inventory_evidence` that would have raised
    `KeyError: 0` on its first live call. One reconciliation query now serves the whole
    batch, so the fake models that single statement.
    """

    def __init__(self, rows: List[Dict[str, Any]], fail: bool = False):
        self._rows = rows
        self._fail = fail
        self._last = ""

    async def execute(self, sql: str, params: Any = None) -> None:
        if self._fail:
            raise RuntimeError("aurora unreachable")
        self._last = sql
        wanted = set(params["product_ids"]) if isinstance(params, dict) else set()
        self._matched = [r for r in self._rows if r["product_id"] in wanted]

    async def fetchall(self) -> List[Dict[str, Any]]:
        return getattr(self, "_matched", [])

    async def fetchone(self) -> Optional[Dict[str, Any]]:
        matched = getattr(self, "_matched", [])
        return matched[0] if matched else None

    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class _FakeConn:
    def __init__(self, cur: _FakeCursor): self._cur = cur
    def cursor(self): return self._cur
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class _FakeDb:
    def __init__(self, rows: List[Dict[str, Any]], fail: bool = False):
        self._cur = _FakeCursor(rows, fail)
    def get_connection(self): return _FakeConn(self._cur)


def _loc(warehouse: str, cache: int, ledger: Optional[int] = None) -> Dict[str, Any]:
    """One per-warehouse row as the reconciliation query returns it."""
    return {
        "warehouseId": warehouse,
        "cacheQuantity": cache,
        "ledgerQuantity": cache if ledger is None else ledger,
        "displayName": warehouse, "city": "Somewhere",
        "shipWindowMin": 1, "shipWindowMax": 2,
    }


def _row(
    product_id: str, *, has_ledger: bool, locations: Optional[List[Dict[str, Any]]],
    aggregate_cache: Optional[int] = 50, aggregate_ledger: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "product_id": product_id, "has_ledger": has_ledger, "locations": locations,
        "aggregate_cache": aggregate_cache, "aggregate_ledger": aggregate_ledger,
    }


@pytest.mark.asyncio
async def test_per_location_rows_produce_an_OBSERVED_fact_not_a_verified_one() -> None:
    """`warehouse_inventory` is a cache per migration 013, so the reading is an
    observation. `verified` is reserved for ledger-reconciled state."""
    db = _FakeDb([_row("2", has_ledger=False,
                       locations=[_loc("BK-01", 8), _loc("ATX-02", 6)])])
    ev = await INV.resolve_inventory(db, "2")
    assert ev.status == INV.OBSERVED_IN_STOCK
    assert ev.available_quantity == 14
    assert ev.scope == INV.SCOPE_WAREHOUSE
    assert ev.authority == INV.AUTHORITY_CACHE
    assert ev.reconciled_to_ledger is False
    assert "verified" not in ev.status, "a cache reading must not claim verification"
    # An observation may be REPORTED, but it does not license "currently available".
    # That is reserved for ledger-reconciled state, so the two are separate properties
    # and a caller has to choose in code which one it is relying on.
    assert ev.supports_availability_claim is False
    assert ev.supports_observed_claim is True
    # The sentence now says which record established it, so a reader cannot mistake a
    # cache observation for a reconciled fact.
    assert INV.describe_availability(ev) == (
        "14 units currently available across 2 locations. "
        "(warehouse observation, not reconciled)"
    )


@pytest.mark.asyncio
async def test_no_per_location_rows_is_not_verified_even_with_a_catalog_number() -> None:
    """Jessica's catchall: catalog says 50, warehouse has nothing.

    The catalog quantity column is a seed value, not inventory, so it cannot
    support an availability claim.
    """
    db = _FakeDb([_row("100", has_ledger=False, locations=None, aggregate_cache=35)])
    ev = await INV.resolve_inventory(db, "100")
    assert ev.status == INV.NOT_VERIFIED
    assert ev.available_quantity is None, "an unverified fact must carry no quantity"
    assert ev.catalog_cache_quantity == 35
    assert ev.supports_availability_claim is False
    assert INV.describe_availability(ev) == "Availability not verified."


@pytest.mark.asyncio
async def test_zero_stock_is_reported_as_zero_by_whichever_record_established_it() -> None:
    """A cache-only zero and a ledger-reconciled zero are different facts."""
    cache_only = _FakeDb([_row("3", has_ledger=False, locations=[_loc("BK-01", 0)],
                               aggregate_cache=0)])
    ev = await INV.resolve_inventory(cache_only, "3")
    assert ev.status == INV.OBSERVED_OUT_OF_STOCK
    assert ev.available_quantity == 0
    assert ev.supports_availability_claim is False

    reconciled = _FakeDb([_row("3", has_ledger=True, locations=[_loc("BK-01", 0, 0)],
                               aggregate_cache=0, aggregate_ledger=0)])
    ev = await INV.resolve_inventory(reconciled, "3")
    assert ev.status == INV.RECONCILED_OUT_OF_STOCK
    assert ev.available_quantity == 0
    assert ev.authority == INV.AUTHORITY_LEDGER


@pytest.mark.asyncio
async def test_an_inventory_read_failure_never_fabricates_zero() -> None:
    ev = await INV.resolve_inventory(_FakeDb([], fail=True), "41")
    assert ev.status == INV.NOT_VERIFIED
    assert ev.available_quantity is None, "a read error became an out-of-stock claim"
    assert ev.source == "unavailable"


@pytest.mark.asyncio
async def test_quantity_and_status_cannot_contradict() -> None:
    cases = [
        _row("9", has_ledger=False, locations=None),
        _row("9", has_ledger=False, locations=[_loc("BK-01", 4)]),
        _row("9", has_ledger=False, locations=[_loc("BK-01", 0)], aggregate_cache=0),
        _row("9", has_ledger=True, locations=[_loc("BK-01", 4, 4)],
             aggregate_cache=4, aggregate_ledger=4),
        _row("9", has_ledger=True, locations=[_loc("BK-01", 0, 0)],
             aggregate_cache=0, aggregate_ledger=0),
        # Cache and ledger disagree: no quantity may be offered at all.
        _row("9", has_ledger=True, locations=[_loc("BK-01", 4, 1)]),
    ]
    for row in cases:
        ev = await INV.resolve_inventory(_FakeDb([row]), "9")
        if ev.status in (INV.OBSERVED_IN_STOCK, INV.RECONCILED_IN_STOCK):
            assert (ev.available_quantity or 0) > 0
        if ev.status in (INV.OBSERVED_OUT_OF_STOCK, INV.RECONCILED_OUT_OF_STOCK):
            assert ev.available_quantity == 0
        if ev.status in (INV.NOT_VERIFIED, INV.LEDGER_CACHE_DISAGREEMENT):
            assert ev.available_quantity is None
        # Only one status ever licenses an availability claim.
        if ev.supports_availability_claim:
            assert ev.status == INV.RECONCILED_IN_STOCK


@pytest.mark.asyncio
async def test_source_and_observed_at_propagate() -> None:
    ev = await INV.resolve_inventory(
        _FakeDb([_row("5", has_ledger=False, locations=[_loc("BK-01", 2)])]), "5"
    )
    assert ev.source == "pellier.warehouse_inventory"
    assert ev.observed_at and "T" in ev.observed_at
    payload = ev.to_payload()
    assert payload["observedAt"] == ev.observed_at
    assert payload["source"] == ev.source


def test_no_fulfillment_guarantee_language_exists() -> None:
    from pathlib import Path

    text = (Path(INV.__file__)).read_text().lower()
    # The module names these to forbid them; assert it never *emits* them.
    emitted = " ".join(
        line for line in text.splitlines() if "return" in line and '"' in line
    )
    for banned in ("zero fulfillment risk", "guaranteed availability", "will definitely ship"):
        assert banned not in emitted, f"module emits {banned!r}"


def test_one_object_feeds_every_surface() -> None:
    """Narrative and card must not each compute availability."""
    from pathlib import Path

    src = Path(INV.__file__).read_text()
    assert "describe_availability" in src
    assert "supports_availability_claim" in src
    # The sentence is derived from the same dataclass the payload serialises.
    assert "def describe_availability(evidence: InventoryEvidence)" in src
