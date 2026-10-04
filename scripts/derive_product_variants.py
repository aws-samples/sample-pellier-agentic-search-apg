#!/usr/bin/env python3
"""Validate supplied product masters and derive their responsive variants.

This is step 2 through 7 of the intake procedure in
``docs/image-replacement-manifest.md``, made repeatable. It exists because the
variants were previously generated ad hoc, which is how the repository ended up
serving nine multi-megabyte PNGs with no derivatives at all while 29 other SKUs
had a full set.

What it will not do
-------------------

It never alters a supplied master. It does not crop, pad, stretch, or recompose
anything: a master that fails the 4:5 catalog contract is reported and skipped,
because silently cropping a landscape master into a portrait slot is the defect
this file was written to surface, not a fix for it.

Usage
-----

    # Report only. Nothing is written.
    python3 scripts/derive_product_variants.py --check

    # Take masters from a drop folder, then derive.
    python3 scripts/derive_product_variants.py --from ~/Desktop/DAT416-UI-rehaul

    # Re-derive variants for masters already in the repository.
    python3 scripts/derive_product_variants.py
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
PRODUCTS = REPO / "pellier" / "frontend" / "public" / "products"

# The catalog product contract. Masters in a 4:5 slot must hold this ratio; the
# tolerance absorbs a one-pixel rounding difference, nothing more.
CATALOG_RATIO = 0.8
RATIO_TOLERANCE = 0.01
MIN_CATALOG_WIDTH = 1122

# Derived widths, matching what the frontend's srcset already requests.
VARIANT_WIDTHS = (480, 960)

# Encoder settings chosen to land on the sizes the existing committed variants
# already have, so a re-derive does not change the visual or the byte budget.
WEBP_QUALITY = "82"
AVIF_QUALITY = "58"

# Editorial and hero slots are intentionally landscape. They are not catalog
# SKUs and must not be held to the 4:5 contract.
LANDSCAPE_PREFIXES = ("hero-", "landing-")


def _dimensions(path: Path) -> Tuple[int, int]:
    """Pixel width and height, via sips so no third-party dependency is added."""
    out = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    width = height = 0
    for line in out.splitlines():
        if "pixelWidth" in line:
            width = int(line.split(":")[1].strip())
        elif "pixelHeight" in line:
            height = int(line.split(":")[1].strip())
    if not width or not height:
        raise SystemExit(f"could not read dimensions of {path}")
    return width, height


def _is_catalog_master(name: str) -> bool:
    return not name.startswith(LANDSCAPE_PREFIXES)


def validate(path: Path) -> Optional[str]:
    """Return a rejection reason, or None when the master is acceptable."""
    width, height = _dimensions(path)
    if not _is_catalog_master(path.name):
        return None
    ratio = width / height
    if abs(ratio - CATALOG_RATIO) > RATIO_TOLERANCE:
        return (
            f"{width}x{height} is ratio {ratio:.3f}, not 4:5 ({CATALOG_RATIO}). "
            "Regenerate at 4:5; this script will not crop it."
        )
    if width < MIN_CATALOG_WIDTH:
        return f"{width}px wide is below the {MIN_CATALOG_WIDTH}px minimum"
    return None


def _encode(
    master: Path, width: int, suffix: str, out_dir: Optional[Path] = None
) -> Path:
    """Write one derivative beside the master, or into ``out_dir``.

    ``out_dir`` lets a master that lives outside the repository (the catalog
    photographs stay with their generation provenance) publish its variants
    without copying a multi-megabyte PNG into ``public/products``.
    """
    target_dir = out_dir or master.parent
    out = target_dir / f"{master.stem}-{width}.{suffix}"
    src_w, src_h = _dimensions(master)
    height = round(width * src_h / src_w)
    if suffix == "webp":
        cmd = [
            "cwebp", "-quiet", "-q", WEBP_QUALITY,
            "-resize", str(width), str(height),
            str(master), "-o", str(out),
        ]
    else:
        # avifenc has no resize, so scale to a temporary PNG first. Both
        # dimensions are given explicitly: `--resampleWidth` alone derives the
        # height with its own rounding, which produced 480x599 against cwebp's
        # 480x600 for the same master. Two formats in one srcset disagreeing by a
        # pixel is a layout shift waiting for whichever the browser picks.
        scaled = target_dir / f".{master.stem}-{width}-scaled.png"
        shutil.copy2(master, scaled)
        subprocess.run(
            ["sips", "--resampleHeightWidth", str(height), str(width), str(scaled)],
            capture_output=True, check=True,
        )
        cmd = ["avifenc", "-q", AVIF_QUALITY, str(scaled), str(out)]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        finally:
            scaled.unlink(missing_ok=True)
        return out
    subprocess.run(cmd, capture_output=True, check=True)
    return out


def widths_for(master: Path) -> Tuple[int, ...]:
    """Every width this master already publishes, else the default pair.

    Re-deriving a fixed 480/960 pair would silently drop the 1600 variant the
    hero images publish, and the frontend's srcset would then point at files that
    no longer exist. So the existing set is the contract; the default only
    applies to a master that has never had variants.
    """
    existing = {
        int(part)
        for candidate in master.parent.glob(f"{master.stem}-*.webp")
        for part in [candidate.stem.rsplit("-", 1)[-1]]
        if part.isdigit()
    }
    existing.update(
        int(part)
        for candidate in master.parent.glob(f"{master.stem}-*.avif")
        for part in [candidate.stem.rsplit("-", 1)[-1]]
        if part.isdigit()
    )
    source_width, _ = _dimensions(master)
    usable = tuple(sorted(w for w in existing if w <= source_width))
    return usable or VARIANT_WIDTHS


def derive(master: Path) -> List[Path]:
    written = []
    for width in widths_for(master):
        for suffix in ("webp", "avif"):
            written.append(_encode(master, width, suffix))
    return written


def _masters_in(directory: Path) -> List[Path]:
    """Named PNG masters only.

    Files whose names came straight off an image generator carry no SKU, so they
    cannot be mapped to a catalog row and are skipped rather than guessed at.
    """
    return sorted(
        p for p in directory.glob("*.png")
        if not p.name.startswith("ChatGPT") and " " not in p.name
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", default="", help="drop folder")
    parser.add_argument("--check", action="store_true", help="report only")
    parser.add_argument("--only", default="", help="comma-separated filenames")
    args = parser.parse_args()

    source = Path(args.source).expanduser() if args.source else PRODUCTS
    if not source.is_dir():
        raise SystemExit(f"{source} is not a directory")

    wanted = {n.strip() for n in args.only.split(",") if n.strip()}
    candidates = [p for p in _masters_in(source) if not wanted or p.name in wanted]
    if not candidates:
        raise SystemExit(f"no named PNG masters in {source}")

    skipped: List[Tuple[str, str]] = []
    accepted: List[Path] = []
    unmapped: List[str] = []

    for path in candidates:
        reason = validate(path)
        if reason:
            skipped.append((path.name, reason))
            continue
        if source != PRODUCTS and not (PRODUCTS / path.name).exists():
            unmapped.append(path.name)
            continue
        accepted.append(path)

    print(f"source: {source}")
    print(f"  accepted : {len(accepted)}")
    print(f"  rejected : {len(skipped)}")
    print(f"  unmapped : {len(unmapped)}")

    for name, reason in skipped:
        print(f"  REJECT {name}: {reason}")
    for name in unmapped:
        print(f"  UNMAPPED {name}: no existing master of that name in the catalog")

    if args.check:
        print("\nCHECK ONLY. Nothing was written.")
        return 1 if skipped else 0

    changed: Dict[str, str] = {}
    for path in accepted:
        target = PRODUCTS / path.name
        if source != PRODUCTS:
            before = _dimensions(target) if target.is_file() else (0, 0)
            shutil.copy2(path, target)
            after = _dimensions(target)
            changed[path.name] = (
                f"{before[0]}x{before[1]} -> {after[0]}x{after[1]}"
                if before != after else f"{after[0]}x{after[1]} (same size, new bytes)"
            )
        variants = derive(target)
        print(f"  {path.name}: {len(variants)} variants")

    for name, note in changed.items():
        print(f"  master replaced {name}: {note}")
    print(f"\n{len(accepted)} masters processed, {len(accepted) * 4} variants written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
