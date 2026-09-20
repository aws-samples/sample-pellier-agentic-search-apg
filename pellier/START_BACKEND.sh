#!/bin/bash
# Start the Pellier backend (FastAPI on :8000)
export PATH="/opt/pellier/bin:$PATH"
cd "$(dirname "$0")/backend" || exit 1
python3 generate_mcp_config.py 2>/dev/null || echo "⚠️  MCP config generation skipped"
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
