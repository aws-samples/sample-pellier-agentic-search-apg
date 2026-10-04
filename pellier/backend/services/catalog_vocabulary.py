"""The catalog vocabulary a search plan may name.

Kept in sync with the ``pellier.product_catalog`` seed. The structured
extractor shows these lists to the model, and ``services.search_plan`` drops
any value outside them, so a hallucinated department or tag can only ever be
ignored. Standard library only: the Gateway Lambda plans searches with it.
"""

from typing import List

# The eight store departments (`DEPARTMENTS` in scripts/seed_pellier_catalog.py).
# If the catalog adds a department, tag or material, update these lists.
KNOWN_CATEGORIES: List[str] = [
    "Clothing",
    "Shoes",
    "Bags and travel",
    "Accessories",
    "Home",
    "Kitchen and table",
    "Bath and body",
    "Stationery and gifts",
]

KNOWN_TAGS: List[str] = [
    "accessories", "activewear", "apothecary", "artisanal", "beauty",
    "candle", "canvas", "ceramic", "classic", "earth", "everyday",
    "footwear", "gift", "home", "leather", "linen", "loungewear",
    "merino", "minimal", "neutral", "resort", "sculptural", "slow",
    "timeless", "travel", "warm", "watch", "wellness",
]

# Everything a product is made of, components and blends included. A material
# exclusion ("no wool") is enforced against this list, because the merchandising
# tags above name only a product's main material. Merino and cashmere products
# also list wool; suede is leather; stoneware and terracotta are ceramic.
KNOWN_MATERIALS: List[str] = [
    "acetate", "beeswax", "brass", "canvas", "cashmere", "ceramic", "cotton", "foam",
    "glass", "gold", "iron", "jute", "leather", "linen", "merino", "nylon", "paper",
    "polyester", "rattan", "rubber", "seagrass", "silicone", "silk", "silver",
    "soy wax", "steel", "stone", "straw", "wood", "wool",
]
