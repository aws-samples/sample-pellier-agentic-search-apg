"""Durable retrieval receipts — the ``Prove`` step for retrieval.

``pellier.tool_audit`` proves a tool *ran*. It cannot answer why one
product won: which constraints were hard, which preferences were widened,
how each branch ranked the candidates, or which merchandising rule
reordered the final list. This module writes the other half of that
evidence into ``pellier.retrieval_receipts``.

The receipt exists so an attendee can ask one question and get a complete
answer from SQL:

    Why did this result appear, what evidence influenced it, and which
    constraints were enforced?

Two design choices worth stating:

* **The raw query is not stored.** ``query_hash`` is a SHA-256 of the
  normalized text, with a short preview for human readability. Receipts
  stay groupable and comparable without retaining shopper phrasing
  indefinitely. That claim covers the whole row, not just
  ``query_preview``: ``_redact_plan`` truncates the two free-text fields
  the plan carries (``intent``, and ``soft_preferences.soft_signal``) to
  the same preview length before the plan is persisted.
* **Writes are best-effort and never block a turn.** A receipt is
  evidence about a turn, not part of serving it. A failed insert logs and
  returns; it does not fail the shopper's request. Losing a receipt is a
  gap in evidence, whereas failing the turn is a gap in the product.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Preview length. Long enough to recognize the query in a SQL result,
# short enough that a receipt table is not a transcript archive.
_PREVIEW_CHARS = 120

# The storefront route sets this once per local turn before it calls
# ``chat_stream``. ``asyncio.to_thread`` copies ContextVars into the Strands
# worker, so the sync retrieval tool can bind its receipt to the same
# server-minted turn without accepting identity fields from the model.
_turn_context_var: contextvars.ContextVar[Dict[str, Any] | None] = (
    contextvars.ContextVar("retrieval_receipt_turn_context", default=None)
)


def set_turn_context(
    *,
    turn_id: str,
    session_id: Optional[str],
    principal_sub: Optional[str],
    rail: Optional[str],
) -> contextvars.Token:
    """Bind trusted route context to receipts written during one local turn."""
    return _turn_context_var.set(
        {
            "turn_id": turn_id,
            "session_id": session_id,
            "principal_sub": principal_sub,
            "rail": rail,
        }
    )


def reset_turn_context(token: contextvars.Token) -> None:
    """Clear a route-scoped receipt context after the stream terminates."""
    _turn_context_var.reset(token)


def current_turn_context() -> Dict[str, Any]:
    """Return a defensive copy of the trusted context for the current turn."""
    return dict(_turn_context_var.get() or {})


def _redact_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Strip raw shopper phrasing out of the persisted plan.

    The structured half of a plan -- categories, price ceiling, stock, tags,
    exclusions, relaxations, strategy -- is what makes a receipt explainable,
    and none of it is free text. Two fields are: ``intent`` is the query
    verbatim, and ``soft_signal`` is the residual phrase carved out of it.
    Both are replaced with the same bounded preview the receipt already stores,
    so a receipt stays readable without holding the sentence indefinitely.
    """
    redacted = dict(plan)
    if "intent" in redacted:
        redacted["intent"] = str(redacted["intent"] or "")[:_PREVIEW_CHARS]
    soft = redacted.get("soft_preferences")
    if isinstance(soft, dict) and "soft_signal" in soft:
        soft = dict(soft)
        soft["soft_signal"] = str(soft["soft_signal"] or "")[:_PREVIEW_CHARS]
        redacted["soft_preferences"] = soft
    return redacted


def query_hash(query: str) -> str:
    """Return a stable SHA-256 hash of the normalized query text.

    Normalization is lowercase + whitespace collapse, so "Under $100 Gift"
    and "under $100  gift" group together.
    """
    normalized = " ".join((query or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def citation_snapshot_hash(snapshots: List[Dict[str, Any]]) -> str:
    """Hash the ordered catalog evidence captured for one retrieval turn."""
    canonical = json.dumps(
        snapshots,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _citation_snapshot(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Capture bounded catalog evidence before returning the product."""
    value = row.get("product_id", row.get("productId"))
    if value is None or not str(value).strip():
        return None
    product_id = str(value)
    name = " ".join(str(row.get("name") or product_id).split())
    description = " ".join(str(row.get("description") or "").split())
    quote = f"{name}: {description}".rstrip(":").strip()[:280]
    updated_at = row.get("updated_at")
    revision = (
        updated_at.isoformat()
        if hasattr(updated_at, "isoformat")
        else str(updated_at).strip() or None
    )
    return {
        "entity_id": product_id,
        "source_uri": f"aurora://pellier/product_catalog/{product_id}",
        "revision": revision,
        "quote": quote,
    }


@dataclass
class RetrievalReceipt:
    """One retrieval turn's evidence, ready to persist.

    Built by :func:`build_receipt` from a :class:`~services.search_plan.SearchPlan`
    plus the per-stage rankings the pipeline already produces.
    """

    query: str
    plan: Any
    turn_id: Optional[str] = None
    session_id: Optional[str] = None
    principal_sub: Optional[str] = None
    embedding_model: Optional[str] = None
    rerank_model: Optional[str] = None
    retrieval_config: Dict[str, Any] = field(default_factory=dict)
    index_parameters: Dict[str, Any] = field(default_factory=dict)
    candidate_product_ids: List[Any] = field(default_factory=list)
    vector_ranks: Dict[str, Any] = field(default_factory=dict)
    lexical_ranks: Dict[str, Any] = field(default_factory=dict)
    rrf_scores: Dict[str, Any] = field(default_factory=dict)
    rerank_scores: Dict[str, Any] = field(default_factory=dict)
    merchandising_rules: List[Dict[str, Any]] = field(default_factory=list)
    memory_record_ids_used: List[Any] = field(default_factory=list)
    # Citation snapshots are captured at retrieval time. Resolving product IDs
    # against the live catalog later would make an old receipt mutable.
    citation_ids: List[Any] = field(default_factory=list)
    citation_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    citation_snapshot_hash: Optional[str] = None
    latency_breakdown: Dict[str, Any] = field(default_factory=dict)
    modeled_cost_usd: Optional[float] = None
    trace_id: Optional[str] = None
    rail: Optional[str] = None

    def to_row(self) -> Dict[str, Any]:
        """Project this receipt onto ``pellier.retrieval_receipts`` columns.

        The plan is redacted first. ``SearchPlan.intent`` is the raw query and
        ``SoftPreferences.soft_signal`` is the residual phrase from it, so
        persisting the plan verbatim contradicted this module's own
        minimization claim in two columns while ``query_preview`` was being
        carefully truncated in a third.
        """
        plan_dict = _redact_plan(
            self.plan.to_dict() if hasattr(self.plan, "to_dict") else {}
        )
        return {
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "principal_sub": self.principal_sub,
            "query_hash": query_hash(self.query),
            "query_preview": (self.query or "")[:_PREVIEW_CHARS],
            "search_plan": plan_dict,
            "hard_constraints": plan_dict.get("hard_constraints", {}),
            "soft_preferences": plan_dict.get("soft_preferences", {}),
            "exclusions": plan_dict.get("exclusions", []),
            "relaxations": plan_dict.get("relaxations", []),
            "embedding_model": self.embedding_model,
            "rerank_model": self.rerank_model,
            "retrieval_config": self.retrieval_config,
            "index_parameters": self.index_parameters,
            "candidate_product_ids": self.candidate_product_ids,
            "vector_ranks": self.vector_ranks,
            "lexical_ranks": self.lexical_ranks,
            "rrf_scores": self.rrf_scores,
            "rerank_scores": self.rerank_scores,
            "merchandising_rules": self.merchandising_rules,
            "memory_record_ids_used": self.memory_record_ids_used,
            "citation_ids": self.citation_ids,
            "citation_snapshots": self.citation_snapshots,
            "citation_snapshot_hash": self.citation_snapshot_hash,
            "latency_breakdown": self.latency_breakdown,
            "modeled_cost_usd": self.modeled_cost_usd,
            "trace_id": self.trace_id,
            "rail": self.rail,
        }


def build_receipt(
    *,
    query: str,
    plan: Any,
    candidates: Optional[List[Dict[str, Any]]] = None,
    ordered: Optional[List[Dict[str, Any]]] = None,
    citation_rows: Optional[List[Dict[str, Any]]] = None,
    merchandising_rules: Optional[List[Dict[str, Any]]] = None,
    **extra: Any,
) -> RetrievalReceipt:
    """Assemble a receipt from a plan and the pipeline's own rankings.

    Args:
        query: The shopper's raw query.
        plan: The :class:`SearchPlan` that ran.
        candidates: The fused candidate pool. Rows may carry ``vec_rank``,
            ``fts_rank``, and ``rrf_score``, which the explained hybrid
            path already produces.
        ordered: The reranked list. Rows may carry ``rerank_score``.
        citation_rows: The final product rows returned to the shopper. Defaults
            to ``ordered`` for callers without a later post-rerank filter.
        merchandising_rules: Any declared ranking rules that fired.
        **extra: Passed through to :class:`RetrievalReceipt` (session id,
            models, trace id, rail, latency, cost).

    Returns:
        A populated :class:`RetrievalReceipt`. Missing rank fields are
        simply absent rather than fabricated — an empty ``rerank_scores``
        means rerank did not run, which is itself evidence.
    """
    candidates = candidates or []
    ordered = ordered or []

    def _pid(row: Dict[str, Any]) -> Optional[str]:
        value = row.get("product_id", row.get("productId"))
        return None if value is None else str(value)

    vector_ranks: Dict[str, Any] = {}
    lexical_ranks: Dict[str, Any] = {}
    rrf_scores: Dict[str, Any] = {}
    candidate_ids: List[Any] = []
    for row in candidates:
        pid = _pid(row)
        if pid is None:
            continue
        candidate_ids.append(pid)
        if row.get("vec_rank") is not None:
            vector_ranks[pid] = row["vec_rank"]
        if row.get("fts_rank") is not None:
            lexical_ranks[pid] = row["fts_rank"]
        if row.get("rrf_score") is not None:
            rrf_scores[pid] = float(row["rrf_score"])

    rerank_scores: Dict[str, Any] = {}
    citation_ids: List[Any] = []
    for row in ordered:
        pid = _pid(row)
        if pid is None:
            continue
        score = row.get("rerank_score")
        if score is not None:
            rerank_scores[pid] = float(score)

    snapshots: List[Dict[str, Any]] = []
    for row in citation_rows if citation_rows is not None else ordered:
        pid = _pid(row)
        if pid is None:
            continue
        citation_ids.append(pid)
        snapshot = _citation_snapshot(row)
        if snapshot is not None:
            snapshots.append(snapshot)

    return RetrievalReceipt(
        query=query,
        plan=plan,
        candidate_product_ids=candidate_ids,
        vector_ranks=vector_ranks,
        lexical_ranks=lexical_ranks,
        rrf_scores=rrf_scores,
        rerank_scores=rerank_scores,
        citation_ids=citation_ids,
        citation_snapshots=snapshots,
        citation_snapshot_hash=citation_snapshot_hash(snapshots) if snapshots else None,
        merchandising_rules=merchandising_rules or [],
        **extra,
    )


INSERT_SQL = """
    INSERT INTO pellier.retrieval_receipts (
        turn_id, session_id, principal_sub, query_hash, query_preview,
        search_plan, hard_constraints, soft_preferences, exclusions,
        relaxations, embedding_model, rerank_model, retrieval_config,
        index_parameters, candidate_product_ids, vector_ranks,
        lexical_ranks, rrf_scores, rerank_scores, merchandising_rules,
        memory_record_ids_used, citation_ids, latency_breakdown,
        citation_snapshots, citation_snapshot_hash, modeled_cost_usd, trace_id, rail
    ) VALUES (
        %s, %s, %s, %s, %s,
        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
        %s::jsonb, %s, %s, %s::jsonb,
        %s::jsonb, %s::jsonb, %s::jsonb,
        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s,
        %s, %s, %s
    )
    RETURNING receipt_id
"""

_JSON_COLUMNS = (
    "search_plan",
    "hard_constraints",
    "soft_preferences",
    "exclusions",
    "relaxations",
    "retrieval_config",
    "index_parameters",
    "candidate_product_ids",
    "vector_ranks",
    "lexical_ranks",
    "rrf_scores",
    "rerank_scores",
    "merchandising_rules",
    "memory_record_ids_used",
    "citation_ids",
    "citation_snapshots",
    "latency_breakdown",
)

_COLUMN_ORDER = (
    "turn_id",
    "session_id",
    "principal_sub",
    "query_hash",
    "query_preview",
    "search_plan",
    "hard_constraints",
    "soft_preferences",
    "exclusions",
    "relaxations",
    "embedding_model",
    "rerank_model",
    "retrieval_config",
    "index_parameters",
    "candidate_product_ids",
    "vector_ranks",
    "lexical_ranks",
    "rrf_scores",
    "rerank_scores",
    "merchandising_rules",
    "memory_record_ids_used",
    "citation_ids",
    "latency_breakdown",
    "citation_snapshots",
    "citation_snapshot_hash",
    "modeled_cost_usd",
    "trace_id",
    "rail",
)


def receipt_params(receipt: RetrievalReceipt) -> List[Any]:
    """Bind a receipt to ``INSERT_SQL``'s positional parameters."""
    row = receipt.to_row()
    params: List[Any] = []
    for column in _COLUMN_ORDER:
        value = row.get(column)
        if column in _JSON_COLUMNS:
            params.append(json.dumps(value if value is not None else {}, default=str))
        else:
            params.append(value)
    return params


async def persist_receipt(db: Any, receipt: RetrievalReceipt) -> bool:
    """Insert one receipt. Returns True on success.

    Best-effort by contract: a failure is logged and reported as ``False``
    rather than raised, so evidence collection can never break the turn it
    describes.
    """
    if db is None:
        return False
    try:
        await db.execute_query(INSERT_SQL, *receipt_params(receipt))
        return True
    except Exception as exc:
        logger.warning("retrieval receipt insert failed: %s", exc)
        return False
