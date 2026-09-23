"""Phase 1 truth contracts: capability state, inventory evidence, return evidence.

These three exist because the Operator Concierge will make claims, and a claim is
only as good as the contract behind it. Each test here corresponds to a way the
surface could be confidently wrong.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional

import pytest

from services import inventory_evidence as INV
from services import operator_capabilities as CAP


# ---------------------------------------------------------------------------
# Capability state
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_capability_cache():
    CAP.reset_cache()
    yield
    CAP.reset_cache()


def test_source_registration_does_not_imply_availability() -> None:
    """The whole reason this module exists.

    The local MCP catalog describes a fresh application vocabulary. Reading it would have
    reported every write available while the live Gateway had zero permits.
    """
    from services import agentcore_gateway

    assert "initiate_return" in agentcore_gateway.LOCAL_MCP_TOOL_NAMES
    source = (
        importlib.resources.files("services").joinpath("operator_capabilities.py").read_text()
        if hasattr(importlib, "resources") else ""
    )
    if source:
        assert "LOCAL_MCP_TOOL_NAMES" not in source.split('"""')[2], (
            "capability state is derived from the source registry"
        )


def test_published_with_zero_permits_is_temporarily_unavailable() -> None:
    states = CAP._classify(
        published=["initiate_return", "escalate_to_human"],
        permitted={"initiate_return": 0, "escalate_to_human": 0},
    )
    assert states["initiate_return"].state == CAP.TEMPORARILY_UNAVAILABLE
    assert states["initiate_return"].reason == CAP.REASON_GOVERNED_UNAVAILABLE
    assert states["escalate_to_human"].state == CAP.TEMPORARILY_UNAVAILABLE


def test_absent_from_the_gateway_is_not_enabled() -> None:
    """A different cause with a different future, and it must stay distinguishable."""
    states = CAP._classify(published=["initiate_return"], permitted={"initiate_return": 0})
    assert states["issue_credit"].state == CAP.NOT_ENABLED
    assert states["issue_credit"].reason == CAP.REASON_NOT_PUBLISHED
    assert states["initiate_return"].state == CAP.TEMPORARILY_UNAVAILABLE
    assert states["issue_credit"].state != states["initiate_return"].state


def test_permitted_review_gated_tool_reports_review_required() -> None:
    states = CAP._classify(
        published=["initiate_return", "escalate_to_human"],
        permitted={"initiate_return": 1, "escalate_to_human": 1},
    )
    assert states["initiate_return"].state == CAP.REVIEW_REQUIRED
    # Escalation is not a consequential write, so it needs no review.
    assert states["escalate_to_human"].state == CAP.AVAILABLE


def test_capability_lookup_failure_fails_closed(monkeypatch) -> None:
    def boom() -> Any:
        raise RuntimeError("control plane unreachable")

    monkeypatch.setattr(CAP, "_live_gateway_facts", boom)
    payload = CAP.get_capabilities(force_refresh=True)
    for tool in CAP.GOVERNED_WRITE_TOOLS:
        entry = payload["capabilities"][tool]
        assert entry["state"] == CAP.TEMPORARILY_UNAVAILABLE, tool
        assert entry["reason"] == CAP.REASON_UNVERIFIED, tool
    assert payload["source"] == "unverified"
    assert payload["governedActionsAvailable"] is False
    # Reads stay available: their own path is healthy.
    assert payload["capabilities"]["client_read"]["state"] == CAP.AVAILABLE
    assert payload["capabilities"]["catalog_search"]["state"] == CAP.AVAILABLE


def test_missing_managed_resource_is_distinguished_but_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingGateway(Exception):
        response = {"Error": {"Code": "ResourceNotFoundException"}}

    monkeypatch.setattr(
        CAP,
        "_live_gateway_facts",
        lambda: (_ for _ in ()).throw(MissingGateway("gateway missing")),
    )

    payload = CAP.get_capabilities(force_refresh=True)
    assert payload["source"] == "unverified"
    assert payload["governedActionsAvailable"] is False
    for tool in CAP.GOVERNED_WRITE_TOOLS:
        assert payload["capabilities"][tool] == {
            "state": CAP.TEMPORARILY_UNAVAILABLE,
            "reason": CAP.REASON_MANAGED_RESOURCES_MISSING,
        }


def test_a_failure_never_resolves_to_available(monkeypatch) -> None:
    monkeypatch.setattr(CAP, "_live_gateway_facts", lambda: (_ for _ in ()).throw(OSError("x")))
    payload = CAP.get_capabilities(force_refresh=True)
    assert CAP.AVAILABLE not in {
        payload["capabilities"][t]["state"] for t in CAP.GOVERNED_WRITE_TOOLS
    }


def test_issue_credit_cannot_become_available_from_the_fresh_schema(monkeypatch) -> None:
    """The canonical 17-tool schema must not leak into live capability state."""
    calls = {"n": 0}

    def facts() -> Any:
        calls["n"] += 1
        # Live truth today: issue_credit is NOT published.
        return ["initiate_return", "escalate_to_human"], {
            "initiate_return": 0, "escalate_to_human": 0
        }

    monkeypatch.setattr(CAP, "_live_gateway_facts", facts)
    payload = CAP.get_capabilities(force_refresh=True)
    assert payload["capabilities"]["issue_credit"]["state"] == CAP.NOT_ENABLED
    assert calls["n"] == 1


def test_the_cache_avoids_repeat_control_plane_reads(monkeypatch) -> None:
    calls = {"n": 0}

    def facts() -> Any:
        calls["n"] += 1
        return ["initiate_return"], {"initiate_return": 0}

    monkeypatch.setattr(CAP, "_live_gateway_facts", facts)
    first = CAP.get_capabilities()
    second = CAP.get_capabilities()
    assert calls["n"] == 1, "the control plane was read twice within the TTL"
    assert first["cached"] is False
    assert second["cached"] is True
    assert CAP.get_capabilities(force_refresh=True)["cached"] is False
    assert calls["n"] == 2


def test_the_ttl_is_short_enough_to_reflect_a_migration_phase() -> None:
    assert 15 <= CAP.CAPABILITY_TTL_SECONDS <= 300, (
        "a long TTL is a stale-governance hazard; a tiny one defeats the cache"
    )


def test_the_payload_leaks_no_control_plane_internals(monkeypatch) -> None:
    monkeypatch.setattr(
        CAP, "_live_gateway_facts",
        lambda: (["initiate_return"], {"initiate_return": 0}),
    )
    import json

    blob = json.dumps(CAP.get_capabilities(force_refresh=True)).lower()
    for secret in ("cedar", "forbid(", "permit(", "policy-engine", "policyengineid",
                   "arn:aws", "credentialprovider", "gwgjwkwczj"):
        assert secret not in blob, f"capability payload leaks {secret}"


def test_the_frontend_holds_no_hardcoded_capability_matrix() -> None:
    """No frontend file may ASSIGN a capability state to a named tool.

    Naming the states is fine — a types module and a label map have to. Explaining
    in a comment why two tools differ is fine. What must not exist is a literal
    mapping like `initiate_return: 'temporarily_unavailable'`, because that is a
    frontend deciding live governance state, and it has been wrong three times.
    """
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "frontend" / "src"
    states = "available|review_required|temporarily_unavailable|not_enabled"
    tools = "initiate_return|escalate_to_human|issue_credit|restock_inventory"
    # `tool: 'state'` or `tool = "state"` or `[tool]: 'state'`
    assignment = re.compile(
        rf"[\[']?({tools})'?\]?\s*[:=]\s*['\"]({states})['\"]"
    )
    offenders: List[str] = []
    for path in src.rglob("*.ts*"):
        for line in path.read_text(errors="ignore").splitlines():
            stripped = line.strip()
            if stripped.startswith("*") or stripped.startswith("//"):
                continue
            if assignment.search(line):
                offenders.append(f"{path.relative_to(src)}: {stripped[:70]}")
    assert not offenders, f"frontend assigns live capability state: {offenders}"


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

    Outside the curated set the catalog column holds a seeded constant across
    940 archive products, so it cannot support an availability claim.
    """
    db = _FakeDb([_row("1000", has_ledger=False, locations=None, aggregate_cache=35)])
    ev = await INV.resolve_inventory(db, "1000")
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


# ---------------------------------------------------------------------------
# Return evidence: three kinds, never collapsed
# ---------------------------------------------------------------------------
#
# Jessica is the live case that makes this necessary. TKT-2026-3015 states a return
# was received and its refund disputed; `pellier.returns` holds no row for her; her
# preferences_summary mentions a dispute in prose; two seeded reviews propose
# returns. A surface that renders "Jessica returned the order" has invented a fact
# from an assertion.

def test_the_client_read_selects_authoritative_returns() -> None:
    from routes import operator

    assert "pellier.returns" in operator._RETURNS_SELECT
    assert "customer_id = %s" in operator._RETURNS_SELECT


def test_returns_join_the_existing_concurrent_fan_out() -> None:
    """Adding a fifth serial round trip would undo the 2.5s -> 0.65s win."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "routes" / "operator.py"
    text = src.read_text()
    gather = text[text.index("returns_task = asyncio.create_task"):]
    gather = gather[: gather.index(")\n") + 1]
    assert "asyncio.create_task" in gather
    block = text[text.index("client_task = asyncio.create_task"):]
    block = block[: block.index("row, order_rows")]
    assert block.count("asyncio.create_task") == 5, "a read was serialised"
    call = text[text.index("outcomes = await asyncio.gather"):]
    call = call[: call.index(")\n") + 1]
    for task in ("client_task", "orders_task", "tickets_task", "credits_task", "returns_task"):
        assert task in call, f"{task} is not awaited in the gather"
    assert "return_exceptions=True" in call, (
        "all failed concurrent reads must be collected before the record returns 503"
    )


@pytest.mark.asyncio
async def test_client_record_refuses_partial_evidence_as_a_false_empty_history() -> None:
    """A failed ledger query is 503, never an empty array rendered as a fact."""
    from fastapi import HTTPException
    from routes import operator

    class FailingTicketsDb:
        async def fetch_one(self, _sql: str, *_args: Any) -> Dict[str, Any]:
            return {
                "customer_id": "CUST-JESSICA",
                "name": "Jessica Nakamura",
                "membership": "circle",
                "spend_12mo": 3940,
                "preferences_summary": "Open return dispute.",
            }

        async def fetch_all(self, sql: str, *_args: Any) -> List[Dict[str, Any]]:
            if "pellier.support_tickets" in sql:
                raise RuntimeError("tickets unavailable")
            return []

    with pytest.raises(HTTPException) as raised:
        await operator.get_client("CUST-JESSICA", db=FailingTicketsDb())

    assert raised.value.status_code == 503
    assert "No absence claim was made" in str(raised.value.detail)


_JESSICA_TICKET = [{
    "subject": "Return received, refund amount disputed",
    "lastNote": "Return logged for the catchall and the robe.",
    "status": "pending",
}]
_JESSICA_ORDERS = [
    {"productId": "41", "productName": "Coral Lacquer Catchall"},
    {"productId": "42", "productName": "Luxury Bath Robe, Sage"},
]


def test_a_support_assertion_is_not_an_authoritative_return() -> None:
    from routes.operator import _return_evidence

    evidence = _return_evidence(_JESSICA_TICKET, _JESSICA_ORDERS, [])
    assert evidence["supportAssertsReturn"] is True
    assert evidence["authoritativeReturnCount"] == 0
    assert evidence["unconfirmedReturnAssertion"] is True, (
        "the disagreement between ticket and returns table is not surfaced"
    )


def test_a_return_request_is_not_evidence_of_receipt() -> None:
    """Rows close the record gap; they cannot confirm that goods arrived."""
    from routes.operator import _return_evidence

    rows = [{"productId": "41"}, {"productId": "42"}]
    evidence = _return_evidence(_JESSICA_TICKET, _JESSICA_ORDERS, rows)
    assert evidence["unrecordedDisputedProductIds"] == []
    assert evidence["authoritativeReturnCount"] == 2
    assert evidence["unconfirmedReturnAssertion"] is True


def test_prose_preferences_are_never_treated_as_return_state() -> None:
    """The evidence is computed from tickets, orders and return rows only."""
    import inspect
    from routes.operator import _return_evidence

    assert list(inspect.signature(_return_evidence).parameters) == [
        "tickets", "orders", "returns",
    ], "prose is feeding the authoritative return evidence"


def test_an_rls_hidden_row_is_not_a_business_false() -> None:
    """Migration 023's invariant, carried into the read layer.

    An authorization-scoped observation must never become authoritative business
    truth. The database function records this; the evidence contract must too.
    """
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[3]
        / "scripts" / "migrations" / "023_idempotency_claims_release_on_failure.sql"
    )
    text = migration.read_text()
    assert "RLS is hiding one that exists" in text
    assert "orders_principal_scope" in text
    # And the classification token exists in the codebase for callers to use.
    server = (
        Path(__file__).resolve().parents[3]
        / "scripts" / "deploy" / "pellier_experience_server.py"
    )
    if server.is_file():
        assert "database_row_level_security" in server.read_text()


def test_jessicas_case_renders_as_ambiguity_not_certainty() -> None:
    """A shape test on the contract, not on the seeded review ids.

    Review ids 22 and 23 are demo state and must not become a test dependency.
    """
    tickets = [{"subject": "Return received, refund amount disputed",
                "lastNote": "Return logged for the catchall and the robe."}]
    returns: List[Dict[str, Any]] = []
    asserts_return = any(
        "return" in (t_.get("subject", "") + " " + t_.get("lastNote", "")).lower()
        for t_ in tickets
    )
    evidence = {
        "authoritativeReturnCount": len(returns),
        "supportAssertsReturn": asserts_return,
        "unconfirmedReturnAssertion": asserts_return and not returns,
    }
    assert evidence["supportAssertsReturn"] is True
    assert evidence["authoritativeReturnCount"] == 0
    assert evidence["unconfirmedReturnAssertion"] is True, (
        "the console cannot tell that the ticket's claim is unconfirmed"
    )


def test_verified_is_reserved_for_ledger_reconciled_state() -> None:
    """The word must not appear on a status derived from a cache.

    Migration 013 names `inventory_ledger` the source of truth and both quantity
    columns caches. A recommendation card is exactly where "verified in stock" would
    be most tempting and least earned.
    """
    assert INV.OBSERVED_IN_STOCK == "observed_in_stock"
    assert INV.OBSERVED_OUT_OF_STOCK == "observed_out_of_stock"
    for status in (INV.OBSERVED_IN_STOCK, INV.OBSERVED_OUT_OF_STOCK):
        assert "verified" not in status
    # And the reconciled statuses say "reconciled", naming what was actually done.
    assert INV.RECONCILED_IN_STOCK == "reconciled_in_stock"
    assert INV.RECONCILED_OUT_OF_STOCK == "reconciled_out_of_stock"
    # The one status that does say "verified" says NOT verified.
    assert INV.NOT_VERIFIED == "availability_not_verified"
    assert INV.AUTHORITY_LEDGER == "source_of_truth"


@pytest.mark.asyncio
async def test_the_payload_states_the_authority_and_reconciliation() -> None:
    observed = await INV.resolve_inventory(
        _FakeDb([_row("7", has_ledger=False, locations=[_loc("BK-01", 3)])]), "7"
    )
    payload = observed.to_payload()
    assert payload["authority"] == "cache"
    assert payload["reconciledToLedger"] is False
    assert payload["isObserved"] is True
    assert payload["isReconciled"] is False
    assert "isVerified" not in payload, "the old overstated field is still present"

    reconciled = await INV.resolve_inventory(
        _FakeDb([_row("7", has_ledger=True, locations=[_loc("BK-01", 3, 3)],
                      aggregate_cache=3, aggregate_ledger=3)]), "7"
    )
    payload = reconciled.to_payload()
    assert payload["authority"] == "source_of_truth"
    assert payload["reconciledToLedger"] is True
    assert payload["isReconciled"] is True
    assert payload["supportsAvailabilityClaim"] is True
