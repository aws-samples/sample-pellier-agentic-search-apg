#!/bin/bash
# Start Lab 2 Backend
cd "$(dirname "$0")/backend"
python3 generate_mcp_config.py 2>/dev/null || echo "⚠️  MCP config generation skipped"
uvicorn app:app --reload --host 0.0.0.0 --port 8000
