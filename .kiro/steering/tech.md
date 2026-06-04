---
inclusion: always
---

# Pellier — Tech Stack

## Backend

- Python 3.13, FastAPI, uvicorn
- Strands Agents SDK — `@tool` decorator, `Agent` class, `BedrockModel`
- psycopg 3 (async) with connection pooling
- Amazon Bedrock: Claude Opus 4.6 (agents), Claude Haiku 4.5 (orchestrator), Cohere Embed v4 (embeddings), Cohere Rerank v3.5
- Amazon Aurora PostgreSQL (latest available at workshop time; currently 17.9) Serverless v2 with pgvector (latest version)
- bedrock-agentcore SDK for Memory, Gateway, Policy, Runtime

## Frontend

- React 18, TypeScript, Vite
- Tailwind CSS
- SSE streaming for real-time agent responses

## Infrastructure

- CloudFormation nested stacks (VPC, Database, Code Editor)
- Aurora Serverless v2 (0-16 ACU, scale-to-zero)
- EC2 (c6g.2xlarge Graviton) with CloudFront for Code Editor
- Workshop Studio for provisioning

## Key Dependencies

- `strands-agents` — Agent framework
- `strands-agents-tools` — AgentCore Code Interpreter
- `bedrock-agentcore` — Memory, Gateway, Policy SDKs
- `mcp` — Model Context Protocol client (streamable HTTP)
- `psycopg[binary,pool]` — PostgreSQL async driver
- `pydantic-settings` — Configuration management

## Build & Run

- Backend: `cd pellier/backend && uvicorn app:app --reload --host 0.0.0.0 --port 8000`
- Frontend: `cd pellier/frontend && npm run dev`
- Solutions: `cp solutions/moduleN/path/file.py pellier/backend/path/file.py`
- Database seed: `bash scripts/seed-database.sh`
