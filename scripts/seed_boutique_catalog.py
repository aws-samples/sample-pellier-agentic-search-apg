#!/usr/bin/env python3
"""
Seed the boutique catalog — 36 curated products with real Cohere Embed v4 embeddings.

10 products per persona (Marco / Anna / Theo / Fresh), zero overlap.
Each persona: 1 hero + 1 weekend edit featured + 8 grid = 10 total.
Each product gets a 1024-dim embedding via Bedrock's Cohere Embed v4,
stored in Aurora's pgvector column for HNSW-indexed similarity search.

Usage:
    # Generate embeddings + write CSV (no DB connection needed):
    python scripts/seed_boutique_catalog.py --csv-only

    # Generate embeddings + seed directly into Aurora:
    python scripts/seed_boutique_catalog.py

    # Skip embedding generation (use empty vectors, for local dev):
    python scripts/seed_boutique_catalog.py --skip-embeddings --csv-only

Environment:
    DB_HOST, DB_NAME, DB_USER, DB_PASSWORD — Aurora connection
    AWS_REGION — Bedrock region (default: us-east-1)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CSV_OUT = os.path.join(DATA_DIR, "boutique_catalog_40.csv")

# CSV column order matches the seed-database.sh temp_products schema
CSV_FIELDS = [
    "productId", "product_description", "imgurl", "producturl",
    "stars", "reviews", "price", "category_id", "isbestseller",
    "boughtinlastmonth", "category_name", "quantity", "embedding",
]

# Category IDs (matching existing catalog conventions)
CAT_APPAREL = 1
CAT_ACCESSORIES = 2
CAT_HOME = 3
CAT_BEAUTY = 4
CAT_FOOTWEAR = 5
CAT_GIFTS = 6

CATEGORY_NAMES = {
    CAT_APPAREL: "Apparel",
    CAT_ACCESSORIES: "Accessories",
    CAT_HOME: "Home Decor",
    CAT_BEAUTY: "Beauty",
    CAT_FOOTWEAR: "Footwear",
    CAT_GIFTS: "Gifts",
}


@dataclass
class Product:
    productId: int
    name: str
    brand: str
    color: str
    price: float
    description: str
    category_id: int
    tags: List[str]
    rating: float
    reviews: int
    imgPath: str  # relative to /products/ in the frontend
    quantity: int = 50
    isBestSeller: bool = False
    boughtInLastMonth: int = 0
    persona: str = "fresh"  # which persona owns this product
    badge: Optional[str] = None
    embedding: Optional[List[float]] = None

    @property
    def category_name(self) -> str:
        return CATEGORY_NAMES.get(self.category_id, "Other")

    @property
    def search_text(self) -> str:
        """The text we embed — rich enough for high-quality semantic search.

        Includes name, full description, brand, color, category, tags,
        AND persona context so intra-persona products cluster tightly
        in embedding space. This is what makes the pgvector demo work:
        a query like "linen for travel" lands close to Marco's products
        because the embedding captured both the product attributes AND
        the shopper context.
        """
        tag_str = ", ".join(self.tags)
        persona_context = {
            "marco": "For a traveler who loves natural fibers, linen, leather, and warm neutrals. Travel-ready, packable, timeless.",
            "anna": "For a gift-giver who values thoughtful, wrap-ready pieces across price bands. Milestone occasions, considered objects.",
            "theo": "For a slow-living enthusiast who values ceramics, artisanal craft, patina, and home ritual objects.",
            "fresh": "For a new visitor exploring a curated boutique. Editorial bestsellers, versatile everyday pieces.",
        }
        context = persona_context.get(self.persona, "")
        return (
            f"{self.name}. {self.description} "
            f"Brand: {self.brand}. Color: {self.color}. "
            f"Category: {self.category_name}. Tags: {tag_str}. "
            f"{context}"
        )

    def to_csv_row(self) -> dict:
        return {
            "productId": str(self.productId).ljust(10),
            "product_description": self.description,
            "imgurl": f"/products/{self.imgPath}",
            "producturl": f"/p/{self.productId}",
            "stars": self.rating,
            "reviews": self.reviews,
            "price": self.price,
            "category_id": self.category_id,
            "isbestseller": str(self.isBestSeller).lower(),
            "boughtinlastmonth": self.boughtInLastMonth,
            "category_name": self.category_name,
            "quantity": self.quantity,
            "embedding": json.dumps(self.embedding) if self.embedding else "",
        }


# =========================================================================
# THE 40 PRODUCTS — 10 per persona, zero overlap
# =========================================================================

FRESH_PRODUCTS: List[Product] = [
    Product(1, "Olive Branch Vessel", "Pellier Home", "Ivory", 185,
            "Sculptural ceramic vase with olive branch motif. Hand-thrown stoneware with a matte ivory glaze.",
            CAT_HOME, ["ceramic", "sculptural", "minimal", "warm", "neutral", "home"],
            4.9, 127, "fresh-olive-branch-vessel.png", persona="fresh"),
    Product(2, "Hadley Linen Shirt", "Hadley", "Ivory", 248,
            "Airy, textured, and endlessly versatile. Cut from pure European linen with a relaxed silhouette and mother of pearl buttons.",
            CAT_APPAREL, ["linen", "minimal", "resort", "warm", "neutral", "everyday"],
            4.8, 312, "fresh-hadley-linen-shirt.png", persona="fresh", badge="EDITORS_PICK"),
    Product(3, "Nocturne Leather Weekender", "Pellier Travel", "Espresso", 425,
            "Full-grain leather weekend bag with canvas lining. Burnished brass hardware. The quiet kind of heft.",
            CAT_ACCESSORIES, ["leather", "travel", "classic", "warm", "earth", "accessories"],
            4.9, 89, "fresh-nocturne-leather-weekender.png", persona="fresh"),
    Product(4, "Santal & Fig Candle", "Pellier Home", "Amber", 92,
            "Hand-poured soy candle with santal, fig leaf, and cedarwood. 60-hour burn time in a reusable amber glass vessel.",
            CAT_HOME, ["candle", "home", "minimal", "warm", "slow"],
            4.7, 445, "fresh-santal-fig-candle.png", persona="fresh"),
    Product(5, "Heritage Rectangular Watch", "Pellier Editions", "Tan", 420,
            "Swiss movement, rectangular case in brushed steel. Italian leather strap in warm tan.",
            CAT_ACCESSORIES, ["watch", "classic", "minimal", "timeless", "accessories"],
            4.8, 203, "fresh-heritage-rectangular-watch.png", persona="fresh", badge="JUST_IN"),
    Product(6, "Neroli Apothecary Bottle", "Pellier Home", "Clear", 78,
            "Cold-pressed neroli oil in a hand-blown apothecary bottle. For pulse points or a warm bath.",
            CAT_BEAUTY, ["beauty", "apothecary", "minimal", "home", "warm"],
            4.6, 178, "fresh-neroli-apothecary-bottle.png", persona="fresh"),
    Product(7, "Solstice Woven Mat Set", "Pellier Home", "Natural", 145,
            "Set of four hand-woven placemats in natural jute. Each one slightly different — the mark of handcraft.",
            CAT_HOME, ["wellness", "home", "neutral", "artisanal", "slow"],
            4.5, 92, "fresh-solstice-woven-mat-set.png", persona="fresh"),
    Product(8, "Alba Linen Lounge Set", "Pellier Editions", "Oat", 298,
            "Two-piece lounge set in pre-washed European linen. Relaxed-fit top and drawstring trousers.",
            CAT_APPAREL, ["linen", "loungewear", "neutral", "minimal", "everyday", "slow"],
            4.7, 156, "fresh-alba-linen-lounge-set.png", persona="fresh"),
    Product(9, "Cloudform Studio Runner", "Pellier Active", "Stone", 165,
            "Lightweight knit runner with cloud-foam midsole. Breathable, packable, built for all-day wear.",
            CAT_FOOTWEAR, ["activewear", "neutral", "minimal", "wellness", "footwear"],
            4.6, 234, "fresh-cloudform-studio-runner.png", persona="fresh"),
    Product(10, "Washed Canvas Tote", "Pellier Everyday", "Cream", 68,
            "Washed canvas tote with leather handle straps. Roomy, lightweight, universally appealing.",
            CAT_ACCESSORIES, ["canvas", "everyday", "neutral", "accessories", "minimal"],
            4.5, 310, "fresh-linen-tote-bag.png", persona="fresh"),
]

MARCO_PRODUCTS: List[Product] = [
    Product(11, "Italian Linen Camp Shirt", "Pellier Editions", "Indigo", 228,
            "Camp-collar shirt in deep indigo European linen. Relaxed fit, mother of pearl buttons, pre-washed softness.",
            CAT_APPAREL, ["linen", "resort", "travel", "warm", "minimal", "everyday"],
            4.8, 287, "marco-linen-camp-shirt-indigo.png", persona="marco", badge="BESTSELLER"),
    Product(12, "Canvas Dopp Kit", "Pellier Travel", "Olive", 85,
            "Waxed canvas dopp kit with brass YKK zipper. Water-resistant lining. Sized for a carry-on.",
            CAT_ACCESSORIES, ["canvas", "travel", "classic", "accessories", "minimal"],
            4.7, 198, "marco-canvas-dopp-kit.png", persona="marco"),
    Product(13, "Leather Card Wallet", "Pellier Editions", "Cognac", 95,
            "Slim card wallet in full-grain vegetable-tanned leather. Four slots, one center pocket. Ages beautifully.",
            CAT_ACCESSORIES, ["leather", "classic", "minimal", "timeless", "accessories", "everyday"],
            4.9, 342, "marco-leather-card-wallet.png", persona="marco"),
    Product(14, "Linen Drawstring Trousers", "Pellier Editions", "Oat", 178,
            "Lightweight drawstring trousers in pre-washed European linen. Tapered leg, deep pockets.",
            CAT_APPAREL, ["linen", "travel", "resort", "neutral", "minimal", "everyday"],
            4.7, 225, "marco-linen-drawstring-trousers.png", persona="marco"),
    Product(15, "Espadrille Slides", "Pellier Editions", "Natural", 118,
            "Jute-soled espadrille slides with leather footbed. For coastal mornings and golden-hour terraces.",
            CAT_FOOTWEAR, ["footwear", "resort", "travel", "warm", "neutral"],
            4.6, 167, "marco-espadrille-slides.png", persona="marco"),
    Product(16, "Linen Overshirt", "Pellier Editions", "Sage", 195,
            "Linen-cotton blend overshirt in sage green. Relaxed fit, chest pocket. A layer that earns its keep.",
            CAT_APPAREL, ["linen", "travel", "minimal", "neutral", "everyday", "warm"],
            4.7, 143, "marco-linen-overshirt-sage.png", persona="marco", badge="EDITORS_PICK"),
    Product(17, "Leather Weekend Holdall", "Pellier Travel", "Tan", 485,
            "Full-grain leather holdall with brass buckles. Canvas-lined interior, padded base. Built for 48 hours.",
            CAT_ACCESSORIES, ["leather", "travel", "classic", "warm", "earth", "accessories"],
            4.9, 76, "marco-leather-weekend-holdall.png", persona="marco"),
    Product(18, "Cotton-Linen Crew Tee", "Pellier Editions", "Cream", 68,
            "Cotton-linen blend crew neck tee. Pre-washed for softness, slightly textured weave.",
            CAT_APPAREL, ["linen", "everyday", "minimal", "neutral", "warm"],
            4.5, 412, "marco-cotton-linen-tee.png", persona="marco"),
    Product(19, "Straw Panama Hat", "Pellier Editions", "Cream", 145,
            "Woven straw panama with black grosgrain ribbon. UPF 50+. Rolls without creasing.",
            CAT_ACCESSORIES, ["accessories", "travel", "resort", "classic", "warm"],
            4.8, 98, "marco-straw-panama-hat.png", persona="marco", badge="JUST_IN"),
    Product(20, "Merino Travel Socks", "Pellier Active", "Multi", 38,
            "Three-pack of merino wool crew socks in charcoal, oat, and olive. Temperature-regulating, odor-resistant.",
            CAT_APPAREL, ["merino", "travel", "everyday", "minimal", "accessories"],
            4.6, 534, "marco-merino-travel-socks.png", persona="marco"),
]

ANNA_PRODUCTS: List[Product] = [
    Product(21, "Beeswax Taper Candles", "Pellier Home", "Ivory", 48,
            "Set of four hand-poured beeswax tapers. Clean burn, subtle honey scent. Arrives tied with cotton twine.",
            CAT_HOME, ["candle", "home", "gift", "slow", "artisanal"],
            4.8, 289, "anna-beeswax-taper-candles.png", persona="anna", badge="BESTSELLER"),
    Product(22, "Monogrammed Linen Napkins", "Pellier Home", "White", 72,
            "Set of four linen napkins in soft white with optional monogram. Hemstitched edges, gift-boxed.",
            CAT_HOME, ["linen", "home", "gift", "minimal", "artisanal"],
            4.7, 178, "anna-monogrammed-napkins.png", persona="anna"),
    Product(23, "Ceramic Ring Dish", "Pellier Home", "Speckled Cream", 35,
            "Small hand-thrown ceramic ring dish in speckled cream glaze. For the bedside, the vanity, the windowsill.",
            CAT_HOME, ["ceramic", "home", "gift", "artisanal", "minimal"],
            4.9, 412, "anna-ceramic-ring-dish.png", persona="anna"),
    Product(24, "Botanical Print Scarf", "Pellier Editions", "Sage/Terracotta", 128,
            "Silk scarf in muted botanical print — sage leaves and terracotta blooms. Hand-rolled edges.",
            CAT_ACCESSORIES, ["accessories", "gift", "classic", "warm", "earth"],
            4.6, 145, "anna-botanical-scarf.png", persona="anna", badge="EDITORS_PICK"),
    Product(25, "Reed Diffuser", "Pellier Home", "Black Glass", 62,
            "Matte black glass reed diffuser with natural rattan sticks. Neroli and sandalwood. Lasts 3 months.",
            CAT_HOME, ["home", "gift", "minimal", "warm", "slow"],
            4.7, 367, "anna-reed-diffuser.png", persona="anna"),
    Product(26, "Handmade Soap Set", "Pellier Apothecary", "Multi", 45,
            "Three artisan soap bars in a wooden box — lavender, oat milk, and wild honey. Tied with hemp cord.",
            CAT_BEAUTY, ["beauty", "gift", "artisanal", "home", "slow"],
            4.8, 298, "anna-handmade-soap-set.png", persona="anna"),
    Product(27, "Ceramic Bud Vase", "Pellier Home", "Dusty Rose", 42,
            "Small ceramic bud vase in dusty rose glaze. For a single stem on a desk, a shelf, a bedside table.",
            CAT_HOME, ["ceramic", "home", "gift", "sculptural", "minimal"],
            4.6, 223, "anna-ceramic-bud-vase.png", persona="anna"),
    Product(28, "Leather Journal", "Pellier Editions", "Chestnut", 58,
            "Leather-bound journal with hand-stitched spine. 192 pages of cream laid paper. Refillable.",
            CAT_ACCESSORIES, ["leather", "gift", "classic", "timeless", "accessories"],
            4.9, 187, "anna-leather-journal.png", persona="anna", badge="JUST_IN"),
    Product(29, "Brass Photo Frame", "Pellier Home", "Gold", 55,
            "Hammered brass photo frame, 5x7. Stands or hangs. The kind of frame that makes a photo feel kept.",
            CAT_HOME, ["home", "gift", "classic", "warm", "accessories"],
            4.7, 156, "anna-brass-photo-frame.png", persona="anna"),
    Product(30, "Gift Wrapping Kit", "Pellier Gifting", "Blush", 28,
            "Cream tissue paper, blush satin ribbon, kraft gift tags with cotton string. Enough for three gifts.",
            CAT_GIFTS, ["gift", "minimal", "artisanal", "accessories"],
            4.5, 478, "anna-gift-wrapping-kit.png", persona="anna"),
]

THEO_PRODUCTS: List[Product] = [
    Product(31, "Stoneware Pour-Over Set", "Pellier Home", "Ash Grey", 165,
            "Hand-thrown stoneware pour-over dripper and carafe in ash grey glaze. The morning ritual, elevated.",
            CAT_HOME, ["ceramic", "home", "slow", "artisanal", "minimal"],
            4.9, 134, "theo-stoneware-pour-over.png", persona="theo", badge="EDITORS_PICK"),
    Product(32, "Raw Linen Throw", "Pellier Home", "Flax", 195,
            "Raw linen throw blanket in natural flax. Gets softer with every wash. For the chair, the sofa, the bed.",
            CAT_HOME, ["linen", "home", "slow", "neutral", "minimal"],
            4.8, 201, "theo-raw-linen-throw.png", persona="theo"),
    Product(33, "Olive Wood Cutting Board", "Pellier Home", "Natural", 88,
            "Hand-carved olive wood cutting board with natural grain patterns. Each one unique — the mark of the tree.",
            CAT_HOME, ["home", "artisanal", "slow", "warm", "earth"],
            4.7, 312, "theo-olive-wood-board.png", persona="theo", badge="BESTSELLER"),
    Product(34, "Terracotta Planter", "Pellier Home", "Earth", 52,
            "Unglazed terracotta planter with drainage hole. Develops a natural patina over months.",
            CAT_HOME, ["ceramic", "home", "slow", "earth", "artisanal"],
            4.6, 256, "theo-terracotta-planter.png", persona="theo"),
    Product(35, "Brass Incense Holder", "Pellier Home", "Brass", 45,
            "Minimal brass incense holder with a single channel. Hand-forged, develops patina. For the ritual, not the rush.",
            CAT_HOME, ["home", "slow", "minimal", "artisanal", "warm"],
            4.8, 189, "theo-brass-incense-holder.png", persona="theo"),
    Product(36, "Ceramic Tumblers", "Pellier Home", "Charcoal", 78,
            "Set of two hand-thrown ceramic tumblers in speckled charcoal glaze. No two exactly alike.",
            CAT_HOME, ["ceramic", "home", "slow", "artisanal", "minimal"],
            4.7, 245, "theo-ceramic-tumblers.png", persona="theo"),
    Product(37, "Wabi-Sabi Bowl", "Pellier Home", "Cream", 65,
            "Stoneware bowl in matte cream with deliberate imperfections. For the morning granola, the evening soup.",
            CAT_HOME, ["ceramic", "home", "slow", "artisanal", "minimal", "sculptural"],
            4.9, 167, "theo-wabi-sabi-bowl.png", persona="theo"),
    Product(38, "Beeswax Pillar Candle", "Pellier Home", "Natural", 38,
            "Thick beeswax pillar candle, hand-dipped. Burns for 80 hours. The uneven surface is the point.",
            CAT_HOME, ["candle", "home", "slow", "artisanal", "warm"],
            4.6, 334, "theo-beeswax-pillar-candle.png", persona="theo"),
    Product(39, "Linen Table Runner", "Pellier Home", "Flax", 85,
            "Hand-woven linen table runner in natural undyed flax. The kind of piece that makes a Tuesday feel intentional.",
            CAT_HOME, ["linen", "home", "slow", "neutral", "artisanal"],
            4.7, 178, "theo-linen-table-runner.png", persona="theo", badge="JUST_IN"),
    Product(40, "Charcoal Soap Bar", "Pellier Apothecary", "Black", 24,
            "Japanese-style activated charcoal soap. Handmade in small batches. Detoxifying, grounding, minimal.",
            CAT_BEAUTY, ["beauty", "slow", "artisanal", "minimal", "home"],
            4.5, 412, "theo-charcoal-soap-bar.png", persona="theo"),
]

ALL_PRODUCTS = FRESH_PRODUCTS + MARCO_PRODUCTS + ANNA_PRODUCTS + THEO_PRODUCTS


# =========================================================================
# EMBEDDING GENERATION
# =========================================================================

def generate_embeddings(products: List[Product], region: str) -> None:
    """Generate Cohere Embed v4 embeddings via Bedrock for all products."""
    import boto3

    client = boto3.client("bedrock-runtime", region_name=region)
    logger.info("Generating embeddings for %d products via Cohere Embed v4...", len(products))

    for i, product in enumerate(products):
        text = product.search_text
        try:
            payload = json.dumps({
                "texts": [text],
                "input_type": "search_document",
                "embedding_types": ["float"],
                "output_dimension": 1024,
            })
            response = client.invoke_model(
                body=payload,
                modelId="us.cohere.embed-v4:0",
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
# CSV EXPORT
# =========================================================================

def write_csv(products: List[Product], path: str) -> None:
    """Write the catalog to a CSV matching seed-database.sh's schema."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for p in products:
            writer.writerow(p.to_csv_row())
    logger.info("Wrote %d products to %s", len(products), path)


# =========================================================================
# DIRECT DB SEEDING
# =========================================================================

def seed_database(products: List[Product]) -> None:
    """Insert products directly into Aurora via psycopg."""
    import psycopg

    dsn = (
        f"host={os.environ['DB_HOST']} "
        f"dbname={os.environ['DB_NAME']} "
        f"user={os.environ['DB_USER']} "
        f"password={os.environ['DB_PASSWORD']}"
    )

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Clear existing boutique products (IDs 1-40)
            cur.execute(
                'DELETE FROM pellier.product_catalog WHERE "productId"::int BETWEEN 1 AND 40'
            )
            logger.info("Cleared existing boutique products (IDs 1-39)")

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
                         badge, tier, quantity, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s::vector)
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
                        embedding = EXCLUDED.embedding
                    """,
                    (
                        str(p.productId),
                        p.name,
                        p.brand,
                        p.color,
                        p.price,
                        p.description,
                        p.category_name,
                        tags_json,
                        p.rating,
                        p.reviews,
                        f"/products/{p.imgPath}",
                        p.badge or '',
                        p.quantity,
                        embedding_str,
                    ),
                )

            conn.commit()
            logger.info("Seeded %d products into Aurora", len(products))


# =========================================================================
# SUMMARY
# =========================================================================

def print_summary(products: List[Product]) -> None:
    """Print a summary table grouped by persona."""
    personas = {}
    for p in products:
        personas.setdefault(p.persona, []).append(p)

    total = len(products)
    print("\n" + "=" * 72)
    print(f"BOUTIQUE CATALOG — {total} PRODUCTS (9 per persona)")
    print("=" * 72)

    for persona_id in ["fresh", "marco", "anna", "theo"]:
        items = personas.get(persona_id, [])
        embedded = sum(1 for p in items if p.embedding)
        print(f"\n  {persona_id.upper()} ({len(items)} products, {embedded} embedded)")
        print(f"  {'─' * 60}")
        for p in items:
            badge = f" [{p.badge}]" if p.badge else ""
            emb = "✓" if p.embedding else "·"
            print(f"  {emb} {p.productId:>3}  ${p.price:>6.0f}  {p.name}{badge}")

    total = len(products)
    total_embedded = sum(1 for p in products if p.embedding)
    price_range = f"${min(p.price for p in products):.0f}–${max(p.price for p in products):.0f}"
    print(f"\n  Total: {total} products | {total_embedded} embedded | {price_range}")
    print("=" * 72 + "\n")


# =========================================================================
# MAIN
# =========================================================================

def main():
    parser = argparse.ArgumentParser(description="Seed boutique catalog with embeddings")
    parser.add_argument("--csv-only", action="store_true", help="Write CSV only, no DB connection")
    parser.add_argument("--skip-embeddings", action="store_true", help="Skip Cohere embedding generation")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"), help="AWS region")
    args = parser.parse_args()

    products = ALL_PRODUCTS

    if not args.skip_embeddings:
        generate_embeddings(products, args.region)
    else:
        logger.info("Skipping embedding generation (--skip-embeddings)")

    write_csv(products, CSV_OUT)
    print_summary(products)

    if not args.csv_only:
        seed_database(products)
    else:
        logger.info("CSV-only mode — skipping DB seeding")
        logger.info("To seed Aurora, run without --csv-only")


if __name__ == "__main__":
    main()
