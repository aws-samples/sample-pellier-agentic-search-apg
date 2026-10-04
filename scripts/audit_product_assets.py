#!/usr/bin/env python3
"""Which product images the app requires, and whether a clean clone would get them.

The defect this exists to surface
---------------------------------

Every earlier asset check asked whether a file was on the developer's disk. The
pre-handoff audit asked a different question and got a different answer: of the
images the shipped catalog references, 20 masters and 261 derivatives were
present locally and **untracked by git**. A fresh clone would render the
storefront grid, the operator client record, and every Concierge
recommendation card against missing files, while local development looked
finished.

So the authority here is ``git ls-files``, not ``Path.exists``.

What "required" means
---------------------

Three kinds of reference, because the app builds image URLs three ways:

1. **Literal** - a ``/products/<name>`` string in source, a fixture, or the
   seed CSV.
2. **Derived** - ``ResponsiveImage`` expands a ``.png`` master into
   ``-<width>.webp`` and ``-<width>.avif`` for every width in its srcset. The
   literal source master and every generated candidate remain required: a clean
   clone needs the source named by shipped code as well as the files the browser
   requests. Widths come from what the master already publishes, matching
   ``derive_product_variants.widths_for``.
3. **Templated** - ``personaPhotos.ts`` composes client portrait filenames from
   a slug list at runtime. No literal exists to grep, so the slug list is read
   out of that module: adding a client slug without its portrait must fail here
   rather than resolve to an initial circle in production.

Usage
-----

    python3 scripts/audit_product_assets.py              # summary
    python3 scripts/audit_product_assets.py --table      # per-image detail
    python3 scripts/audit_product_assets.py --json out.json
    python3 scripts/audit_product_assets.py --print-untracked | xargs git add

Exit status is non-zero when a required asset is missing or untracked.
Dimensions are reported only when ``sips`` is available, so the machine-checked
part of this contract stays portable; the shape rule itself lives in
``derive_product_variants.validate``.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

REPO = pathlib.Path(__file__).resolve().parents[1]
PRODUCTS_DIR = REPO / "pellier" / "frontend" / "public" / "products"
PRODUCTS_PREFIX = "pellier/frontend/public/products/"
PERSONA_PHOTOS_TS = REPO / "pellier" / "frontend" / "src" / "data" / "personaPhotos.ts"

# Extensions worth scanning for a reference. Source, fixtures, seeds and docs.
SOURCE_SUFFIXES = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".sql", ".sh", ".md", ".csv",
    ".css", ".html",
)
SCAN_EXCLUDES = ("node_modules", "/.venv/", "/dist/", "/build/", "audit/", ".worktrees")

MASTER_SUFFIXES = (".png", ".jpg", ".jpeg")
DERIVATIVE_FORMATS = ("webp", "avif")
# `ResponsiveImage`'s default srcset widths, for a master with no variants yet.
DEFAULT_WIDTHS = (480, 960)

REFERENCE_RE = re.compile(
    r"/products/([A-Za-z0-9][A-Za-z0-9._-]*\.(?:png|jpe?g|webp|avif))"
)

# Line prefixes that begin a comment, per language. A reference inside a comment
# describes history; it does not ship, so counting it would make an explanatory
# note look like a missing asset. Only whole comment LINES are dropped, never text
# after a mid-line `//`, because that would also eat a URL's scheme separator and
# lose a real reference.
COMMENT_PREFIXES: Dict[str, Tuple[str, ...]] = {
    ".ts": ("//", "*", "/*"),
    ".tsx": ("//", "*", "/*"),
    ".js": ("//", "*", "/*"),
    ".jsx": ("//", "*", "/*"),
    ".css": ("*", "/*"),
    ".py": ("#",),
    ".sh": ("#",),
}

# Path fragments that mark a non-shipping test input. A fixture may name a
# malformed image specifically to test error rendering; it must never expand
# the release asset contract for the browser bundle.
TEST_PATH_MARKERS = (
    "/tests/",
    "test_",
    ".test.",
    "__tests__",
    "/fixtures/",
)


def _run(args: Sequence[str]) -> str:
    return subprocess.run(
        list(args), cwd=REPO, capture_output=True, text=True, check=True
    ).stdout


def tracked_paths() -> Set[str]:
    """Every repo-relative path git tracks. One call, not one per file."""
    return set(filter(None, _run(["git", "ls-files", "-z"]).split("\0")))


def _scannable_files() -> List[pathlib.Path]:
    """Tracked plus not-yet-committed source. New source references count too."""
    listed = set(filter(None, _run(["git", "ls-files", "-z"]).split("\0")))
    listed |= set(
        filter(None, _run(["git", "ls-files", "-o", "--exclude-standard", "-z"]).split("\0"))
    )
    files = []
    for rel in sorted(listed):
        if any(token in f"/{rel}" for token in SCAN_EXCLUDES):
            continue
        if not rel.endswith(SOURCE_SUFFIXES):
            continue
        path = REPO / rel
        if path.is_file():
            files.append(path)
    return files


def _code_only(text: str, suffix: str) -> str:
    prefixes = COMMENT_PREFIXES.get(suffix)
    if not prefixes:
        return text
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith(prefixes)
    )


def is_test_path(rel: str) -> bool:
    return any(marker in f"/{rel}" for marker in TEST_PATH_MARKERS)


def literal_references() -> Dict[str, List[str]]:
    """Filename -> the source files that name it, comments excluded."""
    found: Dict[str, Set[str]] = {}
    for path in _scannable_files():
        text = _code_only(
            path.read_text(encoding="utf-8", errors="ignore"), path.suffix
        )
        for match in REFERENCE_RE.finditer(text):
            rel = path.relative_to(REPO).as_posix()
            found.setdefault(match.group(1), set()).add(rel)
    return {name: sorted(sources) for name, sources in found.items()}


def client_portrait_names() -> List[str]:
    """Portrait filenames `personaPhotos.ts` composes at runtime.

    Parsed rather than duplicated. A new slug in that module immediately becomes a
    required asset, which is the only way a missing portrait fails before a
    participant sees an initial circle where a face belongs.
    """
    text = PERSONA_PHOTOS_TS.read_text(encoding="utf-8")
    block = re.search(r"const CLIENT_SLUGS = \[(.*?)\] as const", text, re.S)
    if not block:
        raise SystemExit(
            f"CLIENT_SLUGS not found in {PERSONA_PHOTOS_TS.relative_to(REPO)}; "
            "the portrait contract can no longer be derived from source."
        )
    slugs = re.findall(r"'([a-z][a-z0-9-]*)'", block.group(1))
    sizes = sorted({int(size) for size in re.findall(r"clientMap\((\d+)\)", text)})
    if not slugs or not sizes:
        raise SystemExit("CLIENT_SLUGS or clientMap sizes parsed empty")
    return [f"client-{slug}-portrait-{size}.webp" for slug in slugs for size in sizes]


_CONCRETE_DERIVATIVE_RE = re.compile(
    r"-(?:160|480|960|1600)\.(?:avif|webp)$", re.I
)


def image_stem(name: str) -> str:
    """The responsive stem that runtime image resolution uses."""
    return _CONCRETE_DERIVATIVE_RE.sub(
        "", re.sub(r"\.(?:png|jpe?g|webp|avif)$", "", name, flags=re.I)
    )


def resolved_public_name(name: str) -> str:
    """Mirror `imageSrc()` for local product paths.

    Catalog rows deliberately keep a human-readable source-style filename
    (historically PNG, now generally unsuffixed WebP). The browser never
    requests either master: it requests the committed 960px WebP fallback,
    while `<picture>` may select a matching AVIF/WebP derivative. Auditing the
    pre-resolution filename would make every fresh clone look broken even
    though the actual request is correct.
    """
    if _CONCRETE_DERIVATIVE_RE.search(name):
        return name
    if re.search(r"\.(?:png|jpe?g|webp)$", name, flags=re.I):
        return f"{image_stem(name)}-960.webp"
    return name


def published_widths(name: str) -> Tuple[int, ...]:
    """Widths this image stem publishes, else the srcset default.

    Same rule as ``derive_product_variants.widths_for``: the existing set is the
    contract, so a hero that publishes 1600 keeps it and an ordinary SKU is not
    forced to grow one.
    """
    stem = image_stem(name)
    widths: Set[int] = set()
    for fmt in DERIVATIVE_FORMATS:
        for candidate in PRODUCTS_DIR.glob(f"{stem}-*.{fmt}"):
            tail = candidate.stem.rsplit("-", 1)[-1]
            if tail.isdigit():
                widths.add(int(tail))
    return tuple(sorted(widths)) or DEFAULT_WIDTHS


def derivatives_for(name: str) -> List[str]:
    """The `ResponsiveImage` candidates emitted for a non-concrete path."""
    if _CONCRETE_DERIVATIVE_RE.search(name):
        return []
    stem = image_stem(name)
    if not any(PRODUCTS_DIR.glob(f"{stem}-*.webp")):
        return []
    return [
        f"{stem}-{width}.{fmt}"
        for width in published_widths(name)
        for fmt in DERIVATIVE_FORMATS
    ]


def _dimensions(path: pathlib.Path) -> Optional[str]:
    """`sips` when present. Absent on Linux CI, which is why nothing asserts it."""
    try:
        out = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            capture_output=True, text=True, check=False,
        ).stdout
    except FileNotFoundError:
        return None
    width = height = 0
    for line in out.splitlines():
        if "pixelWidth" in line:
            width = int(line.split(":")[1].strip())
        elif "pixelHeight" in line:
            height = int(line.split(":")[1].strip())
    return f"{width}x{height}" if width and height else None


def audit(*, with_dimensions: bool = False) -> Dict[str, object]:
    """The whole contract in one structure. Used by the release test."""
    tracked = tracked_paths()
    on_disk = {path.name for path in PRODUCTS_DIR.iterdir() if path.is_file()}
    literals = literal_references()
    templated = client_portrait_names()

    entries: List[Dict[str, object]] = []
    required: Set[str] = set()
    dangling: List[Dict[str, object]] = []

    def record(name: str, kind: str, sources: Iterable[str]) -> None:
        resolved = resolved_public_name(name)
        rel = PRODUCTS_PREFIX + resolved
        derived = derivatives_for(name)
        required.add(rel)
        if name in on_disk and name.lower().endswith(MASTER_SUFFIXES):
            required.add(PRODUCTS_PREFIX + name)
        required.update(PRODUCTS_PREFIX + child for child in derived)
        entry: Dict[str, object] = {
            "referenced": f"/products/{name}",
            "resolved": f"/products/{resolved}",
            "kind": kind,
            "onDisk": resolved in on_disk,
            "tracked": rel in tracked,
            "derivatives": [
                {
                    "name": child,
                    "onDisk": child in on_disk,
                    "tracked": PRODUCTS_PREFIX + child in tracked,
                }
                for child in derived
            ],
            "sources": sorted(sources)[:4],
        }
        if with_dimensions and resolved in on_disk:
            entry["dimensions"] = _dimensions(PRODUCTS_DIR / resolved)
        entries.append(entry)

    for name, sources in sorted(literals.items()):
        if name in on_disk or resolved_public_name(name) in on_disk:
            record(name, "literal", sources)
            continue
        dangling.append({
            "referenced": f"/products/{name}",
            "sources": sources,
            "testOnly": all(is_test_path(source) for source in sources),
        })
    for name in templated:
        if name in literals:
            continue
        record(name, "templated", [PERSONA_PHOTOS_TS.relative_to(REPO).as_posix()])

    tracked_products = {path for path in tracked if path.startswith(PRODUCTS_PREFIX)}
    return {
        "entries": entries,
        "required": sorted(required),
        "requiredMissing": sorted(required - {PRODUCTS_PREFIX + n for n in on_disk}),
        "requiredUntracked": sorted(required - tracked),
        "trackedNotRequired": sorted(tracked_products - required),
        "presentNotRequired": sorted(
            {PRODUCTS_PREFIX + n for n in on_disk} - required - tracked
        ),
        "dangling": dangling,
    }


def unresolved_references(result: Dict[str, object]) -> List[Dict[str, object]]:
    """References that would 404 for a participant.

    A reference survives this filter only when neither its literal asset nor
    the runtime-resolved derivative exists and it is made from something that
    actually ships.
    """
    return [
        item for item in result["dangling"]  # type: ignore[union-attr]
        if not item["testOnly"]
    ]


def _print_table(result: Dict[str, object]) -> None:
    entries: List[Dict[str, object]] = result["entries"]  # type: ignore[assignment]
    header = f"{'referenced':46} {'kind':10} {'disk':5} {'git':5} derivatives (git)"
    print(header)
    print("-" * len(header))
    for entry in sorted(entries, key=lambda e: str(e["referenced"])):
        derived: List[Dict[str, object]] = entry["derivatives"]  # type: ignore[assignment]
        if derived:
            ok = sum(1 for child in derived if child["tracked"])
            summary = f"{ok}/{len(derived)} tracked"
        else:
            summary = "-"
        dims = f"  {entry['dimensions']}" if entry.get("dimensions") else ""
        print(
            f"{entry['referenced']:46} {entry['kind']:10} "
            f"{'yes' if entry['onDisk'] else 'NO':5} "
            f"{'yes' if entry['tracked'] else 'NO':5} {summary}{dims}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", action="store_true", help="per-image detail")
    parser.add_argument("--json", metavar="PATH", help="write the audit as JSON")
    parser.add_argument("--dimensions", action="store_true",
                        help="read pixel dimensions via sips (macOS)")
    parser.add_argument("--print-untracked", action="store_true",
                        help="print required-but-untracked paths, one per line")
    args = parser.parse_args()

    result = audit(with_dimensions=args.dimensions or args.table)

    if args.print_untracked:
        for path in result["requiredUntracked"]:  # type: ignore[index]
            print(path)
        return 1 if result["requiredUntracked"] else 0

    if args.table:
        _print_table(result)
        print()

    entries = result["entries"]  # type: ignore[assignment]
    print(f"referenced images     : {len(entries)}")
    print(f"required assets       : {len(result['required'])}")  # type: ignore[arg-type]
    print(f"missing on disk       : {len(result['requiredMissing'])}")  # type: ignore[arg-type]
    print(f"required but UNTRACKED: {len(result['requiredUntracked'])}")  # type: ignore[arg-type]
    print(f"tracked, not required : {len(result['trackedNotRequired'])}")  # type: ignore[arg-type]
    print(f"present, not required : {len(result['presentNotRequired'])}")  # type: ignore[arg-type]

    for label, key in (
        ("MISSING ON DISK", "requiredMissing"),
        ("UNTRACKED", "requiredUntracked"),
    ):
        paths: List[str] = result[key]  # type: ignore[assignment]
        if paths:
            print(f"\n{label}:")
            for path in paths[:40]:
                print(f"  {path.split('/')[-1]}")
            if len(paths) > 40:
                print(f"  ... and {len(paths) - 40} more")

    unresolved = unresolved_references(result)
    if unresolved:
        print("\nREFERENCED, NOT ON DISK, NOT ALIASED:")
        for item in unresolved:
            print(f"  {item['referenced']}  <- {', '.join(item['sources'][:2])}")

    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(result, indent=2) + "\n")
        print(f"\nwritten to {args.json}")

    broken = (
        result["requiredMissing"] or result["requiredUntracked"] or unresolved
    )
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
