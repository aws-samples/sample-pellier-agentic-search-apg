"""Episodic memory for the Operator desk: what happened, and how it ended.

The substrate, and what it is not
--------------------------------

Pellier's four memory substrates have different owners, and this is the Aurora one:

    working     AgentCore Memory   the session timeline
    semantic    AgentCore Memory   USER_PREFERENCE, what to remember about a person
    episodic    Aurora             THIS — what actually happened, and how it ended
    procedural  the repository     checked-in skills and MCP tool contracts

Two things it is deliberately not:

``pellier.customer_episodic_seed`` (migration 003) is narrative demo material the
memory surfaces render. It is a story, not a record, and this module never reads or
writes it.

``pellier.tool_audit`` records that a tool ran. ``pellier.write_operations`` records
that a write applied exactly once. Neither answers "what kind of situation was this,
and did the resolution hold?", because neither carries the human decision, the policy
decision and the database outcome together.

An episode is a significant durable outcome
-------------------------------------------

One row per resolution, not one per turn. A client summary that read five orders is
not an episode; a damaged return that a human confirmed, Cedar allowed, row-level
security permitted, and Aurora applied exactly once is. The four read workflows write
nothing here — they establish facts and produce prose, and none of them changes the
world.

Who writes, and when
--------------------

:func:`record_outcome_episode`, called from ``governed_execution`` after the execution
receipt is durable, and nothing else. Three terminal shapes qualify:

    human confirmed, policy ALLOW, Aurora PERMITTED   the write applied
    human confirmed, policy DENY,  Aurora NOT_REACHED  authorization refused it
    human confirmed, policy ALLOW, Aurora DENIED       the database refused it

Every field is DERIVED from durable artifacts — the approval, the receipt, the tool's
own result — and none of it from model prose. An episode that remembers what a model
said rather than what happened is worse than no episode.

An empty table stays the correct answer until a governed resolution completes, and
:func:`retrieve_episodes` returning nothing is that answer rather than a gap to be
filled. Seeding a "successful past resolution" to make a surface look convincing would
be the exact failure this application argues against — and for two weeks the only rows
in here came from a capture script, which is why the writer now lives on the real path.

Three outcomes, kept apart
--------------------------

``human_outcome``, ``policy_outcome`` and ``aurora_outcome`` are separate columns
because they answer different questions and regularly disagree. A Cedar ALLOW beside
an Aurora rollback is the most instructive row this table can hold, and collapsing
them into one ``status`` would destroy it.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Episode kinds, matching the CHECK constraint in migration 024. Duplicated here so a
# caller gets a clear Python-side error instead of a constraint violation, and
# `test_episode_types_match_the_migration` proves the two lists agree.
EPISODE_RETURN_RESOLUTION = "return_resolution"
EPISODE_REPLACEMENT_OFFERED = "replacement_offered"
EPISODE_CREDIT_ISSUED = "credit_issued"
EPISODE_ESCALATION = "escalation"
EPISODE_INVENTORY_CORRECTION = "inventory_correction"

EPISODE_TYPES = (
    EPISODE_RETURN_RESOLUTION,
    EPISODE_REPLACEMENT_OFFERED,
    EPISODE_CREDIT_ISSUED,
    EPISODE_ESCALATION,
    EPISODE_INVENTORY_CORRECTION,
)

HUMAN_OUTCOMES = ("confirmed", "declined", "not_required", "pending")
POLICY_OUTCOMES = ("allow", "deny", "not_evaluated")
AURORA_OUTCOMES = ("applied", "refused", "rolled_back", "not_attempted")

# Bounded recall. Unlimited episode history to a model is a cost and a relevance
# problem, not a feature.
_DEFAULT_LIMIT = 5


class EpisodeError(Exception):
    """A refused episode write. Carries a machine code, like SessionError."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class Episode:
    """One durable outcome."""

    customer_id: str
    episode_type: str
    situation: str
    source_turn_id: str = ""
    session_id: str = ""
    # The reviewed execution that produced this outcome (migration 026). `review_id` is
    # the idempotency key: one reviewed outcome, one episode, however many times the
    # tool was replayed.
    review_id: Optional[int] = None
    execution_turn_id: str = ""
    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    action_summary: Dict[str, Any] = field(default_factory=dict)
    human_outcome: str = "not_required"
    policy_outcome: str = "not_evaluated"
    aurora_outcome: str = "not_attempted"
    resolution: str = ""
    episode_id: Optional[int] = None
    created_at: Optional[str] = None
    similarity: Optional[float] = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            "episodeId": self.episode_id,
            "customerId": self.customer_id,
            "episodeType": self.episode_type,
            "situation": self.situation,
            "sourceTurnId": self.source_turn_id,
            "sessionId": self.session_id,
            "reviewId": self.review_id,
            "executionTurnId": self.execution_turn_id,
            "evidenceSummary": self.evidence_summary,
            "actionSummary": self.action_summary,
            # Three outcomes, never merged: a policy ALLOW beside an Aurora rollback
            # is the most instructive shape this row can have.
            "humanOutcome": self.human_outcome,
            "policyOutcome": self.policy_outcome,
            "auroraOutcome": self.aurora_outcome,
            "resolution": self.resolution,
            "createdAt": self.created_at,
            "similarity": self.similarity,
        }


# `ON CONFLICT DO NOTHING`: a retried write of the same outcome must not append a
# second episode. The RETURNING clause is empty on a conflict, which the caller reports
# as a replay rather than as a failure.
#
# Two conflict targets, and only one can be named in a statement. The LOGICAL OUTCOME
# key wins: `(review_id, episode_type)` from migration 026 is what a replay must not
# duplicate, and `execution_turn_id` is assign-once per review so the two are the same
# contract. `(source_turn_id, episode_type)` from 024 still constrains rows that carry
# no review — a background reconciliation, say — and those take the other statement.
_INSERT_SQL = """
INSERT INTO pellier.operator_episodes
    (customer_id, source_turn_id, session_id, review_id, execution_turn_id,
     episode_type, situation, evidence_summary, action_summary, human_outcome,
     policy_outcome, aurora_outcome, resolution, embedding)
VALUES
    (%(customer_id)s, %(source_turn_id)s, %(session_id)s, %(review_id)s,
     %(execution_turn_id)s, %(episode_type)s, %(situation)s, %(evidence_summary)s,
     %(action_summary)s, %(human_outcome)s, %(policy_outcome)s, %(aurora_outcome)s,
     %(resolution)s, %(embedding)s)
ON CONFLICT (review_id, episode_type) WHERE review_id IS NOT NULL
DO NOTHING
RETURNING episode_id, created_at
"""

# The same insert for an episode with no review. Identical but for the conflict target,
# because Postgres resolves `ON CONFLICT` against one index.
_INSERT_NO_REVIEW_SQL = _INSERT_SQL.replace(
    "ON CONFLICT (review_id, episode_type) WHERE review_id IS NOT NULL",
    "ON CONFLICT (source_turn_id, episode_type) WHERE source_turn_id IS NOT NULL",
)

_SELECT_COLUMNS = """
       episode_id, customer_id, source_turn_id, session_id, review_id,
       execution_turn_id, episode_type,
       situation, evidence_summary, action_summary, human_outcome,
       policy_outcome, aurora_outcome, resolution, created_at
"""

_RECENT_SQL = f"""
SELECT {_SELECT_COLUMNS}, NULL::float AS similarity
  FROM pellier.operator_episodes
 WHERE customer_id = %(customer_id)s
   AND (%(episode_type)s::text IS NULL
        OR episode_type = %(episode_type)s::text)
 ORDER BY created_at DESC, episode_id DESC
 LIMIT %(limit)s
"""

# Semantic recall. Cosine distance, the same operator the catalog and the semantic
# cache use, so one embedding configuration serves the whole application. Rows with no
# embedding are excluded rather than treated as maximally distant.
_SIMILAR_SQL = f"""
SELECT {_SELECT_COLUMNS},
       1 - (embedding <=> %(embedding)s::vector) AS similarity
  FROM pellier.operator_episodes
 WHERE customer_id = %(customer_id)s
   AND embedding IS NOT NULL
   AND (%(episode_type)s::text IS NULL
        OR episode_type = %(episode_type)s::text)
 ORDER BY embedding <=> %(embedding)s::vector
 LIMIT %(limit)s
"""


def _validate(episode: Episode) -> None:
    """Fail fast with a clear code rather than on a database CHECK constraint."""
    if not (episode.customer_id or "").strip():
        raise EpisodeError("customer_required")
    if not (episode.situation or "").strip():
        raise EpisodeError("situation_required")
    if episode.episode_type not in EPISODE_TYPES:
        raise EpisodeError(f"unknown_episode_type:{episode.episode_type}")
    if episode.human_outcome not in HUMAN_OUTCOMES:
        raise EpisodeError(f"unknown_human_outcome:{episode.human_outcome}")
    if episode.policy_outcome not in POLICY_OUTCOMES:
        raise EpisodeError(f"unknown_policy_outcome:{episode.policy_outcome}")
    if episode.aurora_outcome not in AURORA_OUTCOMES:
        raise EpisodeError(f"unknown_aurora_outcome:{episode.aurora_outcome}")


async def store_episode(
    db: Any, episode: Episode, *, embedding: Optional[Sequence[float]] = None
) -> Dict[str, Any]:
    """Record one significant durable outcome.

    The embedding is optional and is never generated here: an episode is durable the
    moment it happens, and an embedding call that fails must not be able to lose it.
    A caller that wants semantic recall supplies the vector; one that does not gets a
    row that is still fully queryable by customer, type, time and full-text.

    Returns ``{"episodeId", "createdAt", "replayed"}``. ``replayed`` is True when this
    turn already recorded an episode of this type, which is a success.
    """
    _validate(episode)

    params = {
        "customer_id": episode.customer_id.strip(),
        "source_turn_id": (episode.source_turn_id or "").strip() or None,
        "session_id": (episode.session_id or "").strip() or None,
        "review_id": int(episode.review_id) if episode.review_id is not None else None,
        "execution_turn_id": (episode.execution_turn_id or "").strip() or None,
        "episode_type": episode.episode_type,
        "situation": episode.situation.strip(),
        "evidence_summary": json.dumps(episode.evidence_summary or {}),
        "action_summary": json.dumps(episode.action_summary or {}),
        "human_outcome": episode.human_outcome,
        "policy_outcome": episode.policy_outcome,
        "aurora_outcome": episode.aurora_outcome,
        "resolution": episode.resolution or "",
        "embedding": list(embedding) if embedding else None,
    }

    sql = _INSERT_SQL if params["review_id"] is not None else _INSERT_NO_REVIEW_SQL
    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()

    if not row:
        # The partial unique index refused a duplicate. Report it plainly instead of
        # raising: the caller's intent — "this outcome is on the record" — holds.
        return {"episodeId": None, "createdAt": None, "replayed": True}
    return {
        "episodeId": int(row["episode_id"]),
        "createdAt": _iso(row.get("created_at")),
        "replayed": False,
    }


# ---------------------------------------------------------------------------
# The production writer: a derived memory of one reviewed execution
# ---------------------------------------------------------------------------

# The three terminal shapes that are worth remembering, keyed by
# (policy_outcome, aurora_outcome) from the execution receipt. Anything else is not an
# outcome yet, and inventing an episode for it would be the "plausible history" failure
# this module exists to refuse:
#
#   ALLOW / PERMITTED   the action ran and the database applied it
#   DENY  / NOT_REACHED authorization refused it; the tool was never entered
#   ALLOW / DENIED      authorization permitted it; the database refused it
#
# Deliberately absent: a proposal, a pending review, a confirmation on its own, and
# every read workflow. None of them has ended.
_TERMINAL_OUTCOMES: Dict[tuple, tuple] = {
    ("ALLOW", "PERMITTED"): ("allow", "applied"),
    ("DENY", "NOT_REACHED"): ("deny", "not_attempted"),
    ("ALLOW", "DENIED"): ("allow", "refused"),
}

# Which kind of situation a tool's outcome is. Not derived from prose.
_EPISODE_TYPE_BY_TOOL: Dict[str, str] = {
    "give_store_credit": EPISODE_CREDIT_ISSUED,
    "ask_a_person": EPISODE_ESCALATION,
}

# Approval status to the human axis. `pellier.approvals.status` is the human axis and
# nothing else, which is migration 021's argument and still holds.
_HUMAN_BY_STATUS: Dict[str, str] = {
    "approved": "confirmed",
    "rejected": "declined",
    "pending": "pending",
}


def is_terminal_outcome(policy_outcome: str, aurora_outcome: str) -> bool:
    """Whether these two axes describe an outcome worth remembering.

    Uses the ``services.governed_execution`` vocabulary, not the episode vocabulary:
    this is asked of a live receipt before any mapping happens.
    """
    return (str(policy_outcome), str(aurora_outcome)) in _TERMINAL_OUTCOMES


def derive_episode(
    *,
    review: Any,
    receipt: Any,
    result: Optional[Dict[str, Any]] = None,
) -> Optional[Episode]:
    """Build an episode from durable artifacts, or None when there is no outcome yet.

    Every field is derived. Nothing here reads model prose, because an episode that
    remembers what a model said rather than what happened is worse than no episode:

        pellier.approvals        -> human_outcome, customer, situation material
        execution receipt        -> policy_outcome, aurora_outcome, execution_turn_id
        the tool's own result    -> the concrete effect, e.g. which return was created

    Returns None for every non-terminal shape, which is the common case: a proposal, a
    pending review, a confirmation on its own, and all four read workflows.
    """
    policy = str((receipt or {}).get("policy_outcome") or "")
    aurora = str((receipt or {}).get("aurora_outcome") or "")
    mapped = _TERMINAL_OUTCOMES.get((policy, aurora))
    if mapped is None:
        return None

    tool = str((receipt or {}).get("tool") or review.get("action") or "")
    episode_type = _EPISODE_TYPE_BY_TOOL.get(tool)
    if episode_type is None:
        # A governed tool with no episode kind yet. Refuse rather than filing it under a
        # kind that does not describe it; widen `_EPISODE_TYPE_BY_TOOL` when one appears.
        logger.info("no episode kind for tool %r; no episode recorded", tool)
        return None

    policy_outcome, aurora_outcome = mapped
    human_outcome = _HUMAN_BY_STATUS.get(
        str(review.get("status") or ""), "not_required"
    )
    args = review.get("args") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    reason = str(args.get("reason") or "").replace("_", " ")
    customer_id = str(review.get("customer_id") or "")
    result = dict(result or {})

    return Episode(
        customer_id=customer_id,
        episode_type=episode_type,
        source_turn_id=str(review.get("source_turn_id") or ""),
        review_id=int(review["review_id"]) if review.get("review_id") else None,
        execution_turn_id=str((receipt or {}).get("execution_turn_id") or ""),
        situation=_situation(tool, reason, customer_id, args),
        resolution=_resolution(policy, aurora, result),
        human_outcome=human_outcome,
        policy_outcome=policy_outcome,
        aurora_outcome=aurora_outcome,
        # The pointers a reconstruction needs, and no copies of business truth: current
        # stock, membership and order state are read live from the tables that own them.
        evidence_summary={
            "reviewId": review.get("review_id"),
            "sourceTurnId": review.get("source_turn_id"),
            "executionTurnId": (receipt or {}).get("execution_turn_id"),
            "receiptId": (receipt or {}).get("receipt_id"),
            "idempotencyKey": (receipt or {}).get("idempotency_key"),
            "gatewayActionId": (receipt or {}).get("gateway_action_id"),
            "gatewayMode": (receipt or {}).get("gateway_mode"),
            "rail": (receipt or {}).get("rail"),
        },
        action_summary={
            "tool": tool,
            "reason": args.get("reason"),
            "amountCents": args.get("amount_cents"),
            "creditId": result.get("credit_id"),
            "idempotentReplay": bool(result.get("idempotent_replay")),
        },
    )


def _situation(tool: str, reason: str, customer_id: str, args: Any) -> str:
    """What kind of situation this was, in one sentence, for a human and for FTS."""
    cents = args.get("amount_cents") if isinstance(args, dict) else None
    if tool == "give_store_credit" and cents is not None:
        detail = f" for {reason}" if reason else ""
        return f"{customer_id} was proposed a ${int(cents) / 100:.2f} store credit{detail}."
    return f"{customer_id}: {tool}."


def _resolution(policy: str, aurora: str, result: Dict[str, Any]) -> str:
    """How it ended. Names the layer that decided, because that is the lesson."""
    if policy == "DENY":
        return (
            "AgentCore Policy refused the action, so the tool was never entered and "
            "nothing reached the database."
        )
    if aurora == "DENIED":
        return (
            "AgentCore Policy permitted the action and the database refused it, so "
            "nothing changed."
        )
    credit_id = result.get("credit_id")
    if credit_id:
        applied = f"Credit {credit_id} was recorded through the governed path."
    else:
        applied = "The write applied through the governed path."
    if result.get("idempotent_replay"):
        applied += " This call replayed a write that had already applied."
    return applied


async def record_outcome_episode(
    db: Any,
    *,
    review: Any,
    receipt: Any,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record the episode for one reviewed execution, if it reached an outcome.

    Called from the governed execution path, after the receipt is written, so the
    episode is derived from the artifact rather than from the classification in flight.

    Never raises, and never blocks the execution it describes. An episode is a DERIVED
    MEMORY: losing one costs recall, while failing a completed governed write over it
    would cost an operator their afternoon. The authoritative artifacts are the
    approval, the receipt, `tool_audit`, `write_operations` and the domain rows, and all
    of them are already durable by the time this runs.

    Returns ``{"episodeId", "replayed", "recorded"}``. ``recorded`` is False when the
    outcome was not terminal, which is a decision rather than a failure.
    """
    episode = derive_episode(review=review, receipt=receipt, result=result)
    if episode is None:
        return {"episodeId": None, "replayed": False, "recorded": False}

    embedding = await _embed_situation(episode.situation)
    try:
        stored = await store_episode(db, episode, embedding=embedding)
    except Exception as exc:  # noqa: BLE001 - memory must not fail the write
        logger.warning(
            "episode not recorded for review %s: %s", episode.review_id, exc
        )
        return {"episodeId": None, "replayed": False, "recorded": False}
    return {**stored, "recorded": True}


async def _embed_situation(situation: str) -> Optional[List[float]]:
    """Embed the situation for semantic recall, or None when that fails.

    Best effort by contract. The episode is durable the moment it happens and an
    embedding call that fails must not be able to lose it, so a failure here yields a
    row with a NULL embedding that is still fully queryable by customer, kind, time and
    full-text. No business rollback, and no second vector service.
    """
    if not (situation or "").strip():
        return None
    try:
        from services.embeddings import EmbeddingService

        # `embed_document`, not `embed_query`: Cohere Embed v4 is asymmetric, and the
        # stored side must be indexed as a document or every recall is measured against
        # the wrong half of the model. `retrieve_episodes` embeds the operator's
        # question with `embed_query`.
        #
        # In a thread because the Bedrock call is blocking, and this runs on the request
        # loop directly after a governed write.
        vector = await asyncio.to_thread(
            EmbeddingService().embed_document, situation
        )
    except Exception as exc:  # noqa: BLE001 - recall is an enhancement, not the record
        logger.info("episode embedding unavailable: %s", exc)
        return None
    if not vector:
        return None
    return list(vector)


async def retrieve_episodes(
    db: Any,
    *,
    customer_id: str,
    episode_type: Optional[str] = None,
    embedding: Optional[Sequence[float]] = None,
    limit: int = _DEFAULT_LIMIT,
) -> List[Episode]:
    """Recall this client's episodes, semantically when an embedding is supplied.

    Never raises. A read failure yields an empty list, and an empty list is also the
    honest answer for a client with no prior resolutions — the caller must render
    "no prior episodes" rather than implying recall happened and found nothing useful.
    """
    if not (customer_id or "").strip():
        return []
    sql = _SIMILAR_SQL if embedding else _RECENT_SQL
    params: Dict[str, Any] = {
        "customer_id": customer_id.strip(),
        "episode_type": episode_type,
        "limit": max(1, min(int(limit or _DEFAULT_LIMIT), 25)),
    }
    if embedding:
        params["embedding"] = list(embedding)

    try:
        async with db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
    except Exception as exc:  # noqa: BLE001 - recall is best effort
        # WARNING, not INFO: this handler also swallows a malformed query, and an
        # empty list is indistinguishable from "this client has no episodes".
        logger.warning("episode recall failed for %s: %s", customer_id, exc)
        return []

    return [_episode_from_row(row) for row in rows]


def _episode_from_row(row: Dict[str, Any]) -> Episode:
    return Episode(
        episode_id=int(row["episode_id"]),
        customer_id=str(row["customer_id"]),
        source_turn_id=str(row.get("source_turn_id") or ""),
        session_id=str(row.get("session_id") or ""),
        review_id=(
            int(row["review_id"]) if row.get("review_id") is not None else None
        ),
        execution_turn_id=str(row.get("execution_turn_id") or ""),
        episode_type=str(row["episode_type"]),
        situation=str(row.get("situation") or ""),
        evidence_summary=row.get("evidence_summary") or {},
        action_summary=row.get("action_summary") or {},
        human_outcome=str(row.get("human_outcome") or "not_required"),
        policy_outcome=str(row.get("policy_outcome") or "not_evaluated"),
        aurora_outcome=str(row.get("aurora_outcome") or "not_attempted"),
        resolution=str(row.get("resolution") or ""),
        created_at=_iso(row.get("created_at")),
        similarity=(
            float(row["similarity"]) if row.get("similarity") is not None else None
        ),
    )


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else value
