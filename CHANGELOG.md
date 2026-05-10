# Changelog: DAT406 (2025) → DAT4XX (2026)

## Summary

The workshop was restructured so participants edit the real Pellier application instead of standalone lab scripts. TODOs live directly in the backend files. The app ships in "legacy mode" and progressively gains intelligence as participants complete each module.

---

## Architecture Change

**Before (2025):** Participants ran standalone Python scripts in `labs/` that reimplemented functionality already in the app. Two parallel codebases, two DB layers (`labs/shared/db.py` vs `services/database.py`), no connection between lab work and the running storefront.

**After (2026):** Participants edit files in `pellier/backend/`, restart the server, and watch the storefront evolve. One codebase, one DB layer, immediate visual feedback. The app has graceful fallbacks so it runs at every stage — keyword-only search before Module 2, "orchestrator not ready" message before Module 3b, etc.

---

## What Moved to `archive/`

| Directory/File                    | Reason                                                      |
| --------------------------------- | ----------------------------------------------------------- |
| `labs/` (entire directory)        | Replaced by in-app TODOs in `pellier/backend/`        |
| `notebooks/`                      | Old Jupyter notebooks from 2025                             |
| `docs/`                           | Single technical deep-dive doc                              |
| `tmp/`                            | One-off data fix scripts                                    |
| `deployment/cfn/`                 | CFN templates live in `lab-content/assets/` (separate repo) |
| `AMAZON_Q_PROMPTS.md`             | Old Amazon Q prompts for 2025 structure                     |
| `MIGRATION_GUIDE.md`              | Superseded by this changelog                                |
| `KIRO_SESSION_PROMPT.md`          | Old session prompt for migration                            |
| `pellier/LAB2_GUIDE.md`     | Old lab guide from 2025                                     |
| `pellier/backend/test_*.py` | Dev test scripts, not part of workshop                      |
| `data/amazon-products-sample.csv` | Replaced by `premium-products-with-embeddings.csv`          |

`archive/` is gitignored.

---

## New: `solutions/` Directory

Drop-in replacement files for participants short on time. Each solution is the complete working version of the file being edited. Structure mirrors `pellier/backend/`:

```
solutions/
├── module2/services/       hybrid_search.py, business_logic.py
├── module3a/services/      agent_tools.py
├── module3b/agents/        recommendation_agent.py, orchestrator.py
├── module4/services/       agentcore_memory.py, agentcore_gateway.py, agentcore_policy.py
└── README.md               Copy commands for each module
```

Usage: `cp solutions/module2/services/hybrid_search.py pellier/backend/services/hybrid_search.py`

---

## TODO Files (what participants implement)

| Module | File                             | TODO                                                  | Fallback                                       |
| ------ | -------------------------------- | ----------------------------------------------------- | ---------------------------------------------- |
| 2      | `services/hybrid_search.py`      | `_vector_search()` — pgvector cosine distance query   | Returns empty → fulltext search still works    |
| 2      | `services/business_logic.py`     | `search_products()` — filtered vector search with CTE | Returns empty product list                     |
| 3a     | `services/agent_tools.py`        | `get_trending_products()` — @tool function            | Returns "not implemented" JSON                 |
| 3b     | `agents/recommendation_agent.py` | `product_recommendation_agent()` — specialist agent   | Returns "not implemented" JSON                 |
| 3b     | `agents/orchestrator.py`         | `ORCHESTRATOR_PROMPT` + `create_orchestrator()`       | Returns `None` → chat shows "not wired up"     |
| 4      | `services/agentcore_memory.py`   | `create_agentcore_session_manager()`                  | Returns `None` → falls back to Aurora sessions |
| 4      | `services/agentcore_gateway.py`  | `create_gateway_orchestrator()`                       | Returns `None` → falls back to direct imports  |
| 4      | `services/agentcore_policy.py`   | `_check_policy()` — Cedar policy evaluation           | Returns `None` → all actions allowed           |

Null guards added in `chat.py` (sync + streaming), `app.py`, and `agentcore_runtime.py`.

---

## Workshop Content Restructure

**Before (2025):**

```
1-Introduction/ → a-Business-challenge/ + b-Workshop-Overview/
2-Prerequisites/
3-Pellier-Bazaar-Demo/
4-Building-agentic-AI-powered-search/ → Part1/ Part2/ Part3/ Part4/
5-FAQs/
6-Troubleshooting/
93-Workshop-Credits/
```

**After (2026):**

```
1-Welcome/                              Merged intro + challenge + overview
2-Getting-Started/                      Merged prereqs + app launch + demo
3-Teaching-Your-Database-to-Think/      Semantic search (was Part1)
4-Giving-Your-Agent-Superpowers/        Custom tools (was Part2)
5-Building-the-Agent-Team/              Multi-agent + AgentCore (was Part3)
6-Going-to-Production/                  Policies + deployment (was Part4)
7-Reference/                            Merged FAQs + Troubleshooting + Credits
```

All "Part N" references replaced with narrative titles throughout.

---

## Dataset Change

Switched from `amazon-products-sample-with-embeddings.csv` (21,704 products, 455MB) to `premium-products-with-embeddings.csv` (~1,000 curated products, 12MB). Updated across: `scripts/load-database-fast.sh`, `scripts/bootstrap-labs.sh`, `data/README.md`, `.gitignore`, `README.md`, and all workshop content pages. Old CSVs removed from `lab-content/assets/`.

---

## Bootstrap Script Updates

- `scripts/bootstrap-environment.sh`: Updated welcome message directory structure, changed auto-open from notebook to `hybrid_search.py`, changed pip install from `notebooks/requirements.txt` to `pellier/backend/requirements.txt`
- `scripts/bootstrap-labs.sh`: Replaced `install_notebooks()` with no-op (notebooks archived), updated product count messages
- `scripts/load-database-fast.sh`: Updated CSV filename references to premium dataset

---

## Workshop Content Repo (`lab-content/`)

`lab-content/` and `reference/` are separate git repos, gitignored from the main code repo. Changes made inside `lab-content/` (content restructure, narrative titles, new pages) are committed separately in that repo.

Removed from lab-content: `MIGRATION_GUIDE.md`, `LIVESTREAM_RUNDOWN.md`, `KIRO_SESSION_PROMPT.md`.

---

## Other Cleanup

- Removed empty `pellier/config/` directory
- Added `lab-content/` and `reference/` to `.gitignore` (embedded git repos)

---

## Files NOT Changed

- `pellier/frontend/` — untouched, pre-built React app
- `pellier/backend/services/database.py` — untouched
- `pellier/backend/services/embeddings.py` — untouched
- `pellier/backend/agents/inventory_agent.py` — untouched (pre-built example)
- `pellier/backend/agents/pricing_agent.py` — untouched (pre-built example)
- `modules/05/` — deployment scripts, untouched
- `sample-images/` — visual search test images, untouched
