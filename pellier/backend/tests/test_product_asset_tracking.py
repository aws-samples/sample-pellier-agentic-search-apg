"""Every image the app requires must be TRACKED IN GIT, not merely on disk.

The defect this closes
----------------------

The pre-handoff audit found the product pass uncommitted: of the images the shipped
catalog and console reference, 20 masters and 265 derivatives were present locally and
untracked. Every existing check passed, because every existing check asked whether the
file existed on the developer's disk.

A clean clone would therefore render the storefront grid, the operator client record and
every Concierge recommendation card against missing files while local development looked
finished. So the authority here is ``git ls-files``, not ``Path.exists``. That reads the
index rather than ``HEAD``, which is deliberate: the question a pre-commit gate must
answer is whether committing the current index would carry the asset, not whether some
earlier commit already did.

Why this imports the audit script
---------------------------------

``scripts/audit_product_assets.py`` owns the definition of "required": literal
``/products/`` references after the same public-path resolution the browser
uses, the ``-<width>.<format>`` derivatives ``ResponsiveImage`` puts in a
srcset, and the client portrait filenames ``personaPhotos.ts`` composes from a
slug list at runtime. Re-implementing that here would produce a second contract
that can agree with the first while both are wrong. The tests below assert
outcomes against the one derivation, and each names the specific failure it is
guarding.

Nothing here needs a database, a network, or macOS: pixel dimensions are the audit
script's optional ``--dimensions`` mode, because ``sips`` does not exist in CI.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Dict, List

import pytest

REPO = Path(__file__).resolve().parents[3]
AUDIT_SCRIPT = REPO / "scripts" / "audit_product_assets.py"
PRODUCTS_DIR = REPO / "pellier" / "frontend" / "public" / "products"


def _load_audit_module():
    name = "pellier_product_asset_audit"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, AUDIT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


@pytest.fixture(scope="module")
def audit_module():
    return _load_audit_module()


@pytest.fixture(scope="module")
def result(audit_module) -> Dict[str, object]:
    return audit_module.audit()


def _names(paths: List[str]) -> List[str]:
    return sorted(path.rsplit("/", 1)[-1] for path in paths)


def test_the_audit_finds_a_real_catalog(result) -> None:
    """Guards the tests below from becoming vacuous.

    Every other assertion here is a "no bad entries" check, which a parsing regression
    would satisfy by finding nothing at all.
    """
    entries: List[Dict[str, object]] = result["entries"]  # type: ignore[assignment]
    assert len(entries) >= 90, f"only {len(entries)} referenced images discovered"
    assert len(result["required"]) >= 300, result["required"]  # type: ignore[arg-type]
    kinds = {entry["kind"] for entry in entries}
    assert kinds == {"literal"}, kinds


def test_every_required_asset_is_tracked_in_git(result) -> None:
    """The load-bearing assertion. Existing on disk is not sufficient."""
    untracked: List[str] = result["requiredUntracked"]  # type: ignore[assignment]
    assert not untracked, (
        f"{len(untracked)} required product assets are untracked, so a clean clone "
        "cannot render them. Run:\n"
        "  python3 scripts/audit_product_assets.py --print-untracked | xargs git add\n"
        f"first few: {_names(untracked)[:8]}"
    )


def test_every_required_asset_exists_on_disk(result) -> None:
    missing: List[str] = result["requiredMissing"]  # type: ignore[assignment]
    assert not missing, f"required product assets absent from the working tree: {_names(missing)}"


def test_the_house_and_signature_catalog_images_are_tracked(result) -> None:
    """The exact two catalog families the audit found absent from a fresh clone.

    Named explicitly so the regression cannot return disguised as a passing total: the
    house and signature SKUs are what the operator client book and the Concierge
    recommendation cards render, and they were the last twenty images added.
    """
    entries: List[Dict[str, object]] = result["entries"]  # type: ignore[assignment]
    families = {"house-": [], "signature-": []}
    for entry in entries:
        name = str(entry["referenced"]).rsplit("/", 1)[-1]
        for prefix in families:
            if name.startswith(prefix):
                families[prefix].append(entry)
    for prefix, found in families.items():
        assert len(found) >= 10, f"expected the {prefix}* family in the catalog, saw {len(found)}"
        untracked = [e["resolved"] for e in found if not e["tracked"]]
        assert not untracked, f"{prefix}* catalog images not tracked: {untracked}"


def test_no_master_ships_a_half_tracked_srcset(result) -> None:
    """A partly tracked srcset is worse than none: the browser picks the missing one.

    ``ResponsiveImage`` emits an AVIF and a WebP source per width and only falls back to
    the original after the request fails, so an untracked derivative costs a 404 and a
    re-render on every card in a fresh clone.
    """
    broken = []
    for entry in result["entries"]:  # type: ignore[union-attr]
        derived: List[Dict[str, object]] = entry["derivatives"]  # type: ignore[assignment]
        if not derived:
            continue
        tracked = [child for child in derived if child["tracked"]]
        if tracked and len(tracked) != len(derived):
            absent = [child["name"] for child in derived if not child["tracked"]]
            broken.append(f"{entry['referenced']} missing {absent}")
    assert not broken, "masters with an incomplete tracked derivative set:\n  " + "\n  ".join(broken)


def test_literal_source_masters_remain_required_with_their_derivatives(
    audit_module,
    result,
) -> None:
    """The resolver may request a derivative, but shipped source still names the master."""
    required: List[str] = result["required"]  # type: ignore[assignment]
    for name in (
        "hero-fresh-2.png",
        "hero-marco.png",
        "hero-anna.png",
        "hero-theo.png",
    ):
        assert audit_module.PRODUCTS_PREFIX + name in required


def test_derivative_widths_are_symmetric_across_formats(result) -> None:
    """Both formats must publish the same widths.

    ``derive_product_variants`` scales AVIF through a temporary PNG precisely because the
    two encoders round height differently; a width present in one format and absent in
    the other reintroduces the layout shift that fix removed.
    """
    mismatched = []
    for entry in result["entries"]:  # type: ignore[union-attr]
        widths: Dict[str, set] = {"webp": set(), "avif": set()}
        for child in entry["derivatives"]:  # type: ignore[union-attr]
            name = str(child["name"])
            stem, fmt = name.rsplit(".", 1)
            if child["onDisk"]:
                widths[fmt].add(stem.rsplit("-", 1)[-1])
        if widths["webp"] != widths["avif"]:
            mismatched.append(f"{entry['referenced']}: webp {sorted(widths['webp'])} vs avif {sorted(widths['avif'])}")
    assert not mismatched, "\n  ".join(mismatched)


def test_no_shipped_reference_resolves_to_nothing(audit_module, result) -> None:
    """Every shipped source path must resolve to a committed public asset."""
    unresolved = audit_module.unresolved_references(result)
    assert not unresolved, (
        "these references name no file or runtime-resolved derivative:\n  "
        + "\n  ".join(f"{item['referenced']} <- {item['sources'][0]}" for item in unresolved)
    )


def test_nothing_is_tracked_that_nothing_references(result) -> None:
    """Dead weight in a repository participants clone over a workshop network."""
    stale: List[str] = result["trackedNotRequired"]  # type: ignore[assignment]
    assert not stale, f"tracked product assets nothing references: {_names(stale)}"


def test_no_reference_escapes_the_public_products_directory(result) -> None:
    """An absolute developer path or a traversal works locally and nowhere else."""
    for entry in result["entries"]:  # type: ignore[union-attr]
        referenced = str(entry["referenced"])
        assert referenced.startswith("/products/"), referenced
        assert ".." not in referenced, referenced
        assert "/Users/" not in referenced, referenced
