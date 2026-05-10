#!/usr/bin/env python3
"""Generate the boutique catalog CSV + Tier 2 review markdown.

Output:
    data/pellier_catalog_unverified.csv   — 90-100 rows, embedding column empty
    data/pellier_catalog_review_tier2.md  — Tier 2 image verification checklist

CSV schema:
    productId, name, brand, color, price, description, category, tags,
    rating, reviews, imgUrl, reasoning_lead, reasoning_body, reasoning_urgent,
    match_reason, badge, tier, image_verified, embedding

Tier conventions:
    1 = showcase (hand-verified, do not modify)
    2 = demo-likely (verification required before going to prod)
    3 = background catalog (AI-suggested images, accepted drift)

Run:
    python scripts/build_boutique_catalog.py
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, field
from typing import List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

CSV_OUT = os.path.join(DATA_DIR, "pellier_catalog_unverified.csv")
REVIEW_OUT = os.path.join(DATA_DIR, "pellier_catalog_review_tier2.md")

CSV_FIELDS = [
    "productId", "name", "brand", "color", "price", "description",
    "category", "tags", "rating", "reviews", "imgUrl",
    "reasoning_lead", "reasoning_body", "reasoning_urgent",
    "match_reason", "badge", "tier", "image_verified", "embedding",
]


@dataclass
class Product:
    productId: int
    name: str
    brand: str
    color: str
    price: float
    description: str
    category: str
    tags: List[str]
    rating: float
    reviews: int
    imgUrl: str
    tier: int
    image_verified: bool = False
    reasoning_lead: str = ""
    reasoning_body: str = ""
    reasoning_urgent: str = ""
    match_reason: str = ""
    badge: Optional[str] = None
    embedding: str = ""

    def to_row(self) -> dict:
        d = asdict(self)
        d["tags"] = json.dumps(self.tags)
        d["badge"] = self.badge if self.badge else ""
        d["image_verified"] = "true" if self.image_verified else "false"
        return d


# ---------------------------------------------------------------------------
# TIER 1 — showcase products (hand-verified, do not modify)
# ---------------------------------------------------------------------------

TIER_1: List[Product] = [
    Product(
        productId=1, name="Italian Linen Camp Shirt", brand="Pellier Editions",
        color="Indigo", price=128.0,
        description="Breathable Italian linen with an easy camp collar and mother-of-pearl buttons. Softens with every wash.",
        category="Linen",
        tags=["minimal", "serene", "classic", "warm", "neutral", "everyday", "slow", "linen"],
        rating=4.8, reviews=214,
        imgUrl="https://images.unsplash.com/photo-1740711152088-88a009e877bb?w=1600&q=85",
        tier=1, image_verified=True,
        reasoning_lead="Picked because linen breathes beautifully in July",
        match_reason="linen, warm, everyday",
        badge="EDITORS_PICK",
    ),
    Product(
        productId=2, name="Wide-Leg Linen Trousers", brand="Pellier Editions",
        color="Oatmeal", price=98.0,
        description="Flowing wide-leg silhouette in garment-washed linen. Cut long with a relaxed waistband that moves with you.",
        category="Linen",
        tags=["creative", "bold", "warm", "earth", "everyday", "travel", "linen"],
        rating=4.7, reviews=166,
        imgUrl="https://images.unsplash.com/photo-1621767527621-ecdea6e1c522?w=1600&q=85",
        tier=1, image_verified=True,
        reasoning_lead="Matched on: earth, warm, travel",
        match_reason="earth, warm, travel",
    ),
    Product(
        productId=3, name="Signature Straw Tote", brand="Pellier Editions",
        color="Sand", price=68.0,
        description="Hand-woven seagrass tote with leather handles that darken beautifully with wear. Roomy enough for a weekend.",
        category="Accessories",
        tags=["classic", "serene", "neutral", "soft", "travel", "everyday", "accessories"],
        rating=4.9, reviews=402,
        imgUrl="https://images.unsplash.com/photo-1657118493503-9cabb641a033?w=1600&q=85",
        tier=1, image_verified=True,
        reasoning_lead="Price watch: $14 below category average.",
        reasoning_urgent="Only 3 left.",
        match_reason="travel, everyday, accessories",
        badge="BESTSELLER",
    ),
    Product(
        productId=4, name="Relaxed Oxford Shirt", brand="Pellier Editions",
        color="Chambray", price=88.0,
        description="Japanese oxford cotton with a soft collar roll. Tailored through the shoulder, relaxed through the body.",
        category="Linen",
        tags=["classic", "minimal", "neutral", "soft", "everyday", "work", "linen"],
        rating=4.6, reviews=131,
        imgUrl="https://images.unsplash.com/photo-1732605559386-bc59426d1b16?w=1600&q=85",
        tier=1, image_verified=True,
        reasoning_lead="Gift-ready: signature packaging, arrives tomorrow",
        match_reason="everyday, work, classic",
    ),
    Product(
        productId=5, name="Sundress in Washed Linen", brand="Pellier Editions",
        color="Russet", price=148.0,
        description="Midi-length sundress cut from washed linen in warm russet. Bias-cut skirt with a low tie back.",
        category="Dresses",
        tags=["creative", "bold", "warm", "earth", "evening", "dresses", "linen"],
        rating=4.9, reviews=286,
        imgUrl="https://images.unsplash.com/photo-1667905632551-361dd00e5e35?w=1600&q=85",
        tier=1, image_verified=True,
        reasoning_lead="Picked because you mentioned warm evenings",
        match_reason="evening, warm, dresses",
        badge="JUST_IN",
    ),
    Product(
        productId=6, name="Leather Slide Sandal", brand="Pellier Editions",
        color="Onyx", price=112.0,
        description="Vegetable-tanned Italian leather with a cushioned footbed that molds to your step. Hand-finished edges.",
        category="Footwear",
        tags=["minimal", "classic", "earth", "warm", "everyday", "travel", "footwear"],
        rating=4.7, reviews=178,
        imgUrl="https://images.unsplash.com/photo-1625318880107-49baad6765fd?w=1600&q=85",
        tier=1, image_verified=True,
        reasoning_lead="Matched on: classic, warm, travel",
        match_reason="classic, warm, travel",
    ),
    Product(
        productId=7, name="Cashmere-Blend Cardigan", brand="Pellier Editions",
        color="Forest", price=158.0,
        description="Long-line cardigan in a cashmere and merino blend. Ribbed cuffs, dropped shoulder, enough weight to drape.",
        category="Outerwear",
        tags=["minimal", "serene", "classic", "neutral", "earth", "slow", "evening", "outerwear"],
        rating=4.8, reviews=244,
        imgUrl="https://images.unsplash.com/photo-1687275168013-dcc11d9c74ab?w=1600&q=85",
        tier=1, image_verified=True,
        reasoning_lead="Price watch: $8 below category average.",
        reasoning_urgent="Only 5 left.",
        match_reason="slow, evening, outerwear",
    ),
    Product(
        productId=8, name="Ceramic Tumbler Set", brand="Pellier Home",
        color="Stoneware", price=52.0,
        description="Set of four hand-thrown stoneware tumblers with a pale matte glaze. Each one slightly different, all dishwasher safe.",
        category="Home",
        tags=["minimal", "serene", "creative", "neutral", "soft", "slow", "home"],
        rating=4.9, reviews=358,
        imgUrl="https://images.unsplash.com/photo-1610701596007-11502861dcfa?w=1600&q=85",
        tier=1, image_verified=True,
        reasoning_lead="Quiet layer that earns its evenings",
        match_reason="slow, home, minimal",
    ),
    Product(
        productId=9, name="Linen Utility Jacket", brand="Pellier Editions",
        color="Flax", price=178.0,
        description="Workwear-inspired utility jacket in heavyweight linen. Four patch pockets, horn buttons, a collar that stands.",
        category="Outerwear",
        tags=["adventurous", "creative", "earth", "neutral", "outdoor", "travel", "outerwear"],
        rating=4.7, reviews=152,
        imgUrl="https://images.unsplash.com/photo-1691053318576-4bf08315e877?w=1600&q=85",
        tier=1, image_verified=True,
        reasoning_lead="Picked because you liked outdoor layers",
        match_reason="outdoor, travel, outerwear",
    ),
    Product(
        productId=10, name="Featherweight Trail Runner", brand="Pellier Editions",
        color="Ember \u00b7 9.5", price=168.0,
        description="Lightweight trail runner with a breathable knit upper and a grippy rubber outsole. Engineered for warm-weather miles.",
        category="Footwear",
        tags=["adventurous", "warm", "outdoor", "everyday", "travel", "footwear"],
        rating=4.9, reviews=1400,
        imgUrl="https://images.unsplash.com/photo-1469395446868-fb6a048d5ca3?w=1600&q=85",
        tier=1, image_verified=True,
        reasoning_lead="Picked because the weave catches the last bit of golden hour",
        match_reason="athletic, footwear, gift",
        badge="JUST_IN",
    ),
]


# Populated by register_tier2 / register_tier3 in follow-up modules.
TIER_2: List[Product] = []
TIER_3: List[Product] = []


def _review_markdown(products: List[Product]) -> str:
    lines = ["# Tier 2 Image Verification", ""]
    lines.append(
        "Open each image URL in a browser. Mark **Approve** if the image "
        "reads as the described product in the storefront aesthetic. "
        "Otherwise suggest a replacement URL or keyword."
    )
    lines.append("")
    for p in products:
        search_slug = p.name.lower().replace(" ", "-")
        lines.append(f"## Product {p.productId}: {p.name} \u2014 {p.color}")
        lines.append(f"**Category:** {p.category}   **Price:** ${p.price:.0f}")
        lines.append(f"**Description:** {p.description}")
        lines.append(f"**Suggested URL:** {p.imgUrl}")
        lines.append(
            f"**Search if replacement needed:** "
            f"https://unsplash.com/s/photos/{search_slug}"
        )
        lines.append("**Verified:** [ ] Approve / [ ] Replace with: ___________")
        lines.append("")
    return "\n".join(lines)


def emit() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    all_products = TIER_1 + TIER_2 + TIER_3

    with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for p in all_products:
            writer.writerow(p.to_row())

    with open(REVIEW_OUT, "w", encoding="utf-8") as f:
        f.write(_review_markdown(TIER_2))

    by_tier = {1: 0, 2: 0, 3: 0}
    by_category: dict = {}
    for p in all_products:
        by_tier[p.tier] = by_tier.get(p.tier, 0) + 1
        by_category[p.category] = by_category.get(p.category, 0) + 1

    print(f"Wrote {len(all_products)} products to {CSV_OUT}")
    print(f"  Tier 1: {by_tier[1]}  Tier 2: {by_tier[2]}  Tier 3: {by_tier[3]}")
    print(f"  Categories: {sorted(by_category.items())}")
    print(f"Wrote review checklist to {REVIEW_OUT}")


if __name__ == "__main__":
    # Tier 2/3 are registered by sibling modules before we emit.
    from build_boutique_tier2 import register as register_tier2  # noqa: E402
    from build_boutique_tier3 import register as register_tier3  # noqa: E402

    register_tier2(TIER_2)
    register_tier3(TIER_3)
    emit()
