# Pellier backend guidance

This directory owns FastAPI, Strands specialists, tools, retrieval, memory,
AgentCore adapters, policy integration, SSE streaming, and backend tests.

Read the repository `CLAUDE.md` first and choose participant or maintainer
mode before editing.

## Participant mode: Lab 1 only

The participant may name one of two build sites. Work only inside the named
marker region.

### Inventory Agent definition

File:

```text
agents/inventory_agent.py
```

Markers:

```text
# === WORKSHOP · Inventory Agent · definition: START ===
# === WORKSHOP · Inventory Agent · definition: END ===
```

Prompt and model configuration are supplied. Task 1B authors only the permitted
inventory reads and clears the stub after that grant is ready. Derive the tool
choice from the customer's required facts and the imported tool contracts.
Task 1A implements the `check_inventory` body before Task 1B wires it into a turn.

Do not add temperature. The active Sonnet profile rejects that deprecated
argument.

### `check_inventory` body

File:

```text
services/agent_tools.py
```

Markers:

```text
# === WORKSHOP · Inventory Agent · check_inventory: START ===
# === WORKSHOP · Inventory Agent · check_inventory: END ===
```

Derive the implementation from `get_trending_products` or `get_price_analysis` in
the same file:

1. Return a JSON error envelope when `_db_service` is unavailable.
2. Lazily import `BusinessLogic`.
3. Construct it with `_db_service`.
4. Normalize `product_query` with `.strip()` and pass `None` when empty.
5. Call `BusinessLogic.check_inventory(...)` through `_run_async(...)`.
6. Return `json.dumps(result, indent=2)`.
7. Catch `Exception` and return a JSON error envelope.

Do not change the decorator, signature, docstring, comments, imports, tests,
or any code outside the markers. Never inspect `solutions/`.

The participant verifies through `/api/observatory/build-state`, Pellier Observatory's Tool
Registry, and Marco's Brooklyn warehouse turn. Do not run tests or git for
them.

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
