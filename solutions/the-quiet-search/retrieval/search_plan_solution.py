"""Typed query planning — the ``Plan`` step of Plan → Retrieve → Rank → Act → Prove.

This module is the single planner for every retrieval path in Pellier. The
shipped Personalization Agent tool path and the Observatory strategy comparison both compile
their retrieval through :func:`build_plan`, so the "agentic" strategy the
workshop *demonstrates* is the same one shoppers actually get.

The division of labour is the lesson:

  * The **model** (Sonnet, via ``services.structured_extract``) proposes a
    typed plan. It never writes SQL.
  * **Deterministic code** here validates that plan against the catalog
    facets, sorts each field into a hard constraint, a soft preference, or
    an exclusion, and compiles parameterized PostgreSQL predicates.

Why the hard/soft split matters more than it looks: "under $100",
"in stock", and "no candles" are not ranking hints. They are correctness
boundaries. A semantic search engine that quietly returns a $250 candle
for that query has not degraded gracefully — it has lied. The relaxation
ladder in :meth:`SearchPlan.relaxation_ladder` can widen *preferences*
when a strict pass returns too little, but it can never drop a hard
constraint or an exclusion. Every widening step is recorded in
:class:`Relaxation` so the response and the retrieval receipt can say
exactly what changed.

Terminology, so the surfaces can agree:

  ``hard``       never relaxed automatically (price ceiling, availability,
                 explicit category, exclusions)
  ``soft``       may be relaxed per the declared policy (tags, taste signal)
  ``exclusions`` hard *negative* predicates ("avoid candles")
  ``ambiguous``  extracted but untrusted; surfaced, never silently applied
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Relaxation policies. ``soft_only`` is the default and the only policy
# that runs unattended: it widens preferences and stops. ``strict`` never
# widens anything, so a short result set stays short and honest.
RELAXATION_POLICY_SOFT_ONLY = "soft_only"
RELAXATION_POLICY_STRICT = "strict"
_RELAXATION_POLICIES = (RELAXATION_POLICY_SOFT_ONLY, RELAXATION_POLICY_STRICT)

# Retrieval strategies the planner may select. These name real code paths.
STRATEGY_VECTOR = "vector"
STRATEGY_HYBRID = "hybrid"
STRATEGY_HYBRID_RERANK = "hybrid+rerank"
_STRATEGIES = (STRATEGY_VECTOR, STRATEGY_HYBRID, STRATEGY_HYBRID_RERANK)


@dataclass(frozen=True)
class HardConstraints:
    """Constraints that must hold for a candidate to be valid at all.

    Attributes:
        price_max_usd: Inclusive price ceiling in USD, or None.
        in_stock_only: When True, only rows with ``quantity > 0`` qualify.
        categories: Explicit catalog categories. Empty means unconstrained.
    """

    price_max_usd: Optional[float] = None
    in_stock_only: bool = False
    categories: Tuple[str, ...] = ()

    def is_empty(self) -> bool:
        """Return True when nothing here restricts the candidate set."""
        return (
            self.price_max_usd is None
            and not self.in_stock_only
            and not self.categories
        )

    def describe(self) -> List[str]:
        """Human-readable constraint list for receipts and UI copy."""
        parts: List[str] = []
        if self.price_max_usd is not None:
            parts.append(f"price <= ${self.price_max_usd:g}")
        if self.in_stock_only:
            parts.append("in stock")
        if self.categories:
            parts.append("category in " + ", ".join(self.categories))
        return parts


@dataclass(frozen=True)
class SoftPreferences:
    """Preferences that shape ranking and may be widened when sparse.

    Attributes:
        tags: Catalog tags treated as preferences, not requirements.
        soft_signal: The residual taste phrase the reranker scores against.
    """

    tags: Tuple[str, ...] = ()
    soft_signal: str = ""


@dataclass(frozen=True)
class Relaxation:
    """One recorded widening step.

    Attributes:
        step: Machine label for the step, e.g. ``drop_tags``.
        reason: Why the widening happened.
        dropped: The preference values no longer applied.
    """

    step: str
    reason: str
    dropped: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for the response envelope and retrieval receipt."""
        return {
            "step": self.step,
            "reason": self.reason,
            "dropped": list(self.dropped),
        }


@dataclass
class SearchPlan:
    """A validated, typed retrieval plan.

    Produced by :func:`build_plan` and consumed by the retrieval layer.
    Deterministic code owns every field; the model only proposes inputs.

    Attributes:
        intent: The shopper's goal in their own words (the raw query).
        hard: Constraints that gate candidate validity.
        soft: Preferences that shape ranking.
        exclusions: Hard negative tag predicates.
        retrieval_strategy: Which retrieval path to run.
        top_k: Number of final results requested.
        evidence_required: When True, the answer must cite retrieved rows.
        relaxation_policy: Which widening is permitted.
        ambiguous: Fields extracted but not trusted enough to apply.
        relaxations: Widening steps actually applied, in order.
    """

    intent: str
    hard: HardConstraints = field(default_factory=HardConstraints)
    soft: SoftPreferences = field(default_factory=SoftPreferences)
    exclusions: Tuple[str, ...] = ()
    retrieval_strategy: str = STRATEGY_HYBRID_RERANK
    top_k: int = 5
    evidence_required: bool = True
    relaxation_policy: str = RELAXATION_POLICY_SOFT_ONLY
    ambiguous: Tuple[str, ...] = ()
    relaxations: List[Relaxation] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Predicate compilation
    # ------------------------------------------------------------------
    def compile_predicates(
        self, *, include_soft: bool = True
    ) -> Tuple[List[str], List[Any]]:
        """Compile this plan into parameterized SQL predicates.

        The model never produces SQL. Each predicate here is a fixed
        string with ``%s`` placeholders; every value travels as a bound
        parameter, so a hallucinated category name can only ever be a
        non-matching string, never injected syntax.

        Args:
            include_soft: When False, tag preferences are omitted. Hard
                constraints and exclusions are always included.

        Returns:
            ``(clauses, params)`` — SQL fragments to AND together, and the
            positional parameters they consume, in matching order.
        """
        clauses: List[str] = []
        params: List[Any] = []

        if self.hard.categories:
            clauses.append("category = ANY(%s)")
            params.append(list(self.hard.categories))
        if self.hard.price_max_usd is not None:
            clauses.append("price <= %s")
            params.append(float(self.hard.price_max_usd))
        if self.hard.in_stock_only:
            # No parameter: a literal predicate cannot be tampered with.
            clauses.append("quantity > 0")
        if self.exclusions:
            clauses.append("NOT (tags ?| %s)")
            params.append(list(self.exclusions))
        if include_soft and self.soft.tags:
            clauses.append("tags ?| %s")
            params.append(list(self.soft.tags))

        return clauses, params

    # ------------------------------------------------------------------
    # Relaxation
    # ------------------------------------------------------------------
    def relaxation_ladder(self) -> List["SearchPlan"]:
        """Return the ordered attempts to try, strictest first.

        The ladder only ever widens :class:`SoftPreferences`. Hard
        constraints and exclusions are carried unchanged into every rung,
        which is what makes "under $100, no candles" safe to trust: no
        rung of this ladder can produce a $250 candle.

        Under ``strict`` policy the ladder is a single rung — a sparse
        result stays sparse rather than silently becoming a wider one.
        """
        first = self._with_relaxations([])
        if self.relaxation_policy == RELAXATION_POLICY_STRICT:
            return [first]
        if not self.soft.tags:
            return [first]

        widened = self._with_relaxations(
            [
                Relaxation(
                    step="drop_tags",
                    reason=(
                        "strict pass returned too few valid candidates; "
                        "tag preferences widened (hard constraints kept)"
                    ),
                    dropped=self.soft.tags,
                )
            ]
        )
        widened.soft = SoftPreferences(tags=(), soft_signal=self.soft.soft_signal)
        return [first, widened]

    def _with_relaxations(self, relaxations: Sequence[Relaxation]) -> "SearchPlan":
        # === WORKSHOP · Search plan · preserve requirements: START ===
        return replace(self, relaxations=list(relaxations))
        # === WORKSHOP · Search plan · preserve requirements: END ===

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Serialize the plan for API envelopes and retrieval receipts."""
        return {
            "intent": self.intent,
            "hard_constraints": {
                "price_max_usd": self.hard.price_max_usd,
                "in_stock_only": self.hard.in_stock_only,
                "categories": list(self.hard.categories),
            },
            "soft_preferences": {
                "tags": list(self.soft.tags),
                "soft_signal": self.soft.soft_signal,
            },
            "exclusions": list(self.exclusions),
            "retrieval_strategy": self.retrieval_strategy,
            "top_k": self.top_k,
            "evidence_required": self.evidence_required,
            "relaxation_policy": self.relaxation_policy,
            "ambiguous": list(self.ambiguous),
            "relaxations": [r.to_dict() for r in self.relaxations],
        }


def _clean_tags(values: Any, allowed: Sequence[str]) -> Tuple[str, ...]:
    """Keep only known catalog tags, lowercased and de-duplicated."""
    allowed_set = {str(tag).lower() for tag in allowed}
    seen: List[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        lowered = value.strip().lower()
        if lowered in allowed_set and lowered not in seen:
            seen.append(lowered)
    return tuple(seen)


def _clean_categories(values: Any, allowed: Sequence[str]) -> Tuple[str, ...]:
    """Map extracted categories onto canonical catalog casing."""
    canonical = {str(cat).lower(): str(cat) for cat in allowed}
    seen: List[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        match = canonical.get(value.strip().lower())
        if match and match not in seen:
            seen.append(match)
    return tuple(seen)


def _clean_price(value: Any) -> Tuple[Optional[float], bool]:
    """Return ``(price_max, was_ambiguous)`` for an extracted ceiling."""
    if value is None:
        return None, False
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None, True
    if price <= 0:
        return None, True
    return price, False


def _clamp_top_k(value: Any) -> int:
    """Clamp a requested result count into ``1..50``.

    A falsy-but-explicit ``0`` clamps to 1 rather than defaulting to 5:
    the caller asked for a bounded list, so silently widening it would be
    the same class of surprise the relaxation ladder exists to prevent.
    """
    try:
        requested = int(value)
    except (TypeError, ValueError):
        return 5
    return max(1, min(requested, 50))


def build_plan(
    query: str,
    extracted: Optional[Dict[str, Any]] = None,
    *,
    known_categories: Optional[Sequence[str]] = None,
    known_tags: Optional[Sequence[str]] = None,
    price_max_usd: Optional[float] = None,
    category: Optional[str] = None,
    top_k: int = 5,
    retrieval_strategy: str = STRATEGY_HYBRID_RERANK,
    relaxation_policy: str = RELAXATION_POLICY_SOFT_ONLY,
) -> SearchPlan:
    """Validate a model-proposed extraction into a typed :class:`SearchPlan`.

    Args:
        query: The shopper's raw query; becomes ``intent``.
        extracted: The structured extractor's output
            (``categories``, ``tags``, ``price_max_usd``, ``in_stock_only``,
            ``exclusions``, ``soft_signal``). Missing or malformed fields
            degrade to "unconstrained", never to a guess.
        known_categories: Allowed catalog categories. Defaults to the
            facets declared in ``services.structured_extract``.
        known_tags: Allowed catalog tags. Same default.
        price_max_usd: Caller-supplied ceiling. A caller-supplied value is
            authoritative and overrides the extracted one — the agent
            passed it explicitly, so it is not a guess.
        category: Caller-supplied explicit category, treated as hard.
        top_k: Number of final results requested.
        retrieval_strategy: One of ``vector``, ``hybrid``,
            ``hybrid+rerank``. Unknown values fall back to
            ``hybrid+rerank``.
        relaxation_policy: ``soft_only`` (default) or ``strict``.

    Returns:
        A validated :class:`SearchPlan`. Never raises on bad model output;
        unusable fields land in ``ambiguous`` instead.
    """
    from services.structured_extract import KNOWN_CATEGORIES, KNOWN_TAGS

    categories_allowed = known_categories or KNOWN_CATEGORIES
    tags_allowed = known_tags or KNOWN_TAGS
    payload = extracted or {}
    ambiguous: List[str] = []

    extracted_price, price_ambiguous = _clean_price(payload.get("price_max_usd"))
    if price_ambiguous:
        ambiguous.append("price_max_usd")

    # A caller-supplied ceiling wins: the agent named it explicitly.
    resolved_price = (
        float(price_max_usd) if price_max_usd is not None else extracted_price
    )

    hard_categories = _clean_categories(payload.get("categories"), categories_allowed)
    if category:
        explicit = _clean_categories([category], categories_allowed)
        # An explicit category the catalog does not know is surfaced rather
        # than silently dropped or silently applied.
        hard_categories = explicit or hard_categories
        if not explicit:
            ambiguous.append("category")

    exclusions = _clean_tags(payload.get("exclusions"), tags_allowed)
    soft_tags = tuple(
        tag for tag in _clean_tags(payload.get("tags"), tags_allowed)
        if tag not in exclusions
    )

    soft_signal = payload.get("soft_signal")
    if not isinstance(soft_signal, str) or not soft_signal.strip():
        soft_signal = (query or "").strip()

    if retrieval_strategy not in _STRATEGIES:
        logger.debug(
            "unknown retrieval_strategy %r — using %s",
            retrieval_strategy,
            STRATEGY_HYBRID_RERANK,
        )
        retrieval_strategy = STRATEGY_HYBRID_RERANK
    if relaxation_policy not in _RELAXATION_POLICIES:
        relaxation_policy = RELAXATION_POLICY_SOFT_ONLY

    return SearchPlan(
        intent=(query or "").strip(),
        hard=HardConstraints(
            price_max_usd=resolved_price,
            in_stock_only=bool(payload.get("in_stock_only", False)),
            categories=hard_categories,
        ),
        soft=SoftPreferences(tags=soft_tags, soft_signal=soft_signal.strip()),
        exclusions=exclusions,
        retrieval_strategy=retrieval_strategy,
        top_k=_clamp_top_k(top_k),
        evidence_required=True,
        relaxation_policy=relaxation_policy,
        ambiguous=tuple(ambiguous),
    )
