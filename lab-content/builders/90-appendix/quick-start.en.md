---
title: "Quick Start (reference)"
weight: 40
---

Use this page when the editor is open and the repo is on disk: either
for quick orientation or for a fast recovery from a fresh terminal.

---

## Your URLs

| Surface                            | URL                                            |
| ---------------------------------- | ---------------------------------------------- |
| **Storefront**                     | `https://<your-cloudfront>/ports/8000/`        |
| **Atelier** (workshop observatory) | `https://<your-cloudfront>/ports/8000/atelier` |
| **Code Editor**                    | Workshop Studio Code Editor tab                |

Find your CloudFront domain in the Workshop Studio **Outputs** tab.

---

## Terminal commands

Everything runs from the terminal inside Code Editor. The environment is pre-configured — no installs needed.

### Start / restart the app

```bash
start-backend          # Stops any running service, starts uvicorn with --reload
```

The app serves both the storefront UI and the API on port 8000. Edit a `.py` file, save, and uvicorn auto-restarts.

### Rebuild the frontend (after editing React/CSS)

```bash
rebuild-frontend       # Builds the SPA + restarts the app (no sudo)
```

You only need this if you edit files in `pellier/frontend/src/`. Python changes are picked up automatically by `--reload`. The alias runs `npm run build` and restarts serving: **Builder's Session** respawns the nohup uvicorn process; **Workshop** uses `systemctl restart pellier` (passwordless for the `pellier` unit after bootstrap).

### Connect to the database

```bash
psql                   # Connects to Aurora PostgreSQL (credentials pre-loaded)
                       # Same command works against Amazon RDS for PostgreSQL
                       # if you re-point DB_HOST in .env to an RDS endpoint.
```

### Check model access

```bash
python3 scripts/check_model_access.py
```

Verifies all four Bedrock models are accessible:

- `global.anthropic.claude-opus-4-6-v1` (Claude Opus 4.6)
- `global.anthropic.claude-haiku-4-5-20251001-v1:0` (Claude Haiku 4.5)
- `us.cohere.embed-v4:0` (Cohere Embed v4 · 1024-dim)
- `cohere.rerank-v3-5:0` (Cohere Rerank v3.5)

These are pinned in `pellier/backend/config.py`. The legacy
`BEDROCK_SONNET_MODEL` env name still resolves to Opus by default —
you may see it in older code paths.

---

## Project layout

```
pellier/
├── backend/           ← FastAPI + Strands agents (you edit here)
│   ├── agents/        ← Specialist agents (one file per agent)
│   ├── services/      ← Tools, search, embeddings, AgentCore
│   ├── routes/        ← API endpoints
│   ├── skills/        ← SKILL.md files injected into prompts
│   └── app.py         ← FastAPI app entry point
├── frontend/          ← React + Vite + Tailwind (pre-built)
│   ├── src/
│   └── dist/          ← Built SPA served by FastAPI
└── config/            ← MCP server config (auto-generated)

solutions/             ← Drop-in reference files by named module
scripts/               ← Bootstrap, seed, and utility scripts
data/                  ← Product catalog CSV with embeddings
```

---

## The five agents

| Agent                | File                         | Role                            |
| -------------------- | ---------------------------- | ------------------------------- |
| **Style Advisor**    | `agents/style_advisor.py`    | Semantic product search         |
| **Curator**          | `agents/curator.py`          | Recommendations + hybrid search |
| **Value Analyst**    | `agents/value_analyst.py`    | Pricing analysis                |
| **Stock Keeper**     | `agents/stock_keeper.py`     | Inventory checks + restock      |
| **Experience Guide** | `agents/experience_guide.py` | Returns + support               |

The **Orchestrator** (`agents/orchestrator.py`) routes every query to the right specialist.

---

## If something breaks

**Blank page after rebuild?** Hard-refresh: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows).

**Import error on startup?** Check the terminal — the error names the missing function. Most commonly in this builder lab, `floor_check` is still in stub state:

```bash
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

If the traceback points to a different module (for example, orchestrator), copy
the matching solution file for that module:

```bash
# Example: orchestrator fallback
cp solutions/closing-marcos-gap/agents/orchestrator.py pellier/backend/agents/orchestrator.py
```

**Database empty?** Re-seed:

```bash
bash scripts/seed-database.sh
```

**Model access denied?** Run `python3 scripts/check_model_access.py` to identify which model needs enabling.

---

## Workflow for the build exercise

1. Read the `floor_check` challenge description in the lab guide
2. Open `pellier/backend/services/agent_tools.py` — look for the `floor_check` challenge block
3. Implement between the markers (hints are in the comments)
4. Save — uvicorn restarts automatically
5. Test in the storefront or Atelier

Short on time? Copy the Closing Marco's Gap solution:

```bash
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

The exact command is also in the challenge comments.
