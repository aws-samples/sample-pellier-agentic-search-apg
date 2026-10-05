# Pellier runtime skill guidance

Files under this directory are runtime prompt overlays for Pellier's three
Strands agents. They are not Claude Code skills.

Claude Code project skills live under:

```text
.claude/skills/<skill-name>/SKILL.md
```

Pellier runtime skills live under:

```text
skills/<skill-name>/SKILL.md
```

## Runtime skill contract

- `name` is the stable machine identifier.
- `description` is what the agent reads in on-demand mode to decide whether
  to open the skill. Keep it specific.
- `persona`, `display_name`, and `version` are Pellier-specific metadata.
- Each agent carries a fixed set of skills (`pellier/backend/skills/assignments.py`),
  injected into its system prompt with no model call. The optional on-demand
  mode lists only names and descriptions and lets the agent open a body with
  its local loader tool.
- Skills are procedural memory: checked-in skills plus MCP schemas. They say
  how to answer, never what is true. No prices, no stock, no customer facts.

## Editing rules

- Read `../VOICE.md` first.
- Keep the activation description specific enough to avoid over-triggering.
- Make the body concise, imperative, and additive to the base prompt.
- Do not put product facts, prices, inventory, policy decisions, or customer
  history in a skill unless the runtime will retrieve and verify them.
- Label examples as conditional and require the item to be present in tool
  results.
- Never grant a tool or authorization capability through prose.
- Keep care, proof, and handoff claims tied to tool results.
- Avoid copying the same rule into multiple skills. Put shared voice rules in
  `VOICE.md` and shared runtime behavior in the appropriate base prompt.

After editing, restart the backend so the boot-time registry reloads, then
run `tests/test_skill_assignments.py` and `tests/test_product_name_references.py`
and replay the relevant Pellier turn.
