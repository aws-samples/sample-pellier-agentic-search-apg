#!/bin/bash
# Pellier Workshop - Stage 2: Labs Bootstrap
# Optimizations: Parallel pip installs, reduced redundancy, faster execution
# Duration: ~12-15 minutes

set -uo pipefail  # Removed -e to allow graceful failures

# ============================================================================
# PARAMETERS & LOGGING
# ============================================================================
CODE_EDITOR_USER="${CODE_EDITOR_USER:-participant}"
HOME_FOLDER="${HOME_FOLDER:-/workshop}"
REPO_NAME="sample-pellier-agentic-search-apg"
REPO_PATH="$HOME_FOLDER/$REPO_NAME"
AWS_REGION="${AWS_REGION:-us-west-2}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"; }

log "=========================================="
log "Pellier Stage 2: Labs Bootstrap (Optimized)"
log "=========================================="

# ============================================================================
# STEP 1: CLONE REPOSITORY (~30 sec)
# ============================================================================
log "Cloning repository..."
if [ ! -d "$REPO_PATH" ]; then
    sudo -u "$CODE_EDITOR_USER" git clone "${REPO_URL:-https://github.com/aws-samples/sample-pellier-agentic-search-apg.git}" "$REPO_PATH" 2>/dev/null && \
    rm -rf "$REPO_PATH/.git" && log "✅ Repository cloned" || warn "Clone failed"
else
    log "✅ Repository exists"
fi

# ============================================================================
# STEP 2: FETCH DB CREDENTIALS (~10 sec)
# ============================================================================
log "Fetching database credentials..."
export DB_HOST="" DB_PORT="5432" DB_USER="" DB_PASSWORD="" DB_NAME="${DB_NAME:-postgres}"

if [ -n "${DB_SECRET_ARN:-}" ]; then
    DB_SECRET=$(aws secretsmanager get-secret-value --secret-id "$DB_SECRET_ARN" --region "$AWS_REGION" --query SecretString --output text 2>/dev/null || echo "")
    if [ -n "$DB_SECRET" ]; then
        export DB_HOST=$(echo "$DB_SECRET" | jq -r '.host // empty')
        export DB_USER=$(echo "$DB_SECRET" | jq -r '.username // empty')
        export DB_PASSWORD=$(echo "$DB_SECRET" | jq -r '.password // empty')
        export DB_NAME=$(echo "$DB_SECRET" | jq -r '.dbname // .database // "postgres"')
        log "✅ Database credentials retrieved"
    fi
fi

# ============================================================================
# STEP 3: CREATE .ENV FILES (~5 sec) - CONSOLIDATED
# ============================================================================
log "Creating environment files..."

# Frontend .env (always create).
#
# Single-process model: FastAPI on :8000 serves BOTH the built SPA
# and /api, so the browser hits the same origin for both — no
# separate API base URL is needed. VITE_API_URL stays empty (the
# chat/search services default to '' → relative URLs).
#
# VITE_BASE_PATH is the asset URL prefix baked into the built bundle
# so CloudFront's /ports/8000/* reverse proxy matches what code-server
# forwards. Override to "/" for a pure-local prod-build test.
[ -d "$REPO_PATH/pellier/frontend" ] && cat > "$REPO_PATH/pellier/frontend/.env" << EOF
VITE_API_URL=
VITE_BASE_PATH=/ports/8000/
VITE_AWS_REGION=$AWS_REGION
VITE_ENABLE_LAB2=true
EOF

# Backend/Root .env (if DB available)
if [ -n "$DB_HOST" ]; then
    DB_CLUSTER_ARN="arn:aws:rds:${AWS_REGION}:$(aws sts get-caller-identity --query Account --output text):cluster:pellier-cluster"
    
    # Single .env template
    cat > "$REPO_PATH/.env" << EOF
DB_SECRET_ARN=${DB_SECRET_ARN:-}
DB_CLUSTER_ARN=$DB_CLUSTER_ARN
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME
PGHOST=$DB_HOST
PGPORT=$DB_PORT
PGUSER=$DB_USER
PGPASSWORD=$DB_PASSWORD
PGDATABASE=$DB_NAME
AWS_REGION=$AWS_REGION
AWS_DEFAULT_REGION=$AWS_REGION
BEDROCK_EMBEDDING_MODEL=${BEDROCK_EMBEDDING_MODEL:-us.cohere.embed-v4:0}
BEDROCK_CHAT_MODEL=${BEDROCK_CHAT_MODEL:-global.anthropic.claude-opus-4-6-v1}
COGNITO_USER_POOL_ID=${COGNITO_USER_POOL_ID:-}
COGNITO_CLIENT_ID=${COGNITO_CLIENT_ID:-}
COGNITO_CLIENT_SECRET_ARN=${COGNITO_CLIENT_SECRET_ARN:-}
COGNITO_DOMAIN=${COGNITO_DOMAIN:-}
COGNITO_HOSTED_UI_URL=${COGNITO_HOSTED_UI_URL:-}
COGNITO_TEST_CREDENTIALS_SECRET_ARN=${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}
WORKSHOP_ID=${WORKSHOP_ID:-}
WORKSHOP_FORMAT=${WORKSHOP_FORMAT:-workshop}
EOF
    
    chmod 600 "$REPO_PATH/.env"
    chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.env"
    
    # Symlink for backend (avoid duplication)
    ln -sf "$REPO_PATH/.env" "$REPO_PATH/pellier/backend/.env" 2>/dev/null
    
    # .pgpass for psql CLI
    echo "$DB_HOST:$DB_PORT:$DB_NAME:$DB_USER:$DB_PASSWORD" > "/home/$CODE_EDITOR_USER/.pgpass"
    chmod 600 "/home/$CODE_EDITOR_USER/.pgpass"
    chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "/home/$CODE_EDITOR_USER/.pgpass"
    
    log "✅ Environment files created (.env, .pgpass)"
else
    warn "Database credentials not available - skipping DB configuration"
fi

# Fix permissions
chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH"

# ============================================================================
# STEP 4-6: PARALLEL PYTHON DEPENDENCIES (~3-4 min vs 7 min)
# ============================================================================
log "Installing Python dependencies (parallel)..."

install_notebooks() {
    # Notebooks archived — skip notebook dependencies
    log "Notebooks archived — skipping notebook dependencies"
    return 0
}

install_pellier() {
    if [ -f "$REPO_PATH/pellier/backend/requirements.txt" ]; then
        cd "$REPO_PATH/pellier/backend"
        sudo -u "$CODE_EDITOR_USER" python3.13 -m pip install --user -r requirements.txt 2>&1 | tee /var/log/pellier-pip-install.log >/dev/null
        return ${PIPESTATUS[0]}
    fi
    return 1
}

# Run in parallel
install_notebooks & PID1=$!
install_pellier & PID2=$!
if wait $PID1; then
    log "✅ Notebooks dependencies installed"
else
    warn "Notebooks install issues - check /var/log/notebooks-pip-install.log"
fi
if wait $PID2; then
    log "✅ Pellier Backend dependencies installed"
else
    warn "Pellier Backend install issues - check /var/log/pellier-pip-install.log"
fi

# ============================================================================
# STEP 7: INSTALL UV (~30 sec)
# ============================================================================
log "Installing uv..."
if ! sudo -u "$CODE_EDITOR_USER" bash -c 'export PATH="$HOME/.local/bin:$PATH" && command -v uv' &>/dev/null; then
    sudo -u "$CODE_EDITOR_USER" bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' &>/dev/null || \
    sudo -u "$CODE_EDITOR_USER" python3.13 -m pip install --user uv &>/dev/null
    log "✅ uv installed"
else
    log "✅ uv already installed"
fi

# ============================================================================
# STEP 8: MCP CONFIG DIRECTORY & GENERATION
# ============================================================================
log "Setting up MCP configuration..."
mkdir -p "$REPO_PATH/pellier/config"
chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/pellier/config"

# Generate MCP config if database credentials are available
if [ -n "$DB_HOST" ] && [ -f "$REPO_PATH/pellier/backend/generate_mcp_config.py" ]; then
    cd "$REPO_PATH/pellier/backend"
    
    # Source .env file to get all variables
    if [ -f "$REPO_PATH/.env" ]; then
        set -a
        source "$REPO_PATH/.env"
        set +a
    fi
    
    # Verify required variables are set
    if [ -z "${DB_SECRET_ARN:-}" ] || [ -z "${DB_CLUSTER_ARN:-}" ]; then
        warn "Missing DB_SECRET_ARN or DB_CLUSTER_ARN - MCP config will be generated on backend startup"
    else
        # Generate MCP config with variables from .env
        sudo -u "$CODE_EDITOR_USER" bash -c "export DB_SECRET_ARN='$DB_SECRET_ARN' && \
            export DB_CLUSTER_ARN='$DB_CLUSTER_ARN' && \
            export DB_NAME='$DB_NAME' && \
            export AWS_REGION='$AWS_REGION' && \
            python3.13 generate_mcp_config.py" 2>&1 | tee /var/log/mcp-config-generation.log
        
        if [ -f "$REPO_PATH/pellier/config/mcp-server-config.json" ]; then
            log "✅ MCP config generated at pellier/config/mcp-server-config.json"
            
            # Deploy MCP config to all Amazon Q locations
            log "Deploying MCP config to Amazon Q..."
            
            # Create .amazonq directories
            mkdir -p "/home/$CODE_EDITOR_USER/.aws/amazonq"
            mkdir -p "$HOME_FOLDER/.amazonq"
            mkdir -p "$REPO_PATH/.amazonq"
            
            # Read generated config and add useLegacyMcpJson for global config
            MCP_CONFIG=$(cat "$REPO_PATH/pellier/config/mcp-server-config.json")
            MCP_CONFIG_WITH_LEGACY=$(echo "$MCP_CONFIG" | jq '. + {"useLegacyMcpJson": true}')
            
            # Deploy to global configs (with useLegacyMcpJson)
            echo "$MCP_CONFIG_WITH_LEGACY" > "/home/$CODE_EDITOR_USER/.aws/amazonq/default.json"
            echo "$MCP_CONFIG" > "/home/$CODE_EDITOR_USER/.aws/amazonq/mcp.json"
            chmod 600 "/home/$CODE_EDITOR_USER/.aws/amazonq/default.json" "/home/$CODE_EDITOR_USER/.aws/amazonq/mcp.json"
            
            # Deploy to workspace configs
            echo "$MCP_CONFIG" > "$HOME_FOLDER/.amazonq/default.json"
            echo "$MCP_CONFIG" > "$HOME_FOLDER/.amazonq/mcp.json"
            echo "$MCP_CONFIG" > "$REPO_PATH/.amazonq/default.json"
            echo "$MCP_CONFIG" > "$REPO_PATH/.amazonq/mcp.json"
            
            # Fix permissions
            chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "/home/$CODE_EDITOR_USER/.aws/amazonq"
            chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$HOME_FOLDER/.amazonq"
            chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.amazonq"
            
            log "✅ MCP config deployed to Amazon Q (global + workspace)"
        else
            warn "MCP config generation failed - will be generated on backend startup"
        fi
    fi
    cd "$REPO_PATH"
else
    log "ℹ️  MCP config will be generated on backend startup"
fi

# ============================================================================
# STEP 9-10: PARALLEL FRONTEND + DATABASE (~8 min vs 8.5 min)
# ============================================================================
log "Setting up frontend and database (parallel)..."

setup_frontend() {
    if [ -d "$REPO_PATH/pellier/frontend" ]; then
        cd "$REPO_PATH/pellier/frontend"
        sudo -u "$CODE_EDITOR_USER" npm install &>/dev/null
    fi
}

setup_database() {
    if [ -n "$DB_HOST" ] && [ -f "$REPO_PATH/scripts/load_catalog.py" ]; then
        cd "$REPO_PATH"
        export DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD AWS_REGION
        export ASSETS_BUCKET_NAME ASSETS_BUCKET_PREFIX
        export DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
        # Boutique catalog loader (92 products with pre-computed Cohere
        # Embed v4 embeddings). Replaces the legacy seed-database.sh path,
        # which loaded the 444-product product-catalog-cohere-v4.csv.
        python3 scripts/load_catalog.py --yes --quiet --json \
            2>&1 | tee /var/log/database-setup.log
        return ${PIPESTATUS[0]}
    fi
    return 1
}

setup_frontend & PID_FE=$!
setup_database & PID_DB=$!
wait $PID_FE && log "✅ Frontend dependencies installed" || warn "Frontend install issues"
if wait $PID_DB; then
    log "✅ Database setup complete (92 boutique products, HNSW index, iterative_scan configured)"
else
    warn "Database setup had issues - check /var/log/database-setup.log and logs/load_catalog_audit.log"
fi

# ============================================================================
# STEP 10b: PROVISION AGENTCORE MEMORY (STM) (~15 sec)
# ============================================================================
log "Provisioning AgentCore Memory (STM)..."

AGENTCORE_MEMORY_ID=""
if command -v python3.13 &>/dev/null; then
    AGENTCORE_MEMORY_ID=$(sudo -u "$CODE_EDITOR_USER" bash -c "
        export PATH=\"\$HOME/.local/bin:\$PATH\"
        export AWS_REGION=$AWS_REGION
        python3.13 -c '
import boto3
import time
import sys

try:
    client = boto3.client(\"bedrock-agentcore-control\", region_name=\"$AWS_REGION\")

    # Check if memory already exists
    existing = client.list_memories(maxResults=10)
    for mem in existing.get(\"memories\", []):
        if mem.get(\"name\") == \"PellierSTM\":
            mem_id = mem[\"id\"]
            print(mem_id)
            sys.exit(0)

    # Create new STM-only memory (no strategies = short-term only)
    response = client.create_memory(
        name=\"PellierSTM\",
        description=\"Short-term memory for Pellier workshop — conversation context within sessions\",
        eventExpiryDuration=30
    )
    mem_id = response[\"memory\"][\"id\"]

    # Wait for ACTIVE status (usually <10 seconds for STM-only)
    for i in range(12):
        status = client.get_memory(memoryId=mem_id)[\"memory\"][\"status\"]
        if status == \"ACTIVE\":
            print(mem_id)
            sys.exit(0)
        if status == \"FAILED\":
            print(\"\", file=sys.stderr)
            sys.exit(1)
        time.sleep(5)

    # Timeout — print ID anyway, it may activate later
    print(mem_id)
except Exception as e:
    print(f\"Memory provisioning failed: {e}\", file=sys.stderr)
    sys.exit(1)
' 2>/dev/null
    " 2>/dev/null)
fi

if [ -n "$AGENTCORE_MEMORY_ID" ]; then
    log "✅ AgentCore Memory provisioned: $AGENTCORE_MEMORY_ID"
    # Append to .env
    echo "AGENTCORE_MEMORY_ID=$AGENTCORE_MEMORY_ID" >> "$REPO_PATH/.env"
    chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.env"
else
    warn "AgentCore Memory provisioning skipped — STM will fall back to Aurora session tables"
fi

# ============================================================================
# STEP 11: CREATE START SCRIPTS (~5 sec)
# ============================================================================
log "Creating start scripts..."

# Single-process model: FastAPI on :8000 serves both /api/* and the
# built SPA. The legacy start-frontend.sh / http-server on 5173 is
# gone — attendees point their browser at /ports/8000/* only.
cat > "$REPO_PATH/pellier/start-backend.sh" << 'EOF'
#!/bin/bash
# Convenience script for interactive iteration. The workshop's
# production flow is the pellier systemd service (see below).
# Use this script when you want --reload during local dev.
cd "$(dirname "$0")/backend"
export PATH="$HOME/.local/bin:$PATH"
[ -f "../../.env" ] && export $(grep -v '^#' ../../.env | xargs)
[ ! -f "../config/mcp-server-config.json" ] && [ -f "generate_mcp_config.py" ] && python3 generate_mcp_config.py 2>/dev/null
echo "🚀 Starting FastAPI backend on http://localhost:8000 (with --reload)"
echo "   App: http://localhost:8000/ — uvicorn serves the built SPA + /api"
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
EOF

chmod +x "$REPO_PATH/pellier/start-backend.sh"
chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/pellier/start-backend.sh"
log "✅ Start scripts created"

# ============================================================================
# STEP 12: BASH ENVIRONMENT (~5 sec)
# ============================================================================
log "Configuring bash environment..."

cat >> "/home/$CODE_EDITOR_USER/.bashrc" << 'EOF'

# ============================================================================
# Pellier Workshop Environment
# ============================================================================

if [ -f /workshop/sample-pellier-agentic-search-apg/.env ]; then
    set -a
    source /workshop/sample-pellier-agentic-search-apg/.env
    set +a
    
    # Explicitly export PostgreSQL variables for psql
    export PGHOST
    export PGPORT
    export PGUSER
    export PGPASSWORD
    export PGDATABASE
fi

# Workshop Navigation Aliases
alias workshop='cd /workshop/sample-pellier-agentic-search-apg'
alias notebooks='cd /workshop/sample-pellier-agentic-search-apg/notebooks'
alias pellier='cd /workshop/sample-pellier-agentic-search-apg/pellier'
alias backend='cd /workshop/sample-pellier-agentic-search-apg/pellier/backend'
alias frontend='cd /workshop/sample-pellier-agentic-search-apg/pellier/frontend'

# Pellier Service Shortcuts — single-process model: uvicorn on
# :8000 serves the built SPA AND /api. Frontend changes require a
# rebuild (``npm run build`` in pellier/frontend/) and are
# handled automatically by the pellier systemd service.
alias start-backend='/workshop/sample-pellier-agentic-search-apg/pellier/start-backend.sh'
alias rebuild-frontend='cd /workshop/sample-pellier-agentic-search-apg/pellier/frontend && npm run build && cd - >/dev/null && systemctl restart pellier 2>/dev/null || true'

# Database Shortcut (psql uses PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE from .env)
alias psql='psql'

# AWS Region for boto3
export AWS_DEFAULT_REGION=${AWS_REGION:-us-west-2}

# Ensure uv is in PATH (required for MCP)
export PATH="$HOME/.local/bin:$PATH"

# Auto-navigate to workshop directory on terminal open
if [ "$PWD" = "$HOME" ] || [ "$PWD" = "/workshop" ]; then
    cd /workshop/sample-pellier-agentic-search-apg 2>/dev/null || true
fi
EOF

log "✅ Bash environment configured (.bashrc updated with psql support)"

# ============================================================================
# STEP 13: FINAL VERIFICATION
# ============================================================================
log "Performing final verification..."

# Verify database setup
if [ -n "$DB_HOST" ]; then
    PRODUCT_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM pellier.product_catalog;" 2>/dev/null | xargs || echo "0")
    if [ "$PRODUCT_COUNT" -gt 0 ]; then
        log "✅ Database verified ($PRODUCT_COUNT products)"
    else
        warn "⚠️  Database may not be set up correctly (0 products found)"
    fi
fi

# Verify Python packages
if sudo -u "$CODE_EDITOR_USER" python3.13 -c "import fastapi, uvicorn, strands" 2>/dev/null; then
    log "✅ Pellier Backend dependencies verified"
else
    warn "⚠️  Some Pellier Backend dependencies may be missing"
fi

# ============================================================================
# STEP 14: AUTO-START PELLIER SERVICE (single-process, port 8000)
# ============================================================================
# Single systemd service. FastAPI serves:
#   - the built SPA at /, /atelier, /storyboard, /discover, ...
#   - the API at /api/*
#   - self-hosted fonts + hashed bundles at /assets/*, /fonts/*
#
# One port, one process, one unit to troubleshoot. Drop-in migration
# from the earlier two/three-service layout: after running this
# bootstrap on a host that had pellier-{backend,frontend,frontend-watcher}
# services, those are stopped + disabled below so there's no port-5173
# collision at restart.
log "Creating pellier auto-start service (single process, port 8000)..."

# Cleanup of the legacy two/three-service layout. Safe to run
# unconditionally — absent services return non-zero and we swallow.
systemctl stop pellier-backend pellier-frontend pellier-frontend-watcher 2>/dev/null || true
systemctl disable pellier-backend pellier-frontend pellier-frontend-watcher 2>/dev/null || true
rm -f /etc/systemd/system/pellier-backend.service \
      /etc/systemd/system/pellier-frontend.service \
      /etc/systemd/system/pellier-frontend-watcher.service

# --- pellier.service: build frontend once, then run uvicorn ---
cat > /etc/systemd/system/pellier.service << EOF
[Unit]
Description=Pellier (FastAPI + built SPA on :8000)
After=network.target

[Service]
Type=simple
User=$CODE_EDITOR_USER
Group=$CODE_EDITOR_USER
WorkingDirectory=$REPO_PATH/pellier/backend
EnvironmentFile=$REPO_PATH/.env
Environment=PATH=/home/$CODE_EDITOR_USER/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=HOME=/home/$CODE_EDITOR_USER
# VITE_BASE_PATH is baked into the built bundle so asset URLs match
# the CloudFront /ports/8000/* reverse-proxy prefix.
Environment=VITE_BASE_PATH=/ports/8000/
# ExecStartPre runs every restart: regenerate MCP config (cheap) and
# rebuild the frontend bundle so the latest /src/ lands in dist/. The
# build is a one-shot vite run — no watcher, no second process.
ExecStartPre=/bin/bash -c 'cd $REPO_PATH/pellier/backend && python3 generate_mcp_config.py 2>/dev/null || true'
ExecStartPre=/bin/bash -c 'cd $REPO_PATH/pellier/frontend && npm run build'
ExecStart=/home/$CODE_EDITOR_USER/.local/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
StandardOutput=append:/tmp/pellier/uvicorn.log
StandardError=append:/tmp/pellier/uvicorn.log

[Install]
WantedBy=multi-user.target
EOF

# Create log directory
mkdir -p /tmp/pellier
chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" /tmp/pellier

# Enable + start the single service
systemctl daemon-reload
systemctl enable pellier
systemctl start pellier

# Verify it started
sleep 8
if systemctl is-active --quiet pellier; then
    log "✅ pellier service running (port 8000, serves SPA + /api)"
else
    warn "pellier service failed to start — check: journalctl -u pellier"
fi

log "✅ Auto-start service configured"
log "   App URL (Workshop Studio): https://<cloudfront>/ports/8000/"
log "   App URL (local):           http://localhost:8000/"
log "   Frontend rebuild: run 'rebuild-frontend' alias or restart the service"

# ============================================================================
# STEP 15: STATUS MARKER
# ============================================================================
cat > /tmp/workshop-ready.json << EOF
{
    "status": "complete",
    "timestamp": "$(date -Iseconds)",
    "stage": "labs-bootstrap",
    "components": {
        "notebooks_dependencies": "ready",
        "pellier_backend": "ready",
        "pellier_frontend": "ready",
        "database_config": "ready",
        "jupyter_kernel": "ready"
    }
}
EOF
chmod 644 /tmp/workshop-ready.json
log "✅ Status marker created"

# ============================================================================
# STEP 16: BUILDERS FORMAT - Pre-complete challenges 3-9 with solution files
# ============================================================================
if [ "${WORKSHOP_FORMAT:-workshop}" = "builders" ]; then
    log "=========================================="
    log "Builders Session: pre-completing challenges 3-9"
    log "=========================================="

    copy_solution() {
        local src="$1" dest="$2" label="$3"
        if [ -f "$REPO_PATH/$src" ]; then
            cp "$REPO_PATH/$src" "$REPO_PATH/$dest" && \
                log "  builders: $label" || warn "  builders: $label copy failed"
        fi
    }

    copy_solution "solutions/module2/agents/recommendation_agent.py" \
                  "pellier/backend/agents/recommendation_agent.py" "C3 recommendation_agent.py"
    copy_solution "solutions/module2/agents/orchestrator.py" \
                  "pellier/backend/agents/orchestrator.py" "C4 orchestrator.py"
    copy_solution "solutions/module3/services/agentcore_runtime.py" \
                  "pellier/backend/agentcore_runtime.py" "C5 agentcore_runtime.py"
    copy_solution "solutions/module3/services/agentcore_memory.py" \
                  "pellier/backend/services/agentcore_memory.py" "C6 agentcore_memory.py"
    copy_solution "solutions/module3/services/agentcore_gateway.py" \
                  "pellier/backend/services/agentcore_gateway.py" "C7 agentcore_gateway.py"
    copy_solution "solutions/module3/services/otel_trace_extractor.py" \
                  "pellier/backend/services/otel_trace_extractor.py" "C8 otel_trace_extractor.py"
    copy_solution "solutions/module3/frontend/agentIdentity.ts" \
                  "pellier/frontend/src/utils/agentIdentity.ts" "C9 agentIdentity.ts"

    chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/pellier/"
    # Single-service restart — re-runs the ExecStartPre vite build so
    # the frontend bundle picks up any C9 solution drop-in too.
    systemctl restart pellier 2>/dev/null || true
    log "✅ Builders solutions applied and pellier service restarted"
fi

# ============================================================================
# STEP 17: WRITE TEST CREDENTIALS FILE
# ============================================================================
if [ -n "${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}" ] && [ -x "$REPO_PATH/scripts/write-test-credentials.sh" ]; then
    log "Writing test credentials file..."
    export COGNITO_TEST_CREDENTIALS_SECRET_ARN COGNITO_HOSTED_UI_URL AWS_REGION \
           CODE_EDITOR_USER HOME_FOLDER
    bash "$REPO_PATH/scripts/write-test-credentials.sh" 2>&1 | tee /var/log/pellier-write-credentials.log || \
        warn "write-test-credentials.sh reported issues"
fi

# ============================================================================
# STEP 18: SEED SAMPLE PREFERENCES (users 1-3)
# ============================================================================
if [ -n "${COGNITO_USER_POOL_ID:-}" ] && [ -x "$REPO_PATH/scripts/seed-sample-preferences.sh" ]; then
    log "Seeding sample preferences for test users 1-3..."
    export COGNITO_USER_POOL_ID COGNITO_CLIENT_ID COGNITO_CLIENT_SECRET_ARN \
           COGNITO_TEST_CREDENTIALS_SECRET_ARN AWS_REGION
    export BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
    bash "$REPO_PATH/scripts/seed-sample-preferences.sh" 2>&1 | tee /var/log/pellier-seed-preferences.log || \
        warn "seed-sample-preferences.sh reported issues"
fi

# ============================================================================
# SUMMARY
# ============================================================================
log "=========================================="
log "Stage 2: Labs Bootstrap Complete!"
log "=========================================="
echo ""
echo "✅ Notebooks (Jupyter) dependencies installed"
echo "✅ Pellier Backend (FastAPI + Strands) installed"
echo "✅ Pellier Frontend (React) dependencies installed"
echo "✅ Database setup complete (~92 products with indexes)"
echo "✅ MCP server configured for Amazon Q"
echo "✅ Bash environment configured (psql ready)"
echo "✅ pellier service auto-started (single process on :8000)"
echo ""
echo "🌐 App is live at: https://<cloudfront>/ports/8000/"
echo "   Frontend + API both served by one uvicorn process."
echo "   Edits to pellier/frontend/src/ require a rebuild:"
echo "     rebuild-frontend    # alias: npm run build + systemctl restart"
echo ""
echo "Quick Commands:"
echo "  psql                             # Connect to database"
echo "  journalctl -fu pellier     # Service logs"
echo "  rebuild-frontend                 # Rebuild SPA + restart service"
echo ""
log "=========================================="

exit 0