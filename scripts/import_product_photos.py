#!/usr/bin/env python3
"""Import the catalog's product photographs and derive the variants the app serves.

PNG masters stay with their generation provenance; the repository ships
responsive derivatives. The catalog's explicit image references select the
masters. Rows with no photograph are skipped. ``derive_product_variants`` owns
dimension validation and encoding; this script validates the product mapping.

Mapping rule
------------

The original 100 products each have their own photograph. New photographs
may serve only the two size options listed in data/catalog_photography.json,
with matching design and color. Missing or unrecognized masters fail before
writing. Use --only-supplied to process a partial delivery of known masters.
Neither mode changes catalog content or assigns photos to unphotographed rows.

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
    uv run scripts/import_product_photos.py --source <folder> --check

    # Derive every variant from a complete collection of masters.
    uv run scripts/import_product_photos.py --source <folder>

    # Derive only the known masters in a partial delivery.
    uv run scripts/import_product_photos.py --source <folder> --only-supplied
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
PHOTOGRAPHY = REPO / "data" / "catalog_photography.json"

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


def plan(catalog: List[dict], source: Path, *, photos: List[dict] | None = None,
         only_supplied: bool = False) -> List[Mapping]:
    """Validate explicit image ownership before deriving any files."""
    if photos is None:
        photos = json.loads(PHOTOGRAPHY.read_text(encoding="utf-8"))["photos"]
    problems: List[str] = []
    mappings: List[Mapping] = []
    claimed: Dict[str, List[dict]] = {}
    allowed = {photo["image"]: photo for photo in photos}
    if len(allowed) != len(photos):
        problems.append("photography manifest repeats an image")
    for product in catalog:
        product_id = int(product["id"])
        image = product["image"]
        if image is None:
            continue
        if not isinstance(image, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*\.png", image):
            problems.append(f"id {product_id}: invalid image filename {image!r}")
            continue
        claimed.setdefault(image, []).append(product)
        if product_id <= 100 and image != f"{expected_stem(product)}.png":
            problems.append(f"id {product_id}: original product photo does not match its name")

    for image, products in claimed.items():
        ids = [int(p["id"]) for p in products]
        if any(pid > 100 for pid in ids):
            photo = allowed.get(image)
            if not photo or sorted(ids) != sorted(photo["product_ids"]):
                problems.append(f"{image}: product IDs do not match the photography manifest")
            elif len(ids) != 2 or any(
                p["color"] != photo["color"]
                or not p["name"].startswith(f"{photo['design']}, {photo['color']}, ")
                for p in products
            ):
                problems.append(f"{image}: sharing is limited to two sizes of one design and color")
        elif len(ids) != 1:
            problems.append(f"{image}: original product photographs cannot be shared")
        master = source / image
        if not master.is_file():
            if not only_supplied:
                problems.append(f"ids {ids}: no master {image}")
            continue
        width, height = _dimensions(master)
        mappings.extend(Mapping(int(p["id"]), p["name"], master.stem, master, width, height)
                        for p in products)

    unused = sorted(p.name for p in source.glob("*.png") if p.name not in claimed)
    problems.extend(f"master {name} maps to no product" for name in unused)
    if not mappings:
        problems.append("no catalog masters supplied")
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
        (master, width, suffix)
        for master in sorted({m.master for m in mappings})
        for width in CATALOG_WIDTHS
        for suffix in FORMATS
    ]
    with ThreadPoolExecutor() as pool:
        written = list(pool.map(lambda job: _encode(*job, out_dir=PRODUCTS), jobs))
    return len(written)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="folder holding <stem>.png masters")
    parser.add_argument("--check", action="store_true", help="report only")
    parser.add_argument("--only-supplied", action="store_true",
                        help="accept a partial delivery; reject unknown masters")
    args = parser.parse_args()

    source = Path(args.source).expanduser()
    if not source.is_dir():
        raise SystemExit(f"{source} is not a directory")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    mappings = plan(catalog, source, only_supplied=args.only_supplied)
    print_mapping(mappings)
    print(f"\n{len(mappings)} products mapped to {len({m.master for m in mappings})} masters in {source}")

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
    print(f"{written} variants written to {PRODUCTS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
