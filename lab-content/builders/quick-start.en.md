---
title: "Quick Start (reference)"
weight: 98
---

# Quick Start

Your environment is ready. Here's everything you need to get oriented.

---

## Your URLs

| Surface                            | URL                                            |
| ---------------------------------- | ---------------------------------------------- |
| **Storefront**                     | `https://<your-cloudfront>/ports/8000/`        |
| **Atelier** (workshop observatory) | `https://<your-cloudfront>/ports/8000/atelier` |
| **Code Editor**                    | The tab you're reading this in                 |

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
```

### Check model access

```bash
python3 scripts/check_model_access.py
```

Verifies all four Bedrock models are accessible: Claude Opus 4.6, Claude Haiku 4.5, Cohere Embed v4, Cohere Rerank v3.5.

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

**Import error on startup?** Check the terminal — the error names the missing function. Most likely a challenge file needs the solution copied:

```bash
# Example: copy the Closing Marco's Gap orchestrator solution
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
