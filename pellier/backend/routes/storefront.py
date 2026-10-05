"""Live storefront catalog statistics.

The storefront uses this small Aurora read for catalog facts.
It deliberately returns an error when Aurora is unavailable rather than
inventing an empty catalog, a default product, or a process-local metric.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pellier_copy import STOREFRONT_COPY

router = APIRouter(prefix="/api/storefront", tags=["storefront"])


class CatalogStatsResponse(BaseModel):
    product_count: int
    category_count: int
    standout_name: Optional[str] = None
    standout_category: Optional[str] = None
    generated_at: str


@router.get("/catalog-stats", response_model=CatalogStatsResponse)
async def catalog_stats() -> CatalogStatsResponse:
    """Return actual catalog totals and the current top editorial row."""
    from app import db_service

    if db_service is None:
        raise HTTPException(
            status_code=503,
            detail="Aurora is unavailable; catalog statistics cannot be shown.",
        )

    try:
        counts = await db_service.fetch_one(
            """
            SELECT
                count(*)::integer AS product_count,
                count(DISTINCT category)::integer AS category_count
              FROM pellier.product_catalog
            """
        )
        standout = await db_service.fetch_one(
            """
            SELECT name, category
              FROM pellier.product_catalog
             WHERE "imgUrl" IS NOT NULL
             ORDER BY tier NULLS LAST, rating DESC NULLS LAST,
                      reviews::integer DESC NULLS LAST, "productId"
             LIMIT 1
            """
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=STOREFRONT_COPY["CATALOG_STATS_UNAVAILABLE"],
        ) from exc

    if not counts:
        raise HTTPException(
            status_code=503,
            detail=STOREFRONT_COPY["CATALOG_STATS_EMPTY"],
        )

    return CatalogStatsResponse(
        product_count=int(counts["product_count"]),
        category_count=int(counts["category_count"]),
        standout_name=str(standout["name"]) if standout else None,
        standout_category=str(standout["category"]) if standout else None,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
