"""One canonical inventory fact, so narrative and product card cannot disagree.

Why this exists
---------------

Pellier holds three representations of stock, and they are not interchangeable.
Established from the migrations rather than assumed:

    pellier.inventory_ledger        migration 013 states it plainly: "The ledger is
                                    the source of truth; the two quantity columns
                                    become caches that a check query can reconcile
                                    against." One signed ``delta`` row per movement.
                                    Baseline coverage: all 100 curated products
                                    (292 ``seed`` rows on a fresh reset).

    pellier.warehouse_inventory     migration 006, per-warehouse counts. The
                                    fulfillment-grade cache, and the one a shopper's
                                    ``check_inventory`` reads.

    product_catalog.quantity        migration 001 creates it as the AGGREGATE
                                    cache. It is a seed value, not inventory, so it
                                    cannot support an availability claim.

How the ledger is reconciled
----------------------------

Migration 013 supplies the derivation, so this module does not invent one:

    pellier.warehouse_balance   VIEW  sum(delta) GROUP BY product_id, warehouse_id
                                      (warehouse_id IS NOT NULL)
    pellier.catalog_balance     VIEW  sum(delta) GROUP BY product_id
    pellier.reconcile_inventory() FUNCTION  rows where a cache disagrees with its
                                      balance; zero rows means everything agrees

This module reads those views rather than re-deriving ``sum(delta)``, so if the
derivation ever changes, availability follows it instead of drifting from it.

The five states
---------------

``reconciled_in_stock`` / ``reconciled_out_of_stock``
    Ledger movements exist for this product AND every per-warehouse cache row
    agrees with its ledger balance. The quantity reported is the LEDGER's, because
    that is the source of truth. This is the only state that licenses "currently
    available".

``ledger_cache_disagreement``
    Ledger movements exist and a per-warehouse cache contradicts its balance. Both
    numbers are retained and neither is silently preferred. No availability claim is
    licensed: the authoritative per-location number is contested, and quietly
    picking a side is how an operator promises a unit that is not there.

``observed_in_stock`` / ``observed_out_of_stock``
    Per-warehouse rows exist but NO ledger movement does, so there is a cache
    reading and nothing to reconcile it against. ``authority="cache"``.

``availability_not_verified``
    No per-location evidence at all - the case for most catalog rows - or the
    read failed. ``available_quantity`` is None, so a caller cannot render a number
    that was never established.

The aggregate cache is reported separately and is never the basis of an availability
claim. Where it disagrees with ``catalog_balance`` the discrepancy is carried on
``aggregate_cache_stale`` rather than resolved: measured 2026-08-27, products 11, 21
and 31 sit at the seed constant 50 while the ledger says 39, 41 and 49. That is real
drift in live data, and hiding it would be the one thing this module exists to prevent.

Every surface that mentions availability — narrative sentence, recommendation
rationale, product card, action eligibility — reads the SAME object returned here.
That is what makes the reference implementation's defect ("the item remains in
stock" beside a card reading "Out of stock") impossible rather than merely
discouraged.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Status values. Deliberately five, not a boolean: "we could not establish it",
# "there is none", and "our two records disagree" are three different answers, and
# collapsing them is how a UI ends up claiming stock it never established.
#
# "verified"/"reconciled" is reserved for state agreed with `inventory_ledger`.
# A reading taken from `warehouse_inventory` alone is an OBSERVATION of a cache, and
# calling it verified would overstate the evidence in exactly the place a
# recommendation card is most tempted to.
RECONCILED_IN_STOCK = "reconciled_in_stock"
RECONCILED_OUT_OF_STOCK = "reconciled_out_of_stock"
OBSERVED_IN_STOCK = "observed_in_stock"
OBSERVED_OUT_OF_STOCK = "observed_out_of_stock"
LEDGER_CACHE_DISAGREEMENT = "ledger_cache_disagreement"
NOT_VERIFIED = "availability_not_verified"

# Where an observed quantity came from.
SCOPE_WAREHOUSE = "warehouse"

# Authority of the reading, so a caller can tell a cache from a source of truth.
AUTHORITY_CACHE = "cache"
AUTHORITY_LEDGER = "source_of_truth"

# One round trip for N products. A per-candidate query would cost one Aurora
# round trip each; a replacement search reconciles a dozen candidates at once.
#
# `merged` is the warehouse arm of `pellier.reconcile_inventory()` restricted to the
# requested products: a FULL OUTER JOIN so a cache row with no balance and a balance
# with no cache row both surface as disagreements rather than vanishing.
_BATCH_SQL = """
WITH targets AS (
    SELECT unnest(%(product_ids)s::text[]) AS product_id
),
cache AS (
    SELECT t.product_id, wi.warehouse_id, wi.quantity
      FROM targets t
      JOIN pellier.warehouse_inventory wi ON wi.product_id = t.product_id
),
ledger AS (
    SELECT t.product_id, wb.warehouse_id, wb.quantity
      FROM targets t
      JOIN pellier.warehouse_balance wb ON wb.product_id = t.product_id
),
merged AS (
    SELECT COALESCE(c.product_id, l.product_id)     AS product_id,
           COALESCE(c.warehouse_id, l.warehouse_id) AS warehouse_id,
           COALESCE(c.quantity, 0)                  AS cache_quantity,
           COALESCE(l.quantity, 0)                  AS ledger_quantity
      FROM cache c
      FULL OUTER JOIN ledger l
        ON l.product_id = c.product_id
       AND l.warehouse_id = c.warehouse_id
)
SELECT t.product_id,
       EXISTS (SELECT 1 FROM pellier.inventory_ledger il
                WHERE il.product_id = t.product_id)      AS has_ledger,
       (SELECT json_agg(json_build_object(
                   'warehouseId',    m.warehouse_id,
                   'cacheQuantity',  m.cache_quantity,
                   'ledgerQuantity', m.ledger_quantity,
                   'displayName',    w.display_name,
                   'city',           w.city,
                   'shipWindowMin',  w.ship_window_min,
                   'shipWindowMax',  w.ship_window_max)
                 ORDER BY m.ledger_quantity DESC, m.warehouse_id)
          FROM merged m
          LEFT JOIN pellier.warehouses w ON w.id = m.warehouse_id
         WHERE m.product_id = t.product_id)              AS locations,
       (SELECT pc.quantity FROM pellier.product_catalog pc
         WHERE pc."productId" = t.product_id)            AS aggregate_cache,
       (SELECT cb.quantity FROM pellier.catalog_balance cb
         WHERE cb.product_id = t.product_id)             AS aggregate_ledger
  FROM targets t
"""

# The SQL form of "reconciled and currently available", for callers that must apply
# availability as a HARD retrieval constraint rather than as a post-filter.
#
# Two predicates, both required. `product_catalog.quantity > 0` — what the shopper
# planner compiles for `in_stock_only` — is deliberately NOT used: it is the
# aggregate cache, it carries a seed constant for most rows, and letting it
# satisfy an explicit "in stock" request would make the phrase mean nothing.
#
# Correlates on `product_catalog."productId"`, so it composes with any query whose
# FROM clause is `pellier.product_catalog`.
RECONCILED_AVAILABLE_SQL = """(
        EXISTS (
            SELECT 1 FROM pellier.warehouse_balance wb
             WHERE wb.product_id = product_catalog."productId"
               AND wb.quantity > 0
        )
        AND NOT EXISTS (
            SELECT 1
              FROM pellier.warehouse_inventory wi
              FULL OUTER JOIN pellier.warehouse_balance wb2
                   ON wb2.product_id = wi.product_id
                  AND wb2.warehouse_id = wi.warehouse_id
             WHERE COALESCE(wi.product_id, wb2.product_id)
                   = product_catalog."productId"
               AND COALESCE(wi.quantity, 0) <> COALESCE(wb2.quantity, 0)
        )
    )"""


@dataclass
class InventoryEvidence:
    """A single inventory fact, with its own confidence attached.

    ``available_quantity`` is None whenever nothing authoritative was established.
    A caller cannot accidentally render a number that was never established,
    because there is no number to render.
    """

    product_id: str
    status: str
    available_quantity: Optional[int] = None
    scope: Optional[str] = None
    locations: List[Dict[str, Any]] = field(default_factory=list)
    source: str = ""
    # The role the source plays in Pellier's inventory hierarchy. Carried so a
    # surface cannot present a cache reading as a reconciled fact.
    authority: Optional[str] = None
    reconciled_to_ledger: bool = False
    observed_at: str = ""
    # The aggregate column, carried for transparency and explicitly NOT an
    # availability claim. Named so no caller mistakes it for one.
    catalog_cache_quantity: Optional[int] = None
    # The ledger's own catalog-level balance, and whether the aggregate cache has
    # fallen behind it. Real in live data for products 11, 21 and 31.
    catalog_ledger_quantity: Optional[int] = None
    aggregate_cache_stale: bool = False
    # Per-warehouse rows where cache and ledger disagree. Retained, never resolved.
    disagreements: List[Dict[str, Any]] = field(default_factory=list)
    note: str = ""

    @property
    def is_reconciled(self) -> bool:
        """The ledger and the per-warehouse cache agree."""
        return self.status in (RECONCILED_IN_STOCK, RECONCILED_OUT_OF_STOCK)

    @property
    def is_observed(self) -> bool:
        """A cache reading exists. NOT the same as reconciled against the ledger."""
        return self.status in (OBSERVED_IN_STOCK, OBSERVED_OUT_OF_STOCK)

    @property
    def supports_availability_claim(self) -> bool:
        """Whether a surface may say units are currently available.

        Reconciled positive stock only. A cache observation does not qualify, and
        neither does a disagreement — that is the whole point of separating them.
        """
        return (
            self.status == RECONCILED_IN_STOCK and (self.available_quantity or 0) > 0
        )

    @property
    def supports_observed_claim(self) -> bool:
        """Whether a surface may report an unreconciled cache observation.

        Distinct from :attr:`supports_availability_claim` so a caller has to choose,
        in code, whether a cache reading is good enough for what it is about to say.
        """
        return self.status == OBSERVED_IN_STOCK and (self.available_quantity or 0) > 0

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        return {
            "productId": payload["product_id"],
            "status": payload["status"],
            "availableQuantity": payload["available_quantity"],
            "scope": payload["scope"],
            "locations": payload["locations"],
            "source": payload["source"],
            "observedAt": payload["observed_at"],
            "catalogCacheQuantity": payload["catalog_cache_quantity"],
            "catalogLedgerQuantity": payload["catalog_ledger_quantity"],
            "aggregateCacheStale": payload["aggregate_cache_stale"],
            "disagreements": payload["disagreements"],
            "authority": payload["authority"],
            "reconciledToLedger": payload["reconciled_to_ledger"],
            "note": payload["note"],
            "isReconciled": self.is_reconciled,
            "isObserved": self.is_observed,
            "supportsAvailabilityClaim": self.supports_availability_claim,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unavailable(product_id: str) -> InventoryEvidence:
    return InventoryEvidence(
        product_id=product_id,
        status=NOT_VERIFIED,
        source="unavailable",
        observed_at=_now(),
        note="Inventory could not be read. No availability claim has been made.",
    )


async def resolve_inventory_many(
    db: Any, product_ids: Sequence[str]
) -> Dict[str, InventoryEvidence]:
    """Resolve availability for many products in one round trip.

    Never raises. A read failure yields ``availability_not_verified`` for every
    requested product rather than a zero, because a zero would be indistinguishable
    from an observed empty shelf and would let a transport error read as an
    out-of-stock business fact.
    """
    wanted = [str(pid) for pid in product_ids if str(pid or "").strip()]
    if not wanted:
        return {}

    try:
        async with db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_BATCH_SQL, {"product_ids": wanted})
                rows = await cur.fetchall()
    except Exception as exc:  # noqa: BLE001 - an unknown is a valid answer here
        logger.warning("inventory read failed for %d products: %s", len(wanted), exc)
        return {pid: _unavailable(pid) for pid in wanted}

    resolved: Dict[str, InventoryEvidence] = {}
    for row in rows:
        # Mappings, not tuples: the pool configures `dict_row`. An earlier revision
        # indexed these positionally, which would have raised `KeyError: 0` on its
        # first live call — it passed only because the test fake was looser than the
        # real driver.
        pid = str(row["product_id"])
        resolved[pid] = _evidence_from_row(pid, row)
    for pid in wanted:
        resolved.setdefault(pid, _unavailable(pid))
    return resolved


async def resolve_inventory(db: Any, product_id: str) -> InventoryEvidence:
    """The one place that decides what is known about a product's availability."""
    pid = str(product_id)
    batch = await resolve_inventory_many(db, [pid])
    return batch.get(pid) or _unavailable(pid)


def _evidence_from_row(pid: str, row: Dict[str, Any]) -> InventoryEvidence:
    """Turn one reconciliation row into the canonical fact. Pure, so it is testable."""
    has_ledger = bool(row.get("has_ledger"))
    aggregate_cache = _as_int(row.get("aggregate_cache"))
    aggregate_ledger = _as_int(row.get("aggregate_ledger"))
    aggregate_stale = (
        has_ledger
        and aggregate_cache is not None
        and aggregate_ledger is not None
        and aggregate_cache != aggregate_ledger
    )

    locations: List[Dict[str, Any]] = []
    disagreements: List[Dict[str, Any]] = []
    for entry in row.get("locations") or []:
        cache_qty = _as_int(entry.get("cacheQuantity")) or 0
        ledger_qty = _as_int(entry.get("ledgerQuantity")) or 0
        location = {
            "warehouseId": entry.get("warehouseId"),
            # `quantity` is the number a surface may print, and it comes from the
            # ledger whenever there is one. Both are carried so the discrepancy
            # survives into expanded evidence.
            "quantity": ledger_qty if has_ledger else cache_qty,
            "cacheQuantity": cache_qty,
            "ledgerQuantity": ledger_qty if has_ledger else None,
            "displayName": entry.get("displayName"),
            "city": entry.get("city"),
            "shipWindowMin": entry.get("shipWindowMin"),
            "shipWindowMax": entry.get("shipWindowMax"),
        }
        locations.append(location)
        if has_ledger and cache_qty != ledger_qty:
            disagreements.append({
                "warehouseId": entry.get("warehouseId"),
                "cacheQuantity": cache_qty,
                "ledgerQuantity": ledger_qty,
            })

    if not locations:
        # No per-location rows means no ledger or warehouse coverage. The
        # aggregate column is reported but cannot support a claim: it holds a
        # seeded value, not a measured count.
        return InventoryEvidence(
            product_id=pid,
            status=NOT_VERIFIED,
            available_quantity=None,
            source="no per-location inventory record",
            observed_at=_now(),
            catalog_cache_quantity=aggregate_cache,
            catalog_ledger_quantity=aggregate_ledger,
            aggregate_cache_stale=aggregate_stale,
            note=(
                "No per-warehouse inventory record exists for this product, so "
                "current availability has not been verified."
            ),
        )

    if not has_ledger:
        # A cache reading with nothing to reconcile it against.
        total = sum(int(loc["cacheQuantity"]) for loc in locations)
        return InventoryEvidence(
            product_id=pid,
            status=OBSERVED_IN_STOCK if total > 0 else OBSERVED_OUT_OF_STOCK,
            available_quantity=total,
            scope=SCOPE_WAREHOUSE,
            locations=locations,
            source="pellier.warehouse_inventory",
            authority=AUTHORITY_CACHE,
            reconciled_to_ledger=False,
            observed_at=_now(),
            catalog_cache_quantity=aggregate_cache,
            catalog_ledger_quantity=aggregate_ledger,
            note=(
                "Warehouse observation available; no ledger movement exists to "
                "reconcile it against."
            ),
        )

    ledger_total = sum(int(loc["ledgerQuantity"] or 0) for loc in locations)

    if disagreements:
        # Do not resolve it. Both numbers are on the record and no availability
        # claim is licensed until they agree.
        return InventoryEvidence(
            product_id=pid,
            status=LEDGER_CACHE_DISAGREEMENT,
            available_quantity=None,
            scope=SCOPE_WAREHOUSE,
            locations=locations,
            source="pellier.inventory_ledger vs pellier.warehouse_inventory",
            authority=AUTHORITY_LEDGER,
            reconciled_to_ledger=False,
            observed_at=_now(),
            catalog_cache_quantity=aggregate_cache,
            catalog_ledger_quantity=aggregate_ledger,
            aggregate_cache_stale=aggregate_stale,
            disagreements=disagreements,
            note=(
                "The ledger and the warehouse cache disagree for this product, so "
                "current availability has not been established."
            ),
        )

    return InventoryEvidence(
        product_id=pid,
        status=RECONCILED_IN_STOCK if ledger_total > 0 else RECONCILED_OUT_OF_STOCK,
        available_quantity=ledger_total,
        scope=SCOPE_WAREHOUSE,
        locations=locations,
        source="pellier.inventory_ledger",
        authority=AUTHORITY_LEDGER,
        reconciled_to_ledger=True,
        observed_at=_now(),
        catalog_cache_quantity=aggregate_cache,
        catalog_ledger_quantity=aggregate_ledger,
        aggregate_cache_stale=aggregate_stale,
        note=(
            "The aggregate catalog cache has not caught up with the ledger; "
            "per-warehouse stock reconciles."
            if aggregate_stale else ""
        ),
    )


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def describe_availability(evidence: InventoryEvidence) -> str:
    """The sentence a surface may print. Point-in-time fact, never a guarantee.

    No "zero fulfillment risk", no "guaranteed", no "will ship" — current inventory
    is an observation, and a fulfillment promise needs an SLA this application does
    not have.
    """
    if evidence.status == NOT_VERIFIED:
        return "Availability not verified."
    if evidence.status == LEDGER_CACHE_DISAGREEMENT:
        return "Inventory records disagree; availability not established."
    if evidence.status == OBSERVED_OUT_OF_STOCK:
        return "No units currently available (warehouse observation)."
    if evidence.status == RECONCILED_OUT_OF_STOCK:
        return "No units currently available."
    count = evidence.available_quantity or 0
    places = len(evidence.locations)
    unit = "unit" if count == 1 else "units"
    if evidence.status == OBSERVED_IN_STOCK:
        suffix = " (warehouse observation, not reconciled)"
    else:
        suffix = ""
    if places == 1:
        where = str(evidence.locations[0]["warehouseId"])
        return f"{count} {unit} currently available at {where}.{suffix}"
    return f"{count} {unit} currently available across {places} locations.{suffix}"
