# Pellier - Claude Code project guidance

This repository is the application behind the flagship governed agentic search
workshop. Read this file before editing. `AGENTS.md` is a link to this file, so
Codex and other coding agents that read `AGENTS.md` follow the same contract.

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

| Task | How | Explorer name | File it links to | Allowed marker |
|---|---|---|---|---|
| 1A | Applied by command | `labs/01-retrieve/1A-vector-branch.py` | `pellier/backend/services/store_tools.py` | `Vector branch - order by meaning` |
| 1B | Written | `labs/01-retrieve/1B-search-plan.py` | `pellier/backend/services/search_plan.py` | `Search plan - preserve requirements` |
| 1, Go deeper | Written | `labs/01-retrieve/go-deeper-fusion.sql` | `workshop/lab-1-fusion.sql` | `PostgreSQL RRF - fusion expression` |
| 2A | Applied by command | `labs/02-ground/2A-stock-agent.py` | `pellier/backend/agents/stock_agent.py` | `Stock agent - definition` |
| 2B | Written | `labs/02-ground/2B-check-stock.sql` | `workshop/lab-2-check-stock.sql` | `Stock check - not carried` |
| 3A | Applied by command | `labs/03-deploy/3A-1-publish-tool.py` | `scripts/deploy/gateway_tool_schemas.py` | `Gateway catalogue - published tools` |
| 3A | Applied by command | `labs/03-deploy/3A-2-bind-caller.py` | `pellier/backend/services/agentcore_gateway.py` | `Support agent - Gateway tools` |
| 3B | Written | `labs/03-deploy/3B-row-ownership.sql` | `workshop/lab-3-row-ownership.sql` | `Row ownership - predicate` |
| 4A | Written | `labs/04-govern/4A-credit-policy.cedar` | `policies/workshop_credit_limit.cedar` | final `unless` block |
| 4B | Written | `labs/04-govern/4B-credit-writer.sql` | `workshop/lab-4-credit-writer.sql` | `Credit writer - privileges` |

The `labs/` names are links to the application's own files. The participant writes 1B, 2B,
3B, 4A and 4B in the marked region. 1A, 2A and 3A they apply by command after seeing the change
(`python3 scripts/lab_run.py solution --lab N --task NX`); explain the change, do not write it
for them. Task 3B writes the row-ownership predicate while the deploy runs, then challenges it.
Lab 1's meaning query (`workshop/lab-1-meaning.sql`, run before Task 1A), Lab 3's
live row-level security check (`scripts/lab3_row_ownership_check.py`), Lab 3's workload
query (`workshop/lab-3-agent-workload.sql`), Lab 4's keyed absence check
(`workshop/lab-4-absence.sql`), Task 4B's check (`scripts/lab4_check.py --task 4B`) and the
Wrap-up's reconstruction (`workshop/wrap-up-reconstruct.sql`) are supplied; none has a
region to author. A SQL file a participant edits and runs is an exercise; one they only run is
a query.
Use the exact START–END comments in each file; for Cedar, edit only the final
`unless` block inside its exercise boundary. This table grants access only to
the task the participant names, never every file at once.

- Ask for the prediction first. Name the invariant, then ask one question
  that helps the participant choose. Offer one hint at a time; do not reveal
  a finished implementation in the first response.
- Read surrounding source patterns and the nearest module guidance.
- Propose only a minimal change inside the named region after the participant
  asks for an edit. Do not inspect `solutions/`, its editor aliases under
  `labs/*/solution/`, recovery implementations, `scripts/lab_run.py diff`
  output, or `takeaway/`, which holds the finished patterns participants take
  home.
- Do not edit tests, dependencies, deployment configuration or infrastructure.
  The named Cedar block and Gateway catalogue block are the explicit exercise
  exceptions; they do not authorize other policy or deployment edits.
- Do not read credentials, tokens, environment secrets or unrelated customer data.
- The participant runs the guide's checks, restarts, deployments, resets and business
  actions. Resets are the Reset Lab 1 to 4, Reset the whole workshop and Repair workshop
  files tasks in Code Editor (Terminal > Run Task), `python3 scripts/lab_run.py reset
  --lab N` and `bash scripts/reset-governed-workshop.sh`. The coach explains what a reset
  restores and does not run one. It does not run Git, install packages, deploy or approve
  actions.
- Verification is the task's check command in the terminal and its pass token.
  Never send the participant to Ask Pellier, the Operator or the AgentCore
  console to verify; explain what the token establishes and what it does not.
  The app comes after the token, to look at what the terminal proved.
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
|---|---|---|---|---|
| 1. Build and Measure PostgreSQL Hybrid Retrieval | Anna | Search by what she means | Keep her limits on the retry |
| 2. Build a PostgreSQL-Grounded Agent | Marco | Connect `check_stock` to the Stock agent, alone | Keep "not carried" distinct from sold out |
| 3. Deploy Agents and Bind the Caller with Amazon Bedrock AgentCore | Theo | Publish `get_tickets` and bind it to the caller | Deploy, write the ownership rule, then challenge it |
| 4. Govern Agent Actions with Cedar Policies and PostgreSQL Privileges | Jessica, with Nadia | Cap the credit at $100 in Cedar | Let the money role write only through the function |

`workshop/story-arc.json` and `docs/WORKSHOP-STORY-ARC.md` define the connected
task map. `pellier/backend/tests/test_workshop_marker_contract.py` checks the
nine marked regions, starter fragments, and recovery references behind the
eight tasks. Every task runs in the terminal first: See it fail is a command,
Build is the region, Prove it is one check and one pass token, and the app
comes after the token.
Task 3A edits a file inside `RUNTIME_SOURCE_FILES`; Task 3B must prove that the
deployed build fingerprint includes that edit. Do not move the exercise to an
unpackaged file or infer deployed completion from source inspection.

The schedule is 120 minutes. Getting started happens as people arrive, before the talk.
Then the talk takes 20 minutes, Lab 1 15, Lab 2 15, Before Lab 3 (the one scheduled catch-up,
then the move from local agents to AgentCore) 5, Lab 3 25, Lab 4 30 and the Wrap-up 10. Reading,
deployment waits, and explanation share those allocations. These are targets pending a timed
fresh-account rehearsal.

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
