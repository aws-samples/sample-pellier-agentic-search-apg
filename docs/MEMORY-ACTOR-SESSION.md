# After re:Invent: live turns write Memory under the wrong actor for recall

Status: open, deferred until after the DAT416 event. No product change before
then; Lab 3 proves memory with Theo's seeded record, and the participant's own
words are a Go deeper tab.

## What happens today

The agent reads a shopper's preferences from one namespace,
`/pellier/preferences/<customer id>/`: `AgentCoreMemory.get_semantic_memories`
lists it, with no query, from `services/chat.py` (`_remembered_preferences`)
and from `app.py`. Provisioning writes Theo's first conversation with the actor
`CUST-THEO`, so the preference AgentCore Memory extracts from it lands where
the agent reads.

Both live-turn writes use the session namespace as the actor:

- Ask Pellier's streamed turn: `services/chat.py`, `_append_pellier_stm_turn`,
  actor `user-<Cognito sub>-session-<session id>`.
- `/api/agent/chat`: `routes/agent.py`, the same namespace through
  `append_session_turns`.

`append_session_turns` passes that namespace as both `actor_id` and
`session_id`. A preference a shopper states in a live turn is therefore
extracted under `/pellier/preferences/user-<sub>-session-<id>/`, which no read
looks at. Pellier cannot recall anything a shopper says in a live turn.

## Evidence

Measured on 2026-10-13 against `pelliercap1006c_PellierCap1006cMemory-6TIO8TE4gK`
(USER_PREFERENCE strategy, namespace `/pellier/preferences/{actorId}/`), with
throwaway actors whose events and records were deleted afterwards:

- Written with `append_memory_event` under a customer actor and read with
  `get_semantic_memories`, polled every 5 s: readable after 116.8 s, 138.0 s
  and 148.8 s.
- Written with `append_session_turns`, the live-turn path: the record landed
  under `/pellier/preferences/user-memprobe20261013-session-ae280f9f/` after
  134.3 s, and the customer read returned 0 records.

`python3 scripts/lab3_where_memory_lands.py` prints the customer namespace beside
Theo's session actors on any deployment.

## Why the code does this

`services/chat.py` gives no reason at the write. `append_session_turns` in
`services/agentcore_memory.py` calls its semantics frozen:
"`actor_id == session_id == session_ns` is intentional and load-bearing for
shopper isolation", and "We treat the full namespace as actor_id so anon-{sid}
and user-{uid}-session-{sid} land in separate AgentCore actors". The
requirement it cites (4.3.3) is that an anonymous session is never merged into
a signed-in user's.

That requirement does not need the session as the actor. It needs an
anonymous session and a signed-in customer to be different actors.

## The canonical pattern

`actorId` is the customer and `sessionId` is the conversation. Short-term
memory stays per session, because AgentCore scopes events by actor and
session, and extraction lands under the customer, where the agent reads. An
anonymous shopper keeps a per-session actor (`anon-<session id>`), which still
never merges into a customer.

## Proposed change

1. Write live shopper turns with `append_memory_event(actor_id=<server-resolved
   customer id>, session_id=<session namespace>)` when the turn has a verified
   customer, and keep `anon-<session id>` as both when it has none.
2. Read short-term history with the same pair (`get_memory_events`), so
   `GET /api/agent/session/<id>` keeps working.
3. Keep `get_semantic_memories` as it is: it already reads the customer.
4. Tests: a signed-in turn's events carry the customer as actor; an anonymous
   turn's do not; a preference stated in a live turn is readable by the next
   turn's read after extraction; an anonymous session's preference never
   appears under a customer.

## What to decide first

- Whether a preference stated in one session should shape the next session's
  answers without the shopper confirming it. Today nothing a shopper says in a
  live turn reaches a later turn, so turning recall on is a product change, not
  only a fix.
- Whether the operator surface's mapping (`actor_id` = operator subject) stays
  as it is; it already follows the canonical pattern.
