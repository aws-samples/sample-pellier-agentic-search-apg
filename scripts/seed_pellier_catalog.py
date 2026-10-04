#!/usr/bin/env python3
"""
Seed the Pellier catalog from data/pellier_catalog.json.

The catalog file is the single source of product data: each product carries a
department (one of DEPARTMENTS) and a moment (one of MOMENTS) that the workshop
story, inventory, orders, returns, and policy exercises refer to by product ID.
Embeddings come from the committed Cohere Embed v4 cache, so a fresh-account
bootstrap makes zero catalog-embedding Bedrock calls.

Usage:
    # Generate embeddings via Bedrock + seed directly into Aurora:
    python scripts/seed_pellier_catalog.py

    # Generate embeddings + write CSV + embeddings cache (no DB connection):
    python scripts/seed_pellier_catalog.py --csv-only

    # PREFERRED FOR WORKSHOPS — seed from the committed embeddings cache,
    # no Bedrock embedding calls (deterministic, fast, no throttle/AccessDenied):
    python scripts/seed_pellier_catalog.py --from-cache

    # Skip embedding generation (use zero vectors, for local dev):
    python scripts/seed_pellier_catalog.py --skip-embeddings --csv-only

Environment:
    DB_HOST, DB_NAME, DB_USER, DB_PASSWORD — Aurora connection
    AWS_REGION — Bedrock region (default: us-east-1)

Workshop note:
    The catalog embeddings never change between runs, so we generate them
    ONCE (committing data/embeddings_cache.json) and every participant
    account seeds from that cache via --from-cache. This removes the
    Cohere Embed v4 Bedrock call from the bootstrap critical path — the
    slowest, most throttle-prone step — turning the seed into a
    deterministic SQL load. Runtime models (Cohere Rerank, Claude) are
    still required and checked by the model-access preflight.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CATALOG_JSON = os.path.join(DATA_DIR, "pellier_catalog.json")
CSV_OUT_CURATED = os.path.join(DATA_DIR, "pellier_catalog_curated.csv")
# Committed cache of precomputed 1024-dim embeddings, keyed by productId.
# Generated once via --csv-only; loaded by --from-cache so the workshop
# bootstrap never has to call Bedrock to embed the catalog.
EMBED_CACHE = os.path.join(DATA_DIR, "embeddings_cache.json")
EMBED_DIM = 1024

# CSV column order matches the seed-database.sh temp_products schema
CSV_FIELDS = [
    "productId", "product_description", "imgurl", "producturl",
    "stars", "reviews", "price", "category_id", "isbestseller",
    "boughtinlastmonth", "category_name", "quantity", "embedding",
]

DEPARTMENTS = (
    "Clothing", "Shoes", "Bags and travel", "Accessories",
    "Home", "Kitchen and table", "Bath and body", "Stationery and gifts",
)
MOMENTS = ("fresh", "marco", "anna", "theo", "house", "signature")


@dataclass
class Product:
    productId: int
    name: str
    brand: str
    color: str
    price: float
    description: str
    department: str
    tags: List[str]
    rating: float
    reviews: int
    imgPath: str  # relative to /products/ in the frontend
    quantity: int
    persona: str  # the moment slot key this product belongs to
    badge: Optional[str] = None
    embedding: Optional[List[float]] = None

    @property
    def category_id(self) -> int:
        return DEPARTMENTS.index(self.department) + 1

    @property
    def search_text(self) -> str:
        """The product's own words. No shopper persona sentence: vectors must find
        meaning in the product, not in a label we planted."""
        return (
            f"{self.name}. {self.description} "
            f"Brand: {self.brand}. Color: {self.color}. "
            f"Category: {self.department}. Tags: {', '.join(self.tags)}."
        )

    @property
    def public_image_path(self) -> str:
        """Return the browser-served WebP path, never the PNG source master."""
        stem, _separator, _extension = self.imgPath.rpartition(".")
        return f"/products/{stem or self.imgPath}.webp"

    def to_csv_row(self) -> dict:
        return {
            "productId": str(self.productId).ljust(10),
            "product_description": self.description,
            "imgurl": self.public_image_path,
            "producturl": f"/p/{self.productId}",
            "stars": self.rating,
            "reviews": self.reviews,
            "price": self.price,
            "category_id": self.category_id,
            "isbestseller": "false",
            "boughtinlastmonth": 0,
            "category_name": self.department,
            "quantity": self.quantity,
            "embedding": json.dumps(self.embedding) if self.embedding else "",
        }


def load_catalog(path: str = CATALOG_JSON) -> List[Product]:
    """Load products from the catalog JSON, rejecting unknown departments or moments."""
    with open(path) as handle:
        rows = json.load(handle)
    products = [
        Product(
            productId=r["id"], name=r["name"], brand=r["brand"], color=r["color"],
            price=float(r["price"]), description=r["description"],
            department=r["department"], tags=list(r["tags"]), rating=float(r["rating"]),
            reviews=int(r["reviews"]), imgPath=r["image"], quantity=int(r["quantity"]),
            persona=r["moment"], badge=r.get("badge"),
        )
        for r in rows
    ]
    for p in products:
        if p.department not in DEPARTMENTS:
            raise SystemExit(f"Product {p.productId}: unknown department {p.department!r}")
        if p.persona not in MOMENTS:
            raise SystemExit(f"Product {p.productId}: unknown moment {p.persona!r}")
    return products


# =========================================================================
# EMBEDDING GENERATION
# =========================================================================

def generate_embeddings(products: List[Product], region: str) -> None:
    """Generate Cohere Embed v4 embeddings via Bedrock for all products.

    Cohere Embed v4 is enabled in AWS Workshop Studio. We invoke it through a
    cross-region inference profile (us.* / eu.* / apac.*, derived from the
    region here) for throughput headroom during a seeded room; the bare model
    ID also serves on-demand traffic. Overridable via BEDROCK_EMBED_MODEL_ID
    for an explicit ID/ARN.

    output_dimension is pinned to EMBED_DIM (1024) so generated vectors match
    the vector(1024) schema and the runtime query embeddings (which also
    request 1024). Keep this in lockstep with services/embeddings.py.
    """
    import boto3

    # Region-derived cross-region inference profile prefix (us. / eu. / apac.).
    group = (region or "us-east-1").split("-")[0]
    if group not in ("us", "eu", "apac"):
        group = "us"
    default_model = f"{group}.cohere.embed-v4:0"
    model_id = os.getenv("BEDROCK_EMBED_MODEL_ID", default_model)

    client = boto3.client("bedrock-runtime", region_name=region)
    logger.info(
        "Generating embeddings for %d products via %s...",
        len(products), model_id,
    )

    for i, product in enumerate(products):
        text = product.search_text
        try:
            # v4 accepts output_dimension; pin 1024 to match schema + cache.
            payload = json.dumps({
                "texts": [text],
                "input_type": "search_document",
                "embedding_types": ["float"],
                "output_dimension": EMBED_DIM,
            })
            response = client.invoke_model(
                body=payload,
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
            )
            body = json.loads(response["body"].read())
            embedding = body.get("embeddings", {}).get("float", [[]])[0]
            if len(embedding) == 1024:
                product.embedding = embedding
                logger.info(
                    "  [%d/%d] ✓ %s — %d dims",
                    i + 1, len(products), product.name, len(embedding),
                )
            else:
                logger.warning(
                    "  [%d/%d] ✗ %s — unexpected dim %d",
                    i + 1, len(products), product.name, len(embedding),
                )
        except Exception as exc:
            logger.warning(
                "  [%d/%d] ✗ %s — %s",
                i + 1, len(products), product.name, exc,
            )
        # Respect rate limits
        if (i + 1) % 10 == 0:
            time.sleep(1)


# =========================================================================
# EMBEDDINGS CACHE (precomputed vectors, committed to the repo)
# =========================================================================

def _text_digest(product: Product) -> str:
    """Fingerprint of the exact text a product's vector was generated from."""
    return hashlib.sha256(product.search_text.encode("utf-8")).hexdigest()


def write_embeddings_cache(products: List[Product], path: str) -> None:
    """Persist generated embeddings keyed by productId, stamped with each text's digest."""
    cache = {
        str(p.productId): p.embedding
        for p in products
        if p.embedding and len(p.embedding) == EMBED_DIM
    }
    digests = {str(p.productId): _text_digest(p) for p in products if str(p.productId) in cache}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(
            {
                "model": "us.cohere.embed-v4:0",
                "dim": EMBED_DIM,
                "text_sha256": digests,
                "embeddings": cache,
            },
            f,
        )
    logger.info("Wrote %d cached embeddings to %s", len(cache), path)


def load_embeddings_cache(products: List[Product], path: str) -> int:
    """Attach precomputed embeddings from the committed cache. Returns count applied.

    Raises:
        SystemExit: a product has no cached vector, or its text changed since
            its vector was generated. Either would seed a row that semantic
            search cannot place correctly.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Embeddings cache not found at {path}. Generate it once with "
            f"`python scripts/seed_pellier_catalog.py --csv-only` and commit it."
        )
    with open(path) as f:
        payload = json.load(f)

    # Guard: the cached vectors MUST come from the same embedding model the
    # backend uses at query time. A v3 cache + v4 runtime (or vice-versa)
    # silently returns nonsense — different latent spaces. Warn loudly so a
    # stale cache is caught at seed, not by a participant mid-search.
    cache_model = payload.get("model", "<unstamped>")
    expected_model = os.getenv("BEDROCK_EMBED_MODEL_ID", "us.cohere.embed-v4:0")
    if cache_model != expected_model:
        logger.warning(
            "⚠️  Embeddings cache model mismatch: cache was built with '%s' but "
            "runtime expects '%s'. Vectors from different models are NOT "
            "comparable — regenerate the cache with "
            "`python scripts/seed_pellier_catalog.py --csv-only` against an "
            "account that has the expected model enabled, then commit "
            "data/embeddings_cache.json.",
            cache_model, expected_model,
        )

    cache = payload.get("embeddings", {})
    digests = payload.get("text_sha256", {})
    missing = [
        p.productId for p in products
        if len(cache.get(str(p.productId)) or []) != EMBED_DIM
    ]
    if missing:
        raise SystemExit(
            f"Embeddings cache has no cached vector for products {missing}: "
            "regenerate with --csv-only"
        )
    changed = [p.productId for p in products if digests.get(str(p.productId)) != _text_digest(p)]
    if changed:
        raise SystemExit(
            f"Embeddings cache text changed for products {changed}: regenerate with --csv-only"
        )
    for p in products:
        p.embedding = cache[str(p.productId)]
    logger.info("Applied %d cached embeddings from %s", len(products), path)
    return len(products)


# =========================================================================
# CSV EXPORT
# =========================================================================

def write_csv(products: List[Product], path: str) -> None:
    """Write the catalog to a CSV matching seed-database.sh's schema."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        # lineterminator is explicit: csv writers default to "\r\n" on every platform,
        # and `git diff --check` reports that bare carriage return as trailing
        # whitespace on every row the diff adds. The release gate fails on a file
        # nobody hand-edited.
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for p in products:
            writer.writerow(p.to_csv_row())
    logger.info("Wrote %d products to %s", len(products), path)


# =========================================================================
# DIRECT DB SEEDING
# =========================================================================

def _database_dsn() -> str:
    """Build the libpq DSN from the documented database environment."""
    return (
        f"host={os.environ['DB_HOST']} "
        f"port={os.getenv('DB_PORT', '5432')} "
        f"dbname={os.environ['DB_NAME']} "
        f"user={os.environ['DB_USER']} "
        f"password={os.environ['DB_PASSWORD']}"
    )


def seed_database(products: List[Product]) -> None:
    """Insert products directly into Aurora via psycopg."""
    import psycopg

    with psycopg.connect(_database_dsn()) as conn:
        with conn.cursor() as cur:
            managed_product_ids = [str(p.productId) for p in products]
            # Clear only numeric-ID rows the catalog no longer lists. Keeping
            # current rows in place avoids ON DELETE CASCADE wiping
            # warehouse_inventory when the seeder is rerun after migrations.
            cur.execute(
                """
                DELETE FROM pellier.product_catalog
                WHERE "productId" ~ '^[0-9]+$'
                  AND NOT ("productId" = ANY(%s))
                """,
                (managed_product_ids,),
            )
            logger.info("Cleared stale managed catalog rows")

            for p in products:
                tags_json = json.dumps(p.tags)
                # Use zero vector as placeholder when no embedding generated
                if p.embedding:
                    embedding_str = json.dumps(p.embedding)
                else:
                    embedding_str = json.dumps([0.0] * 1024)
                cur.execute(
                    """
                    INSERT INTO pellier.product_catalog
                        ("productId", name, brand, color, price, description,
                         category, tags, rating, reviews, "imgUrl",
                         badge, tier, quantity, embedding, persona_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s::vector, %s)
                    ON CONFLICT ("productId") DO UPDATE SET
                        name = EXCLUDED.name,
                        brand = EXCLUDED.brand,
                        color = EXCLUDED.color,
                        price = EXCLUDED.price,
                        description = EXCLUDED.description,
                        category = EXCLUDED.category,
                        tags = EXCLUDED.tags,
                        rating = EXCLUDED.rating,
                        reviews = EXCLUDED.reviews,
                        "imgUrl" = EXCLUDED."imgUrl",
                        badge = EXCLUDED.badge,
                        tier = EXCLUDED.tier,
                        quantity = EXCLUDED.quantity,
                        embedding = EXCLUDED.embedding,
                        persona_id = EXCLUDED.persona_id
                    """,
                    (
                        str(p.productId),
                        p.name,
                        p.brand,
                        p.color,
                        p.price,
                        p.description,
                        p.department,
                        tags_json,
                        p.rating,
                        p.reviews,
                        p.public_image_path,
                        p.badge or '',
                        p.quantity,
                        embedding_str,
                        p.persona,
                    ),
                )

            conn.commit()
            logger.info("Seeded %d products into Aurora", len(products))


# =========================================================================
# SUMMARY
# =========================================================================

def print_summary(products: List[Product]) -> None:
    """Print product counts per department and per moment."""
    print("\n" + "=" * 72)
    print(f"PELLIER CATALOG — {len(products)} products")
    print("=" * 72)

    print("\n  By department")
    for department in DEPARTMENTS:
        count = sum(1 for p in products if p.department == department)
        print(f"    {department:<22} {count:>3}")

    print("\n  By moment")
    for moment in MOMENTS:
        items = [p for p in products if p.persona == moment]
        embedded = sum(1 for p in items if p.embedding)
        print(f"\n  {moment.upper()} ({len(items)} products, {embedded} embedded)")
        print(f"  {'─' * 60}")
        for p in items:
            badge = f" [{p.badge}]" if p.badge else ""
            emb = "✓" if p.embedding else "·"
            print(f"  {emb} {p.productId:>3}  ${p.price:>6.0f}  {p.name}{badge}")

    total_embedded = sum(1 for p in products if p.embedding)
    price_range = f"${min(p.price for p in products):.0f}–${max(p.price for p in products):.0f}"
    print(f"\n  Total: {len(products)} products | {total_embedded} embedded | {price_range}")
    print("=" * 72 + "\n")


# =========================================================================
# MAIN
# =========================================================================

def main():
    parser = argparse.ArgumentParser(description="Seed Pellier catalog with embeddings")
    parser.add_argument(
        "--csv-only", action="store_true",
        help="Write CSV + embeddings cache only, no DB connection",
    )
    parser.add_argument(
        "--from-cache", action="store_true",
        help="Seed using committed embeddings cache (no Bedrock calls) — preferred for workshops",
    )
    parser.add_argument(
        "--skip-embeddings", action="store_true",
        help="Skip Cohere embedding generation (zero vectors)",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION", "us-east-1"),
        help="AWS region",
    )
    args = parser.parse_args()

    products = load_catalog()

    if args.from_cache:
        # Workshop fast path: deterministic SQL load from precomputed vectors.
        load_embeddings_cache(products, EMBED_CACHE)
    elif not args.skip_embeddings:
        generate_embeddings(products, args.region)
        failed = [p.productId for p in products if not p.embedding]
        if failed:
            raise SystemExit(
                f"Bedrock returned no embedding for products {failed}; "
                "the cache was not written. Check model access in the region and rerun."
            )
        # Refresh the committed cache whenever we regenerate, so the next
        # --from-cache run stays in sync with the live model output.
        write_embeddings_cache(products, EMBED_CACHE)
    else:
        logger.info("Skipping embedding generation (--skip-embeddings)")

    print_summary(products)

    if not args.csv_only:
        seed_database(products)
    else:
        write_csv(products, CSV_OUT_CURATED)
        logger.info("CSV-only mode — wrote CSV, skipped DB seeding")
        logger.info("To seed Aurora from the cache, run: --from-cache")


if __name__ == "__main__":
    main()
