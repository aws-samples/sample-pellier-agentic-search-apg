#!/usr/bin/env python3
"""
Seed the Pellier catalog from data/pellier_catalog.json.

The catalog file is the single source of product data: each product carries a
department (one of DEPARTMENTS) and a moment (one of MOMENTS) that the workshop
story, inventory, orders, returns, and policy exercises refer to by product ID.
Embeddings come from the committed Cohere Embed v4 cache, so a fresh-account
bootstrap makes zero catalog-embedding Bedrock calls.

Usage:
    # Seed from the committed cache (default; no catalog-embedding calls):
    python scripts/seed_pellier_catalog.py

    # Generate the sharded embedding cache (no DB connection):
    python scripts/seed_pellier_catalog.py --cache-only

    # Optional local CSV export, including vectors (large; not committed):
    python scripts/seed_pellier_catalog.py --from-cache --csv-only

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
    ONCE (committing the manifest and data/embeddings/ shards) and every participant
    account seeds from that cache via --from-cache. This removes the
    Cohere Embed v4 Bedrock call from the bootstrap critical path — the
    slowest, most throttle-prone step — turning the seed into a
    deterministic SQL load. Runtime models (Cohere Rerank, Claude) are
    still required and checked by the model-access preflight.
"""

from __future__ import annotations

import argparse
from array import array
import csv
import gzip
import hashlib
import json
import logging
import math
import os
import sys
import tempfile
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
# Generated once via --cache-only; loaded by --from-cache so the workshop
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
MATERIALS = (
    "acetate", "beeswax", "brass", "canvas", "cashmere", "ceramic", "cotton", "foam",
    "glass", "gold", "iron", "jute", "leather", "linen", "merino", "nylon", "paper",
    "polyester", "rattan", "rubber", "seagrass", "silicone", "silk", "silver",
    "soy wax", "steel", "stone", "straw", "wood", "wool",
)
# Seed-time limits. The schema keeps these columns as unbounded text, so the seed is
# where an over-long value is caught; the UI is laid out for values inside them.
MAX_NAME = 120
MAX_BRAND = 60
MAX_COLOR = 60
MAX_DESCRIPTION = 1000
MAX_TAGS = 12
MAX_TAG = 40
MAX_PRICE = 99_999_999.99  # numeric(10,2)
BADGES = (None, "EDITORS_PICK", "BESTSELLER", "JUST_IN")


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
    materials: List[str]
    rating: float
    reviews: int
    imgPath: Optional[str]  # None means no photograph; never borrow another product's image
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
    def public_image_path(self) -> Optional[str]:
        """Return the browser-served WebP path, never the PNG source master.

        A product without photography stores NULL, so the column's own
        `"imgUrl" IS NOT NULL` test excludes the scale rows as well as
        VISIBLE_CATALOG_SQL does.
        """
        if not self.imgPath:
            return None
        stem, _separator, _extension = self.imgPath.rpartition(".")
        return f"/products/{stem or self.imgPath}.webp"

    def to_csv_row(self) -> dict:
        return {
            "productId": str(self.productId).ljust(10),
            "product_description": self.description,
            "imgurl": self.public_image_path or "",
            "producturl": f"/p/{self.productId}",
            "stars": self.rating,
            "reviews": self.reviews,
            "price": self.price,
            "category_id": self.category_id,
            "isbestseller": "false",
            "boughtinlastmonth": 0,
            "category_name": self.department,
            "quantity": self.quantity,
            "embedding": json.dumps(list(self.embedding)) if self.embedding else "",
        }


def load_catalog(path: str = CATALOG_JSON) -> List[Product]:
    """Load products from the catalog JSON, rejecting unknown departments or moments."""
    with open(path) as handle:
        rows = json.load(handle)
    products = [
        Product(
            productId=r["id"], name=r["name"], brand=r["brand"], color=r["color"],
            price=float(r["price"]), description=r["description"],
            department=r["department"], tags=list(r["tags"]),
            materials=list(r["materials"]), rating=float(r["rating"]),
            reviews=int(r["reviews"]), imgPath=r["image"], quantity=int(r["quantity"]),
            persona=r["moment"], badge=r.get("badge"),
        )
        for r in rows
    ]
    if len({p.productId for p in products}) != len(products):
        raise SystemExit("Catalog contains duplicate product IDs")
    if len({p.name.casefold() for p in products}) != len(products):
        raise SystemExit("Catalog contains duplicate product names")
    for p in products:
        if p.department not in DEPARTMENTS:
            raise SystemExit(f"Product {p.productId}: unknown department {p.department!r}")
        if p.persona not in MOMENTS:
            raise SystemExit(f"Product {p.productId}: unknown moment {p.persona!r}")
        unknown = sorted(set(p.materials) - set(MATERIALS))
        if unknown:
            raise SystemExit(f"Product {p.productId}: unknown materials {unknown}")
    problems = [
        f"Product {p.productId}: {problem}" for p in products for problem in limit_problems(p)
    ]
    if problems:
        raise SystemExit("Catalog values outside the seed limits:\n  " + "\n  ".join(problems))
    return products


def limit_problems(p: Product) -> List[str]:
    """Each way one product breaks the seed limits, worded for the person fixing the catalog."""
    checks = [
        (len(p.name) > MAX_NAME, f"name is {len(p.name)} characters (limit {MAX_NAME})"),
        (len(p.brand) > MAX_BRAND, f"brand is {len(p.brand)} characters (limit {MAX_BRAND})"),
        (len(p.color) > MAX_COLOR, f"color is {len(p.color)} characters (limit {MAX_COLOR})"),
        (len(p.description) > MAX_DESCRIPTION,
         f"description is {len(p.description)} characters (limit {MAX_DESCRIPTION})"),
        (len(p.tags) > MAX_TAGS, f"{len(p.tags)} tags (limit {MAX_TAGS})"),
        (any(len(tag) > MAX_TAG for tag in p.tags), f"a tag is longer than {MAX_TAG} characters"),
        (not 0 <= p.price <= MAX_PRICE, f"price {p.price} is outside 0 to {MAX_PRICE:,.2f}"),
        (p.badge not in BADGES, f"unknown badge {p.badge!r}"),
        (p.quantity < 0, "quantity must be non-negative"),
        (not math.isfinite(p.price), "price must be finite"),
        (not math.isfinite(p.rating) or not 0 <= p.rating <= 5, "rating must be between 0 and 5"),
    ]
    return [message for broken, message in checks if broken]


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

    from botocore.config import Config

    client = boto3.client("bedrock-runtime", region_name=region, config=Config(
        connect_timeout=10, read_timeout=120,
        retries={"mode": "adaptive", "max_attempts": 8},
    ))
    logger.info("Generating %d embeddings via %s", len(products), model_id)
    # Cohere v4 accepts up to 96 texts per request. Fail before publishing a
    # cache if any response is incomplete, malformed, or not a usable vector.
    for offset in range(0, len(products), 96):
        batch = products[offset:offset + 96]
        response = client.invoke_model(
            body=json.dumps({
                "texts": [p.search_text for p in batch],
                "input_type": "search_document",
                "embedding_types": ["float"],
                "output_dimension": EMBED_DIM,
            }),
            modelId=model_id, contentType="application/json", accept="application/json",
        )
        with response["body"] as body:
            vectors = json.loads(body.read()).get("embeddings", {}).get("float", [])
        if len(vectors) != len(batch) or not all(_valid_vector(v) for v in vectors):
            raise ValueError(
                f"Invalid embedding response for batch starting at {batch[0].productId}")
        for product, vector in zip(batch, vectors):
            product.embedding = array("f", vector)
        logger.info("Embedded %d/%d products", offset + len(batch), len(products))


# =========================================================================
# EMBEDDINGS CACHE (precomputed vectors, committed to the repo)
# =========================================================================

def _text_digest(product: Product) -> str:
    """Fingerprint of the exact text a product's vector was generated from."""
    return hashlib.sha256(product.search_text.encode("utf-8")).hexdigest()


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
            f"`python scripts/seed_pellier_catalog.py --cache-only` and commit it."
        )
    with open(path) as f:
        payload = json.load(f)

    if payload.get("format") != "float32-gzip-v1":
        raise SystemExit(
            f"Embeddings cache at {path} is not the sharded float32-gzip-v1 format: "
            "regenerate it with --cache-only"
        )
    return _load_sharded_cache(products, path, payload)


def _valid_vector(vector) -> bool:
    return (len(vector) == EMBED_DIM and all(math.isfinite(x) for x in vector)
            and any(x != 0 for x in vector))


def write_sharded_embeddings_cache(products: List[Product], path: str,
                                   shard_size: int = 5000) -> None:
    """Write portable float32 shards and publish their manifest atomically.

    Content-addressed shards stay below Git's per-file limit. The manifest binds
    each ID to its exact source text and each shard to its bytes. Float32 is the
    precision PostgreSQL's vector type stores; no quantization or new model is used.
    """
    from pathlib import Path

    if shard_size < 1:
        raise ValueError("shard_size must be positive")
    invalid = [p.productId for p in products
               if p.embedding is None or not _valid_vector(p.embedding)]
    if invalid:
        raise ValueError(f"Invalid embeddings for products {invalid[:20]}")
    if len({p.productId for p in products}) != len(products):
        raise ValueError("Duplicate product IDs in embedding cache")
    directory = Path(path).parent
    shards_dir = directory / "embeddings"
    shards_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"format": "float32-gzip-v1", "model": "us.cohere.embed-v4:0",
                "dim": EMBED_DIM, "count": len(products),
                "text_sha256": {str(p.productId): _text_digest(p) for p in products},
                "shards": []}
    for offset in range(0, len(products), shard_size):
        batch = products[offset:offset + shard_size]
        values = array("f")
        for product in batch:
            values.extend(product.embedding)
        if sys.byteorder != "little":
            values.byteswap()
        compressed = gzip.compress(values.tobytes(), compresslevel=6, mtime=0)
        digest = hashlib.sha256(compressed).hexdigest()
        relative = f"embeddings/{digest}.f32.gz"
        target = directory / relative
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            target.write_bytes(compressed)
        manifest["shards"].append({"file": relative, "sha256": digest,
                                   "ids": [p.productId for p in batch]})
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as handle:
        temporary = handle.name
        json.dump(manifest, handle, separators=(",", ":"))
        handle.write("\n")
    os.replace(temporary, path)
    logger.info("Wrote %d embeddings in %d verified shards", len(products), len(manifest["shards"]))


def _load_sharded_cache(products: List[Product], path: str, payload: dict) -> int:
    from pathlib import Path

    expected_model = os.getenv("BEDROCK_EMBED_MODEL_ID", "us.cohere.embed-v4:0")
    if payload.get("model") != expected_model or payload.get("dim") != EMBED_DIM:
        raise SystemExit("Embeddings cache model or dimension mismatch")
    wanted = {p.productId: p for p in products}
    digests = payload.get("text_sha256", {})
    absent = [p.productId for p in products if str(p.productId) not in digests]
    if absent:
        raise SystemExit(f"Embeddings cache has no cached vector for products {absent[:20]}: "
                         "regenerate with --cache-only")
    changed = [p.productId for p in products if digests[str(p.productId)] != _text_digest(p)]
    if changed:
        raise SystemExit(f"Embeddings cache text changed for products {changed[:20]}")
    directory = Path(path).resolve().parent
    seen = set()
    manifest_ids = set()
    for shard in payload.get("shards", []):
        ids = shard["ids"]
        if len(ids) != len(set(ids)) or manifest_ids.intersection(ids):
            raise SystemExit("Embeddings cache has duplicate product IDs")
        manifest_ids.update(ids)
        if not wanted.keys() & set(ids):
            continue
        source = (directory / shard["file"]).resolve()
        if not source.is_relative_to(directory):
            raise SystemExit("Embeddings shard path escapes the cache directory")
        compressed = source.read_bytes()
        if hashlib.sha256(compressed).hexdigest() != shard["sha256"]:
            raise SystemExit(f"Embeddings shard checksum mismatch: {shard['file']}")
        raw = gzip.decompress(compressed)
        if len(raw) != len(ids) * EMBED_DIM * 4:
            raise SystemExit(f"Embeddings shard has invalid length: {shard['file']}")
        values = array("f")
        values.frombytes(raw)
        if sys.byteorder != "little":
            values.byteswap()
        for index, pid in enumerate(ids):
            if pid not in wanted:
                continue
            vector = values[index * EMBED_DIM:(index + 1) * EMBED_DIM]
            if not _valid_vector(vector):
                raise SystemExit(f"Invalid cached vector for product {pid}")
            wanted[pid].embedding = vector
            seen.add(pid)
    if len(manifest_ids) != payload.get("count") or manifest_ids != {int(pid) for pid in digests}:
        raise SystemExit("Embeddings manifest count or text IDs disagree with its shards")
    if missing := sorted(wanted.keys() - seen):
        raise SystemExit(f"Embeddings cache has no cached vector for products {missing[:20]}")
    logger.info("Applied %d cached embeddings from %s", len(seen), path)
    return len(seen)


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


HNSW_INDEXES = ("pellier.product_catalog_embedding_hnsw", "pellier.product_catalog_visible_hnsw")
# The 50,000-row graph needs about 400 MB; below that the build spills and slows.
HNSW_BUILD_MEMORY = "512MB"


def _drop_hnsw_indexes(cur) -> List[str]:
    """Drop the schema's HNSW indexes on an empty catalog; return their exact definitions.

    Building each graph once after the bulk load is far faster than inserting
    50,000 rows into live graphs. An existing catalog keeps its live indexes.
    """
    cur.execute("SELECT EXISTS (SELECT 1 FROM pellier.product_catalog)")
    if cur.fetchone()[0]:
        return []
    definitions = []
    for name in HNSW_INDEXES:
        cur.execute("SELECT pg_get_indexdef(to_regclass(%s))", (name,))
        definition = cur.fetchone()[0]
        if definition:
            definitions.append(definition)
            cur.execute(f"DROP INDEX {name}")
    return definitions


def seed_database(products: List[Product]) -> None:
    """COPY into staging, then merge atomically without deleting current rows.

    One bulk transfer replaces a network round trip per product. Existing catalog
    rows are updated in place so their warehouse/order references survive reseeding;
    a row whose values are unchanged is not rewritten.
    """
    import psycopg

    columns = ('"productId", name, brand, color, price, description, category, tags, '
               'materials, rating, reviews, "imgUrl", badge, tier, quantity, embedding, persona_id')
    updated = columns.replace('"productId", ', "").split(", ")
    changed = (f"({', '.join('product_catalog.' + c for c in updated)}) IS DISTINCT FROM "
               f"({', '.join('EXCLUDED.' + c for c in updated)})")
    with psycopg.connect(_database_dsn()) as conn:
        with conn.cursor() as cur:
            index_definitions = _drop_hnsw_indexes(cur)
            cur.execute("CREATE TEMP TABLE catalog_seed "
                        "(LIKE pellier.product_catalog INCLUDING DEFAULTS) ON COMMIT DROP")
            with cur.copy(f"COPY catalog_seed ({columns}) FROM STDIN") as copy:
                for p in products:
                    embedding = p.embedding if p.embedding is not None else [0.0] * EMBED_DIM
                    vector = "[" + ",".join(format(x, ".9g") for x in embedding) + "]"
                    copy.write_row((str(p.productId), p.name, p.brand, p.color, p.price,
                                    p.description, p.department, json.dumps(p.tags),
                                    json.dumps(p.materials), p.rating, p.reviews,
                                    p.public_image_path, p.badge or "", 1, p.quantity,
                                    vector, p.persona))
            cur.execute('CREATE UNIQUE INDEX ON catalog_seed ("productId")')
            cur.execute("ANALYZE catalog_seed")
            cur.execute("""
                DELETE FROM pellier.product_catalog p
                 WHERE p."productId" ~ '^[0-9]+$'
                   AND NOT EXISTS (SELECT 1 FROM catalog_seed s
                                    WHERE s."productId" = p."productId")
            """)
            cur.execute(f"""
                INSERT INTO pellier.product_catalog ({columns})
                SELECT {columns} FROM catalog_seed
                ON CONFLICT ("productId") DO UPDATE SET
                    name = EXCLUDED.name, brand = EXCLUDED.brand, color = EXCLUDED.color,
                    price = EXCLUDED.price, description = EXCLUDED.description,
                    category = EXCLUDED.category, tags = EXCLUDED.tags,
                    materials = EXCLUDED.materials, rating = EXCLUDED.rating,
                    reviews = EXCLUDED.reviews, "imgUrl" = EXCLUDED."imgUrl",
                    badge = EXCLUDED.badge, tier = EXCLUDED.tier,
                    quantity = EXCLUDED.quantity, embedding = EXCLUDED.embedding,
                    persona_id = EXCLUDED.persona_id
                WHERE {changed}
            """)
            if index_definitions:
                logger.info("Building the catalog's HNSW indexes after the initial load")
                cur.execute(f"SET LOCAL maintenance_work_mem = '{HNSW_BUILD_MEMORY}'")
                for definition in index_definitions:
                    cur.execute(definition)
            cur.execute("ANALYZE pellier.product_catalog")
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
        for p in items[:10]:
            badge = f" [{p.badge}]" if p.badge else ""
            emb = "✓" if p.embedding else "·"
            print(f"  {emb} {p.productId:>3}  ${p.price:>6.0f}  {p.name}{badge}")

    if len(products) > 60:
        print("\n  Showing at most ten products per moment.")
    total_embedded = sum(1 for p in products if p.embedding)
    price_range = f"${min(p.price for p in products):.0f}–${max(p.price for p in products):.0f}"
    print(f"\n  Total: {len(products)} products | {total_embedded} embedded | {price_range}")
    print("=" * 72 + "\n")


# =========================================================================
# MAIN
# =========================================================================

def main():
    parser = argparse.ArgumentParser(description="Seed Pellier catalog with embeddings")
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--csv-only", action="store_true",
        help="Export CSV locally, no DB connection (large; not committed)",
    )
    output.add_argument(
        "--cache-only", action="store_true",
        help="Generate the sharded embeddings cache, no DB connection or CSV export",
    )
    parser.add_argument(
        "--from-cache", action="store_true",
        help="Use the committed embeddings cache (default; no catalog-embedding calls)",
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
    if args.cache_only and (args.from_cache or args.skip_embeddings):
        parser.error("--cache-only regenerates embeddings; do not combine it with "
                     "--from-cache or --skip-embeddings")
    if args.from_cache and args.skip_embeddings:
        parser.error("--from-cache and --skip-embeddings are mutually exclusive")

    products = load_catalog()

    if args.cache_only:
        # Paid authoring step, always explicit. Bootstrap never enters this path.
        generate_embeddings(products, args.region)
        failed = [p.productId for p in products if not p.embedding]
        if failed:
            raise SystemExit(
                f"Bedrock returned no embedding for products {failed}; "
                "the cache was not written. Check model access in the region and rerun."
            )
        # Refresh the committed cache whenever we regenerate, so the next
        # --from-cache run stays in sync with the live model output.
        write_sharded_embeddings_cache(products, EMBED_CACHE)
    elif args.skip_embeddings:
        logger.info("Skipping embedding generation (--skip-embeddings)")
    else:
        # Missing/stale cache data fails closed. Never fall back to Bedrock.
        load_embeddings_cache(products, EMBED_CACHE)

    print_summary(products)

    if not args.csv_only and not args.cache_only:
        seed_database(products)
    elif args.csv_only:
        write_csv(products, CSV_OUT_CURATED)
        logger.info("CSV-only mode — wrote CSV, skipped DB seeding")
        logger.info("To seed Aurora from the cache, run: --from-cache")


if __name__ == "__main__":
    main()
