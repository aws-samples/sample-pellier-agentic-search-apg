# Pellier — workshop guardrails for an AI coding agent

You are helping a workshop participant during a hands-on lab. This repo is the
**Pellier agentic-search workshop**. The participant has *optionally* chosen to
direct you (instead of pasting code by hand) for **one specific exercise**. Your
job is to help them learn the production shape of wiring an agent tool — not to
hand them a finished answer or take shortcuts that skip the learning.

Read this whole file before you edit anything.

## The only task you should do here

Wire the **`floor_check`** tool body in:

```
pellier/backend/services/agent_tools.py
```

It is a Strands `@tool` whose body is currently a stub. The work lives **between
these two marker comments** (search the file for them):

```
# === CHALLENGE · Stock Keeper · floor_check: START ===
# === CHALLENGE · Stock Keeper · floor_check: END ===
```

Replace the stubbed `return json.dumps({... "error": "floor_check is in stub
state" ...})` block that sits between those markers. The `@tool` decorator, the
function signature `def floor_check(product_query: str = "") -> str:`, the
docstring, and the `# Steps:` comment are already correct — **do not change
them.** Edit only the body between START and END.

## How to figure out the implementation (do not skip this — it is the lesson)

Do **not** read or copy anything under `solutions/`. The participant is here to
learn the pattern, and `solutions/` is the answer key — using it defeats the
exercise. Instead, derive the body from what is already in the file:

1. **Read a sibling tool first.** In the *same* file, `whats_trending` and
   `price_intelligence` are fully wired and follow the identical shape every
   tool body in this codebase uses. Read one of them before writing anything.
2. The shape they share, top to bottom:
   - A **guard**: if the module-level `_db_service` global is falsy, return a
     JSON error envelope and stop.
   - A **`try`** block that lazily does `from services.business_logic import
     BusinessLogic`, builds `logic = BusinessLogic(_db_service)`, calls the
     business method, and returns `json.dumps(result, indent=2)`.
   - An **`except Exception as e`** that returns the error as JSON so a failure
     never crashes the agent turn.
3. The business method to call is **`BusinessLogic.floor_check(product_query=...)`**.
   It is defined in `pellier/backend/services/business_logic.py`. Two things
   matter about it:
   - It is **`async`** — you cannot call it directly from this sync `@tool`.
     Use the existing **`_run_async(...)`** helper (the siblings show how).
   - It dispatches on `if product_query:`. So **normalize** the incoming
     argument: strip it, and pass `None` (not `""`) when it is empty, so the
     "no query" path is reached cleanly.

That is roughly six lines. Write them yourself from the pattern above; don't
fetch them from `solutions/`.

## Hard rules — do not violate

- **Edit only** the body between the `floor_check` START/END markers in
  `agent_tools.py`. Nothing else.
- **Never** modify, read-to-copy, or `cp` from `solutions/` — especially
  `solutions/closing-marcos-gap/`. That directory is the reference answer and is
  off-limits for this exercise.
- **Do not** edit other tools, other files, the docstring, the decorator, the
  function signature, or any file under `tests/`.
- **Do not** run `git` commands, install packages, restart services, or change
  config. The backend auto-reloads on save (~1s); that is all that is needed.
- If you get stuck after a try or two, **say so plainly** and tell the
  participant to fall back to the manual paste / `cp` path in the lab guide.
  Don't thrash.

## How the participant verifies (tell them to do this, don't do it for them)

After they save, the body is checked three ways — all already covered in the lab
guide, identical to the manual path:

- Local contract test, run from `pellier/backend/`:
  ```
  pytest tests/test_solutions_parity.py::test_floor_check_builder_contract -v
  ```
- Atelier → **UNDERSTAND → Tools** strip flips from **12/13** to **13/13 shipped**.
- Boutique → Marco's **Turn 4** pill ("Is the Hadley shirt at the Brooklyn
  warehouse?") returns a real Brooklyn (`BK-01`) quantity instead of the stub
  envelope.

If a save fails, the traceback lands in `tail -f /tmp/pellier/uvicorn.log` first.
