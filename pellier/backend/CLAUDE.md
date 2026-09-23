# Pellier backend guidance

This directory owns FastAPI, Strands specialists, tools, retrieval, memory,
AgentCore adapters, policy integration, SSE streaming, and backend tests.

Read the repository `CLAUDE.md` first and choose participant or maintainer
mode before editing.

## Participant mode: governed Labs 1–4

The root guidance lists all nine permitted regions. This module contains four:

| Task | File | Marker |
|---|---|---|
| 1A | `services/agent_tools.py` | `Inventory Agent · check_inventory` |
| 1B | `agents/inventory_agent.py` | `Inventory Agent · definition` |
| 2B | `services/search_plan.py` | `Search plan · preserve requirements` |
| 3A | `services/agentcore_gateway.py` | `Managed catalogue · support reconcile` |

For SQL, Cedar and Gateway publication tasks, use the root map and the guide.
Those tasks are not forbidden because their files are outside this module.

Start with the participant's prediction and named invariant. Read surrounding
patterns, ask one question and give one hint at a time. Wait for their request
before proposing an edit inside the selected START–END markers. Do not change
signatures, decorators, imports or other regions. Never inspect `solutions/`.
The participant runs verification; explain what the result establishes and
what it does not. A successful local plan check is not managed execution proof.

Model and prompt configuration are supplied in Task 1B. Do not add temperature;
the configured profile does not support that argument. Task 3A's owned and
foreign probes test Cedar separately from the managed caller binding.

## Maintainer architecture

- `app.py` owns FastAPI startup, route registration, smoke mode, and SPA
  serving.
- `services/chat.py` owns the streamed turn contract. Preserve SSE ordering,
  terminal events, cumulative versus delta semantics, and error taxonomy.
- `agents/` owns specialist construction and tool grants.
- `services/agent_tools.py` owns deterministic business-tool boundaries.
- `skills/` loads root `skills/*/SKILL.md` files into specialist prompts.
- `routes/observatory.py` serves evidence read models. It must not
  fabricate readiness or call managed services merely to render a page.
- `agentcore_runtime.py`, `services/agentcore_*`, and `services/managed_policy.py`
  own managed-boundary behavior.

## Backend rules

- Read `../../VOICE.md` before editing model prompts or shopper-visible copy.
- Keep centralized shopper copy in `pellier_copy.py` when practical.
- Preserve JSON/SSE machine fields while improving human-readable messages.
- Distinguish Cedar policy denial, authentication failure, service
  unavailability, and request validation failures.
- Do not call a bare 401 a Cedar DENY.
- Use parameterized SQL and explicit transactions for write paths.
- Keep ALLOW execution rows and DENY absence proof auditable.
- Do not add model parameters unsupported by the configured Bedrock profile.
- If an auto-applied backend file changes, update its solution twin and run
  `tests/test_solutions_parity.py`.

## Backend validation

From `pellier/backend`:

```bash
python -m pytest -q
python tests/test_copy_compliance.py
```

`python -m pytest -q` needs no environment setup. `tests/conftest.py` pins a
hermetic environment: it sets `PELLIER_DISABLE_DOTENV=1` so `Settings` ignores
any real `.env`, and supplies `DB_*` placeholders so importing `config` cannot
raise. Do not reintroduce a `DB_HOST=... python -m pytest` prefix, and do not
remove those lines — without the dotenv guard, tests asserting a variable is
absent read a developer's live `.env` and fail only on boxes that have been
through bootstrap; without the placeholders, every module touching settings
reports a collection error.

Never point a test at workshop Aurora unless the test explicitly requires
live integration and the operator has approved it.
