# Skills authoring guide

This directory (`skills/`) is the source of Pellier's five runtime skills.

## What a skill is

- A skill is markdown added to an agent's system prompt: how to answer, never
  what is true. Prices, stock and customer facts come from the store tools.
- A skill is **not** a tool and **not** a database record.
- Each agent carries a fixed set, with no model call
  (`pellier/backend/skills/assignments.py`): the Shopping agent
  `the-gift-table`, `the-makers-shelf`, `the-packing-list` and
  `the-proof-counter`; the Stock agent `the-proof-counter`; the Support agent
  `the-care-card` and `the-proof-counter`.
- With the Builder view on, "Agent loads its skills" in the Ask Pellier panel
  switches an in-process agent to on-demand mode: it sees only each skill's
  name and description and opens a body with a local loader tool. The managed
  rail always uses the fixed set.

## Canonical path

- Edit: `skills/<skill-name>/SKILL.md`
- Runtime loader: `pellier/backend/skills/loader.py` (defaults to this directory).
- Optional override: `PELLIER_SKILLS_DIR=/custom/path`.

## Frontmatter

- `name`: must match the folder name.
- `description`: what the agent reads in on-demand mode to decide whether to
  open the skill. Keep it specific.
- `version`: free-form string, defaults to `1.0`.
- `display_name` (optional): the label the Builder view shows.

## Check a change

1. Restart the backend so the registry reloads.
2. Run the contract checks from `pellier/backend`:
   - `pytest tests/test_skill_assignments.py tests/test_product_name_references.py`
   - `pytest tests/test_factory_shape.py tests/test_agent_tools.py`
3. Ask the turn the skill is for, with the Builder view on, and read which
   skills the Router step lists.
