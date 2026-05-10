"""``/api/products`` + ``/api/inventory`` routes — storefront listing API (Task 3.6).

Implements Requirements 3.3.1–3.3.5 and 3.5.1–3.5.2 of the
pellier-storefront spec:

  * ``GET /api/products``              editorial or personalized product list
  * ``GET /api/products/{id}``         single product row (404 on unknown id)
  * ``GET /api/inventory``             live status-strip signal

Design notes
------------

* **Personalization is optional auth.** Req 3.3.1 says an unauthenticated
  call returns the default editorial order. Req 3.3.2 says an
  authenticated call with ``personalized=true`` AND saved preferences
  re-sorts by match score. Req 3.3.3 says an authenticated call with
  ``personalized=true`` AND NO saved preferences ALSO returns the
  default editorial order. So this route layer must tolerate every
  combination:

      no JWT                      -> editorial order
      JWT + personalized=false    -> editorial order
      JWT + personalized=true
          + prefs exist           -> sort_personalized(products, prefs)
          + prefs missing/empty   -> editorial order

  We deliberately do not gate the route behind ``require_user``. The
  identity service resolves the anon/user namespace, and the handler
  only consults memory when there is a real ``user_id`` AND the query
  param opts in. That keeps the public ``GET /api/products`` call path
  free of a 401 for signed-out shoppers browsing the home page.

* **Catalog source of truth.** Per the spec header, the product table
  and tag population are owned by the sibling ``catalog-enrichment``
  spec. This module issues read-only SELECTs against
  ``pellier.product_catalog`` using the standard ``DatabaseService``
  pool. The tests mock the DB so the suite runs offline and does not
  require the seeded catalog (per the task prompt).

* **Default editorial order.** "Editorial order" is the curator-chosen
  order the 9 showcase products appear in ``storefront.md``. The
  boutique catalog encodes this via the ``tier`` column (1=featured,
  2=editorial, 3=extended) and we break ties by ``"productId"``
  ascending so the list stays stable for ``sort_personalized``.

* **Inventory shape.** Req 3.5.1 pins the shape at
  ``{last_refreshed: ISO-8601, counts: {[category]: int}}``. Req 3.5.2
  adds ``stale: true`` when the data is older than 24h. We compute
  ``last_refreshed`` as ``MAX(updated_at)`` across rows and the counts
  from a ``GROUP BY category``.

* **Auth integration.** The personalized branch uses
  ``AgentCoreIdentityService.get_verified_user_context`` (Task 3.2) so
  anonymous callers silently fall through to editorial order without a
  401. Reads from ``AgentCoreMemory`` go through the shared instance
  exposed by ``routes/user.py`` (Task 3.4) so the in-memory fallback is
  coherent with the preferences API.

* **Response shape.** Wire format is the storefront ``StorefrontProduct``
  camelCase shape from Task 1.3 (``reviewCount``, ``imageUrl``, etc.).
  We use ``model_dump(by_alias=True)`` at the edge so TypeScript
  consumers in Task 4.6 can keep their existing types.

Routes are NOT part of any workshop challenge block. This file ships
without ``# === CHALLENGE ... ===`` markers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from models import Preferences, StorefrontProduct
from services.agentcore_identity import (
    AgentCoreIdentityService,
    get_agentcore_identity_service,
)
from services.agentcore_memory import AgentCoreMemory
from services.personalization import sort_personalized
from routes.user import get_agentcore_memory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["products"])


# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------
#
# The router pulls the shared ``DatabaseService`` through a small
# indirection so tests can override the dependency with an in-memory
# fake instead of standing up a real pool. ``app.py`` already owns the
# process-wide instance; we import its accessor lazily to avoid a
# circular import (``routes`` -> ``app`` -> ``routes`` chain) at module
# load time.


async def get_db_service() -> Any:
    """FastAPI dependency returning the shared ``DatabaseService``.

    Imported lazily so the router can be collected by pytest without
    triggering ``app.py``'s lifespan (which expects a live Aurora
    cluster). Tests override this dependency with a stub.
    """
    # Local import keeps ``pytest`` collection cheap — ``app.py`` pulls
    # in the full agent/service graph on import, which tests don't need.
    from app import get_db_service as _app_get_db_service

    return await _app_get_db_service()


# ---------------------------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------------------------


_PRODUCT_SELECT = """
    SELECT
        "productId"          AS id,
        brand,
        name,
        color,
        price,
        rating,
        reviews,
        category,
        "imgUrl"             AS image_url,
        badge,
        tags,
        tier
    FROM pellier.product_catalog
"""


def _row_to_storefront_product(row: Dict[str, Any]) -> StorefrontProduct:
    """Project a raw catalog row onto the ``StorefrontProduct`` wire shape.

    The boutique catalog stores ``reviews`` as TEXT (numeric strings like
    "214") and the image column as quoted camelCase ``"imgUrl"``. The
    SELECT above aliases both into plain snake_case keys so this function
    only handles defensive fallbacks for fields that could be ``None`` in
    the DB but must be non-null on the wire.
    """
    reviews_raw = row.get("reviews")
    try:
        review_count = int(reviews_raw) if reviews_raw is not None else 0
    except (TypeError, ValueError):
        review_count = 0

    return StorefrontProduct(
        id=int(row["id"]),
        brand=row.get("brand") or "Pellier Editions",
        name=row["name"],
        color=row.get("color") or "",
        price=float(row.get("price") or 0),
        rating=float(row.get("rating") or 0),
        review_count=review_count,
        category=row["category"],
        image_url=row.get("image_url") or "",
        badge=row.get("badge"),
        tags=list(row.get("tags") or []),
    )


async def _fetch_editorial_catalog(
    db: Any,
    *,
    category: Optional[str] = None,
) -> List[StorefrontProduct]:
    """Return the full catalog in default editorial order.

    Editorial order is the curator-chosen ``editorial_rank`` column when
    populated by ``catalog-enrichment``; otherwise it falls back to the
    stable ``"productId"`` order. Both paths yield a deterministic list
    so ``sort_personalized`` can preserve ties correctly.
    """
    if category:
        # ``database.md`` steering mandates ``ILIKE`` with ``%`` wildcards
        # for category matching so ``Linen`` matches ``Linen Shirts``,
        # ``Home`` matches ``Home & Kitchen``, etc.
        query = (
            _PRODUCT_SELECT
            + " WHERE category ILIKE %s"
            + " ORDER BY tier NULLS LAST, \"productId\" ASC"
        )
        rows = await db.fetch_all(query, f"%{category}%")
    else:
        query = (
            _PRODUCT_SELECT
            + " ORDER BY tier NULLS LAST, \"productId\" ASC"
        )
        rows = await db.fetch_all(query)
    return [_row_to_storefront_product(dict(r)) for r in rows]


def _prefs_empty(prefs: Optional[Preferences]) -> bool:
    """Return True when ``prefs`` is null or has nothing to match on.

    Req 3.3.3: a signed-in shopper with no saved preferences SHALL get
    the editorial order. We treat an all-empty-lists ``Preferences``
    the same as ``None`` — personalization is a no-op either way.
    """
    if prefs is None:
        return True
    return not (prefs.vibe or prefs.colors or prefs.occasions or prefs.categories)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/api/products")
async def list_storefront_products(
    request: Request,
    personalized: bool = Query(default=False),
    category: Optional[str] = Query(default=None),
    db: Any = Depends(get_db_service),
    identity: AgentCoreIdentityService = Depends(get_agentcore_identity_service),
    memory: AgentCoreMemory = Depends(get_agentcore_memory),
) -> JSONResponse:
    """Return the storefront product list.

    Branches on ``personalized`` AND the presence of a verified user
    AND saved preferences. See Req 3.3.1–3.3.4.
    """
    products = await _fetch_editorial_catalog(db, category=category)

    # Short-circuit: no opt-in -> editorial order. This is the anon home
    # page path, and also the path for authenticated shoppers who
    # explicitly set ``personalized=false`` (e.g. a preview toggle).
    if not personalized:
        return JSONResponse(
            status_code=200,
            content=[p.model_dump(mode="json", by_alias=True) for p in products],
        )

    # Personalized opt-in: we need a verified user AND saved prefs. The
    # identity service returns ``user_id=None`` for anonymous callers
    # so the check below handles "bogus/expired token" and
    # "unauthenticated" the same way — fall back to editorial order
    # silently (Req 3.3.1, 3.3.3).
    context = await identity.get_verified_user_context(request)
    if context.user_id is None:
        return JSONResponse(
            status_code=200,
            content=[p.model_dump(mode="json", by_alias=True) for p in products],
        )

    prefs = await memory.get_user_preferences(context.user_id)
    if _prefs_empty(prefs):
        return JSONResponse(
            status_code=200,
            content=[p.model_dump(mode="json", by_alias=True) for p in products],
        )

    # Sort stably by match score desc, ties broken by editorial order
    # (Python's sort is stable and the input list is already in
    # editorial order from ``_fetch_editorial_catalog``).
    ranked = sort_personalized(products, prefs)  # type: ignore[arg-type]
    return JSONResponse(
        status_code=200,
        content=[p.model_dump(mode="json", by_alias=True) for p in ranked],
    )


@router.get("/api/products/{product_id}")
async def get_storefront_product(
    product_id: int,
    db: Any = Depends(get_db_service),
) -> JSONResponse:
    """Return one product or 404 (Req 3.3.5).

    The legacy ``/api/products/{product_id}`` route in ``app.py`` uses
    the older ``Product`` wire shape. This router is mounted earlier
    (``include_router`` runs before the module-level ``@app.get``
    decorators), so this handler wins and the response follows the
    ``StorefrontProduct`` camelCase shape.
    """
    row = await db.fetch_one(_PRODUCT_SELECT + ' WHERE "productId" = %s', product_id)
    if row is None:
        raise HTTPException(status_code=404, detail="product_not_found")

    product = _row_to_storefront_product(dict(row))
    return JSONResponse(
        status_code=200,
        content=product.model_dump(mode="json", by_alias=True),
    )


@router.get("/api/inventory")
async def get_inventory_signal(
    db: Any = Depends(get_db_service),
) -> JSONResponse:
    """Return the live inventory signal for the status strip.

    Shape per Req 3.5.1:
        {
            "last_refreshed": "2025-06-18T14:22:07.123Z",
            "counts": {"Linen": 42, "Dresses": 7, ...},
            "stale": false,
        }
    ``stale`` is set to True when ``last_refreshed`` is older than 24h
    (Req 3.5.2). The frontend status strip uses the flag to flip an
    amber warning without hiding the counts.
    """
    # Group all catalog rows by ``category``. The boutique schema has no
    # ``quantity`` column (everything in the editorial catalog is treated
    # as in-stock); the filter was removed with the schema migration.
    # ``last_refreshed`` is the MAX(updated_at) across rows — the loader
    # populates this on every batch so it reflects the last catalog sync.
    rows = await db.fetch_all(
        """
        SELECT category, COUNT(*) AS count, MAX(updated_at) AS last_refreshed
        FROM pellier.product_catalog
        GROUP BY category
        """
    )

    counts: Dict[str, int] = {}
    max_refreshed: Optional[datetime] = None
    for row in rows:
        row_dict = dict(row)
        category = row_dict.get("category")
        if category is None:
            continue
        counts[str(category)] = int(row_dict.get("count") or 0)
        row_refreshed = row_dict.get("last_refreshed")
        if isinstance(row_refreshed, datetime):
            if max_refreshed is None or row_refreshed > max_refreshed:
                max_refreshed = row_refreshed

    now = datetime.now(timezone.utc)
    last_refreshed = max_refreshed or now
    # Stale if the last catalog sync is >24h old (Req 3.5.2).
    stale = (now - last_refreshed).total_seconds() > 86400

    return JSONResponse(
        status_code=200,
        content={
            "last_refreshed": last_refreshed.isoformat(),
            "counts": counts,
            "stale": stale,
        },
    )
