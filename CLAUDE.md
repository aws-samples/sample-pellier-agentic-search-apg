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
5. `skills/<name>/SKILL.md` contains Pellier runtime skills loaded into
   Strands specialists per shopper turn. These are application data, not
   Claude Code instructions.

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

Use participant mode when the request names Lab 1, Inventory Agent,
`check_inventory`, the workshop markers, or asks Claude Code to complete the
guided build.

In participant mode:

- Edit only the named marker region in
  `pellier/backend/agents/inventory_agent.py` or
  `pellier/backend/services/agent_tools.py`.
- Read the backend `CLAUDE.md` for the exact exercise contract.
- Never inspect or copy from `solutions/`.
- Do not edit tests, config, other tools, or other files.
- Do not run git commands, install packages, or restart services.
- Stop after one failed attempt and direct the participant to the lab guide's
  fallback lane.

These limits protect the learning objective. Do not relax them because a
broader edit would be faster.

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

- A Strands SDK dispatcher routing shoppers to specialist agents.
- Aurora PostgreSQL hybrid retrieval using full-text search and pgvector.
- Cohere Rerank relevance ranking.
- Aurora-backed inventory, orders, customer records, returns, and a queryable
  JSONB audit ledger.
- AgentCore Runtime, Memory, Gateway, and Policy.
- Cedar authorization on sensitive tool actions.
- Inspectable ALLOW execution and DENY non-execution evidence.

The required participant path is four labs, each with two bounded builds
anchored to one person, in climbing order of difficulty:

| Lab | Person | a | b |
|---|---|---|---|
| 1. Build a PostgreSQL-Grounded Agent | Marco | Inventory Agent definition | `check_inventory` body |
| 2. Build and Measure PostgreSQL Hybrid Retrieval | Anna | RRF fusion expression | the live candidate budget |
| 3. Deploy and Operate the Managed Agent Path | Theo | publish the Gateway tool | reconcile the Runtime catalogue, then deploy |
| 4. Govern and Prove Agent Actions | Jessica | the Cedar identity rule | the keyed absence query |

`tests/test_workshop_marker_contract.py` is the authoritative inventory of
those builds: their marker regions, starter fragments, and reference
solutions. Adding, moving, or renaming a build means changing that file, which
is the point. Lab 3b edits a file inside `RUNTIME_SOURCE_FILES`, so completing
it changes the deployed build fingerprint; that is the lab's proof and must not
be broken by moving the exercise to an unpackaged file.

Budgets: 5 minutes orientation, 20 for Lab 1, 25 for Lab 2, 25 for Lab 3,
20 for Lab 4, and 5 to close. Reading, deployment waits, and ten minutes of
recovery are included in these allocations. Rehearse the complete path before release.

Do not reintroduce the old Act I/II/III taxonomy into flagship navigation or
documentation.

## Architecture invariants

- Aurora is the source of truth for catalog, inventory, customer, order,
  return, and audit data.
- Tool results and SQL rows are evidence. UI state alone is not proof.
- A Cedar DENY receipt and the absence of a matching `tool_audit` execution
  row are distinct, intentional evidence.
- Cognito identity travels in the signed token. Do not invent ambient identity
  or correlation fields across managed boundaries.
- Pellier is shopper-facing, Pellier Observatory is an assisted inspection
  surface, and Code Editor plus SQL/curl remain canonical workshop proof.
  Participant-facing chrome and public routes use "Pellier", "Pellier
  Observatory", `/`, and `/observatory`.
- **One name for the inspection surface: Observatory.** It is the display name,
  the route (`/observatory`), the API prefix (`/api/observatory`), the source
  directories (`src/observatory/`, `routes/observatory.py`), the CSS and
  `data-testid` namespace (`observatory-*`), the span table
  (`pellier.observatory_spans`), and the CSS custom-property prefix
  (`--obs-*`). Both former names are fully retired in every casing and
  separator, including `Agent Trace` and its `--at-` variable prefix, and
  `Pellier Labs`. No component, module, file, route, class, test id, API path,
  CSS variable, or database object carries either. The only permitted
  exceptions are the legacy-path redirects in `App.tsx` and the tests that
  assert them, which must name the old paths to do their job, plus the one-time
  `ALTER TABLE` in migration 002 that converges an existing cluster.
  `tests/test_surface_naming.py` enforces this by scanning the repository.
- Boutique is fully retired on the same terms. "boutique" survives only as an
  ordinary noun in shopper copy and model prompts, which `VOICE.md` sanctions.
- Editorial specialists use the configured Opus profile when available;
  reporting and routing specialists use the configured Sonnet profile.
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
```

Use focused tests during iteration. Run the full backend and frontend gates
before a flagship workshop release or a broad product-pass commit.
