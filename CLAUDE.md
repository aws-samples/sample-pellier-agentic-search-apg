# Pellier - Claude Code project guidance

This repository is the application behind the flagship 100-minute governed
agentic search workshop. Read this file before editing.

## Instruction map

Claude Code guidance is intentionally layered:

1. `~/.claude/CLAUDE.md` contains account-wide defaults.
2. This file defines the repository contract and operating modes.
3. The nearest nested `CLAUDE.md` adds module-specific rules:
   - `pellier/backend/CLAUDE.md`
   - `pellier/frontend/CLAUDE.md`
   - `skills/CLAUDE.md`
4. `.claude/skills/<name>/SKILL.md` contains on-demand Claude Code workflows.
5. `skills/<name>/SKILL.md` contains Pellier runtime skills loaded into the
   Strands agents' prompts. These are application data, not Claude Code
   instructions.

Read `VOICE.md` before changing shopper-facing copy, editorial model prompts,
or runtime skills.

## Branch and source contract

- `governed` is the flagship 100-minute re:Invent workshop application.
- `main` supports the shorter one-hour builders session. Do not backport,
  merge, or simplify `governed` changes into `main` unless explicitly asked.
- The application repository is the source of truth for code and runtime
  claims.
- The sibling Workshop Studio repository
  `build-governed-agentic-ai-search-with-aurora-rds-bedrock-agentcore` is the
  source of truth for the flagship lab guide, launch wiring, and screenshots.
- Keep code and workshop claims aligned, but do not edit generated workshop
  artifacts or push the Workshop Studio repository unless explicitly asked.

## Choose the operating mode

### Participant mode

Use participant mode for any governed lab or bounded workshop task. Read the
participant's named task and prediction before proposing a change.

| Task | Allowed file | Allowed marker |
|---|---|---|
| 1A | `workshop/lab-1-rrf.sql` | `PostgreSQL RRF - fusion expression` |
| 1B | `pellier/backend/services/search_plan.py` | `Search plan - preserve requirements` |
| 2A | `pellier/backend/services/agent_tools.py` | `Stock agent - check_stock` |
| 2B | `pellier/backend/agents/stock_agent.py` | `Stock agent - definition` |
| 3A | `scripts/deploy/gateway_tool_schemas.py` | `Gateway catalogue - published tools` |
| 3A | `pellier/backend/services/agentcore_gateway.py` | `Managed catalogue - support reconcile` |
| 4A | `policies/workshop_credit_limit.cedar` | final `unless` block |
| 4B | `workshop/lab-4-rls.sql` | `Row ownership - predicate` |

Task 3B deploys and challenges the Task 3A edits; it adds no authoring region.
Lab 4's keyed absence check (`workshop/lab-4-absence.sql`) is supplied; it has
no region to author.
Use the exact START–END comments in each file; for Cedar, edit only the final
`unless` block inside its exercise boundary. This table grants access only to
the task the participant names, never every file at once.

- Ask for the prediction first. Explain the invariant, then ask one question
  that helps the participant choose. Offer one hint at a time; do not reveal
  a finished implementation in the first response.
- Read surrounding source patterns and the nearest module guidance.
- Propose only a minimal change inside the named region after the participant
  asks for an edit. Do not inspect `solutions/`, its editor aliases under
  `labs/*/solution/`, or recovery implementations.
- Do not edit tests, dependencies, deployment configuration or infrastructure.
  The named Cedar block and Gateway catalogue block are the explicit exercise
  exceptions; they do not authorize other policy or deployment edits.
- Do not read credentials, tokens, environment secrets or unrelated customer data.
- The participant runs the guide's checks, restarts, deployments and business
  actions. The coach does not run Git, install packages, deploy or approve actions.
- On failure, discuss the evidence and one hint. The participant chooses the
  documented recovery and runs it themselves; an unrun check stays incomplete.

### Maintainer mode

Use maintainer mode only when the request explicitly asks for a review,
bugfix, feature, documentation update, test work, release work, or workshop
hardening.

In maintainer mode:

- Inspect the relevant code and tests before editing.
- Preserve the four-lab participant path and terminal-first proof contract.
- Work with existing changes; do not reset or overwrite unrelated work.
- Keep solution copies byte-identical when bootstrap auto-applies them.
- Update Workshop Studio content when a participant-facing claim changes.
- Run the validation gates listed below before committing.

## Flagship workshop contract

**Title:** Build governed agentic AI search with Aurora, RDS, & Bedrock
AgentCore

The application must continue to demonstrate:

- A deterministic Router that sends each shopper request to one of three
  Strands agents: Shopping, Stock and Support.
- Nine store tools with one implementation for the local agents and the
  Gateway Lambda (`pellier/backend/services/store_tools.py`).
- Aurora PostgreSQL hybrid retrieval: full-text search and pgvector fused with
  RRF, then Cohere Rerank.
- Ten Aurora tables (`scripts/migrations/001_schema.sql`): catalog, warehouse
  stock, customers, orders, return policies, support tickets, approvals, store
  credits, the `tool_audit` ledger and retrieval receipts.
- AgentCore Runtime, Memory, Gateway, and Policy.
- Cedar authorization on every Gateway tool call: owner-only customer reads,
  a handoff that may name only the caller's own customer, and a staff-only
  store credit.
- A person approving every credit in the Operator before it is written.
- Inspectable ALLOW execution and DENY non-execution evidence.

The required participant path is four labs, each with Tasks A and B
anchored to one person, in climbing order of difficulty:

| Lab | Person | Task A | Task B |
|---|---|---|---|
| 1. Build and Measure PostgreSQL Hybrid Retrieval | Anna | Recompute the ranking | Keep the limits on the fallback |
| 2. Build a PostgreSQL-Grounded Agent | Marco | Keep not carried apart from zero stock | Connect `check_stock` to the Stock agent, alone |
| 3. Deploy and Operate Agents with Amazon Bedrock AgentCore | Theo | Publish `get_tickets` and bind it to the caller | Deploy, then challenge with the household request |
| 4. Build Governed Agent Actions with Cedar | Jessica, with Nadia | Write the $100 per-credit limit in Cedar | Write the row-ownership predicate |

`workshop/story-arc.json` and `docs/WORKSHOP-STORY-ARC.md` define the connected
task map. `pellier/backend/tests/test_workshop_marker_contract.py` checks the
eight marked regions, starter fragments, and recovery references behind the
eight tasks.
Task 3A edits a file inside `RUNTIME_SOURCE_FILES`; Task 3B must prove that the
deployed build fingerprint includes that edit. Do not move the exercise to an
unpackaged file or infer deployed completion from source inspection.

Budget the presenter introduction separately at 15 minutes. Participant guides
start their hands-on clock with Labs 1–4 at 15/15/20/25 minutes, then five for
recovery and five for closing. Reading, deployment waits, and explanation share
those allocations. These are targets pending a timed fresh-account rehearsal.

Do not reintroduce the old Act I/II/III taxonomy into flagship navigation or
documentation.

## Architecture invariants

- Aurora is the source of truth for the catalog, stock, customers, orders and
  their returns, support tickets, approvals, store credits and audit rows.
- Tool results and SQL rows are evidence. UI state alone is not proof.
- A Cedar DENY receipt and the absence of a matching `tool_audit` execution
  row are distinct, intentional evidence.
- Cognito identity travels in the signed token. Do not invent ambient identity
  or correlation fields across managed boundaries.
- Pellier has two surfaces. The Storefront (`/`) is where shoppers use Ask
  Pellier, the docked chat panel; its Builder view shows each turn's Router
  step, tool calls and "How it ranked". The Operator (`/operator`) is where
  staff investigate a case and approve or reject a credit. Code Editor, SQL
  and the lab checks remain the canonical workshop proof; the Builder view
  shows evidence but does not replace it.
- Retired surface names stay retired in every casing and separator: the
  inspection surface (Observatory, and before it Pellier Labs and Agent Trace
  with its `--at-` variable prefix). No component, module, file, route, class,
  test id, API path, CSS variable, or database object carries them. The
  exceptions are history under `docs/release-readiness/` and
  `docs/superpowers/`, the route test that proves old paths land on the
  Storefront, and this file. `pellier/backend/tests/test_surface_naming.py`
  enforces this by scanning the repository.
- Boutique is fully retired on the same terms. `VOICE.md` bans "boutique" in
  shopper copy, model prompts, runtime skills, and product descriptions.
- The Shopping and Support agents use the configured Opus profile; the Stock
  agent and the Operator's Investigator and Planner use the Sonnet profile.
  The Router makes no model call.
- Never hardcode credentials, JWTs, account IDs, endpoints, or `.env` values
  into tracked files.

## Validation gates

Run checks from the repository root unless a command changes directory.

```bash
# Backend
cd pellier/backend
python -m pytest -q

# Frontend
cd pellier/frontend
npm test -- --run
npm run type-check
npm run lint
npm run build
npm audit --omit=dev --audit-level=high

# Repository
git diff --check
find scripts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
pipx run ruff==0.16.10 check --select F821 scripts/
```

Use focused tests during iteration. Run the full backend and frontend gates
before a flagship workshop release or a broad product-pass commit.
