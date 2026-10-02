#!/usr/bin/env python3
"""
Seed the Pellier catalog — 60 curated products plus generated archive
distractors for retrieval evaluation.

The curated set stays stable: 10 products per persona (Marco / Anna / Theo /
Fresh), plus 10 house pieces the client book owns and 10 signature investment
pieces, zero overlap, IDs 1-60. Workshop story, inventory, orders, returns, and
final-sale policy all refer to those IDs.

The governed retrieval lab adds high-ID archive distractors by default. Their
embeddings are derived deterministically from the 60 committed Cohere Embed v4
vectors, so fresh-account bootstrap still makes zero catalog-embedding Bedrock
calls while the HNSW index and eval harness see a larger corpus.

Usage:
    # Generate embeddings via Bedrock + seed directly into Aurora:
    python scripts/seed_pellier_catalog.py

    # Generate embeddings + write CSV + embeddings cache (no DB connection):
    python scripts/seed_pellier_catalog.py --csv-only

    # PREFERRED FOR WORKSHOPS — seed from the committed embeddings cache,
    # no Bedrock embedding calls (deterministic, fast, no throttle/AccessDenied):
    python scripts/seed_pellier_catalog.py --from-cache

    # Curated-only shape for quick local debugging:
    python scripts/seed_pellier_catalog.py --from-cache --no-distractors

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
import copy
import csv
import json
import logging
import math
import os
import random
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
CSV_OUT_CURATED = os.path.join(DATA_DIR, "pellier_catalog_curated.csv")
CSV_OUT_EXPANDED = os.path.join(DATA_DIR, "pellier_catalog_expanded.csv")
# Committed cache of precomputed 1024-dim embeddings, keyed by productId.
# Generated once via --csv-only; loaded by --from-cache so the workshop
# bootstrap never has to call Bedrock to embed the catalog.
EMBED_CACHE = os.path.join(DATA_DIR, "embeddings_cache.json")
EMBED_DIM = 1024

# Curated products use IDs 1-60. Generated distractors live in a high numeric
# range so persona/order/policy exercises can keep treating 1-60 as stable.
CURATED_PRODUCT_COUNT = 60
DISTRACTOR_ID_START = 1000
DISTRACTOR_ID_END = 9999
# 60 curated + 940 archive = the 1,000-row corpus that README.md,
# scripts/health-gate.sh, and scripts/migrations/README.md all assert.
DEFAULT_DISTRACTOR_COUNT = 940

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
    source_product_id: Optional[int] = None
    blend_product_id: Optional[int] = None

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
            "house": "A house staple owned across the client book. Bath, bedding, tailoring, leather, and desk objects in warm neutrals.",
            "signature": "A signature investment piece for a long-standing client. Outerwear, tailoring, fine fragrance, gold, and hand-made objects at the top of the range.",
        }
        context = persona_context.get(self.persona, "")
        return (
            f"{self.name}. {self.description} "
            f"Brand: {self.brand}. Color: {self.color}. "
            f"Category: {self.category_name}. Tags: {tag_str}. "
            f"{context}"
        )

    @property
    def is_distractor(self) -> bool:
        return self.source_product_id is not None

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
            "isbestseller": str(self.isBestSeller).lower(),
            "boughtinlastmonth": self.boughtInLastMonth,
            "category_name": self.category_name,
            "quantity": self.quantity,
            "embedding": json.dumps(self.embedding) if self.embedding else "",
        }


# =========================================================================
# THE PERSONA PRODUCTS — 10 per persona, zero overlap, IDs 1-40
# =========================================================================

FRESH_PRODUCTS: List[Product] = [
    Product(1, "Olive Branch Vessel", "Pellier Home", "Ivory", 185,
            "Sculptural ceramic vessel for housewarming and new-home milestones. Hand-thrown stoneware with an olive branch motif and matte ivory glaze; a lasting entryway or mantel piece for a new homeowner.",
            CAT_HOME, ["ceramic", "sculptural", "minimal", "warm", "neutral", "home"],
            4.9, 127, "fresh-olive-branch-vessel.png", persona="fresh"),
    Product(2, "Hadley Linen Shirt", "Hadley", "Ivory", 248,
            "Airy, textured, and endlessly versatile. Cut from pure European linen with a relaxed silhouette and mother of pearl buttons.",
            CAT_APPAREL, ["linen", "minimal", "resort", "warm", "neutral", "everyday"],
            4.8, 312, "fresh-pellier-linen-shirt.png", persona="fresh", badge="EDITORS_PICK"),
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


# =========================================================================
# HOUSE PIECES — the SKUs the client book actually owns, IDs 41-50
#
# Client order history has to reference real product_catalog rows: the
# pellier.orders FK enforces it, and an order that cannot be joined is not
# evidence. These are the pieces named in operator queue copy and in
# Jessica Nakamura's return dispute.
# =========================================================================

HOUSE_PRODUCTS: List[Product] = [
    Product(41, "Coral Lacquer Catchall", "Pellier Maison", "Coral", 325.36,
            "Hand-shaped lacquered ceramic catchall with an organic wavy rim and a high-gloss coral glaze. For keys, rings, and the small things that otherwise go missing.",
            CAT_HOME, ["ceramic", "lacquer", "sculptural", "home", "entryway", "gift"],
            4.7, 156, "house-coral-lacquer-catchall.png", persona="house"),
    Product(42, "Luxury Bath Robe, Sage", "NestWell", "Sage", 107.30,
            "Waffle-weave cotton bath robe in muted sage. Long-staple cotton that softens with every wash, with patch pockets and a self-tie belt.",
            CAT_HOME, ["cotton", "bath", "home", "loungewear", "wellness", "gift"],
            4.6, 289, "house-sage-bath-robe.png", persona="house"),
    # Sold out on purpose. Lab 2's check_inventory contract separates a piece the
    # catalog does not carry (not_found) from a piece it carries with no units
    # (success, total_units 0); this is the second case, live, for every box.
    Product(43, "Quilted Silk Vest", "Pellier Atelier", "Ivory", 193.13,
            "Collarless vest in diamond-quilted washed silk. Light as a layer, warm as a coat lining, cut to wear open over knitwear.",
            CAT_APPAREL, ["silk", "quilted", "layering", "minimal", "neutral", "everyday"],
            4.5, 98, "house-quilted-silk-vest.png", quantity=0, persona="house"),
    Product(44, "Travertine Wall Clock", "Pellier Maison", "Stone", 248.00,
            "Wall clock cut from a single piece of honed travertine. No numerals, two slim brushed-brass hands, a silent movement.",
            CAT_HOME, ["stone", "travertine", "minimal", "home", "sculptural", "timeless"],
            4.8, 74, "house-travertine-wall-clock.png", persona="house"),
    Product(45, "Tailored Wool Blazer", "Pellier Atelier", "Charcoal", 346.38,
            "Single-breasted blazer in charcoal wool flannel. Half-canvassed, notch lapel, working cuffs. Tailored in a wool that holds its line.",
            CAT_APPAREL, ["wool", "tailoring", "blazer", "classic", "workwear", "timeless"],
            4.8, 142, "house-tailored-wool-blazer.png", persona="house"),
    Product(46, "Ivory Cashmere Throw", "Pellier Atelier", "Ivory", 420.00,
            "Grade-A Mongolian cashmere throw with hand-knotted fringe. Substantial loft, brushed twice for a surface that stays soft.",
            CAT_HOME, ["cashmere", "throw", "home", "neutral", "slow", "gift"],
            4.9, 118, "house-ivory-cashmere-throw.png", persona="house"),
    Product(47, "Vetiver Quietude", "Pellier Parfum", "Amber", 186.00,
            "Eau de parfum built on Haitian vetiver, dry cedar, and a trace of smoked vanilla. Quiet on the skin, long on the shirt collar.",
            CAT_BEAUTY, ["fragrance", "vetiver", "beauty", "warm", "earth", "gift"],
            4.7, 231, "house-vetiver-quietude.png", persona="house"),
    Product(48, "Cognac Market Tote", "Pellier Atelier", "Cognac", 540.00,
            "Full-grain vegetable-tanned leather market tote with rolled handles and saddle stitching. Unlined, so it takes on a patina rather than wearing out.",
            CAT_ACCESSORIES, ["leather", "tote", "accessories", "classic", "warm", "everyday"],
            4.9, 87, "house-cognac-market-tote.png", persona="house"),
    Product(49, "Stonewashed Linen Set", "EcoThread", "Flax", 310.00,
            "Stonewashed European flax bedding set. Breathable, deliberately relaxed, and finished without softening chemicals.",
            CAT_HOME, ["linen", "bedding", "home", "neutral", "slow", "wellness"],
            4.6, 204, "house-stonewashed-linen-set.png", persona="house"),
    Product(50, "Oat Merino Crew", "ZenMove", "Oat", 168.00,
            "Fine-gauge extra-fine merino crewneck in oat. Temperature-regulating, odour-resistant, and light enough to layer under a blazer.",
            CAT_APPAREL, ["merino", "knitwear", "everyday", "neutral", "minimal", "travel"],
            4.7, 276, "house-oat-merino-crew.png", persona="house"),
]


# =========================================================================
# SIGNATURE PIECES — premium depth, IDs 51-60
#
# Raises the catalog ceiling from $425 to $1,250. A top membership rung and a
# private appointment need pieces behind them that justify both.
# =========================================================================

SIGNATURE_PRODUCTS: List[Product] = [
    Product(51, "Camel Wool Overcoat", "Pellier Atelier", "Camel", 895.00,
            "Full-length overcoat in double-faced Italian wool, bonded rather than lined so it drapes without weight. Notch lapel, patch pockets, hand-finished hem.",
            CAT_APPAREL, ["wool", "outerwear", "tailoring", "camel", "timeless", "investment"],
            4.9, 63, "signature-camel-wool-overcoat.png", persona="signature", badge="JUST_IN"),
    Product(52, "Silk Charmeuse Slip Dress", "Pellier Atelier", "Bone", 485.00,
            "Bias-cut slip dress in heavyweight silk charmeuse. The bias does the shaping; the weight keeps it from clinging.",
            CAT_APPAREL, ["silk", "eveningwear", "bias", "minimal", "neutral", "investment"],
            4.8, 71, "signature-silk-charmeuse-slip-dress.png", persona="signature"),
    Product(53, "Double-Pleat Wool Trouser", "Pellier Atelier", "Chalk", 285.00,
            "High-waisted trouser in chalk wool with a double forward pleat and a turned cuff. Cut wide through the leg, tapered at the hem.",
            CAT_APPAREL, ["wool", "tailoring", "trouser", "neutral", "workwear", "classic"],
            4.7, 109, "signature-double-pleat-wool-trouser.png", persona="signature"),
    Product(54, "Suede Chelsea Boot", "Pellier Editions", "Tobacco", 395.00,
            "Chelsea boot in tobacco calf suede on a stacked leather heel. Goodyear-welted, so it can be resoled rather than replaced.",
            CAT_FOOTWEAR, ["suede", "footwear", "boot", "classic", "warm", "investment"],
            4.8, 134, "signature-suede-chelsea-boot.png", persona="signature"),
    Product(55, "Fig and Cedar Eau de Parfum", "Pellier Parfum", "Amber", 245.00,
            "Eau de parfum of green fig, cedar, and warm milk. Opens sharp and settles into something closer to skin.",
            CAT_BEAUTY, ["fragrance", "fig", "cedar", "beauty", "warm", "gift"],
            4.8, 96, "signature-fig-cedar-eau-de-parfum.png", persona="signature"),
    Product(56, "Rose Absolute Body Oil", "Pellier Parfum", "Blush", 118.00,
            "Body oil of rose absolute, squalane, and apricot kernel. Absorbs without residue; the scent fades to a clean sweetness.",
            CAT_BEAUTY, ["beauty", "body oil", "rose", "apothecary", "wellness", "gift"],
            4.6, 187, "signature-rose-absolute-body-oil.png", persona="signature"),
    Product(57, "Cashmere Travel Wrap", "Pellier Travel", "Oat", 340.00,
            "Oversized cashmere wrap that doubles as an aeroplane blanket. Rolls to the size of a paperback and ties with a flat linen ribbon.",
            CAT_ACCESSORIES, ["cashmere", "travel", "wrap", "neutral", "accessories", "gift"],
            4.9, 112, "signature-cashmere-travel-wrap.png", persona="signature"),
    Product(58, "Signet Ring, Brushed Gold", "Pellier Editions", "Gold", 480.00,
            "Solid brushed 14k gold signet with a blank oval face, left unengraved so it can be made personal later.",
            CAT_ACCESSORIES, ["gold", "jewellery", "signet", "accessories", "timeless", "investment"],
            4.9, 58, "signature-signet-ring-brushed-gold.png", persona="signature"),
    Product(59, "Hand-Knotted Wool Rug", "Pellier Maison", "Sand", 1250.00,
            "Hand-knotted wool rug in undyed sand with a barely-there tonal border. Roughly two hundred knots per square inch, woven over four months.",
            CAT_HOME, ["wool", "rug", "home", "artisanal", "neutral", "investment"],
            4.9, 41, "signature-hand-knotted-wool-rug.png", persona="signature"),
    Product(60, "Blown Glass Decanter", "Pellier Maison", "Clear", 210.00,
            "Mouth-blown glass decanter with a faintly irregular neck and a scatter of seed bubbles. Each one carries the breath that made it.",
            CAT_HOME, ["glass", "decanter", "home", "artisanal", "sculptural", "gift"],
            4.7, 88, "signature-blown-glass-decanter.png", persona="signature"),
]


ALL_PRODUCTS = (
    FRESH_PRODUCTS
    + MARCO_PRODUCTS
    + ANNA_PRODUCTS
    + THEO_PRODUCTS
    + HOUSE_PRODUCTS
    + SIGNATURE_PRODUCTS
)


# =========================================================================
# GENERATED RETRIEVAL DISTRACTORS
# =========================================================================

COLOR_CYCLE = [
    "Ivory", "Oat", "Flax", "Sage", "Clay", "Charcoal", "Chestnut", "Natural",
]

ARCHIVE_MOTIFS = [
    "travel edit",
    "gift edit",
    "home ritual study",
    "weekend capsule",
    "tabletop archive",
    "material study",
    "quiet utility",
    "small-batch run",
]

ARCHIVE_CAVEATS = [
    "slightly more structured than the curated hero piece",
    "not gift boxed by default",
    "made for browsing comparison rather than a featured placement",
    "kept as an archive variant with lower editorial priority",
    "close in material language but tuned for a different use case",
    "similar in tone, less exact for the shopper's stated occasion",
]


def _distractor_count_from_env(default: int = DEFAULT_DISTRACTOR_COUNT) -> int:
    raw = os.getenv("PELLIER_DISTRACTOR_COUNT", str(default))
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        logger.warning("Invalid PELLIER_DISTRACTOR_COUNT=%r; using %d", raw, default)
        return default


def _distractor_name(base: Product, ordinal: int) -> str:
    motif = ARCHIVE_MOTIFS[ordinal % len(ARCHIVE_MOTIFS)]
    noun = {
        CAT_APPAREL: "Garment",
        CAT_ACCESSORIES: "Accessory",
        CAT_HOME: "Object",
        CAT_BEAUTY: "Apothecary",
        CAT_FOOTWEAR: "Footwear",
        CAT_GIFTS: "Gift Kit",
    }.get(base.category_id, "Piece")
    return f"Pellier Archive {noun} {ordinal + 1:03d} - {motif.title()}"


def _distractor_tags(base: Product, ordinal: int) -> List[str]:
    extra = [
        "archive",
        "comparison",
        ARCHIVE_MOTIFS[ordinal % len(ARCHIVE_MOTIFS)].split()[0],
    ]
    tags: List[str] = []
    for tag in [*base.tags, *extra]:
        if tag not in tags:
            tags.append(tag)
    return tags[:8]


def _distractor_description(base: Product, ordinal: int) -> str:
    motif = ARCHIVE_MOTIFS[ordinal % len(ARCHIVE_MOTIFS)]
    caveat = ARCHIVE_CAVEATS[ordinal % len(ARCHIVE_CAVEATS)]
    tags = ", ".join(base.tags[:4])
    return (
        f"Archive variant adjacent to {base.category_name.lower()} searches for "
        f"{motif}. It echoes {base.name}'s material signals ({tags}) and "
        f"{base.color.lower()} palette, but is {caveat}. Use it as a retrieval "
        "distractor: plausible enough to compete, not the canonical workshop item."
    )


def generate_distractor_products(
    curated: List[Product],
    count: int = DEFAULT_DISTRACTOR_COUNT,
) -> List[Product]:
    """Build deterministic high-ID archive rows for retrieval evaluation."""
    if count <= 0:
        return []
    if not curated:
        raise ValueError("curated products are required to generate distractors")

    distractors: List[Product] = []
    for idx in range(count):
        base = curated[idx % len(curated)]
        blend = curated[(idx * 7 + 11) % len(curated)]
        product_id = DISTRACTOR_ID_START + idx
        rng = random.Random(f"pellier-archive-product-{product_id}")
        price_factor = 0.72 + (rng.random() * 0.68)
        price = round(max(18.0, float(base.price) * price_factor), 2)
        rating = round(max(3.7, min(4.8, float(base.rating) - 0.15 + rng.random() * 0.25)), 1)
        reviews = max(12, int(float(base.reviews) * (0.15 + rng.random() * 0.45)))
        distractors.append(
            Product(
                product_id,
                _distractor_name(base, idx),
                "Pellier Archive",
                COLOR_CYCLE[idx % len(COLOR_CYCLE)],
                price,
                _distractor_description(base, idx),
                base.category_id,
                _distractor_tags(base, idx),
                rating,
                reviews,
                base.imgPath,
                quantity=35,
                persona=base.persona,
                source_product_id=base.productId,
                blend_product_id=blend.productId,
            )
        )
    return distractors


def build_catalog(include_distractors: bool = True, distractor_count: int = DEFAULT_DISTRACTOR_COUNT) -> List[Product]:
    """Return curated products plus optional generated archive distractors."""
    curated = copy.deepcopy(ALL_PRODUCTS)
    if not include_distractors:
        return curated
    return curated + generate_distractor_products(curated, distractor_count)


def derive_distractor_embeddings(products: List[Product]) -> int:
    """Attach deterministic derived embeddings to generated distractors.

    The 60 curated vectors are real Cohere Embed v4 outputs from the committed
    cache. Distractors live near those vectors with a small deterministic blend
    and noise term. That keeps bootstrap offline while giving pgvector a corpus
    large enough for recall, rerank, and HNSW tuning to become visible.
    """
    base_vectors = {
        p.productId: p.embedding
        for p in products
        if not p.is_distractor and p.embedding and len(p.embedding) == EMBED_DIM
    }
    applied = 0
    missing: List[int] = []
    for p in products:
        if not p.is_distractor:
            continue
        base = base_vectors.get(int(p.source_product_id or 0))
        blend = base_vectors.get(int(p.blend_product_id or 0)) or base
        if not base or not blend:
            missing.append(p.productId)
            continue
        rng = random.Random(f"pellier-archive-embedding-{p.productId}")
        values = [
            (0.86 * float(base[i])) + (0.10 * float(blend[i])) + (0.012 * rng.uniform(-1.0, 1.0))
            for i in range(EMBED_DIM)
        ]
        base_norm = math.sqrt(sum(float(v) * float(v) for v in base)) or 1.0
        values_norm = math.sqrt(sum(v * v for v in values)) or 1.0
        scale = base_norm / values_norm
        p.embedding = [round(v * scale, 8) for v in values]
        applied += 1
    if missing:
        logger.warning(
            "Could not derive embeddings for %d distractors; missing base IDs: %s",
            len(missing), missing[:12],
        )
    logger.info("Derived %d archive distractor embeddings", applied)
    return applied


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

def write_embeddings_cache(products: List[Product], path: str) -> None:
    """Persist generated embeddings keyed by productId, for later --from-cache."""
    cache = {
        str(p.productId): p.embedding
        for p in products
        if p.embedding and len(p.embedding) == EMBED_DIM
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(
            {"model": "us.cohere.embed-v4:0", "dim": EMBED_DIM, "embeddings": cache},
            f,
        )
    logger.info("Wrote %d cached embeddings to %s", len(cache), path)


def load_embeddings_cache(products: List[Product], path: str) -> int:
    """Attach precomputed embeddings from the committed cache. Returns count applied."""
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
    applied = 0
    missing: List[int] = []
    for p in products:
        vec = cache.get(str(p.productId))
        if vec and len(vec) == EMBED_DIM:
            p.embedding = vec
            applied += 1
        else:
            missing.append(p.productId)
    if missing:
        logger.warning(
            "Cache missing/invalid embeddings for %d products: %s",
            len(missing), missing,
        )
    logger.info("Applied %d/%d cached embeddings from %s", applied, len(products), path)
    return applied


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
            # Clear only stale rows in the managed ID ranges. Keeping current
            # curated rows in place avoids ON DELETE CASCADE wiping
            # warehouse_inventory when the seeder is rerun after migrations.
            cur.execute(
                """
                DELETE FROM pellier.product_catalog
                WHERE "productId" ~ '^[0-9]+$'
                  AND (
                    "productId"::int BETWEEN 1 AND %s
                    OR "productId"::int BETWEEN %s AND %s
                  )
                  AND NOT ("productId" = ANY(%s))
                """,
                (
                    CURATED_PRODUCT_COUNT,
                    DISTRACTOR_ID_START,
                    DISTRACTOR_ID_END,
                    managed_product_ids,
                ),
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
                        p.category_name,
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
    """Print a summary table grouped by persona."""
    personas = {}
    for p in products:
        personas.setdefault(p.persona, []).append(p)

    total = len(products)
    curated_total = sum(1 for p in products if not p.is_distractor)
    distractor_total = total - curated_total
    print("\n" + "=" * 72)
    print(
        "PELLIER CATALOG — "
        f"{curated_total} curated products + {distractor_total} archive distractors"
    )
    print("=" * 72)

    for persona_id in ["fresh", "marco", "anna", "theo"]:
        items = personas.get(persona_id, [])
        curated_items = [p for p in items if not p.is_distractor]
        archive_items = [p for p in items if p.is_distractor]
        embedded = sum(1 for p in items if p.embedding)
        print(
            f"\n  {persona_id.upper()} "
            f"({len(curated_items)} curated, {len(archive_items)} archive, "
            f"{embedded} embedded)"
        )
        print(f"  {'─' * 60}")
        for p in curated_items:
            badge = f" [{p.badge}]" if p.badge else ""
            emb = "✓" if p.embedding else "·"
            print(f"  {emb} {p.productId:>3}  ${p.price:>6.0f}  {p.name}{badge}")
        if archive_items:
            print(
                f"      ... {len(archive_items)} archive distractors "
                f"(IDs {archive_items[0].productId}-{archive_items[-1].productId})"
            )

    total = len(products)
    total_embedded = sum(1 for p in products if p.embedding)
    price_range = f"${min(p.price for p in products):.0f}–${max(p.price for p in products):.0f}"
    print(f"\n  Total: {total} products | {total_embedded} embedded | {price_range}")
    print("=" * 72 + "\n")


# =========================================================================
# MAIN
# =========================================================================

def main():
    parser = argparse.ArgumentParser(description="Seed Pellier catalog with embeddings")
    parser.add_argument("--csv-only", action="store_true", help="Write CSV + embeddings cache only, no DB connection")
    parser.add_argument("--from-cache", action="store_true", help="Seed using committed embeddings cache (no Bedrock calls) — preferred for workshops")
    parser.add_argument("--skip-embeddings", action="store_true", help="Skip Cohere embedding generation (zero vectors)")
    parser.add_argument(
        "--distractor-count",
        type=int,
        default=_distractor_count_from_env(),
        help=(
            "Generated archive distractor rows to add above the 60 curated "
            f"products (default: {DEFAULT_DISTRACTOR_COUNT}, env: "
            "PELLIER_DISTRACTOR_COUNT)"
        ),
    )
    parser.add_argument(
        "--no-distractors",
        action="store_true",
        help="Seed only the 60 curated products.",
    )
    parser.add_argument("--region", default=os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION", "us-east-1"), help="AWS region")
    args = parser.parse_args()

    include_distractors = not args.no_distractors
    products = build_catalog(
        include_distractors=include_distractors,
        distractor_count=max(0, int(args.distractor_count)),
    )
    curated_products = [p for p in products if not p.is_distractor]

    if args.from_cache:
        # Workshop fast path: deterministic SQL load from precomputed vectors.
        # The cache stores the real 60 Cohere vectors; archive distractors are
        # derived from those vectors below.
        applied = load_embeddings_cache(curated_products, EMBED_CACHE)
        if applied < len(curated_products):
            logger.warning(
                "Only %d/%d products have cached embeddings — the rest seed "
                "with zero vectors and will not surface in semantic search.",
                applied, len(curated_products),
            )
    elif not args.skip_embeddings:
        generate_embeddings(curated_products, args.region)
        # Refresh the committed cache whenever we regenerate, so the next
        # --from-cache run stays in sync with the live model output.
        write_embeddings_cache(curated_products, EMBED_CACHE)
    else:
        logger.info("Skipping embedding generation (--skip-embeddings)")

    if include_distractors and not args.skip_embeddings:
        derive_distractor_embeddings(products)

    print_summary(products)

    if not args.csv_only:
        seed_database(products)
    else:
        csv_out = CSV_OUT_EXPANDED if include_distractors else CSV_OUT_CURATED
        write_csv(products, csv_out)
        logger.info("CSV-only mode — wrote CSV, skipped DB seeding")
        logger.info("To seed Aurora from the cache, run: --from-cache")


if __name__ == "__main__":
    main()
