"""Personalization match scoring.

Implements Requirement 3.3.2 (and the 3.3.2.1 Take It Further hook) from
`.kiro/specs/pellier-storefront/requirements.md`:

    When GET /api/products?personalized=true is called with a valid JWT AND
    the user has saved preferences THEN the backend SHALL compute a match
    score per product (count of overlapping values between the product's
    `tags` column and the union of user preferences — each matching tag
    contributes 1, all preference groups weighted equally) and return the
    product list sorted by match score descending, ties broken by default
    editorial order.

The design document (`design.md` -> "Personalization Scoring") calls out the
equal-weight overlap as the workshop default and leaves a kwarg-shaped hook
for a production weighted variant, so call sites (Task 3.6 / routes
`/api/products`) never need to change when advanced participants experiment
with weights.

Public surface:
  - `match_score(product_tags, prefs, *, weights=None)` -> equal-weight tag
    overlap count by default; when `weights` is provided, sums the weight of
    each group that contributed a match.
  - `sort_personalized(products, prefs, *, weights=None)` -> products sorted
    by match score desc, ties broken by the input (editorial) order thanks
    to Python's stable sort.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence, TypeVar, runtime_checkable

from models import Preferences


# The four preference groups, in the order they appear on the onboarding
# modal (storefront.md -> "Preferences onboarding modal"). Used to iterate
# Preferences fields generically in both the union (default) and weighted
# scoring paths.
_PREFERENCE_GROUPS: tuple[str, ...] = ("vibe", "colors", "occasions", "categories")


@runtime_checkable
class _HasTags(Protocol):
    """Structural type for anything with a `tags` sequence.

    `sort_personalized` accepts `StorefrontProduct` instances as well as any
    duck-typed object that exposes a `tags` attribute (e.g. lightweight test
    doubles), without coupling this module to a single concrete class.
    """

    tags: Sequence[str]


P = TypeVar("P", bound=_HasTags)


def match_score(
    product_tags: Iterable[str],
    prefs: Preferences,
    *,
    weights: Optional[Mapping[str, float]] = None,
) -> float:
    """Return the preference match score for a product.

    Default behavior (``weights is None``) implements Requirement 3.3.2
    exactly: the count of tags that appear in the union of the user's four
    preference groups, each matching tag contributing ``1``. Groups are
    weighted equally.

    When ``weights`` is supplied (Requirement 3.3.2.1 "Take It Further"
    extension), the score is the sum over the four preference groups of
    ``weights[group] * |product_tags ∩ prefs[group]|``. Missing group keys
    default to a weight of ``1.0`` so partial weight overrides behave
    predictably. This is a hook for advanced participants; the workshop
    default never passes ``weights``.

    Args:
        product_tags: The product's ``tags`` column values (case-insensitive).
        prefs: The user's saved preferences.
        weights: Optional per-group weight map. Keys are any of
            ``"vibe"``, ``"colors"``, ``"occasions"``, ``"categories"``.

    Returns:
        The match score. ``int`` in the default path (union overlap count)
        and ``float`` when ``weights`` is provided.
    """
    # Catalog-enrichment stores lowercase tags (see design.md); the tag
    # literals in the Preferences model are already lowercase. Lowercase
    # both sides defensively so casing in the product catalog never drops
    # an otherwise-valid match.
    product_set = {tag.lower() for tag in product_tags}

    if weights is None:
        # Equal-weight union overlap, per Requirement 3.3.2.
        union: set[str] = set()
        for group in _PREFERENCE_GROUPS:
            union.update(v.lower() for v in getattr(prefs, group))
        return sum(1 for tag in product_set if tag in union)

    # Weighted variant (Requirement 3.3.2.1). Summing per group allows a
    # product whose tag matches multiple groups (e.g. "linen" in both a
    # categories list and a hypothetical future group) to accrue weight
    # from each — consistent with how a production scorer would boost tags
    # that cover more of the user's signal.
    score = 0.0
    for group in _PREFERENCE_GROUPS:
        group_weight = float(weights.get(group, 1.0))
        selected = {v.lower() for v in getattr(prefs, group)}
        if not selected:
            continue
        score += group_weight * len(product_set & selected)
    return score


def sort_personalized(
    products: Sequence[P],
    prefs: Preferences,
    *,
    weights: Optional[Mapping[str, float]] = None,
) -> list[P]:
    """Return ``products`` sorted by match score descending.

    Ties are broken by the default editorial order of the input sequence:
    Python's ``sorted`` is stable, so two products with the same score keep
    their relative input order.

    The ``weights`` kwarg is forwarded to ``match_score``. Call sites that
    do not supply it get the equal-weight Requirement 3.3.2 behavior, which
    is the storefront default.
    """
    return sorted(
        products,
        key=lambda product: -match_score(product.tags, prefs, weights=weights),
    )


__all__ = ["match_score", "sort_personalized"]
