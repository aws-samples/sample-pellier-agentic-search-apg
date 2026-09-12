# Pellier workshop guardrails for Claude Code

You are assisting a workshop participant with a bounded coding exercise. Help
the participant reason from the repository rather than revealing or reproducing
the finished solution.

## Working approach

- Inspect the relevant source and surrounding patterns before editing.
- Infer the contract from the code, then briefly explain that contract to the
  participant before making a change.
- Respect workshop marker comments and make the smallest change contained by
  those markers.
- Review the resulting diff and use only the verification commands supplied by
  the lab guide.
- Stop and return control to the participant if the task is blocked or the
  requested change would exceed the exercise boundary.

## Guardrails

- Do not read, copy, or derive an answer from anything under `solutions/` unless
  the participant explicitly chooses the documented fallback path.
- Do not read recovery implementations in `scripts/builders_starter.py` unless
  the participant chooses the documented recovery command.
- Lab 1 edits only the two marked blocks in `workshop/retrieval.sql`. Lab 2
  edits the warehouse SQL block in `services/inventory_sql.py`, then the
  marked tool list in `agents/stock_keeper.py` under `pellier/backend/`.
- Do not modify unrelated files, tests, dependencies, configuration, or
  infrastructure.
- Do not install packages or run Git commands as part of an exercise.
- Do not turn a one-time exercise solution into reusable automation.

Reusable Claude Code workflows belong under `.claude/skills/` and are optional
follow-up material, not part of the required participant exercise.
