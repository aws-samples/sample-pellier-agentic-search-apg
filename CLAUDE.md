# Pellier - Claude Code project guidance

This repository is the application behind the flagship governed agentic search
workshop. Read this file before editing. `AGENTS.md` is a link to this file, so
Codex and other coding agents that read `AGENTS.md` follow the same contract.

## Two branches: start on `governed`

The repository holds two applications for two different event formats. They
share early history but have diverged, so never copy code or instructions
between them.

| Branch | What it is | Use it for |
|---|---|---|
| `governed` (default) | The current application: the 120-minute AWS re:Invent workshop, four labs on Amazon Aurora PostgreSQL and Amazon Bedrock AgentCore (Runtime, Memory, Gateway, Policy) | The workshop, running Pellier yourself, and the patterns to reuse in your own applications |
| `main` | An older application built for a different format, the one-hour Builders' Session, with its own labs and app | That session only. It does not receive `governed`'s changes |

A fresh clone checks out `governed`. When this file and a `main` document
disagree, this file describes the code in front of you.

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

- `governed` and `main` are separate applications (see Two branches above). Do
  not backport, merge, or simplify `governed` changes into `main` unless
  explicitly asked.
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
participant's named task before proposing a change.

| Task | How | Explorer name | File it links to | Allowed marker |
|---|---|---|---|---|
| 1A | Apply by command | `labs/01-retrieve/1A-vector-search.py` | `pellier/backend/services/store_tools.py` | `Vector search - order by meaning` |
| 1B | Build | `labs/01-retrieve/1B-search-plan.py` | `pellier/backend/services/search_plan.py` | `Search plan - preserve requirements` |
| 1, Go deeper | Build | `labs/01-retrieve/go-deeper-fusion.sql` | `workshop/lab-1-fusion.sql` | `PostgreSQL RRF - fusion expression` |
| 2A | Apply by command | `labs/02-ground/2A-stock-agent.py` | `pellier/backend/agents/stock_agent.py` | `Stock agent - definition` |
| 2B | Build | `labs/02-ground/2B-check-stock.sql` | `workshop/lab-2-check-stock.sql` | `Stock check - not carried` |
| 3A | Apply by command | `labs/03-deploy/3A-1-publish-tool.py` | `scripts/deploy/gateway_tool_schemas.py` | `Gateway - published tools` |
| 3A | Apply by command | `labs/03-deploy/3A-2-bind-caller.py` | `pellier/backend/services/agentcore_gateway.py` | `Support agent - Gateway tools` |
| 3B | Build | `labs/03-deploy/3B-row-ownership.sql` | `workshop/lab-3-row-ownership.sql` | `Row ownership - predicate` |
| 4A | Apply by command | `labs/04-govern/4A-credit-limit.cedar` | `policies/credit_limit.cedar` | final `unless` block |
| 4B | Build | `labs/04-govern/4B-credit-writer.sql` | `workshop/lab-4-credit-writer.sql` | `Credit writer - privileges` |

The `labs/` names are links to the application's own files. The participant builds 1B, 2B,
3B and 4B in the marked region. 1A, 2A, 3A and 4A they apply by command after seeing the change
(`uv run scripts/lab_run.py solution --lab N --task NX`); explain the change, do not write it
for them. Task 3B writes the row-ownership predicate while the deploy runs, then challenges it.
The supplied SQL file for Lab 1's meaning distances (`workshop/lab-1-meaning.sql`, run before
Task 1A), Lab 3's live row-level security check (`scripts/lab3_row_ownership_check.py`), the
supplied SQL file for Lab 3's agent workload (`workshop/lab-3-agent-workload.sql`), Lab 4's
keyed absence check (`workshop/lab-4-absence.sql`), Task 4B's check
(`scripts/lab4_check.py --task 4B`) and the Wrap-up's reconstruction
(`workshop/wrap-up-reconstruct.sql`) are run, not authored; none has a region to build.
Participants use four verbs: Run (run something supplied and read it), Apply (1A to 4A, a
supplied change installed by command), Build (1B to 4B and Lab 1's optional fusion file) and
Prove (the check that prints `Lab NX check passed`). Do not call a file a worksheet, an
exercise or a query.
Use the exact START–END comments in each file; for Cedar, edit only the final
`unless` block inside its task boundary. This table grants access only to
the task the participant names, never every file at once.

- Do not ask for a prediction before helping.
- For an applied task (1A to 4A), explain the change as soon as asked: what the
  region does in Pellier, what the old lines did (the participant's `.bak` file
  beside the `labs/` link), what the new lines do and what the task's check proves.
- For a built task (1B to 4B), name the invariant and offer one hint at a time;
  do not reveal a finished implementation in the first response.
- Read surrounding source patterns and the nearest module guidance.
- Propose only a minimal change inside the named region after the participant
  asks for an edit. Do not inspect `solutions/`, its editor aliases under
  `labs/*/solution/`, recovery implementations, `scripts/lab_run.py diff`
  output, or `takeaway/`, which holds the finished patterns participants take
  home.
- Do not edit tests, dependencies, deployment configuration or infrastructure.
  The named Cedar block and Gateway published-tools block are the explicit task
  exceptions; they do not authorize other policy or deployment edits.
- Do not read credentials, tokens, environment secrets or unrelated customer data.
- The participant runs the guide's checks, restarts, deployments, resets and business
  actions. Resets are the Reset Lab 1 to 4, Reset the whole workshop and Repair workshop
  files tasks in Code Editor (Terminal > Run Task), `uv run scripts/lab_run.py reset
  --lab N` and `bash scripts/reset-governed-workshop.sh`. The coach explains what a reset
  restores and does not run one. It does not run Git, install packages, deploy or approve
  actions.
- Verification is the task's check command in the terminal and its pass line
  (`Lab NX check passed`). Never send the participant to Ask Pellier, the Operator
  or the AgentCore console to verify; explain what the pass line establishes and
  what it does not. The app comes after the pass line, to look at what the
  terminal proved. Say "pass line", never "pass token": a token is the signed
  Cognito JWT that Lab 3 inspects.
- On failure, discuss the evidence and one hint. The participant chooses the
  documented recovery and runs it themselves; an unrun check stays incomplete.

### Reuse mode: Pellier's patterns in your own application

Use reuse mode when someone who downloaded this repository asks how to apply
Pellier to their own agent, data or AWS account. It never applies inside a lab:
a participant working on a task stays in participant mode, where `solutions/`
and `takeaway/` stay closed.

What transfers is four contracts, not the store. The catalog, the personas and
the lab scaffolding exist to teach. At HEAD, each lab's file still holds that
lab's fault (the retry drops the shopper's requirements, the vector search
ranks nothing, the Cedar rule denies every credit), so take the finished
version from `solutions/`, never the lab file. `solutions/README.md` shows which
lab file each one replaces.

| Contract | The pattern | Read and borrow |
|---|---|---|
| Filter, then rank | The shopper's requirements become SQL predicates applied before ranking. Full-text search and pgvector rank what qualifies, Reciprocal Rank Fusion merges the two lists, and a reranker orders the top. A retry may relax a preference, never a requirement, and every search writes a retrieval receipt. | `solutions/lab-1-retrieve/retrieval/search_plan_solution.py`, `solutions/lab-1-retrieve/retrieval/store_tools_solution.py`, `pellier.retrieval_receipts` in `scripts/migrations/001_schema.sql` |
| Bounded facts | A tool answers from authoritative rows through one SQL function, and a product with no row reads as not carried, never as zero stock. | `solutions/lab-2-ground/sql/lab-2-check-stock-solution.sql`, `solutions/lab-2-ground/agents/stock_agent_solution.py` |
| Ownership | The caller's identity comes from the verified token, never from the model's arguments. Cedar permits owner-only reads at the Gateway, and row-level security under a restricted role limits what the database returns. | `pellier/backend/services/runtime_identity.py`, `solutions/lab-3-deploy/services/agentcore_gateway.py`, `scripts/deploy/render_agentcore_project.py` (the Cedar policies), `solutions/lab-3-deploy/sql/lab-3-row-ownership-solution.sql`, `pellier/backend/services/database.py` (`SET LOCAL ROLE`) |
| Write once | A person approves, Cedar caps the amount, a credit-writer role may only execute one function, and an idempotency key makes a replay apply nothing. | `pellier/backend/services/operator_review.py`, `pellier/backend/services/governed_execution.py`, `solutions/lab-4-govern/policies/credit_limit.cedar`, `solutions/lab-4-govern/sql/lab-4-credit-writer-solution.sql`, `pellier.give_store_credit` in `scripts/migrations/001_schema.sql` |

- To review an existing agent against these contracts, install the take-home
  skill in `takeaway/governed-postgres-agent` (README, Take it home). It asks the
  application team the right questions and carries the SQL that proves each
  contract holds.
- To run the whole stack in an AWS account, follow
  `docs/run-in-your-own-account.md`.
- Leave the teaching scaffolding behind: `labs/`, `workshop/`, the lab and check
  scripts under `scripts/`, the event bootstrap, the seeded catalog, and the
  demo shoppers' server-side sign-in.
- Pellier is an educational sample. Before production use, read Security and
  responsible use in `README.md`, and keep identity in the signed token,
  authorization in Cedar and the database, and proof in rows you can query.

### Maintainer mode

Use maintainer mode only when the request explicitly asks for a review,
bugfix, feature, documentation update, test work, release work, or workshop
hardening.

Work in this order:

1. Inspect the relevant code, its tests and the nearest module guidance before
   editing. Work with existing changes; do not reset or overwrite unrelated work.
2. Reproduce a defect where a participant meets it (the task's check command, the
   route or the SQL) before fixing it. Add or change a test that fails without the
   fix, watch it fail, then fix.
3. Make the smallest change that closes the defect. Pellier is a teaching app: ten
   tables, a Router and three agents, nine store tools and two surfaces. A new
   table, tool, agent, screen, flag or dependency needs a learning outcome the
   workshop cannot reach without it.
4. Run the validation gates below. Fix every failure and every new warning; an
   inline ignore needs a comment that says why.
5. Report what ran and passed, what you checked only by reading, and what you
   could not validate because it needs AWS, a deployed stack or a live event.
   Never report a check you did not run as passing.

Change these together, in one change:

| When you change | Also change | Guard |
|---|---|---|
| A marked region, task or recovery file | `workshop/story-arc.json`, the Participant mode table above, `pellier/backend/CLAUDE.md`, `scripts/reset_participant_exercises.py` and the Workshop Studio guide | `pellier/backend/tests/test_workshop_marker_contract.py`, `pellier/backend/tests/test_governed_coach_scope.py` |
| A file that bootstrap auto-applies | Its byte-identical copy under `solutions/` | `pellier/backend/tests/test_solutions_parity.py` |
| A store tool | `pellier/backend/services/store_tools.py`, `scripts/deploy/gateway_tool_schemas.py` and the Cedar policies in `scripts/deploy/render_agentcore_project.py` | `pellier/backend/tests/test_managed_gateway_tool_contract.py` |
| Shopper copy, a model prompt or a runtime skill | Read `VOICE.md` first | `pellier/backend/tests/test_copy_compliance.py`, `pellier/frontend/src/__tests__/copy_scanner.test.ts` |
| A path that this file or `README.md` names | The document | `pellier/backend/tests/test_doc_paths.py` |
| A gate in `.github/workflows/quality.yml` | Validation gates below | None; keep the two in step by hand |
| The pinned AgentCore CLI (`AGENTCORE_CLI`) | A new `scripts/deploy/agentcore-cdk-<version>/` holding its scaffold's `package.json` and a lockfile proven on a test event, and the CLI version and directory in the CDK install and audit steps of `.github/workflows/quality.yml`. Never patch a package in that lockfile on its own: the box's `npm ci` refuses a tree outside the scaffold's ranges | `pellier/backend/tests/test_agentcore_deploy_templates.py` |

Hold these in every change:

- Preserve the four-lab participant path and the terminal-first proof contract.
- Update the Workshop Studio guide when a participant-facing claim changes.
- Mock only what is slow, external or nondeterministic: Bedrock, AgentCore and
  other AWS APIs. Never point a test at workshop Aurora unless the test requires
  live integration and the operator has approved it.
- Keep evidence honest. An ALLOW does not prove a tool ran, and UI state does not
  prove a row changed; tool results and SQL rows do.
- Keep credentials, JWTs, account IDs, ARNs, endpoints and `.env` values out of
  tracked files, evidence records included; write `<account>` instead.
  `pellier/backend/tests/test_no_environment_identifiers.py` scans every tracked
  text file for account IDs.
- Do not commit or push unless asked, and never rewrite published history.

## Flagship workshop contract

**Title:** Build governed agentic AI search with Aurora, RDS, & Bedrock
AgentCore

The application must continue to demonstrate:

- A deterministic Router that sends each shopper request to one of three
  Strands agents: Catalog, Stock and Support.
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
| 1. Build and measure PostgreSQL hybrid retrieval | Anna | Search by what she means | Keep her requirements on the retry |
| 2. Build a PostgreSQL-grounded agent | Marco | Connect `check_stock` to the Stock agent, alone | Keep "not carried" distinct from sold out |
| 3. Deploy agents and bind the caller with Amazon Bedrock AgentCore | Theo | Publish `get_tickets` and bind it to the caller | Deploy, write the ownership rule, then challenge it |
| 4. Govern agent actions with Cedar policies and PostgreSQL privileges | Jessica, with Nadia | Cap the credit at $100 in Cedar | Let the credit-writer role write only through the function |

`workshop/story-arc.json` and `docs/WORKSHOP-STORY-ARC.md` define the connected
task map. `pellier/backend/tests/test_workshop_marker_contract.py` checks the
nine marked regions, starter fragments, and recovery references behind the
eight tasks. Every task runs in the terminal first: See it fail is a command,
Apply installs a supplied change, Build is the region, Prove it is one check
and one pass line, and the app comes after the pass line.
Task 3A edits a file inside `RUNTIME_SOURCE_FILES`; Task 3B must prove that the
deployed build fingerprint includes that edit. Do not move the task to an
unpackaged file or infer deployed completion from source inspection.

The schedule is 120 minutes. The opening block takes 20: the talk, then Getting started (about 3
minutes; early arrivals may do it before). Then Lab 1 takes 15, Lab 2 15, Before Lab 3 (the one
scheduled catch-up, then the move from local agents to AgentCore) 5, Lab 3 25, Lab 4 30 and the
Wrap-up 10. Reading, deployment waits, and explanation share those allocations. These are targets
pending a timed fresh-account rehearsal.

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
  exceptions are the route test that proves old paths land on the
  Storefront (`pellier/frontend/src/App.routes.test.tsx`), the clean-up of
  legacy browser keys in `pellier/frontend/src/contexts/PersonaContext.tsx`,
  `CLAUDE.md` and `AGENTS.md`, the guard itself, and history: `docs/superpowers/`
  and the gitignored release-readiness records under docs, which a clone lacks.
  `pellier/backend/tests/test_surface_naming.py` enforces this by scanning
  every tracked text file, case-insensitively and across `-`, `_` and space.
- Boutique is fully retired on the same terms. `VOICE.md` bans "boutique" in
  shopper copy, model prompts, runtime skills, and product descriptions.
- The Catalog and Support agents use the configured Opus profile; the Stock
  agent and the Operator's Investigator and Advisor use the Sonnet profile.
  The Router makes no model call.
- Never hardcode credentials, JWTs, account IDs, endpoints, or `.env` values
  into tracked files.

## Validation gates

CI runs `.github/workflows/quality.yml` on every push to `governed`, and that
workflow is the canonical list. These are its local equivalents. Run them from the
repository root unless a command changes directory.

```bash
# Backend, on Python 3.14 as in CI. The PostgreSQL-backed tests skip without a local
# PostgreSQL 18 with pgvector; the workflow's backend-postgres job installs one and
# sets PELLIER_REQUIRE_POSTGRES=1 so they fail there instead of skipping.
cd pellier/backend
python -m pytest -q
pipx run --spec pip-audit==2.10.1 pip-audit --disable-pip --require-hashes -r requirements.lock

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
pipx run ruff==0.16.10 check --select F821 scripts/ deploy/
pipx run cfn-lint==1.59.0 deploy/own-account/templates/*.yml
```

CI also audits the AgentCore Runtime lock (`pellier/backend/uv.lock`), installs the
AgentCore CDK lock (`scripts/deploy/agentcore-cdk-0.29.0/package-lock.json`) into a
scaffold from the pinned CLI with `npm ci` as a box does and audits it through
`scripts/deploy/npm_audit_gate.py`, with each accepted advisory's reason and exit
condition beside it, runs the browser specs against a stand-in API, and runs the
PostgreSQL-backed tests together with `scripts/test_takeaway_package.py`.

Use focused tests while iterating. Before any commit that will be pushed, run the
whole backend suite, not only the tests you touched: the repository-wide scans for
account IDs, retired names, document paths and whitespace live there and run nowhere
else before CI. Run the full backend and frontend gates before a workshop release.
