"""Durable Operator Concierge conversations, on the tables Pellier already has.

Reuse, not a new store
----------------------

``pellier.conversations`` and ``pellier.messages`` exist from migration 007 and hold
140 real messages across 48 sessions from the shopper dispatcher path. Their writer
is gone, so the substrate is dormant rather than missing. This module restores a
writer for the Operator surface and leaves the historical rows exactly as they are.

The live schema supplies everything needed, so this module adds no migration:

    conversations.session_id  VARCHAR PRIMARY KEY   thread identity
    conversations.agent_name  VARCHAR               surface discriminator
    conversations.metadata    JSONB                 client + creation attribution
    messages.id               SERIAL PRIMARY KEY    deterministic replay order
    messages.role             VARCHAR               'user' | 'assistant'
    messages.metadata         JSONB                 turn_id + structured artifact

`messages.id` being a serial primary key matters: replay ordering comes from it
rather than from `created_at`, which is a timestamp without time zone and can tie.

Two identities, two jobs
------------------------

    session_id   one Operator Concierge thread, many turns
    turn_id      one operator request and its resulting assistant artifact

Both sides of an interaction carry the SAME ``turn_id``, minted by
``services/turn_identity.py``. That is what lets a later review point at the exact
turn that proposed it:

    session_id -> turn_id -> review_id -> execution_turn_id -> tool_audit / domain

No new correlation-id family is introduced, because the existing one already
reaches all the way to the write evidence.

What the browser may not do
---------------------------

The browser supplies an operator message and nothing else. It cannot set the role,
the turn id, the client binding, the operator identity, or any artifact. Those are
all server-derived, because every one of them is a claim about what happened rather
than a request to do something.

Aurora is the record
--------------------

For the Operator surface this is the durable transcript. AgentCore Memory may later
improve what the agent knows, but it must not become a second answer to what the
operator said, what evidence was shown, or which turn produced a review.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# The surface discriminator. Distinct from the legacy `dispatcher` (42 rows) and
# `agents_as_tools` (6 rows), so a Concierge query can never return a shopper thread.
SURFACE = "operator_concierge"

# Bumped when the persisted artifact shape changes in a way a reader must notice.
# v2 adds `workflow`, `primaryLabel`, `primaryNote` and `sections`. A v1 row is still
# readable — every added key is optional — but a v1 READER shown a v2 draft would omit
# the "not sent" label, which is exactly the kind of misread the version guards.
ARTIFACT_VERSION = 2

# Roles, matching what the table and the shopper path already use. Inventing
# `operator` as a role would break every existing reader for no gain; the surface
# and actor live in metadata instead.
ROLE_OPERATOR = "user"
ROLE_ASSISTANT = "assistant"

# A turn whose assistant side never arrived. The operator's request is never deleted:
# losing what someone asked is worse than showing that the answer failed.
TURN_INCOMPLETE = "incomplete"
TURN_COMPLETE = "complete"
TURN_FAILED = "failed"
# The work stopped before it saved an answer: the worker restarted, the turn ran past
# its deadline, or it raised. Distinct from `failed`, where the turn itself reported
# that it could not produce the deliverable.
TURN_INTERRUPTED = "interrupted"

# What an unanswered turn is doing now. Derived on every read, never stored.
OPEN_TURN_RUNNING = "running"
OPEN_TURN_ABANDONED = "abandoned"

# Why an interrupted turn stopped, as recorded on its settling artifact.
CAUSE_STOPPED = "stopped"
CAUSE_DEADLINE = "deadline"
CAUSE_ERROR = "error"

# A running turn renews its lease every few seconds. One that goes this long without a
# renewal has no live worker, so a reader may settle it. Measured Concierge turns take
# 13.5s at the median and 28s at the slowest, and renewal keeps a longer one owned.
LEASE_SECONDS = 30

# Names this worker process on the leases it writes. A restarted worker has a new id,
# so a lease written before a restart is never mistaken for work still running here.
WORKER_ID = uuid.uuid4().hex

_MAX_HISTORY = 100


class SessionError(Exception):
    """A session operation the caller should surface rather than retry blindly."""

    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class OpenTurnError(SessionError):
    """The session already has a turn without an answer.

    A new request waits until that turn is answered or settled, and a replayed
    transport key never starts its turn a second time.
    """

    def __init__(self, turn_id: str) -> None:
        super().__init__("turn_in_progress", 409)
        self.turn_id = turn_id


def _nowhere(_session_id: str, _turn_id: str) -> bool:
    return False


RunningHere = Callable[[str, str], bool]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_id(customer_id: str, token: str) -> str:
    """Readable but not semantically load-bearing.

    The customer appears in the id for operator legibility in psql. It is NEVER the
    authority for the binding — `metadata.customer_id` is, and every read verifies
    against that. An id that carries meaning invites someone to parse it.
    """
    return f"opc-{customer_id.lower()}-{token}"


async def create_session(
    db: Any, *, customer_id: str, operator_sub: str
) -> Dict[str, Any]:
    """Open a team-visible Concierge thread bound to one canonical client.

    Not a consequential action: no Bedrock call, no AgentCore call, no review. It
    records who opened the thread for audit attribution. Authorized operators share
    the client thread; each appended turn records the operator who actually authored
    it, so ``created_by`` is not an ownership or read-authorization boundary.
    """
    if not customer_id:
        raise SessionError("customer_id_required", 422)
    if not operator_sub:
        raise SessionError("operator_identity_required", 401)

    session_id = _session_id(customer_id, uuid.uuid4().hex[:16])
    metadata = {
        "surface": SURFACE,
        "customer_id": customer_id,
        "created_by": operator_sub,
        "schema_version": ARTIFACT_VERSION,
    }
    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO pellier.conversations (session_id, agent_name, metadata)
                VALUES (%s, %s, %s::jsonb)
                """,
                (session_id, SURFACE, json.dumps(metadata)),
            )
    return {
        "sessionId": session_id,
        "customerId": customer_id,
        "surface": SURFACE,
        "createdBy": operator_sub,
        "createdAt": _now().isoformat(),
        "turns": [],
    }


async def _load_session_row(db: Any, session_id: str) -> Optional[Dict[str, Any]]:
    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT session_id, agent_name, metadata, created_at, updated_at
                  FROM pellier.conversations
                 WHERE session_id = %s
                """,
                (session_id,),
            )
            row = await cur.fetchone()
    if not row:
        return None
    # Rows are mappings, not tuples: the pool configures a dict row factory, which
    # a tuple-based test fake hid until the first live round-trip.
    r = dict(row)
    raw = r.get("metadata")
    metadata = raw if isinstance(raw, dict) else json.loads(raw or "{}")
    return {
        "session_id": r.get("session_id"),
        "agent_name": r.get("agent_name"),
        "metadata": metadata,
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
    }


async def require_session(db: Any, *, session_id: str, customer_id: str) -> Dict[str, Any]:
    """Load a session and prove it belongs to this surface AND this client.

    The session id alone is never sufficient. A request routed under one client that
    names another client's session is rejected rather than silently switching
    context, which is the difference between a scoping bug and a data leak.
    """
    row = await _load_session_row(db, session_id)
    if row is None:
        raise SessionError("session_not_found", 404)
    if row["agent_name"] != SURFACE or row["metadata"].get("surface") != SURFACE:
        # A shopper dispatcher thread is not a Concierge session, even though both
        # live in this table.
        raise SessionError("not_a_concierge_session", 404)
    if row["metadata"].get("customer_id") != customer_id:
        raise SessionError("session_client_mismatch", 403)
    return row


async def latest_session(db: Any, *, customer_id: str) -> Optional[str]:
    """The most recent Concierge session for this client, for resume."""
    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT session_id
                  FROM pellier.conversations
                 WHERE agent_name = %s
                   AND metadata->>'customer_id' = %s
                 ORDER BY created_at DESC
                 LIMIT 1
                """,
                (SURFACE, customer_id),
            )
            row = await cur.fetchone()
    return dict(row).get("session_id") if row else None


_GRAPH_ARTIFACT_FOR_REVIEW_SQL = """
SELECT c.session_id, m.id, m.metadata
  FROM pellier.conversations c
  JOIN pellier.messages m ON m.session_id = c.session_id
 WHERE c.agent_name = %(surface)s
   AND c.metadata->>'surface' = %(surface)s
   AND c.metadata->>'customer_id' = %(customer_id)s
   AND m.role = %(role)s
   AND m.metadata->>'surface' = %(surface)s
   AND m.metadata->'artifact'->'orchestration'->'checkpoint'->>'reviewId'
       = %(review_id)s
   AND m.metadata->'artifact'->'orchestration'->'checkpoint'->>'actionHash'
       = %(action_hash)s
 ORDER BY m.id DESC
 LIMIT 1
"""


async def load_graph_artifact_for_review(
    db: Any,
    *,
    customer_id: str,
    review_id: int,
    action_hash: str,
) -> Optional[Dict[str, Any]]:
    """Load the graph artifact that proves the exact durable review lineage.

    A client's latest Concierge answer is not necessarily the turn that produced the
    review currently being inspected. Joining on both the server-created review id
    and its action hash prevents a later summary, or an older proposal for the same
    client, from being presented as that review's orchestration evidence.
    """
    if not customer_id or review_id <= 0 or not action_hash:
        return None

    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                _GRAPH_ARTIFACT_FOR_REVIEW_SQL,
                {
                    "surface": SURFACE,
                    "customer_id": customer_id,
                    "role": ROLE_ASSISTANT,
                    "review_id": str(review_id),
                    "action_hash": action_hash,
                },
            )
            row = await cur.fetchone()

    if not row:
        return None

    result = dict(row)
    raw = result.get("metadata")
    metadata = raw if isinstance(raw, dict) else json.loads(raw or "{}")
    artifact = metadata.get("artifact") or {}
    orchestration = artifact.get("orchestration")
    if not isinstance(orchestration, dict):
        return None

    return {
        "sessionId": result.get("session_id"),
        "turnId": metadata.get("turn_id", ""),
        "orchestration": orchestration,
    }


# One statement that validates the session, honours transport idempotency, inserts
# the message and stamps the conversation. Written as CTEs because each `execute`
# is a separate network round trip to a remote Aurora cluster, and the naive
# four-trip version measured 2145ms before any orchestration had begun. Premium UX
# is most sensitive to dead time BEFORE the visible work starts.
#
# Validation is not weakened: `target` is the gate, and nothing inserts unless the
# session matches this surface AND this customer. The returned row carries enough
# state to raise the same precise errors as before.
#
# Two more gates, in the same trip. A session with an unanswered turn takes no new
# request until that turn is answered or settled, so a retry can never start while
# the first attempt might still write a review. And the insert writes the lease that
# says a worker owns the new turn.
_APPEND_TURN_SQL = """
WITH target AS (
    SELECT session_id,
           agent_name,
           metadata->>'customer_id' AS bound_customer,
           metadata->>'surface'     AS bound_surface
      FROM pellier.conversations
     WHERE session_id = %(session_id)s
),
eligible AS (
    SELECT session_id FROM target
     WHERE agent_name = %(surface)s
       AND bound_surface = %(surface)s
       AND bound_customer = %(customer_id)s
),
existing AS (
    SELECT m.id, m.metadata,
           EXISTS (
               SELECT 1 FROM pellier.messages a
                WHERE a.session_id = m.session_id
                  AND a.role = %(assistant_role)s
                  AND a.metadata->>'turn_id' = m.metadata->>'turn_id'
           ) AS answered
      FROM pellier.messages m
      JOIN eligible e ON e.session_id = m.session_id
     WHERE %(transport_key)s <> ''
       AND m.metadata->>'transport_idempotency_key' = %(transport_key)s
     ORDER BY m.id ASC
     LIMIT 1
),
open_turn AS (
    SELECT u.metadata->>'turn_id' AS turn_id
      FROM pellier.messages u
      JOIN eligible e ON e.session_id = u.session_id
     WHERE u.role = %(role)s
       AND NOT EXISTS (
           SELECT 1 FROM pellier.messages a
            WHERE a.session_id = u.session_id
              AND a.role = %(assistant_role)s
              AND a.metadata->>'turn_id' = u.metadata->>'turn_id'
       )
     ORDER BY u.id DESC
     LIMIT 1
),
inserted AS (
    INSERT INTO pellier.messages (session_id, role, content, metadata)
    SELECT e.session_id, %(role)s, %(content)s, %(metadata)s::jsonb
      FROM eligible e
     WHERE NOT EXISTS (SELECT 1 FROM existing)
       AND NOT EXISTS (SELECT 1 FROM open_turn)
    RETURNING id, metadata
),
touched AS (
    UPDATE pellier.conversations c
       SET updated_at = now(),
           metadata = jsonb_set(
               c.metadata, '{active_turn}',
               jsonb_build_object(
                   'turn_id', %(turn_id)s::text,
                   'owner', %(owner)s::text,
                   'lease_until',
                   extract(epoch FROM clock_timestamp())::float8 + %(lease_seconds)s::float8
               )
           )
      FROM inserted i
     WHERE c.session_id = %(session_id)s
    RETURNING c.session_id
)
SELECT (SELECT COUNT(*) FROM target)                       AS session_exists,
       (SELECT bound_customer FROM target)                 AS bound_customer,
       (SELECT bound_surface FROM target)                   AS bound_surface,
       (SELECT agent_name FROM target)                      AS agent_name,
       (SELECT COUNT(*) FROM eligible)                      AS eligible,
       (SELECT id FROM existing)                            AS existing_id,
       (SELECT metadata FROM existing)                      AS existing_metadata,
       (SELECT answered FROM existing)                      AS existing_answered,
       (SELECT turn_id FROM open_turn)                      AS open_turn_id,
       (SELECT id FROM inserted)                            AS inserted_id,
       (SELECT COUNT(*) FROM touched)                       AS touched
"""


async def append_operator_turn(
    db: Any,
    *,
    session_id: str,
    customer_id: str,
    operator_sub: str,
    message: str,
    transport_key: str = "",
) -> Dict[str, Any]:
    """Persist the operator's request and mint the turn id for the interaction.

    ``transport_key`` is TRANSPORT IDEMPOTENCY, not domain lineage: it stops a
    network retry from duplicating the same request. ``turn_id`` remains the only
    lineage identity, and it is generated here rather than accepted from the caller.

    Executed as ONE round trip. The previous four-trip version cost 2145ms against
    the remote cluster; the semantics are unchanged, including append-only writes and
    the surface/customer gate.

    Raises ``OpenTurnError`` when the session already holds an unanswered turn, and
    when the transport key names a turn that has no answer yet: replaying that key
    must follow or settle the first attempt, never run it again.
    """
    text = (message or "").strip()
    if not text:
        raise SessionError("message_required", 422)

    from services.turn_identity import new_turn_id

    turn_id = new_turn_id()
    metadata: Dict[str, Any] = {
        "surface": SURFACE,
        "turn_id": turn_id,
        "actor_type": "operator",
        "actor_sub": operator_sub,
        "turn_state": TURN_INCOMPLETE,
        "artifact_version": ARTIFACT_VERSION,
    }
    if transport_key:
        metadata["transport_idempotency_key"] = transport_key

    params = {
        "session_id": session_id,
        "surface": SURFACE,
        "customer_id": customer_id,
        "transport_key": transport_key or "",
        "role": ROLE_OPERATOR,
        "assistant_role": ROLE_ASSISTANT,
        "content": text,
        "metadata": json.dumps(metadata),
        "turn_id": turn_id,
        "owner": WORKER_ID,
        "lease_seconds": LEASE_SECONDS,
    }
    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(_APPEND_TURN_SQL, params)
            row = dict(await cur.fetchone() or {})

    # Same error precision as the previous multi-trip version.
    if not int(row.get("session_exists") or 0):
        raise SessionError("session_not_found", 404)
    if row.get("agent_name") != SURFACE or row.get("bound_surface") != SURFACE:
        raise SessionError("not_a_concierge_session", 404)
    if row.get("bound_customer") != customer_id:
        raise SessionError("session_client_mismatch", 403)

    if row.get("existing_id") is not None:
        raw = row.get("existing_metadata")
        meta = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        if not row.get("existing_answered"):
            raise OpenTurnError(meta.get("turn_id", ""))
        return {
            "messageId": int(row["existing_id"]),
            "sessionId": session_id,
            "turnId": meta.get("turn_id", ""),
            "role": ROLE_OPERATOR,
            "content": text,
            "turnState": meta.get("turn_state", TURN_INCOMPLETE),
            "replayed": True,
        }

    if row.get("open_turn_id"):
        raise OpenTurnError(str(row["open_turn_id"]))
    if row.get("inserted_id") is None:
        raise SessionError("turn_not_persisted", 500)

    return {
        "messageId": int(row["inserted_id"]),
        "sessionId": session_id,
        "turnId": turn_id,
        "role": ROLE_OPERATOR,
        "content": text,
        "turnState": TURN_INCOMPLETE,
        "replayed": False,
    }


async def _find_by_transport_key(
    db: Any, session_id: str, transport_key: str
) -> Optional[Dict[str, Any]]:
    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, content, metadata
                  FROM pellier.messages
                 WHERE session_id = %s
                   AND metadata->>'transport_idempotency_key' = %s
                 ORDER BY id ASC
                 LIMIT 1
                """,
                (session_id, transport_key),
            )
            row = await cur.fetchone()
    if not row:
        return None
    r = dict(row)
    raw = r.get("metadata")
    meta = raw if isinstance(raw, dict) else json.loads(raw or "{}")
    return {
        "messageId": int(r["id"]),
        "sessionId": session_id,
        "turnId": meta.get("turn_id", ""),
        "role": ROLE_OPERATOR,
        "content": r.get("content"),
        "turnState": meta.get("turn_state", TURN_INCOMPLETE),
    }


_APPEND_ARTIFACT_SQL = """
WITH target AS (
    SELECT session_id,
           agent_name,
           metadata->>'customer_id' AS bound_customer,
           metadata->>'surface'     AS bound_surface
      FROM pellier.conversations
     WHERE session_id = %(session_id)s
),
eligible AS (
    SELECT session_id FROM target
     WHERE agent_name = %(surface)s
       AND bound_surface = %(surface)s
       AND bound_customer = %(customer_id)s
),
inserted AS (
    INSERT INTO pellier.messages (session_id, role, content, metadata)
    SELECT e.session_id, %(role)s, %(content)s, %(metadata)s::jsonb FROM eligible e
    RETURNING id
),
touched AS (
    UPDATE pellier.conversations c
       SET updated_at = now(),
           metadata = CASE
               WHEN c.metadata->'active_turn'->>'turn_id' = %(turn_id)s
               THEN c.metadata - 'active_turn'
               ELSE c.metadata
           END
      FROM inserted i WHERE c.session_id = %(session_id)s
    RETURNING c.session_id
)
SELECT (SELECT COUNT(*) FROM target)       AS session_exists,
       (SELECT bound_customer FROM target) AS bound_customer,
       (SELECT bound_surface FROM target)  AS bound_surface,
       (SELECT agent_name FROM target)     AS agent_name,
       (SELECT id FROM inserted)           AS inserted_id
"""


async def append_assistant_artifact(
    db: Any,
    *,
    session_id: str,
    customer_id: str,
    turn_id: str,
    summary: str,
    artifact: Dict[str, Any],
    state: str = TURN_COMPLETE,
) -> Dict[str, Any]:
    """Persist the assistant side of an existing turn, sharing its turn id.

    Append-only. A later change of review state is recorded in
    ``pellier.approvals``, never by editing what was said at the time — the
    transcript is history, not current state.

    The artifact must contain only operator-safe, observable material. Nothing here
    stores hidden reasoning: the database should not hold anything the surface would
    be wrong to render.

    One round trip, same surface/customer gate as the operator side.
    """
    if not turn_id:
        raise SessionError("turn_id_required", 422)

    rejected = sorted(set(artifact) & _FORBIDDEN_ARTIFACT_KEYS)
    if rejected:
        raise SessionError(f"forbidden_artifact_keys:{','.join(rejected)}", 422)

    metadata = {
        "surface": SURFACE,
        "turn_id": turn_id,
        "actor_type": "assistant",
        "turn_state": state,
        "artifact_version": ARTIFACT_VERSION,
        "artifact": artifact,
    }
    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                _APPEND_ARTIFACT_SQL,
                {
                    "session_id": session_id,
                    "surface": SURFACE,
                    "customer_id": customer_id,
                    "role": ROLE_ASSISTANT,
                    "content": summary or "",
                    "metadata": json.dumps(metadata),
                    "turn_id": turn_id,
                },
            )
            row = dict(await cur.fetchone() or {})

    if not int(row.get("session_exists") or 0):
        raise SessionError("session_not_found", 404)
    if row.get("agent_name") != SURFACE or row.get("bound_surface") != SURFACE:
        raise SessionError("not_a_concierge_session", 404)
    if row.get("bound_customer") != customer_id:
        raise SessionError("session_client_mismatch", 403)
    if row.get("inserted_id") is None:
        raise SessionError("artifact_not_persisted", 500)

    return {
        "messageId": int(row["inserted_id"]),
        "sessionId": session_id,
        "turnId": turn_id,
        "role": ROLE_ASSISTANT,
        "turnState": state,
    }


# Keys that must never be persisted, because they are model interiors rather than
# observable operator-safe evidence.
_FORBIDDEN_ARTIFACT_KEYS = {
    "reasoning",
    "reasoning_trace",
    "chain_of_thought",
    "thoughts",
    "scratchpad",
    "system_prompt",
    "hidden_prompt",
    "raw_prompt",
}


_HISTORY_SQL = """
WITH target AS (
    SELECT session_id,
           agent_name,
           metadata->>'customer_id' AS bound_customer,
           metadata->>'surface'     AS bound_surface,
           metadata->>'created_by'  AS created_by,
           metadata->'active_turn'  AS active_turn,
           COALESCE(
               (metadata->'active_turn'->>'lease_until')::float8
                   > extract(epoch FROM clock_timestamp())::float8,
               false
           ) AS lease_live
      FROM pellier.conversations
     WHERE session_id = %(session_id)s
),
eligible AS (
    SELECT session_id, created_by, active_turn, lease_live FROM target
     WHERE agent_name = %(surface)s
       AND bound_surface = %(surface)s
       AND bound_customer = %(customer_id)s
)
SELECT (SELECT COUNT(*) FROM target)           AS session_exists,
       (SELECT bound_customer FROM target)     AS bound_customer,
       (SELECT bound_surface FROM target)      AS bound_surface,
       (SELECT agent_name FROM target)         AS agent_name,
       (SELECT created_by FROM eligible)       AS created_by,
       (SELECT active_turn FROM eligible)      AS active_turn,
       (SELECT lease_live FROM eligible)       AS lease_live,
       m.id, m.role, m.content, m.metadata, m.created_at
  FROM eligible e
  LEFT JOIN pellier.messages m ON m.session_id = e.session_id
 ORDER BY m.id DESC
 LIMIT %(limit)s
"""


def _json(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


def classify_open_turn(
    *,
    session_id: str,
    turn_id: str,
    active_turn: Optional[Dict[str, Any]],
    lease_live: bool,
    running_here: RunningHere = _nowhere,
) -> str:
    """Whether an unanswered turn still has a worker, from facts a reader can check.

    Running when this process is working on it, or when another worker holds an
    unexpired lease on it. Anything else is abandoned: no lease (a turn from before
    leases existed), an expired lease (the worker stopped renewing it), or this
    worker's own lease on a turn it no longer runs (the task ended without an
    answer). A restart gives the worker a new id, so its old leases count as another
    worker's and are honoured only until they expire.
    """
    if running_here(session_id, turn_id):
        return OPEN_TURN_RUNNING
    lease = active_turn or {}
    if lease.get("turn_id") == turn_id and lease.get("owner") != WORKER_ID and lease_live:
        return OPEN_TURN_RUNNING
    return OPEN_TURN_ABANDONED


async def load_history(
    db: Any,
    *,
    session_id: str,
    customer_id: str,
    limit: int = 40,
    running_here: RunningHere = _nowhere,
) -> Dict[str, Any]:
    """Bounded, deterministically ordered replay of one Concierge session.

    Ordered by ``messages.id``, the serial primary key, not by ``created_at``: the
    timestamp column has no time zone and two inserts in the same tick would tie,
    which would make replay order arbitrary exactly when a turn matters most.

    One round trip. The validation is the same surface/customer gate, expressed as a
    CTE the message join depends on, so a mismatched session returns no rows rather
    than another client's transcript.

    ``openTurn`` names the newest request without an answer and whether a worker
    still owns it, so a reader can wait for a running turn instead of reporting it
    as broken. ``running_here`` answers for this process's own in-flight turns.
    """
    bounded = max(1, min(int(limit or 40), _MAX_HISTORY))
    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                _HISTORY_SQL,
                {
                    "session_id": session_id,
                    "surface": SURFACE,
                    "customer_id": customer_id,
                    "limit": bounded,
                },
            )
            rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        # No rows at all means the gate rejected. Re-read only on this cold path to
        # produce the precise error; the happy path stays at one trip.
        probe = await _load_session_row(db, session_id)
        if probe is None:
            raise SessionError("session_not_found", 404)
        if probe["agent_name"] != SURFACE or probe["metadata"].get("surface") != SURFACE:
            raise SessionError("not_a_concierge_session", 404)
        if probe["metadata"].get("customer_id") != customer_id:
            raise SessionError("session_client_mismatch", 403)
        return {
            "sessionId": session_id,
            "customerId": customer_id,
            "surface": SURFACE,
            "createdBy": probe["metadata"].get("created_by", ""),
            "messages": [],
            "truncated": False,
            "openTurn": None,
        }

    head = rows[0]
    if not int(head.get("session_exists") or 0):
        raise SessionError("session_not_found", 404)
    if head.get("agent_name") != SURFACE or head.get("bound_surface") != SURFACE:
        raise SessionError("not_a_concierge_session", 404)
    if head.get("bound_customer") != customer_id:
        raise SessionError("session_client_mismatch", 403)

    messages: List[Dict[str, Any]] = []
    for r in reversed([x for x in rows if x.get("id") is not None]):
        raw = r.get("metadata")
        meta = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        created = r.get("created_at")
        messages.append(
            {
                "messageId": int(r["id"]),
                "role": r.get("role"),
                "content": r.get("content"),
                "turnId": meta.get("turn_id", ""),
                "turnState": meta.get("turn_state", ""),
                "actorType": meta.get("actor_type", ""),
                "artifact": meta.get("artifact"),
                "artifactVersion": meta.get("artifact_version"),
                "createdAt": created.isoformat() if hasattr(created, "isoformat") else created,
            }
        )

    answered = {m["turnId"] for m in messages if m["role"] == ROLE_ASSISTANT}
    unanswered = [
        m for m in messages
        if m["role"] == ROLE_OPERATOR and m["turnId"] and m["turnId"] not in answered
    ]
    open_turn = None
    if unanswered:
        newest = unanswered[-1]
        open_turn = {
            "turnId": newest["turnId"],
            "messageId": newest["messageId"],
            "state": classify_open_turn(
                session_id=session_id,
                turn_id=newest["turnId"],
                active_turn=_json(head.get("active_turn")),
                lease_live=bool(head.get("lease_live")),
                running_here=running_here,
            ),
        }

    return {
        "sessionId": session_id,
        "customerId": head.get("bound_customer") or customer_id,
        "surface": SURFACE,
        "createdBy": head.get("created_by") or "",
        "messages": messages,
        "truncated": len(messages) >= bounded,
        "openTurn": open_turn,
    }


# ---------------------------------------------------------------------------
# Settling turns whose worker stopped
# ---------------------------------------------------------------------------
#
# A turn saves the operator's request, may prepare a review, and then saves its
# answer. When the worker stops in between, the request stays saved with no answer,
# and any review it prepared stays in `pellier.approvals` under its turn id. Settling
# appends an `interrupted` answer that says which of those happened. Nothing is
# deleted or rewritten: the request row is untouched, and the review keeps its own
# lifecycle.
#
# A review is the only lasting effect a Concierge turn can leave before its answer.
# It does not write `tool_audit`, `write_operations` or domain rows, and its Memory
# mirror runs only after the answer is saved.

# Taken first, in its own statement, so every later statement in the transaction reads
# a snapshot from after any other writer of this session has committed. Two readers
# settling the same turn therefore append one answer, not two.
_LOCK_SESSION_SQL = """
SELECT session_id, agent_name, metadata
  FROM pellier.conversations
 WHERE session_id = %(session_id)s
   FOR UPDATE
"""

_OPEN_TURNS_SQL = """
SELECT u.id AS message_id,
       u.metadata->>'turn_id' AS turn_id,
       c.metadata->'active_turn' AS active_turn,
       COALESCE(
           (c.metadata->'active_turn'->>'lease_until')::float8
               > extract(epoch FROM clock_timestamp())::float8,
           false
       ) AS lease_live,
       COALESCE((
           SELECT jsonb_agg(
                      jsonb_build_object(
                          'reviewId', r.id,
                          'sourceTurnId', r.source_turn_id,
                          'tool', r.tool,
                          'status', r.status,
                          'args', r.args,
                          'actionHash', r.action_hash,
                          'orderId', r.order_id,
                          'productName', p.name
                      )
                      ORDER BY r.id
                  )
             FROM pellier.approvals r
             LEFT JOIN pellier.product_catalog p
               ON p.product_id::text = r.args->>'product_id'
            WHERE r.source_turn_id = u.metadata->>'turn_id'
              AND r.customer_id = %(customer_id)s
       ), '[]'::jsonb) AS reviews
  FROM pellier.messages u
  JOIN pellier.conversations c ON c.session_id = u.session_id
 WHERE u.session_id = %(session_id)s
   AND u.role = %(role)s
   AND NOT EXISTS (
       SELECT 1 FROM pellier.messages a
        WHERE a.session_id = u.session_id
          AND a.role = %(assistant_role)s
          AND a.metadata->>'turn_id' = u.metadata->>'turn_id'
   )
 ORDER BY u.id
"""

_SETTLE_TURN_SQL = """
WITH inserted AS (
    INSERT INTO pellier.messages (session_id, role, content, metadata)
    SELECT %(session_id)s::varchar, %(assistant_role)s::varchar, %(content)s::text,
           %(metadata)s::jsonb
     WHERE NOT EXISTS (
         SELECT 1 FROM pellier.messages a
          WHERE a.session_id = %(session_id)s
            AND a.role = %(assistant_role)s
            AND a.metadata->>'turn_id' = %(turn_id)s
     )
    RETURNING id
),
released AS (
    UPDATE pellier.conversations c
       SET updated_at = now(),
           metadata = CASE
               WHEN c.metadata->'active_turn'->>'turn_id' = %(turn_id)s
               THEN c.metadata - 'active_turn'
               ELSE c.metadata
           END
      FROM inserted i
     WHERE c.session_id = %(session_id)s
    RETURNING c.session_id
)
SELECT (SELECT id FROM inserted) AS inserted_id
"""

# Keyed by session and owner rather than by turn: a session holds at most one open
# turn, and the runner renews only after its own request is saved, so the lease this
# matches is always the one it wrote.
_RENEW_LEASE_SQL = """
UPDATE pellier.conversations
   SET metadata = jsonb_set(
           metadata, '{active_turn,lease_until}',
           to_jsonb(extract(epoch FROM clock_timestamp())::float8 + %(lease_seconds)s::float8)
       )
 WHERE session_id = %(session_id)s
   AND metadata->'active_turn'->>'owner' = %(owner)s
"""

_CAUSE_COPY = {
    CAUSE_STOPPED: "This request stopped before an answer was saved.",
    CAUSE_DEADLINE: "This request ran past its time limit before an answer was saved.",
    CAUSE_ERROR: "This request hit an error before an answer was saved.",
}

_DECISION_COPY = {"approved": "confirmed", "rejected": "declined"}


def _review_refs(reviews: List[Dict[str, Any]]) -> str:
    refs = [f"#{r['reviewId']}" for r in reviews]
    label = "review" if len(refs) == 1 else "reviews"
    listed = refs[0] if len(refs) == 1 else ", ".join(refs[:-1]) + " and " + refs[-1]
    return f"{label} {listed}"


def _interruption_outcome(reviews: List[Dict[str, Any]]) -> str:
    if not reviews:
        return (
            "No review was prepared and nothing changed for this client. "
            "You can send it again."
        )
    pending = [r for r in reviews if r.get("status") == "pending"]
    decided = [r for r in reviews if r.get("status") != "pending"]
    sentences: List[str] = []
    if pending:
        sentences.append(
            f"It had already prepared {_review_refs(pending)}, awaiting a decision. "
            "Sending the request again reuses an open review for the same action "
            "instead of opening a second one."
        )
    for review in decided:
        outcome = _DECISION_COPY.get(str(review.get("status")), str(review.get("status")))
        sentences.append(
            f"It had already prepared review #{review['reviewId']}, which has since "
            f"been {outcome}. Open it before sending the request again."
        )
    return " ".join(sentences)


def interruption_artifact(
    *, customer_id: str, reviews: List[Dict[str, Any]], cause: str
) -> Dict[str, Any]:
    """The answer recorded for a turn that stopped, built only from rows that exist.

    A review the turn prepared is carried as its proposed action, so the operator can
    open it from the conversation. Its decision is read live by the review card; the
    artifact only records that this turn prepared it.
    """
    from services.operator_proposals import STATE_REVIEW_REQUIRED

    opening = _CAUSE_COPY.get(cause, _CAUSE_COPY[CAUSE_STOPPED])
    summary = f"{opening} {_interruption_outcome(reviews)}"
    actions = []
    for review in reviews:
        args = _json(review.get("args")) or {}
        actions.append({
            "tool": review.get("tool", ""),
            "state": STATE_REVIEW_REQUIRED,
            "reviewId": review.get("reviewId"),
            "customer": {"customerId": customer_id},
            "order": {"orderId": review.get("orderId")},
            "product": {
                "productId": str(args.get("product_id", "")),
                "name": review.get("productName") or "",
            },
            "material": args,
            "actionHash": review.get("actionHash") or "",
            # The capability observed when it was prepared was not saved.
            "executionCapability": {"state": "capability_state_unverified"},
            "reviewSourceTurnId": review.get("sourceTurnId") or "",
            "note": "Prepared by this request before it was interrupted.",
        })
    return {
        "summary": summary,
        "primaryLabel": "Request interrupted",
        "primaryNote": "",
        "sections": [],
        "recommendation": None,
        "investigation": [],
        "evidence": [],
        "products": [],
        "proposedActions": actions,
        "sources": [],
        "interruption": {
            "cause": cause,
            "reviewIds": [r.get("reviewId") for r in reviews],
        },
    }


def _check_binding(row: Optional[Dict[str, Any]], customer_id: str) -> None:
    if row is None:
        raise SessionError("session_not_found", 404)
    metadata = _json(row.get("metadata")) or {}
    if row.get("agent_name") != SURFACE or metadata.get("surface") != SURFACE:
        raise SessionError("not_a_concierge_session", 404)
    if metadata.get("customer_id") != customer_id:
        raise SessionError("session_client_mismatch", 403)


async def settle_abandoned_turns(
    db: Any,
    *,
    session_id: str,
    customer_id: str,
    running_here: RunningHere = _nowhere,
    cause: str = CAUSE_STOPPED,
) -> List[Dict[str, Any]]:
    """Record an ``interrupted`` answer for every unanswered turn with no live worker.

    Returns what it settled: each turn id, its new answer's message id, and the
    reviews it had prepared. A turn some worker still owns is left alone, and a turn
    answered meanwhile is skipped, because the insert re-checks under the row lock.
    """
    settled: List[Dict[str, Any]] = []
    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(_LOCK_SESSION_SQL, {"session_id": session_id})
            locked = await cur.fetchone()
            _check_binding(dict(locked) if locked else None, customer_id)

            await cur.execute(
                _OPEN_TURNS_SQL,
                {
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "role": ROLE_OPERATOR,
                    "assistant_role": ROLE_ASSISTANT,
                },
            )
            for turn in [dict(r) for r in await cur.fetchall()]:
                turn_id = turn.get("turn_id") or ""
                state = classify_open_turn(
                    session_id=session_id,
                    turn_id=turn_id,
                    active_turn=_json(turn.get("active_turn")),
                    lease_live=bool(turn.get("lease_live")),
                    running_here=running_here,
                )
                if not turn_id or state != OPEN_TURN_ABANDONED:
                    continue
                reviews = list(_json(turn.get("reviews")) or [])
                artifact = interruption_artifact(
                    customer_id=customer_id, reviews=reviews, cause=cause
                )
                metadata = {
                    "surface": SURFACE,
                    "turn_id": turn_id,
                    "actor_type": "assistant",
                    "turn_state": TURN_INTERRUPTED,
                    "artifact_version": ARTIFACT_VERSION,
                    "artifact": artifact,
                }
                await cur.execute(
                    _SETTLE_TURN_SQL,
                    {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "assistant_role": ROLE_ASSISTANT,
                        "content": artifact["summary"],
                        "metadata": json.dumps(metadata),
                    },
                )
                inserted = dict(await cur.fetchone() or {}).get("inserted_id")
                if inserted is None:
                    continue
                review_ids = [r.get("reviewId") for r in reviews]
                logger.info(
                    "Concierge turn %s in %s settled as interrupted (%s, reviews=%s)",
                    turn_id, session_id, cause, review_ids,
                )
                settled.append({
                    "turnId": turn_id,
                    "messageId": int(inserted),
                    "reviewIds": review_ids,
                })
    return settled


async def renew_lease(db: Any, *, session_id: str) -> None:
    """Extend this worker's lease on the session's running turn."""
    async with db.get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                _RENEW_LEASE_SQL,
                {
                    "session_id": session_id,
                    "owner": WORKER_ID,
                    "lease_seconds": LEASE_SECONDS,
                },
            )


# ---------------------------------------------------------------------------
# AgentCore Memory identity mapping for this surface
# ---------------------------------------------------------------------------
#
# AgentCore scopes short-term events by actor plus session, and they answer
# different questions:
#
#     actorId    the entity interacting with the agent -> the authenticated OPERATOR
#     sessionId  one conversation                      -> the Concierge session id
#
# The client is neither. Jessica is the business subject being investigated; she is
# not the person typing. Setting actorId to the open client would send the live
# USER_PREFERENCE strategy (namespace /pellier/preferences/{actorId}/) to learn
# "Jessica prefers concise drafts" from something the OPERATOR expressed — a subtle
# and ugly memory-contamination bug.
#
# So operator preference memory accrues to the operator, and client facts stay in
# Aurora where they are authoritative and current.


def memory_identity(*, operator_sub: str, session_id: str) -> Dict[str, str]:
    """The actor/session pair for this surface. No derived third identifier."""
    if not operator_sub:
        raise SessionError("operator_identity_required", 401)
    if not session_id:
        raise SessionError("session_required", 422)
    return {"actor_id": operator_sub, "session_id": session_id}


async def append_operator_memory(
    memory: Any,
    *,
    operator_sub: str,
    session_id: str,
    turns: List[Dict[str, Any]],
) -> str:
    """Mirror observable turns into AgentCore Memory for agent context.

    Returns which store took the write — ``"agentcore"``, ``"process_local"``, or
    ``""`` when it failed outright. A bool was not enough: a process-local dict
    accepts every write and dies with the worker, so "it landed" was true and
    "it persisted" was not.

    Never raises: Aurora is the authoritative transcript, so a memory failure must not
    delete or discredit a durable turn. The caller surfaces an honest limitation
    instead — "conversation memory unavailable" — rather than pretending the operator
    never spoke.

    The converse also holds and is the caller's responsibility: a successful memory
    write never substitutes for a failed Aurora write.
    """
    identity = memory_identity(operator_sub=operator_sub, session_id=session_id)
    try:
        return await memory.append_memory_event(
            actor_id=identity["actor_id"],
            session_id=identity["session_id"],
            turns=turns,
        )
    except Exception as exc:  # noqa: BLE001 - context is best-effort by design
        logger.warning(
            "AgentCore Memory unavailable for operator turn (%s/%s): %s",
            identity["actor_id"], identity["session_id"], exc,
        )
        return ""
