"""Tests for `services.personalization`.

Covers Requirement 3.3.2 (equal-weight tag overlap) and the 3.3.2.1
"Take It Further" weighted-hook contract from
`.kiro/specs/pellier-storefront/requirements.md`.

Runnable from the repo root per `pytest.ini`:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_personalization.py -v
"""

from __future__ import annotations

from typing import List

import pytest

from models import Preferences, StorefrontProduct
from services.personalization import match_score, sort_personalized


# ---------------------------------------------------------------------------
# Seeded showcase catalog - the 9 products from storefront.md
# ---------------------------------------------------------------------------
#
# Kept verbatim from `.kiro/steering/storefront.md` -> "The 9 showcase
# products (with preference tags)". This table is authoritative for the
# personalization assertions below; any drift here or there should trip the
# ordering tests before it ships.


def _product(
    *,
    id: int,
    name: str,
    color: str,
    price: float,
    category: str,
    tags: List[str],
) -> StorefrontProduct:
    return StorefrontProduct(
        id=id,
        brand="Pellier Editions",
        name=name,
        color=color,
        price=price,
        rating=4.7,
        review_count=100,
        category=category,  # type: ignore[arg-type]
        image_url=f"https://example.com/product-{id}.jpg",
        tags=tags,
    )


@pytest.fixture
def showcase_catalog() -> List[StorefrontProduct]:
    """The 9 showcase products in default editorial order."""
    return [
        _product(
            id=1,
            name="Italian Linen Camp Shirt",
            color="Sand",
            price=128,
            category="Linen",
            tags=[
                "minimal", "serene", "classic", "warm",
                "neutral", "everyday", "slow", "linen",
            ],
        ),
        _product(
            id=2,
            name="Wide-Leg Linen Trousers",
            color="Terracotta",
            price=98,
            category="Linen",
            tags=["creative", "bold", "warm", "earth", "everyday", "travel", "linen"],
        ),
        _product(
            id=3,
            name="Signature Straw Tote",
            color="Natural",
            price=68,
            category="Accessories",
            tags=["classic", "serene", "neutral", "soft", "travel", "everyday", "accessories"],
        ),
        _product(
            id=4,
            name="Relaxed Oxford Shirt",
            color="Warm Ivory",
            price=88,
            category="Linen",
            tags=["classic", "minimal", "neutral", "soft", "everyday", "work", "linen"],
        ),
        _product(
            id=5,
            name="Sundress in Washed Linen",
            color="Golden Ochre",
            price=148,
            category="Dresses",
            tags=["creative", "bold", "warm", "earth", "evening", "dresses", "linen"],
        ),
        _product(
            id=6,
            name="Leather Slide Sandal",
            color="Chestnut",
            price=112,
            category="Footwear",
            tags=["minimal", "classic", "earth", "warm", "everyday", "travel", "footwear"],
        ),
        _product(
            id=7,
            name="Cashmere-Blend Cardigan",
            color="Driftwood",
            price=158,
            category="Outerwear",
            tags=[
                "minimal", "serene", "classic", "neutral",
                "earth", "slow", "evening", "outerwear",
            ],
        ),
        _product(
            id=8,
            name="Ceramic Tumbler Set",
            color="4pc Set",
            price=52,
            category="Home",
            tags=["minimal", "serene", "creative", "neutral", "soft", "slow", "home"],
        ),
        _product(
            id=9,
            name="Linen Utility Jacket",
            color="Faded Olive",
            price=178,
            category="Outerwear",
            tags=["adventurous", "creative", "earth", "neutral", "outdoor", "travel", "outerwear"],
        ),
    ]


# ---------------------------------------------------------------------------
# Requirement 3.3.2 - equal-weight union overlap (default path)
# ---------------------------------------------------------------------------


def test_match_score_counts_union_overlap_equal_weight() -> None:
    """The default scoring is a count of overlapping tags with the union."""
    prefs = Preferences(vibe=["minimal"], categories=["linen"])

    shirt_tags = [
        "minimal", "serene", "classic", "warm",
        "neutral", "everyday", "slow", "linen",
    ]
    # `minimal` and `linen` are both in the union -> 2.
    assert match_score(shirt_tags, prefs) == 2

    tote_tags = [
        "classic", "serene", "neutral", "soft",
        "travel", "everyday", "accessories",
    ]
    # No overlap with {minimal, linen} -> 0.
    assert match_score(tote_tags, prefs) == 0


def test_match_score_case_insensitive() -> None:
    """Tags stored with different casing still match (design.md note)."""
    prefs = Preferences(vibe=["minimal"], categories=["linen"])
    # Catalog-enrichment is documented to store lowercase, but the scorer
    # is defensive in case the invariant slips.
    assert match_score(["Minimal", "LINEN", "serene"], prefs) == 2


def test_match_score_zero_when_no_overlap() -> None:
    prefs = Preferences(vibe=["bold"], categories=["footwear"])
    assert match_score(["minimal", "linen", "slow"], prefs) == 0


def test_match_score_zero_when_prefs_empty() -> None:
    """Empty preferences (a signed-in user with nothing saved) -> zero score."""
    assert match_score(["minimal", "linen"], Preferences()) == 0


def test_match_score_union_dedupes_across_groups() -> None:
    """A tag in the union once counts once, not once per group it appears in."""
    # `warm` is a ColorTag; `everyday` is an OccasionTag. Each product tag
    # appearing in the union contributes exactly 1, regardless of which
    # group it came from.
    prefs = Preferences(colors=["warm"], occasions=["everyday"])
    assert match_score(["warm", "everyday", "slow"], prefs) == 2


# ---------------------------------------------------------------------------
# Headline acceptance: Camp Shirt outranks Straw Tote for the canonical prefs
# ---------------------------------------------------------------------------


def test_camp_shirt_scores_higher_than_straw_tote_for_minimal_linen(
    showcase_catalog: List[StorefrontProduct],
) -> None:
    """The exact assertion named in tasks.md Task 1.4."""
    prefs = Preferences(vibe=["minimal"], categories=["linen"])
    by_id = {p.id: p for p in showcase_catalog}

    shirt_score = match_score(by_id[1].tags, prefs)
    tote_score = match_score(by_id[3].tags, prefs)

    assert shirt_score > tote_score


def test_sort_personalized_places_camp_shirt_above_straw_tote(
    showcase_catalog: List[StorefrontProduct],
) -> None:
    """End-to-end: the sort puts the camp shirt earlier than the tote."""
    prefs = Preferences(vibe=["minimal"], categories=["linen"])
    ordered = sort_personalized(showcase_catalog, prefs)
    ids = [p.id for p in ordered]

    assert ids.index(1) < ids.index(3)


# ---------------------------------------------------------------------------
# Tie-break: default editorial order preserved for equal scores
# ---------------------------------------------------------------------------


def test_sort_personalized_is_stable_for_tied_scores(
    showcase_catalog: List[StorefrontProduct],
) -> None:
    """Stable sort guarantees input order is preserved for ties."""
    # Empty preferences -> every product scores 0 -> all tied.
    prefs = Preferences()
    original_order = [p.id for p in showcase_catalog]
    sorted_order = [p.id for p in sort_personalized(showcase_catalog, prefs)]

    assert sorted_order == original_order


def test_sort_personalized_breaks_ties_by_editorial_position(
    showcase_catalog: List[StorefrontProduct],
) -> None:
    """Among products with the same non-zero score, input order wins."""
    # `creative` alone matches three products: Wide-Leg Linen Trousers (idx 1),
    # Sundress in Washed Linen (idx 4), Ceramic Tumbler Set (idx 7), and
    # Linen Utility Jacket (idx 8). All score exactly 1.
    prefs = Preferences(vibe=["creative"])
    ordered = sort_personalized(showcase_catalog, prefs)
    top_ids = [p.id for p in ordered if match_score(p.tags, prefs) == 1]

    assert top_ids == [2, 5, 8, 9]


# ---------------------------------------------------------------------------
# Requirement 3.3.2.1 - weighted kwarg hook
# ---------------------------------------------------------------------------


def test_match_score_accepts_weights_kwarg_keyword_only() -> None:
    """The `weights` parameter is keyword-only per the task spec."""
    prefs = Preferences(vibe=["minimal"], categories=["linen"])
    # Calling with a positional third arg must fail; weights is kw-only.
    with pytest.raises(TypeError):
        match_score(["minimal"], prefs, {"vibe": 2.0})  # type: ignore[misc]


def test_match_score_weights_omitted_matches_default(
    showcase_catalog: List[StorefrontProduct],
) -> None:
    """Task 1.4: omitting `weights` must not change default behavior."""
    prefs = Preferences(vibe=["minimal"], categories=["linen"])
    for product in showcase_catalog:
        assert match_score(product.tags, prefs) == match_score(
            product.tags, prefs, weights=None
        )


def test_sort_personalized_weights_omitted_matches_default(
    showcase_catalog: List[StorefrontProduct],
) -> None:
    """Sort results identical whether `weights` is omitted or passed None."""
    prefs = Preferences(vibe=["minimal"], categories=["linen"])
    a = [p.id for p in sort_personalized(showcase_catalog, prefs)]
    b = [p.id for p in sort_personalized(showcase_catalog, prefs, weights=None)]
    assert a == b


def test_match_score_weighted_variant_boosts_selected_group(
    showcase_catalog: List[StorefrontProduct],
) -> None:
    """Weighted hook: boosting a group should amplify its contribution.

    Not a strict production contract — the workshop default never uses this
    path — but this confirms the hook is genuinely wired and not a no-op.
    """
    prefs = Preferences(vibe=["minimal"], categories=["linen"])
    shirt = next(p for p in showcase_catalog if p.id == 1)

    # Equal weights of 1.0 replicate the default count of tag matches across
    # groups (2: one vibe match, one category match).
    baseline = match_score(shirt.tags, prefs, weights={"vibe": 1.0, "categories": 1.0})
    assert baseline == 2.0

    # Triple the categories weight; the `linen` match now contributes 3.
    boosted = match_score(
        shirt.tags, prefs, weights={"vibe": 1.0, "categories": 3.0}
    )
    assert boosted == pytest.approx(4.0)
    assert boosted > baseline
