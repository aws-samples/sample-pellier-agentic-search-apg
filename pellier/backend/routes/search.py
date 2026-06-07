"""``/api/search`` route — storefront vector search (Task 3.7).

Implements Requirement 3.3.6 and 5.1.1 of the pellier-storefront
spec and wires Challenge 1 (``VectorSearch.vector_search`` from
Task 2.1) into the public HTTP surface with the ``StorefrontSearchResponse``
wire shape from Task 1.3.

  * ``POST /api/search`` — embed the query via ``EmbeddingService``,
    call ``VectorSearch.vector_search``, return a
    ``StorefrontSearchResponse`` with camelCase keys
    (``queryEmbeddingMs``, ``searchMs``, ``totalMs``).

Design notes
------------

* **Wire-shape split.** ``app.py`` already exposes a legacy
  ``POST /api/search`` that returns the snake_case ``SearchResponse``
  (``query``, ``results``, ``total_results``, ``search_time_ms``) used by
  the pre-storefront search explorer. The storefront needs a different
  wire shape: a flat list of ``StorefrontProduct`` rows plus three
  timing fields (``queryEmbeddingMs``, ``searchMs``, ``totalMs``).

  Task 3.7 explicitly calls out the two shapes and resolves the overlap
  by mounting this router **before** the legacy ``@app.post`` decorator
  in ``app.py``, matching the pattern already used by ``routes/products.py``
  for the overlapping ``/api/products`` + ``/api/products/{id}`` paths
  (see ``routes/products.py`` docstring and ``app.py`` include_router
  ordering). FastAPI resolves routes in registration order, so the
  storefront shape wins on ``/api/search``.

* **Timing budget.** Req 5.1.1 pins the p95 latency budget at 500ms.
  We split the total wall clock into two numbers the frontend uses to
  render the "340 ms" latency stamp in the hero card (Req 1.3.4):
  ``query_embedding_ms`` (Bedrock embed call) and ``search_ms``
  (Aurora round-trip). ``total_ms`` is the end-to-end sum and is the
  one the 500ms budget measures.

* **Frontend contract.** ``StorefrontSearchResponse`` emits camelCase
  via its ``alias_generator=to_camel`` config. ``vector_search``
  returns legacy product rows with columns like ``"productId"`` and
  ``product_description`` — this layer projects them onto
  ``StorefrontProduct`` so the frontend search pill (Task 4.2) consumes
  the same shape as ``/api/products`` without a second adapter.

* **Embedding service dependency.** We can't pull
  ``get_embedding_service`` from ``app.py`` without re-triggering its
  lifespan (database + Bedrock pool), so this module declares its own
  thin dependency that imports lazily. Tests override it to inject a
  fake service that returns a deterministic 1024-dim vector; the
  live process falls through to ``app.get_embedding_service`` which
  serves the singleton initialised during startup.

* **Catalog source of truth.** Per the spec, product rows and
  embeddings live in ``pellier.product_catalog`` owned by the
  ``catalog-enrichment`` sibling spec. This route issues read-only
  queries through ``VectorSearch.vector_search`` — no writes.

Routes are NOT part of any workshop challenge block. This file ships
without ``# === CHALLENGE ... ===`` markers.
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from models import StorefrontProduct, StorefrontSearchResponse
from services.embeddings import EmbeddingService
from services.vector_search import VectorSearch

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class StorefrontSearchRequest(BaseModel):
    """Incoming search payload for ``POST /api/search``.

    ``limit`` mirrors the bounds on the legacy ``SearchRequest`` model
    (1–100, default 20) so the storefront grid pages the same way the
    search explorer does. ``query`` is trimmed to 2000 chars to bound
    the embedding cost.
    """

    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(default=20, ge=1, le=100)


# ---------------------------------------------------------------------------
# Dependencies (lazy imports to avoid pulling ``app.py``'s lifespan on
# pytest collection — same pattern as ``routes/products.py``)
# ---------------------------------------------------------------------------


async def get_db_service() -> Any:
    """FastAPI dependency returning the shared ``DatabaseService``."""
    from app import get_db_service as _app_get_db_service

    return await _app_get_db_service()


async def get_embedding_service() -> EmbeddingService:
    """FastAPI dependency returning the shared ``EmbeddingService``."""
    from app import get_embedding_service as _app_get_embedding_service

    return await _app_get_embedding_service()


# ---------------------------------------------------------------------------
# Row projection
# ---------------------------------------------------------------------------


_FALLBACK_CATEGORY = "Accessories"
_STOREFRONT_CATEGORIES = {
    "Linen", "Dresses", "Accessories", "Outerwear", "Footwear",
    "Home", "Tops", "Bottoms", "Bags",
}


def _vector_row_to_storefront_product(row: dict) -> StorefrontProduct:
    """Project a ``vector_search`` row onto the storefront wire shape.

    The boutique catalog exposes ``name``, ``brand``, ``color``,
    ``category``, ``tags`` and ``badge`` directly, so the projection is
    largely a 1:1 copy. We retain fallbacks for legacy fixture rows
    (``product_description``, ``category_name``) so the search endpoint
    tests — which still synthesise legacy-shaped rows — keep working
    without a second pass.
    """
    raw_category = row.get("category") or row.get("category_name") or _FALLBACK_CATEGORY
    if str(raw_category) in _STOREFRONT_CATEGORIES:
        category: str = str(raw_category)
    else:
        category = _FALLBACK_CATEGORY
        for storefront_cat in _STOREFRONT_CATEGORIES:
            if storefront_cat.lower() in str(raw_category).lower():
                category = storefront_cat
                break

    name = row.get("name")
    if not name:
        # Legacy fixture path: derive a name from the description column.
        description = row.get("product_description") or row.get("description") or ""
        name = description.split("\n", 1)[0][:80] if description else "Product"

    reviews_raw = row.get("reviews")
    try:
        review_count = int(reviews_raw) if reviews_raw is not None else 0
    except (TypeError, ValueError):
        review_count = 0

    raw_id = row.get("product_id") if row.get("product_id") is not None else row.get("productId")
    badge = row.get("badge") if row.get("badge") in {"EDITORS_PICK", "BESTSELLER", "JUST_IN"} else None
    return StorefrontProduct(
        id=int(raw_id) if raw_id is not None else 0,
        brand=row.get("brand") or "Pellier Editions",
        name=name,
        color=row.get("color") or "",
        price=float(row.get("price") or 0),
        rating=float(row.get("rating") or 0),
        review_count=review_count,
        category=category,  # type: ignore[arg-type]
        image_url=str(row.get("img_url") or row.get("imgurl") or ""),
        badge=badge,
        tags=list(row.get("tags") or []),
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/api/search")
async def storefront_search(
    payload: StorefrontSearchRequest,
    db: Any = Depends(get_db_service),
    embeddings: EmbeddingService = Depends(get_embedding_service),
) -> JSONResponse:
    """Run a vector search and return the storefront wire shape.

    Pipeline (Req 3.3.6 and Design "Sequence Diagram 1 — Vector search"):

      1. Embed the query via ``EmbeddingService.embed_query``
         (Cohere Embed v4 ``input_type=search_query``).
      2. Call ``VectorSearch.vector_search`` with the pre-computed
         vector. ``vector_search`` is the C1 method from Task 2.1 — it
         owns ``SET LOCAL hnsw.ef_search``, the ``iterative_scan``
         branch, and the ``<=>`` cosine ordering.
      3. Project rows onto ``StorefrontProduct`` and assemble
         ``StorefrontSearchResponse`` with the three timing fields.

    The timing fields are always populated (they're ``int`` ms counters,
    not optionals) so the frontend can render the latency stamp on
    every response. ``model_dump(by_alias=True)`` emits camelCase keys
    so the response matches the TypeScript ``StorefrontSearchResponse``
    added in Task 1.2.
    """
    total_start = time.perf_counter()

    try:
        # --- 1. Embed the query --------------------------------------
        embed_start = time.perf_counter()
        try:
            embedding = embeddings.embed_query(payload.query)
        except ValueError as exc:
            # ``embed_query`` raises on empty input; the pydantic
            # min_length=1 guard makes this nearly unreachable, but
            # defense-in-depth keeps the error envelope clean.
            raise HTTPException(status_code=400, detail=str(exc))
        query_embedding_ms = int(
            round((time.perf_counter() - embed_start) * 1000)
        )

        # --- 2. Vector search ---------------------------------------
        search_start = time.perf_counter()
        vector_service = VectorSearch(db)
        rows = await vector_service.vector_search(
            embedding=embedding,
            limit=payload.limit,
            ef_search=40,
        )
        search_ms = int(round((time.perf_counter() - search_start) * 1000))

        # --- 3. Project + assemble ----------------------------------
        products: List[StorefrontProduct] = [
            _vector_row_to_storefront_product(dict(r)) for r in rows
        ]
        total_ms = int(round((time.perf_counter() - total_start) * 1000))

        response = StorefrontSearchResponse(
            products=products,
            query_embedding_ms=query_embedding_ms,
            search_ms=search_ms,
            total_ms=total_ms,
        )

        logger.info(
            "storefront_search query=%r results=%d embed=%dms search=%dms total=%dms",
            payload.query,
            len(products),
            query_embedding_ms,
            search_ms,
            total_ms,
        )

        return JSONResponse(
            status_code=200,
            content=response.model_dump(mode="json", by_alias=True),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("storefront_search failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="search_failed")
