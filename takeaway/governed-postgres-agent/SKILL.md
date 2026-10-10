---
name: governed-postgres-agent
description: Review or build an AI agent that reads and writes business data in PostgreSQL (Aurora or RDS) against four contracts - filter before ranking, return bounded facts, bind identity and enforce ownership, approve and deduplicate writes. Use when designing agent tools over a database, reviewing a retrieval or tool-calling path, adding an agent-initiated write, or asking "what would prove this agent did the right thing?"
---

# Governed PostgreSQL agent

An agent that answers from a database and acts on it is only as trustworthy as
the contract between the agent and the database. This skill encodes four such
contracts, each with a review checklist, an implementation template and the
query that proves it holds. They come from Pellier, the retail assistant built
for the AWS re:Invent workshop *Build governed agentic AI search with Aurora,
RDS, & Bedrock AgentCore*, and they hold on Aurora PostgreSQL and Amazon RDS
for PostgreSQL alike.

The principle behind all four: **the agent proposes, PostgreSQL decides, and
the row is the proof.** A model's output is a proposal. SQL predicates,
policies, constraints and keys decide what is eligible, who may read what, and
what gets written. Evidence is a row you can query, never a chat transcript or
a UI state.

## When to use this skill

- Designing or reviewing tools an agent calls against PostgreSQL.
- Adding retrieval (full-text, vector, hybrid) that an agent will answer from.
- Giving an agent a write path: refunds, credits, work orders, limit changes.
- Deploying an agent behind a gateway where identity crosses a boundary.
- Answering "how do we know the agent did the right thing?" with a query.

## How to run a review

1. **Map the paths.** Find the retrieval SQL, the tool functions the agent can
   call, where identity enters (token, session, header) and where it reaches
   the database, and every statement that writes. List them before judging.
2. **Score each contract** with its checklist below: *holds*, *partly*, or
   *missing*. Quote the line of code or SQL that makes it hold, or the gap.
3. **Name the proof.** For every contract that holds, write the query that
   would show it (see `references/proof-queries.sql`). If no query can show
   it, it does not hold yet.
4. **Report** as one table: contract, status, evidence, the smallest change
   that closes the gap. Lead with the write path; it is where damage happens.

When implementing rather than reviewing, read the matching reference file
first and adapt its template. Keep the names of the person's own schema; the
pattern is what transfers, not Pellier's tables.

## Contract 1: filter before ranking

Hard constraints (budget, availability, exclusions, tenant, date range) are
SQL predicates applied to every candidate list *before* `LIMIT`. Similarity
and ranking decide order among eligible rows; they never decide eligibility.
A retry or a fallback may relax a preference; it may never drop a constraint.

Review checklist:

- [ ] Every candidate branch (vector, full-text, keyword) carries the same
      hard predicates, inside the query, before its `LIMIT`.
- [ ] Nothing filters after fusion or after reranking in application code.
      Post-filtering a top-k list returns short lists and silently drops rows.
- [ ] A fallback path copies the plan and changes only soft fields. Building a
      new plan object from scratch is the classic way constraints vanish.
- [ ] Fusion is arithmetic you can recompute from recorded ranks. Reciprocal
      rank fusion: `1 / (k + rank)` per list, `k = 60`, a missing rank adds
      nothing. Record the ranks so the score can be re-derived later.
- [ ] Under pgvector with a filter, an HNSW scan can come back short.
      `SET hnsw.iterative_scan = strict_order` keeps scanning until `LIMIT`
      is met, in distance order.

Reference: `references/01-filter-before-ranking.md`.

## Contract 2: return bounded facts

Each tool answers one bounded question with one query, and returns the
database's answer unchanged. Distinct states stay distinct: not found, zero,
ambiguous and success are four different answers, never collapsed into one.
An agent holds only the tools its job needs, so it cannot answer a question
from the wrong source.

Review checklist:

- [ ] The tool's result has an explicit `status` (`success`, `not_found`,
      `ambiguous`, `error`) and the agent repeats it rather than interpreting
      it. "No rows" is not "zero".
- [ ] No tool coerces an absence into a value (`not_found` into `0`,
      `NULL` into an empty string that reads as a fact).
- [ ] Row counts are bounded (`LIMIT`, a clamp on caller-supplied limits).
- [ ] The agent that answers stock questions is granted the stock tool and
      not the catalog tools; a prompt that *names* a tool does not grant it.
      Only the tool list the agent is constructed with does.
- [ ] A name lookup is a lookup (`LIKE`, trigram), not a semantic search.

Reference: `references/02-bounded-facts.md`.

## Contract 3: bind identity, enforce ownership

The caller comes from the verified token, never from the conversation. The
server sets the customer or tenant on every scoped call before it leaves the
agent runtime, overwriting whatever the model supplied. The database then
enforces ownership on its own, with row-level security bound to a principal
set per transaction, so a wrong query from any path still returns only that
principal's rows and refuses writes in anyone else's name.

Review checklist:

- [ ] Customer-scoped tool arguments (`customer_id`, `tenant_id`) are set by
      the server from the token, after the model proposes the call.
- [ ] A principal is bound per transaction (`set_config(..., true)` on a
      GUC the policy reads with `current_setting(name, true)`), so an unbound
      session matches nobody rather than everybody.
- [ ] Row-level security is enabled on every customer-owned table, with one
      permissive policy per table using the same expression for `USING` and
      `WITH CHECK`. The agent's role has no `BYPASSRLS`, is not superuser, and
      does not own the tables (or `FORCE ROW LEVEL SECURITY` is set).
- [ ] At a gateway, authorization (Cedar or equivalent) refuses a direct call
      whose customer does not match the token: policy stops a wrong call, RLS
      stops a wrong query. Both are needed.
- [ ] Remembered context (preferences, history) can shape an answer; it
      carries no authority. Only the token does.
- [ ] A model refusing to read someone else's data proves nothing. The test
      is a forged call sent through the binding: it must leave as the caller.

Reference: `references/03-bind-identity-enforce-ownership.md`.

## Contract 4: approve and deduplicate writes

No agent writes money, inventory or commitments on its own. A person approves
the exact terms; the approval row is the thing the write references. A policy
caps the write before the tool runs. A unique idempotency key derived from
the approval makes a retry find the first write instead of making a second.
Every executed call leaves one append-only audit row, and a denied call leaves
none. An ALLOW decision is not proof that anything happened; the row is.

Review checklist:

- [ ] The write function requires an approval row for these exact arguments
      (customer, amount, reason), and refuses otherwise.
- [ ] The idempotency key is derived from the approval, not minted per call,
      and is `UNIQUE` in the written table.
- [ ] Concurrency is handled in the database: lock the approval, then check
      for an existing row under the key, then write. A replay returns the
      first row; a replay with different arguments is a conflict, not a write.
- [ ] A limit is enforced at the gateway (a `forbid ... unless` that lets
      through only a present, valid amount at or under the cap) and a safety
      ceiling is enforced in the database as a `CHECK` or in the function.
- [ ] One audit row per executed call; none for a denied call; none for a
      replay. The audit table is append-only.
- [ ] The proof is three questions with three sources: *Was it permitted?*
      (policy decision) *Did it run?* (audit row) *Did it change state?*
      (the written row). An absence proof needs a positive control beside it.

Reference: `references/04-approve-and-deduplicate-writes.md`.

## Publishing tools over MCP

When the agent reaches its tools through a gateway over the Model Context
Protocol, keep one implementation of each tool for both the in-process and
the gateway path, publish schemas from one source of truth, and bind identity
before the call leaves the runtime. `references/mcp-publishing.md` shows how
Pellier does this with Amazon Bedrock AgentCore Gateway and what to keep when
the gateway is something else.

## Output of a review

```
| Contract | Status | Evidence | Smallest change |
|---|---|---|---|
| 1 Filter before ranking | partly | vector branch carries price predicate; FTS branch does not (search.py:88) | add the same WHERE to fts_branch_sql |
| 2 Bounded facts | holds | check_stock returns not_found / ambiguous / success (store_tools.py:370) | none |
| 3 Bind identity | missing | customer_id taken from model arguments (agent_tools.py:52) | overwrite from token in reconcile step; add RLS policy |
| 4 Approve + dedupe | partly | unique key present; no approval row required | require approval row in the write function |
```

Then the proof queries for every row marked *holds*.
