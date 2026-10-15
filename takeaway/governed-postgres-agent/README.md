# governed-postgres-agent: how a DBA reviews an agent

An Agent Skill for the review a database engineer brings to an application
team's AI agent pull request, when the agent reads or writes business data in
PostgreSQL. It encodes the four contracts from the AWS re:Invent workshop
*Build governed agentic AI search with Aurora, RDS, & Bedrock AgentCore*
(DAT416): for each, the questions to ask the team, a checklist, templates
lifted from the workshop's source, and the SQL that proves the contract holds.
It starts where a DBA starts, with the agent's workload by role from
`pg_stat_statements`.

The skill is plain markdown in the open Agent Skills format: a `SKILL.md`
with frontmatter, and a `references/` folder the agent reads on demand.

## Install

**Claude Code**, for every project:

```bash
mkdir -p ~/.claude/skills
cp -r governed-postgres-agent ~/.claude/skills/
```

For one project, copy it to `.claude/skills/` in that repository instead.
Then, in Claude Code: `/governed-postgres-agent review this agent's pull request like a DBA`.

**Kiro** and other agents that read skills: copy the folder to the location
your agent loads skills from, or point it at `SKILL.md` as a steering file.

## Try it on Pellier first

From the workshop repository, with the coach already configured:

```
/governed-postgres-agent review give_store_credit in pellier/backend/services/store_tools.py
against contract 4 the way a DBA would: the questions to ask, the gaps, and the proof queries.
```

Then point it at the next agent pull request your team sends you.

## What is in it

| File | What it holds |
|---|---|
| `SKILL.md` | The agent in database terms, how to run a review, the four contracts with the questions to ask and checklists, the review you hand back |
| `references/01-filter-before-ranking.md` | Predicates before `LIMIT` on every branch, recomputable RRF, a fallback that keeps constraints, pgvector iterative scan |
| `references/02-bounded-facts.md` | The `success` / `not_found` / `ambiguous` result contract, pass-through, the grant is the tool list |
| `references/03-bind-identity-enforce-ownership.md` | Server-side binding, a principal per transaction, row-level security and its preconditions, policy at the gateway |
| `references/04-approve-and-deduplicate-writes.md` | Approval rows, derived idempotency keys, the write function, the Cedar limit, the append-only audit ledger |
| `references/proof-queries.sql` | The agent's workload by role, then one query per claim for all four contracts, ending with a write rebuilt from request to row |
| `references/mcp-publishing.md` | How Pellier publishes tools over MCP through AgentCore Gateway, and what to keep elsewhere |

The SQL runs on Aurora PostgreSQL and Amazon RDS for PostgreSQL alike. The RDS
Data API in `references/mcp-publishing.md` is Aurora-only; on RDS for
PostgreSQL the tool Lambda connects with a driver instead, through RDS Proxy.
The templates use short names (`catalog`, `app_agent`,
`app.principal_username`); Pellier's are `pellier.product_catalog`,
`pellier_agent` and `pellier.principal_username`.
