#!/usr/bin/env python3
"""Import the catalog's product photographs and derive the variants the app serves.

The 100 catalog masters live outside the repository: they are multi-megabyte
PNG drafts the owner keeps beside their generation provenance, and the
repository ships only responsive derivatives. This script maps every catalog
row to exactly one master by name, derives the WebP and AVIF variants straight
from that master into ``pellier/frontend/public/products/``, and points the
catalog's ``image`` at the stem. ``derive_product_variants`` owns validation
and encoding; this script owns the catalog mapping.

Mapping rule
------------

``<moment>-<slug(name)>.png``, where ``slug`` lowercases the name and turns
every run of characters outside ``[a-z0-9]`` into one hyphen. Six masters were
named differently when generated; ``NAMED_MASTERS`` records them so the rule
stays mechanical for the other 94 and the exceptions stay visible. The run
fails before writing anything if a product has no master, a master would serve
two products, or a master in the source folder maps to no product.

Widths
------

480 and 960 are what every ``ResponsiveImage`` srcset requests. 1122 is the
third candidate catalog cards and the product page add for 2x displays: it is
the native width of the 1122x1402 masters and a 6.5% downscale of the
1200x1500 masters, so no variant is ever upscaled. Masters are never cropped,
resized or re-encoded themselves.

Usage
-----

    # Report the mapping and the validation result. Nothing is written.
    python3 scripts/import_product_photos.py --source <folder> --check

    # Derive every variant and update data/pellier_catalog.json.
    python3 scripts/import_product_photos.py --source <folder>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_product_variants import PRODUCTS, _dimensions, _encode, validate  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "data" / "pellier_catalog.json"

# Widths every catalog stem publishes, in both formats.
CATALOG_WIDTHS = (480, 960, 1122)
FORMATS = ("webp", "avif")

# Masters whose generated file name does not follow the slug rule.
NAMED_MASTERS: Dict[int, str] = {
    4: "fresh-santal-and-fig-candle",
    22: "anna-linen-napkins",
    70: "fresh-linen-apron",
    82: "house-linen-cushion-covers",
    94: "marco-packing-cubes",
    97: "marco-travel-bottles",
}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def expected_stem(product: dict) -> str:
    return NAMED_MASTERS.get(int(product["id"])) or f"{product['moment']}-{slug(product['name'])}"


@dataclass(frozen=True)
class Mapping:
    product_id: int
    name: str
    stem: str
    master: Path
    width: int
    height: int


def plan(catalog: List[dict], source: Path) -> List[Mapping]:
    """One master per product, every master used once. Raises on any gap."""
    problems: List[str] = []
    mappings: List[Mapping] = []
    claimed: Dict[str, int] = {}
    for product in catalog:
        product_id = int(product["id"])
        stem = expected_stem(product)
        master = source / f"{stem}.png"
        if stem in claimed:
            problems.append(f"id {product_id} and id {claimed[stem]} both map to {master.name}")
            continue
        claimed[stem] = product_id
        if not master.is_file():
            problems.append(f"id {product_id} {product['name']!r}: no master {master.name}")
            continue
        width, height = _dimensions(master)
        mappings.append(Mapping(product_id, product["name"], stem, master, width, height))

    unused = sorted(p.name for p in source.glob("*.png") if p.stem not in claimed)
    problems.extend(f"master {name} maps to no product" for name in unused)
    if problems:
        raise SystemExit("mapping failed:\n  " + "\n  ".join(problems))
    return mappings


def rejected(mappings: List[Mapping]) -> List[Tuple[Mapping, str]]:
    return [(m, reason) for m in mappings if (reason := validate(m.master))]


def print_mapping(mappings: List[Mapping]) -> None:
    print(f"{'id':>3}  {'product':34} {'master':44} native")
    for m in mappings:
        print(f"{m.product_id:>3}  {m.name:34} {m.master.name:44} {m.width}x{m.height}")


def derive_all(mappings: List[Mapping]) -> int:
    jobs = [
        (m.master, width, suffix)
        for m in mappings
        for width in CATALOG_WIDTHS
        for suffix in FORMATS
    ]
    with ThreadPoolExecutor() as pool:
        written = list(pool.map(lambda job: _encode(*job, out_dir=PRODUCTS), jobs))
    return len(written)


def update_catalog(catalog: List[dict], mappings: List[Mapping]) -> int:
    by_id = {m.product_id: m for m in mappings}
    changed = 0
    for product in catalog:
        image = f"{by_id[int(product['id'])].stem}.png"
        if product["image"] != image:
            product["image"] = image
            changed += 1
    CATALOG.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="folder holding <stem>.png masters")
    parser.add_argument("--check", action="store_true", help="report only")
    args = parser.parse_args()

    source = Path(args.source).expanduser()
    if not source.is_dir():
        raise SystemExit(f"{source} is not a directory")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    mappings = plan(catalog, source)
    print_mapping(mappings)
    print(f"\n{len(mappings)} products mapped to {len(mappings)} masters in {source}")

    bad = rejected(mappings)
    for mapping, reason in bad:
        print(f"  REJECT {mapping.master.name}: {reason}")
    if bad:
        print(f"{len(bad)} masters rejected. Nothing was written.")
        return 1
    if args.check:
        print("CHECK ONLY. Nothing was written.")
        return 0

    written = derive_all(mappings)
    changed = update_catalog(catalog, mappings)
    print(f"{written} variants written to {PRODUCTS.relative_to(REPO)}")
    print(f"{changed} catalog image fields changed in {CATALOG.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
