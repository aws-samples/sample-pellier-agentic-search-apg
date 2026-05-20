# Skills Authoring Guide

This directory (`/skills`) is the canonical source for workshop skills.

## What a skill is

- A skill is markdown injected into a specialist agent's system prompt.
- A skill is **not** a tool and **not** a database record.
- The skill router loads skills from each skill's `description` contract.

## Canonical path

- Edit: `skills/<skill-name>/SKILL.md`
- Runtime loader: `pellier/backend/skills/loader.py` (default points to `/skills`).
- Optional override: `PELLIER_SKILLS_DIR=/custom/path`.

## Required frontmatter fields

- `name`: must match folder slug.
- `description`: activation contract seen by the router.
- `version`: free-form string, defaults to `1.0`.

Optional:

- `display_name`: human-friendly label in UI attribution.
- other fields are preserved in `frontmatter` but not required.

## Authoring structure (recommended)

1. `When to apply`
2. `Voice and curation rules`
3. `Anchor examples (only if retrieved)`
4. `Guardrails`

Keep guidance concrete and retrieval-grounded. Do not hardcode behavior that conflicts with tool outputs.

## Validation checklist

1. Restart backend (or rely on `--reload`).
2. Confirm boot log shows loaded skills and token counts.
3. Hit `POST /api/atelier/skills/route` with a representative query.
4. Verify Boutique/Atelier "Under the hood" shows expected loaded skill(s).
5. Sync the Atelier fixture after skill edits:
   - `python3 scripts/sync_skills_fixture.py`

## Contract checks (agents + tools)

Use these before shipping skill/router changes to catch drift in agent factories
and `@tool` wrappers:

- `pytest pellier/backend/tests/test_factory_shape.py -v`
- `pytest pellier/backend/tests/test_agent_tools.py -v`

## Mental model

- **Intent router** chooses specialist class (`search`, `pricing`, `inventory`, ...).
- **Skill router** chooses prompt overlays (`the-packing-list`, ...).
- **Tools** execute retrieval/write operations and produce auditable traces.
