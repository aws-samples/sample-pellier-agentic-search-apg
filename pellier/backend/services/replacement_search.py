"""Replacement Search: from a real order item to evidence-bound recommendations.

The shape of the pipeline
-------------------------

    operator request
      -> order item grounded in Aurora            (FACT, not model output)
      -> constraints extracted by Amazon Bedrock  (proposal, validated in code)
      -> PostgreSQL FTS + pgvector, RRF-merged    (candidate generation)
      -> hard constraints in SQL                  (correctness boundary)
      -> Cohere Rerank                            (reordering only)
      -> inventory reconciled against the ledger  (availability)
      -> two or three recommendations

What is composed rather than rebuilt
------------------------------------

Every retrieval mechanism here already exists and is the one the shopper path runs:
``services.structured_extract`` proposes filters, ``services.search_plan.build_plan``
validates them into a typed plan and compiles parameterized predicates,
``services.hybrid_search.HybridSearch`` runs the two branches and the RRF merge, and
``services.rerank`` reorders. This module contributes the *replacement-specific*
parts — grounding, the price anchor, the availability contract, and the
recommendation object — and nothing else. A second retrieval implementation inside
the Concierge would be a second thing to keep true.

What it does *not* share, and why
---------------------------------

The shopper surfaces run one executor,
``services.planned_hybrid_retrieval.execute_search_plan``. This module composes the
same parts one level up instead, because three of its behaviors have no expression
in that executor's contract: it adds two hard predicates of its own (never the SKU
being replaced, and reconciled availability rather than the aggregate cache), it
stops walking the ladder on candidate count *before* reranking rather than on
returned count after it, and it shows the reranker every candidate while keeping
only the best ``_RERANK_POOL``. Routing it through the shared executor would change
which rung serves, how many Bedrock rerank calls a request makes, and which
candidates the reranker ever sees.

The cost of that choice is one thing the shared executor provides and this pipeline
does not: a post-rerank eligibility recheck. Here the hard predicates are enforced
once, in SQL, on both branches — which is the enforcement point, and the reranker
can only reorder what SQL already validated. The executor's second check exists to
catch a row that slipped past the SQL. Add it here if this module ever gains a code
path that can put an unvalidated row into ``candidates``.

Three boundaries that carry the weight
--------------------------------------

**The order item is established by Aurora, never by the request text.** An operator
may write "the coral catchall"; the product id, name, price paid and category come
from ``pellier.orders`` joined to the catalog. If the phrase matches more than one
order line, the workflow asks rather than guessing — a model's confidence is not
authority over which business record is meant.

**A hard constraint is enforced in PostgreSQL, before the reranker.** The reranker
reorders valid candidates; it can never resurrect an invalid one, because an invalid
candidate was never in the pool. "Please stay under $100" in a prompt is not
enforcement.

**"In stock" means reconciled against the ledger.** The shopper planner compiles
``in_stock_only`` to ``quantity > 0`` on the aggregate cache, which holds a seed
constant for 940 of 1000 catalog rows. This module refuses that predicate and uses
``inventory_evidence.RECONCILED_AVAILABLE_SQL`` instead, so the phrase means
something. Where no reconciled candidate exists, the answer says so rather than
quietly widening to a cache reading.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Roles a recommendation may carry.
#
# There is deliberately no UPGRADE role. An upgrade needs a factual improvement
# established by catalog attributes, and this catalog has none to offer: `tier` is
# 1 for all 1000 rows (measured 2026-08-27), and `rating`/`reviews` are review
# aggregates rather than construction specifications. Calling something an upgrade
# because a reranker put it first would be exactly the invented claim this surface
# exists to avoid. If the catalog later carries material, capacity or specification
# columns, the role becomes derivable and can be added then.
ROLE_BEST_MATCH = "best_match"
ROLE_ALTERNATIVE = "alternative"

# Availability requirements a replacement search may carry.
AVAILABILITY_ANY = "any"
AVAILABILITY_RECONCILED = "reconciled"

# The declared similar-price heuristic. NOT business policy: Pellier has no
# replacement price rule, so rather than invent an unexplained band this module
# names the multiplier, applies it as a hard ceiling, and reports it as a heuristic
# wherever the plan is shown. An explicit operator ceiling always wins over it.
SIMILAR_PRICE_CEILING_MULTIPLIER = 1.15

# Candidate pool sizes. Kept small on purpose: this is an operator recommendation,
# not catalog browsing.
_POOL_TOP_N = 24
_RERANK_POOL = 12
_MAX_RECOMMENDATIONS = 3

# Below this, the strict rung is too thin for a reranker to reorder meaningfully and
# the ladder widens SOFT preferences only. Same threshold and same reasoning as the
# shopper comparison path in `app.py` (`AGENTIC_MIN_POOL`).
_MIN_POOL = 5

# Phrases that make availability an explicit operator requirement. The structured
# extractor also reports `in_stock_only`, and either source is sufficient — but a
# match here is what upgrades the requirement from the cache predicate to the
# ledger one.
_AVAILABILITY_PHRASES = (
    "in stock", "in-stock", "currently available", "available now",
    "ready to ship", "can ship", "on hand",
)

_ORDER_ITEMS_SQL = """
    SELECT o.id                AS order_id,
           o.product_id        AS product_id,
           o.quantity          AS quantity,
           o.placed_at         AS placed_at,
           pc.name             AS name,
           pc.brand            AS brand,
           pc.color            AS color,
           pc.category         AS category,
           pc.price            AS price,
           pc.description      AS description,
           pc.tags             AS tags,
           pc."imgUrl"         AS img_url
      FROM pellier.orders o
      JOIN pellier.product_catalog pc ON pc."productId" = o.product_id
     WHERE o.customer_id = %s
     ORDER BY o.placed_at DESC NULLS LAST, o.id DESC
"""


@dataclass
class OrderItem:
    """One real order line. Every field is an Aurora fact."""

    order_id: int
    product_id: str
    name: str
    category: str
    price: float
    quantity: int
    brand: str = ""
    color: str = ""
    description: str = ""
    tags: Tuple[str, ...] = ()
    img_url: str = ""
    placed_at: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            "orderId": self.order_id,
            "productId": self.product_id,
            "name": self.name,
            "category": self.category,
            "price": self.price,
            "quantity": self.quantity,
            "brand": self.brand,
            "color": self.color,
            "imgUrl": self.img_url,
            "placedAt": self.placed_at,
        }


@dataclass
class Grounding:
    """The outcome of resolving which order item the operator meant.

    Exactly one of ``item`` or ``candidates`` is meaningful. Ambiguity is a first
    class result, not an error and not a coin flip.
    """

    item: Optional[OrderItem] = None
    candidates: List[OrderItem] = field(default_factory=list)
    matched_on: str = ""
    ambiguous: bool = False
    reason: str = ""


@dataclass
class ReplacementPlan:
    """The replacement-specific controls, on top of a validated SearchPlan.

    ``search_plan`` owns the hard/soft split and predicate compilation; this owns
    the things only a replacement has: which item is being replaced, where the price
    ceiling came from, and what availability has to mean.
    """

    original: OrderItem
    search_plan: Any
    availability_requirement: str = AVAILABILITY_ANY
    price_anchor_usd: Optional[float] = None
    price_ceiling_source: str = ""
    retrieval_query: str = ""

    def describe_hard_controls(self) -> List[str]:
        """The constraint list a receipt or the UI may print."""
        parts: List[str] = []
        ceiling = self.search_plan.hard.price_max_usd
        if ceiling is not None:
            label = f"price ≤ ${ceiling:,.2f}"
            if self.price_ceiling_source == "similar_price_heuristic":
                label += " (similar-price heuristic)"
            parts.append(label)
        if self.search_plan.hard.categories:
            parts.append("category " + ", ".join(self.search_plan.hard.categories))
        if self.availability_requirement == AVAILABILITY_RECONCILED:
            parts.append("current availability reconciled to the ledger")
        parts.append(f"excludes the original item ({self.original.product_id})")
        return parts

    def to_payload(self) -> Dict[str, Any]:
        return {
            "original": self.original.to_payload(),
            "hardConstraints": {
                "priceMaxUsd": self.search_plan.hard.price_max_usd,
                "categories": list(self.search_plan.hard.categories),
                "availabilityRequirement": self.availability_requirement,
                "excludesProductId": self.original.product_id,
            },
            "softPreferences": {
                "tags": list(self.search_plan.soft.tags),
                "signal": self.search_plan.soft.soft_signal,
            },
            "exclusions": list(self.search_plan.exclusions),
            "priceAnchorUsd": self.price_anchor_usd,
            "priceCeilingSource": self.price_ceiling_source,
            "retrievalQuery": self.retrieval_query,
            # Extracted but untrusted, surfaced rather than silently applied.
            "ambiguous": list(self.search_plan.ambiguous),
            "describeHardControls": self.describe_hard_controls(),
        }


@dataclass
class Recommendation:
    """One canonical recommendation. Narrative and card both hydrate from this.

    The reference implementation's contradiction — prose saying "remains in stock"
    beside a card reading "Out of stock" — is impossible here because there is one
    object and one availability field on it. Bedrock may write ``fit_reasons``; it
    contributes no identifier, price or quantity.
    """

    product_id: str
    name: str
    brand: str
    category: str
    price: float
    img_url: str
    role: str
    inventory: Any
    fit_reasons: List[str] = field(default_factory=list)
    rerank_score: Optional[float] = None
    rrf_score: Optional[float] = None
    price_delta_usd: Optional[float] = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            "productId": self.product_id,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "price": self.price,
            "imgUrl": self.img_url,
            "role": self.role,
            "fitReasons": list(self.fit_reasons),
            "priceDeltaUsd": self.price_delta_usd,
            "inventoryEvidence": self.inventory.to_payload(),
            "availabilitySentence": _describe(self.inventory),
            "retrievalEvidence": {
                "rerankScore": self.rerank_score,
                "rrfScore": self.rrf_score,
            },
        }


@dataclass
class ReplacementResult:
    """Everything one replacement search established."""

    plan: ReplacementPlan
    available: List[Recommendation] = field(default_factory=list)
    close_matches: List[Recommendation] = field(default_factory=list)
    pool_size: int = 0
    after_hard_constraints: int = 0
    reranked: int = 0
    rerank_applied: bool = False
    # How many reranked candidates reconciled, counted BEFORE the display cap.
    # Counting the capped list instead reported "3 of 12 reconciled" for a pool where
    # all twelve had reconciled — the cap is a presentation choice, not a finding.
    reconciled_count: int = 0
    # Soft widening actually applied, in order. Empty means the strict rung was enough.
    relaxations: List[Dict[str, Any]] = field(default_factory=list)
    coverage_note: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_payload(),
            "available": [r.to_payload() for r in self.available],
            "closeMatches": [r.to_payload() for r in self.close_matches],
            "retrieval": {
                "poolSize": self.pool_size,
                "afterHardConstraints": self.after_hard_constraints,
                "reranked": self.reranked,
                "reconciledCount": self.reconciled_count,
                "rerankApplied": self.rerank_applied,
                "strategy": self.plan.search_plan.retrieval_strategy,
                # What was widened, so a short or a broad result explains itself.
                "relaxations": list(self.relaxations),
            },
            "coverageNote": self.coverage_note,
        }


def _describe(evidence: Any) -> str:
    from services.inventory_evidence import describe_availability

    return describe_availability(evidence)


# ---------------------------------------------------------------------------
# 1. Grounding: which order item is the operator talking about
# ---------------------------------------------------------------------------


def _tokens(text: str) -> List[str]:
    """Content words, lowercased. Deliberately dumb: this only narrows candidates."""
    stop = {
        "the", "a", "an", "for", "to", "of", "and", "or", "in", "on", "with", "her",
        "his", "their", "my", "our", "this", "that", "these", "those", "find", "get",
        "me", "please", "recent", "recently", "last", "order", "orders", "item",
        "replacement", "replace", "alternative", "similar", "instead", "something",
        "some", "any", "she", "he", "they", "it", "is", "was", "bought", "purchased",
    }
    words = re.findall(r"[a-z][a-z'-]+", (text or "").lower())
    return [w for w in words if w not in stop and len(w) > 2]


def _match_score(item: OrderItem, tokens: Sequence[str]) -> int:
    """How many request tokens the order line's own text accounts for."""
    haystack = f"{item.name} {item.brand} {item.category}".lower()
    return sum(1 for token in tokens if token in haystack)


async def resolve_order_item(
    db: Any, *, customer_id: str, request: str
) -> Grounding:
    """Establish which order line is being replaced, from Aurora.

    Product facts repeated in the request are not trusted: the order line supplies
    the id, the name, the category and the price. The request text is used only to
    narrow WHICH line, and when it narrows to more than one the caller is told to ask.
    """
    try:
        async with db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_ORDER_ITEMS_SQL, (customer_id,))
                rows = await cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("order items read failed for %s: %s", customer_id, exc)
        return Grounding(reason="order_history_unavailable")

    items = [_order_item(row) for row in rows]
    if not items:
        return Grounding(reason="no_order_history")

    tokens = _tokens(request)
    explicit = _explicit_order_id(request)
    if explicit is not None:
        hit = next((i for i in items if i.order_id == explicit), None)
        if hit is not None:
            return Grounding(item=hit, matched_on=f"order #{explicit}")
        return Grounding(
            candidates=items[:5], ambiguous=True,
            reason=f"order_not_found:{explicit}",
        )

    scored = [(item, _match_score(item, tokens)) for item in items]
    best = max((score for _item, score in scored), default=0)
    if best > 0:
        matches = [item for item, score in scored if score == best]
        if len(matches) > 1:
            # Two order lines fit the phrase equally well. Picking the newer one
            # would be a guess wearing a heuristic's clothes.
            return Grounding(
                candidates=matches, ambiguous=True, reason="ambiguous_item_reference",
            )
        return Grounding(item=matches[0], matched_on="named in the request")

    # Nothing in the request narrowed it. The most recent line is a defensible
    # default AND it is reported as such, so the operator can see what was assumed.
    return Grounding(item=items[0], matched_on="most recent order")


def _explicit_order_id(request: str) -> Optional[int]:
    match = re.search(r"(?:order\s*#?|#)\s*(\d{1,10})\b", request or "", re.I)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _order_item(row: Dict[str, Any]) -> OrderItem:
    placed = row.get("placed_at")
    tags = row.get("tags") or []
    return OrderItem(
        order_id=int(row["order_id"]),
        product_id=str(row["product_id"]),
        name=str(row.get("name") or ""),
        category=str(row.get("category") or ""),
        price=float(row.get("price") or 0.0),
        quantity=int(row.get("quantity") or 1),
        brand=str(row.get("brand") or ""),
        color=str(row.get("color") or ""),
        description=str(row.get("description") or ""),
        tags=tuple(str(t) for t in tags if isinstance(t, str)),
        img_url=str(row.get("img_url") or ""),
        placed_at=placed.isoformat() if hasattr(placed, "isoformat") else placed,
    )


# ---------------------------------------------------------------------------
# 2. The plan: model proposes, code decides what is hard
# ---------------------------------------------------------------------------


def requires_reconciled_availability(request: str, extracted: Dict[str, Any]) -> bool:
    """Whether the operator asked for stock that actually exists.

    Either an explicit phrase or the extractor's ``in_stock_only`` is sufficient.
    What this decides is only whether availability becomes a HARD constraint; what
    that constraint MEANS is fixed — reconciled to the ledger, never a cache read.
    """
    text = (request or "").lower()
    if any(phrase in text for phrase in _AVAILABILITY_PHRASES):
        return True
    return bool(extracted.get("in_stock_only"))


def build_replacement_plan(
    *, original: OrderItem, request: str, extracted: Dict[str, Any]
) -> ReplacementPlan:
    """Compile the operator's intent into a validated, typed plan.

    The extractor proposes; ``build_plan`` validates against the catalog facets and
    sorts every field into hard or soft. Two replacement-specific decisions are made
    here and both are recorded rather than implied:

    * The original item's CATEGORY becomes a hard constraint. That is an Aurora fact
      about the thing being replaced, not an inference about the client — a
      replacement for a pour-over set is not a scarf. An explicit operator category
      overrides it.
    * ``in_stock_only`` is forced off in the SearchPlan so it can never compile the
      aggregate-cache predicate. The requirement is carried on this object instead
      and enforced with the ledger predicate.
    """
    from services.search_plan import build_plan

    availability = (
        AVAILABILITY_RECONCILED
        if requires_reconciled_availability(request, extracted)
        else AVAILABILITY_ANY
    )

    operator_ceiling = _clean_ceiling(extracted.get("price_max_usd"))
    anchor = float(original.price or 0.0) or None
    if operator_ceiling is not None:
        ceiling, source = operator_ceiling, "operator_explicit"
    elif anchor:
        ceiling = round(anchor * SIMILAR_PRICE_CEILING_MULTIPLIER, 2)
        source = "similar_price_heuristic"
    else:
        ceiling, source = None, ""

    # The retrieval query is the ORIGINAL ITEM plus the operator's residual taste
    # phrase. The item's own name and description are what make a replacement
    # search semantically about the item rather than about the sentence.
    soft_signal = str(extracted.get("soft_signal") or "").strip()
    retrieval_query = " ".join(
        part for part in (original.name, original.description[:180], soft_signal)
        if part
    ).strip()

    # `in_stock_only` deliberately stripped: see the docstring.
    proposed = dict(extracted)
    proposed["in_stock_only"] = False

    plan = build_plan(
        retrieval_query,
        proposed,
        price_max_usd=ceiling,
        category=original.category or None,
        top_k=_MAX_RECOMMENDATIONS,
    )
    return ReplacementPlan(
        original=original,
        search_plan=plan,
        availability_requirement=availability,
        price_anchor_usd=anchor,
        price_ceiling_source=source,
        retrieval_query=retrieval_query,
    )


def _clean_ceiling(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def compile_replacement_predicates(
    plan: ReplacementPlan, rung: Optional[Any] = None
) -> Tuple[List[str], List[Any]]:
    """The SQL that gates candidate validity. Applied to BOTH retrieval branches.

    Order of business: the SearchPlan's own predicates for this ladder rung, then the
    two this workflow adds — never the same SKU, and (when required) availability
    reconciled against the ledger rather than read off the aggregate cache.

    ``rung`` is a step from ``SearchPlan.relaxation_ladder()``. Every rung carries the
    same hard constraints; only soft tag preferences differ, so no rung of this ladder
    can produce a candidate over the price ceiling, outside the category, or without
    reconciled stock.
    """
    from services.inventory_evidence import RECONCILED_AVAILABLE_SQL

    clauses, params = (rung or plan.search_plan).compile_predicates()

    # A replacement is never the item it replaces.
    clauses.append('product_catalog."productId" <> %s')
    params.append(plan.original.product_id)

    if plan.availability_requirement == AVAILABILITY_RECONCILED:
        # No parameter: a literal predicate cannot be tampered with, and this one
        # reads the ledger views migration 013 defines.
        clauses.append(RECONCILED_AVAILABLE_SQL)

    return clauses, params


# ---------------------------------------------------------------------------
# 3. Retrieval, reranking, and the availability partition
# ---------------------------------------------------------------------------


async def find_replacements(db: Any, plan: ReplacementPlan) -> ReplacementResult:
    """Run the pipeline and return recommendations bound to their evidence."""
    from config import settings
    from services.embeddings import EmbeddingService
    from services.hybrid_search import HybridSearch
    from services.inventory_evidence import resolve_inventory_many
    from services.rerank import get_rerank_service

    embedding = EmbeddingService().embed_query(plan.retrieval_query)
    hybrid = HybridSearch(db)

    # Walk the relaxation ladder rather than firing the strict rung once. A tag the
    # extractor proposed — "ceramic", "artisanal" — is a PREFERENCE, and leaving it in
    # the predicate made it gate validity: replacing a suede boot returned zero
    # candidates because no Footwear row carried the proposed tags. Every rung keeps
    # the hard constraints, so widening can never cross a correctness boundary.
    async def search_rung(rung: Any) -> List[Dict[str, Any]]:
        hard_clauses, hard_params = compile_replacement_predicates(plan, rung)
        return await hybrid.search(
            query=plan.retrieval_query,
            query_embedding=embedding,
            k_vector=settings.HYBRID_VECTOR_K,
            k_fts=settings.HYBRID_FTS_K,
            top_n=_POOL_TOP_N,
            hard_clauses=hard_clauses,
            hard_params=hard_params,
        )

    # Resolve the strict request before constructing any fallback. A sufficient
    # result must remain usable while Task 2B's fallback is still unfinished.
    rung_used = plan.search_plan
    candidates = await search_rung(rung_used)
    if len(candidates) < _MIN_POOL:
        for rung in plan.search_plan.relaxation_ladder()[1:]:
            candidates = await search_rung(rung)
            rung_used = rung
            if len(candidates) >= _MIN_POOL:
                break

    result = ReplacementResult(
        plan=plan,
        pool_size=len(candidates),
        after_hard_constraints=len(candidates),
        relaxations=[r.to_dict() for r in rung_used.relaxations],
    )
    if not candidates:
        result.coverage_note = (
            "No catalog candidate satisfied the hard constraints."
        )
        return result

    # Rerank reorders VALID candidates. Every row here already passed the hard
    # predicates in SQL, so a reranker failure degrades the ORDER and can never
    # widen the set.
    documents = [_rerank_document(c) for c in candidates]
    rerank_service = get_rerank_service()
    reranked = rerank_service.rerank(
        query=plan.search_plan.soft.soft_signal or plan.retrieval_query,
        documents=documents,
        top_n=min(_RERANK_POOL, len(documents)),
    )
    if reranked:
        ordered = [
            {**candidates[r["index"]], "rerank_score": float(r["relevance_score"])}
            for r in reranked
            if 0 <= int(r.get("index", -1)) < len(candidates)
        ]
        result.rerank_applied = True
    else:
        ordered = [{**c, "rerank_score": None} for c in candidates[:_RERANK_POOL]]
    result.reranked = len(ordered)

    # One round trip for every candidate still standing.
    evidence = await resolve_inventory_many(
        db, [str(c.get("product_id")) for c in ordered]
    )

    recommendations: List[Recommendation] = []
    for candidate in ordered:
        pid = str(candidate.get("product_id"))
        inventory = evidence.get(pid)
        if inventory is None:
            continue
        if inventory.supports_availability_claim:
            result.reconciled_count += 1
        recommendations.append(_recommendation(candidate, inventory, plan))

    # Which options are offered depends on whether availability was REQUIRED.
    #
    #   required      only reconciled options may appear. The SQL predicate already
    #                 restricted the pool, so this is a second gate on the same rule:
    #                 an explicit "in stock" must never be satisfied by a cache read.
    #
    #   not required  the best-ranked options are offered in rerank order, each
    #                 carrying its own availability state. Filling the cap with
    #                 reconciled options first would hide a better-ranked option
    #                 behind an availability requirement the operator never asked
    #                 for — and every card states its own availability, so nothing
    #                 is claimed that the evidence does not support.
    if plan.availability_requirement == AVAILABILITY_RECONCILED:
        shortlist = [r for r in recommendations if r.inventory.supports_availability_claim]
    else:
        shortlist = recommendations
    shortlist = shortlist[:_MAX_RECOMMENDATIONS]

    # Partition for DISPLAY only, preserving rerank order within each group. Two
    # headings, because "available" and "availability not verified" are different
    # promises and an operator has to be able to tell at a glance which is which.
    result.available = [
        r for r in shortlist if r.inventory.supports_availability_claim
    ]
    result.close_matches = [
        r for r in shortlist if not r.inventory.supports_availability_claim
    ]
    _assign_roles(result.available, result.close_matches, shortlist)
    for item in result.close_matches:
        item.role = ROLE_ALTERNATIVE

    result.coverage_note = _coverage_note(result)
    return result


def _rerank_document(candidate: Dict[str, Any]) -> str:
    """The text the reranker scores. Same three fields the shopper path uses."""
    name = (candidate.get("name") or "").strip()
    description = (candidate.get("description") or "").strip()
    category = (candidate.get("category") or "").strip()
    if len(description) > 240:
        description = description[:237] + "…"
    return f"{name} — {description} ({category})"


def _recommendation(
    candidate: Dict[str, Any], inventory: Any, plan: ReplacementPlan
) -> Recommendation:
    price = _as_float(candidate.get("price"))
    anchor = plan.price_anchor_usd
    return Recommendation(
        product_id=str(candidate.get("product_id")),
        name=str(candidate.get("name") or ""),
        brand=str(candidate.get("brand") or ""),
        category=str(candidate.get("category") or ""),
        price=price,
        img_url=str(candidate.get("img_url") or ""),
        role=ROLE_ALTERNATIVE,
        inventory=inventory,
        fit_reasons=_fit_reasons(candidate, plan),
        rerank_score=candidate.get("rerank_score"),
        rrf_score=_as_float(candidate.get("rrf_score")) or None,
        price_delta_usd=(round(price - anchor, 2) if anchor else None),
    )


def _fit_reasons(candidate: Dict[str, Any], plan: ReplacementPlan) -> List[str]:
    """Structural reasons only, from catalog attributes. No taste claims.

    Bedrock writes the recommendation prose; these are the facts it may lean on, and
    each one is checkable against the two rows involved.
    """
    reasons: List[str] = []
    original = plan.original
    if (candidate.get("category") or "") == original.category:
        reasons.append(f"Same category as the original ({original.category})")
    price = _as_float(candidate.get("price"))
    if plan.price_anchor_usd:
        delta = price - plan.price_anchor_usd
        if abs(delta) < 0.01:
            reasons.append("Same price as the item ordered")
        elif delta < 0:
            reasons.append(f"${abs(delta):,.2f} below the ${plan.price_anchor_usd:,.2f} paid")
        else:
            reasons.append(f"${delta:,.2f} above the ${plan.price_anchor_usd:,.2f} paid")
    shared = sorted(set(_tag_list(candidate.get("tags"))) & set(original.tags))
    if shared:
        reasons.append("Shares catalog tags: " + ", ".join(shared[:3]))
    if (candidate.get("brand") or "") and candidate.get("brand") == original.brand:
        reasons.append(f"Same house ({original.brand})")
    return reasons


def _tag_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str)]
    return []


def _assign_roles(
    available: List[Recommendation],
    close_matches: List[Recommendation],
    shortlist: List[Recommendation],
) -> None:
    """Best match first, alternatives after. No role implies an unproven improvement.

    The best match is the top-ranked option WITH reconciled availability. A card an
    operator cannot promise is never the recommendation, even when the reranker liked
    it most — which is why the role is not simply "first in the shortlist".
    """
    for item in shortlist:
        item.role = ROLE_ALTERNATIVE
    if available:
        available[0].role = ROLE_BEST_MATCH
    for item in close_matches:
        item.role = ROLE_ALTERNATIVE


def _coverage_note(result: ReplacementResult) -> str:
    """State inventory coverage honestly. Sparse results are data, not a failure."""
    if result.available:
        return ""
    if not result.close_matches and result.relaxations:
        return (
            "No catalog candidate satisfied the hard constraints, even after tag "
            "preferences were widened."
        )
    if result.close_matches:
        return (
            "No candidate has current availability reconciled to the inventory "
            "ledger. Ledger coverage exists for 40 of 1,000 catalog products, so "
            "close matches are shown with availability unverified."
        )
    return "No catalog candidate satisfied the hard constraints."


def _as_float(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0
