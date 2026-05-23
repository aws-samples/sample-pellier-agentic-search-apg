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
        export DB_NAME=$(echo "$DB_SECRET" | jq -r --arg default_db "${DB_NAME:-postgres}" '.dbname // .database // $default_db')
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

    # URL-encode the password for DATABASE_URL. Aurora master secrets
    # routinely contain @ : / ? % which must be percent-encoded inside
    # a postgresql:// URL or psycopg will misparse the string.
    DB_PASSWORD_URLENC=$(python3 -c "import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=''))" "$DB_PASSWORD")

    # Write the .env with single-quoted values so a downstream
    # `set -a; source .env; set +a` reads them as literals. Without
    # the quotes, any $ in DB_PASSWORD would expand at source time
    # — a real failure mode where a generated password containing
    # `$Z…` triggered "unbound variable" errors under `set -u`.
    cat > "$REPO_PATH/.env" << EOF
DB_SECRET_ARN='${DB_SECRET_ARN:-}'
DB_CLUSTER_ARN='${DB_CLUSTER_ARN}'
DB_HOST='${DB_HOST}'
DB_PORT='${DB_PORT}'
DB_NAME='${DB_NAME}'
DB_USER='${DB_USER}'
DB_PASSWORD='${DB_PASSWORD}'
DATABASE_URL='postgresql://${DB_USER}:${DB_PASSWORD_URLENC}@${DB_HOST}:${DB_PORT}/${DB_NAME}'
PGHOST='${DB_HOST}'
PGPORT='${DB_PORT}'
PGUSER='${DB_USER}'
PGPASSWORD='${DB_PASSWORD}'
PGDATABASE='${DB_NAME}'
AWS_REGION='${AWS_REGION}'
AWS_DEFAULT_REGION='${AWS_REGION}'
BEDROCK_EMBEDDING_MODEL='${BEDROCK_EMBEDDING_MODEL:-cohere.embed-english-v4:0}'
BEDROCK_CHAT_MODEL='${BEDROCK_CHAT_MODEL:-global.anthropic.claude-opus-4-6-v1}'
WORKSHOP_ID='${WORKSHOP_ID:-}'
WORKSHOP_FORMAT='${WORKSHOP_FORMAT:-workshop}'
AUTH_MODE='${AUTH_MODE:-demo}'
EOF

    chmod 600 "$REPO_PATH/.env"
    chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.env"

    # Symlink for backend (avoid duplication)
    ln -sf "$REPO_PATH/.env" "$REPO_PATH/pellier/backend/.env" 2>/dev/null

    # .pgpass for psql CLI. The user's home directory is created by
    # `adduser` in bootstrap-environment.sh; we ensure it exists here
    # too in case Stage 2 ran before Stage 1 (defensive).
    PGPASS_DIR="/home/$CODE_EDITOR_USER"
    if [ ! -d "$PGPASS_DIR" ]; then
        mkdir -p "$PGPASS_DIR"
        chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$PGPASS_DIR"
    fi
    echo "$DB_HOST:$DB_PORT:$DB_NAME:$DB_USER:$DB_PASSWORD" > "$PGPASS_DIR/.pgpass"
    chmod 600 "$PGPASS_DIR/.pgpass"
    chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$PGPASS_DIR/.pgpass"

    log "✅ Environment files created (.env, .pgpass)"
else
    warn "Database credentials not available - skipping DB configuration"
fi

# Fix permissions
chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH"

# ============================================================================
# STEP 4: VERIFY PYTHON DEPENDENCIES
# ============================================================================
# Stage 1 (bootstrap-environment.sh) already installed everything in
# pellier/backend/requirements.txt. Re-running the install here would
# either no-op (best case) or duplicate work without changing the
# environment. We just verify the critical packages reached
# /home/$CODE_EDITOR_USER/.local — if Stage 1's pip failed silently,
# we want to catch it here before the seeder runs and hits
# ModuleNotFoundError.
log "Verifying Python dependencies..."
if sudo -u "$CODE_EDITOR_USER" python3.13 -c "import boto3, fastapi, uvicorn, psycopg, strands" 2>/dev/null; then
    log "✅ Backend dependencies verified"
else
    warn "Some backend dependencies are missing — re-running pip install"
    if [ -f "$REPO_PATH/pellier/backend/requirements.txt" ]; then
        sudo -u "$CODE_EDITOR_USER" python3.13 -m pip install --user \
            -r "$REPO_PATH/pellier/backend/requirements.txt" 2>&1 \
            | tee -a /var/log/pellier-pip-install.log >/dev/null
        if sudo -u "$CODE_EDITOR_USER" python3.13 -c "import boto3, fastapi, uvicorn, psycopg, strands" 2>/dev/null; then
            log "✅ Backend dependencies recovered"
        else
            warn "Backend dependencies still missing after retry — pellier service will fail to start"
            warn "  see /var/log/pellier-pip-install.log"
        fi
    fi
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
            log "   Act III §02 reads this file + verifies awslabs.postgres-mcp-server via uvx"
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
    if [ -n "$DB_HOST" ] && [ -f "$REPO_PATH/scripts/seed_boutique_catalog.py" ]; then
        cd "$REPO_PATH"
        export DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD AWS_REGION
        export ASSETS_BUCKET_NAME ASSETS_BUCKET_PREFIX
        export DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"

        if ! command -v psql >/dev/null 2>&1; then
            warn "psql is not installed or not on PATH — database setup cannot run"
            return 1
        fi

        # ---- 1. Schema bootstrap (CREATE EXTENSION vector + schema +
        # product_catalog table + HNSW index). pellier-database.yml
        # provisions an empty Aurora cluster; this migration is what
        # makes the cluster boutique-ready. Runs first because the
        # seeder INSERTs into pellier.product_catalog and assumes the
        # vector(1024) column exists. ----
        if [ -f "$REPO_PATH/scripts/migrations/001_schema.sql" ]; then
            log "Applying migration 001_schema.sql..."
            PGPASSWORD="$DB_PASSWORD" psql \
                -h "$DB_HOST" -p "$DB_PORT" \
                -U "$DB_USER" -d "$DB_NAME" \
                -v ON_ERROR_STOP=1 \
                -f "$REPO_PATH/scripts/migrations/001_schema.sql" \
                2>&1 | tee /var/log/database-schema.log
            local rc=${PIPESTATUS[0]}
            if [ "$rc" -ne 0 ]; then
                warn "Schema bootstrap failed (rc=$rc) — see /var/log/database-schema.log"
                return "$rc"
            fi
        else
            warn "001_schema.sql not found — seeder will fail without the table"
        fi

        # ---- 2. Boutique catalog seeder — 40 hand-curated products
        # across the four personas (Marco / Anna / Theo / Fresh), with
        # Cohere Embed v4 embeddings generated at seed time.
        # Authoritative source for pellier.product_catalog. ----
        python3 scripts/seed_boutique_catalog.py 2>&1 | tee /var/log/database-setup.log
        local seed_rc=${PIPESTATUS[0]}
        if [ "$seed_rc" -ne 0 ]; then
            warn "Boutique catalog seed failed (rc=$seed_rc) — see /var/log/database-setup.log"
            return "$seed_rc"
        fi

        # ---- 3. Required fresh-cluster migrations. These are intentionally
        # idempotent and run after the catalog exists because several
        # tables FK into pellier.product_catalog. Ordering matters:
        # telemetry creates customers/orders, persona seed populates them,
        # Theo returns references them, and warehouse inventory powers
        # floor_check. ----
        local migration
        for migration in \
            002_workshop_telemetry.sql \
            003_persona_seed.sql \
            004_anna_hybrid_search.sql \
            005_theo_returns.sql \
            006_warehouse_inventory.sql \
            007_chat_session_tables.sql \
            008_search_performance_indexes.sql
        do
            if [ -f "$REPO_PATH/scripts/migrations/$migration" ]; then
                log "Applying migration $migration..."
                PGPASSWORD="$DB_PASSWORD" psql \
                    -h "$DB_HOST" -p "$DB_PORT" \
                    -U "$DB_USER" -d "$DB_NAME" \
                    -v ON_ERROR_STOP=1 \
                    -f "$REPO_PATH/scripts/migrations/$migration" \
                    2>&1 | tee -a /var/log/database-setup.log
                local migration_rc=${PIPESTATUS[0]}
                if [ "$migration_rc" -ne 0 ]; then
                    warn "Migration $migration failed (rc=$migration_rc) — see /var/log/database-setup.log"
                    return "$migration_rc"
                fi
            else
                warn "Migration $migration not found — skipping"
            fi
        done

        return 0
    fi
    return 1
}

setup_frontend & PID_FE=$!
setup_database & PID_DB=$!
wait $PID_FE && log "✅ Frontend dependencies installed" || warn "Frontend install issues"
if wait $PID_DB; then
    log "✅ Database setup complete (40 boutique products, HNSW index, workshop tables)"
else
    warn "Database setup had issues - check /var/log/database-setup.log"
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
alias pellier='cd /workshop/sample-pellier-agentic-search-apg/pellier'
alias backend='cd /workshop/sample-pellier-agentic-search-apg/pellier/backend'
alias frontend='cd /workshop/sample-pellier-agentic-search-apg/pellier/frontend'

# Pellier service shortcuts — see FORMAT_ALIASES below (workshop vs builders).

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

# Format-specific aliases (builders: no sudo; workshop: systemctl — passwordless via STEP 14 sudoers)
if [ "${WORKSHOP_FORMAT:-workshop}" = "builders" ]; then
cat >> "/home/$CODE_EDITOR_USER/.bashrc" << 'ALS'
# --- Pellier aliases (Builder's Session: uvicorn via nohup, not systemd) ---
alias start-backend='bash /workshop/sample-pellier-agentic-search-apg/scripts/start-backend-builders.sh'
alias rebuild-frontend='bash /workshop/sample-pellier-agentic-search-apg/scripts/rebuild-frontend-builders.sh'
ALS
else
cat >> "/home/$CODE_EDITOR_USER/.bashrc" << 'ALS'
# --- Pellier aliases (Workshop: systemd unit ``pellier``) ---
alias start-backend='sudo systemctl stop pellier 2>/dev/null; cd /workshop/sample-pellier-agentic-search-apg/pellier/backend && source ../../.env && export PATH="$HOME/.local/bin:$PATH" && uvicorn app:app --host 0.0.0.0 --port 8000 --reload'
alias rebuild-frontend='cd /workshop/sample-pellier-agentic-search-apg/pellier/frontend && VITE_BASE_PATH=/ports/8000/ npm run build && cd - >/dev/null && sudo systemctl restart pellier'
ALS
fi

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

    WAREHOUSE_ROWS=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM pellier.warehouse_inventory;" 2>/dev/null | xargs || echo "0")
    if [ "$WAREHOUSE_ROWS" -gt 0 ]; then
        log "✅ Warehouse inventory verified ($WAREHOUSE_ROWS rows)"
    else
        warn "⚠️  Warehouse inventory missing — floor_check exercise will not land"
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

# Let the workshop user restart the pellier unit without an interactive
# sudo password (rebuild-frontend / start-backend use systemctl).
SYSTEMCTL_BIN="$(command -v systemctl 2>/dev/null || echo /usr/bin/systemctl)"
SUDOERS_FILE="/etc/sudoers.d/99-pellier-systemctl-${CODE_EDITOR_USER}"
if printf '%s\n' \
    "${CODE_EDITOR_USER} ALL=(ALL) NOPASSWD: ${SYSTEMCTL_BIN} start pellier, ${SYSTEMCTL_BIN} stop pellier, ${SYSTEMCTL_BIN} restart pellier, ${SYSTEMCTL_BIN} is-active pellier, ${SYSTEMCTL_BIN} status pellier" \
    >"$SUDOERS_FILE" 2>/dev/null; then
    chmod 440 "$SUDOERS_FILE"
    if visudo -c -f "$SUDOERS_FILE" >/dev/null 2>&1; then
        log "✅ Passwordless systemctl for unit pellier (${CODE_EDITOR_USER})"
    else
        warn "sudoers drop-in failed visudo check — removing $SUDOERS_FILE"
        rm -f "$SUDOERS_FILE"
    fi
else
    warn "Could not write sudoers drop-in at $SUDOERS_FILE"
fi

# Create log directory
mkdir -p /tmp/pellier
chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" /tmp/pellier

# Enable + start the single service (workshop format only)
# For builders format, we skip the systemd start here — STEP 16 will
# launch uvicorn with --reload directly so participants see live restarts.
systemctl daemon-reload
systemctl enable pellier
if [ "${WORKSHOP_FORMAT:-workshop}" != "builders" ]; then
    systemctl start pellier

    # Verify it started
    sleep 8
    if systemctl is-active --quiet pellier; then
        log "✅ pellier service running (port 8000, serves SPA + /api)"
    else
        warn "pellier service failed to start — check: journalctl -u pellier"
    fi
else
    log "ℹ️  Builders format: skipping systemd start (uvicorn --reload will be launched in STEP 16)"
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
        "pellier_backend": "ready",
        "pellier_frontend": "ready",
        "database_config": "ready"
    }
}
EOF
chmod 644 /tmp/workshop-ready.json
log "✅ Status marker created"

# ============================================================================
# STEP 16: BUILDERS FORMAT — Pre-apply everything participants don't build
# ============================================================================
#
# The 60-min Builder's Session has one coding exercise: wire the
# floor_check tool body in services/agent_tools.py. Stock Keeper's
# system prompt and orchestrator are already in place. AgentCore STM
# + Runtime are pre-provisioned; participants verify STM continuity
# and walk through the Runtime entrypoint + invoke path in-room.
#
# This block copies finished reference files from solutions/ into
# their runtime locations under pellier/backend/ and pellier/frontend/.
# Every src path is verified against the actual repo layout — if
# you add new pre-applies, double-check both src and dest exist.
#
# Solutions directory layout:
#   solutions/the-quiet-search/   — Module 01 reference (observe-only)
#   solutions/closing-marcos-gap/ — Module 02 (the only edited module)
#   solutions/the-ledger/    — Module 03 reference (observe-only)
#
# Files we explicitly do NOT copy (participants build these):
#   inside agent_tools.py — the floor_check tool body only
if [ "${WORKSHOP_FORMAT:-workshop}" = "builders" ]; then
    log "=========================================="
    log "Builders Session: pre-applying reference files"
    log "=========================================="

    copy_solution() {
        local src="$1" dest="$2" label="$3"
        if [ -f "$REPO_PATH/$src" ]; then
            cp "$REPO_PATH/$src" "$REPO_PATH/$dest" && \
                log "  builders: $label" || warn "  builders: $label copy failed"
        else
            warn "  builders: $label — source missing at $src (skipped)"
        fi
    }

    # ---- Specialist agents that aren't Stock Keeper ----
    # Curator handles turn 2 (pairing.score, palette.match). Experience
    # Guide handles turn 5 (cart.holds, process_return). Orchestrator
    # is the dispatcher that routes between them.
    copy_solution "solutions/closing-marcos-gap/agents/curator.py" \
                  "pellier/backend/agents/curator.py" "Curator agent"
    copy_solution "solutions/closing-marcos-gap/agents/experience_guide.py" \
                  "pellier/backend/agents/experience_guide.py" "Experience Guide agent"
    copy_solution "solutions/closing-marcos-gap/agents/orchestrator.py" \
                  "pellier/backend/agents/orchestrator.py" "Orchestrator"

    # ---- agent_tools.py builders variant ----
    # Wires restock_shelf + running_low (everything Stock Keeper-adjacent
    # except floor_check itself). Participants will edit this file in
    # Module 02 to add the floor_check body — and only that body.
    copy_solution "solutions/closing-marcos-gap/services/agent_tools_builders_preapply.py" \
                  "pellier/backend/services/agent_tools.py" "Agent tools (builders variant)"

    # ---- AgentCore production plumbing ----
    # Memory + Gateway + Policy + Runtime + Identity all import each
    # other and are referenced from pellier/backend/routes/*.py. Without
    # these the FastAPI app won't even start. Note the destination is
    # services/agentcore_runtime.py (NOT backend/agentcore_runtime.py
    # — the routes import services.agentcore_runtime).
    copy_solution "solutions/the-ledger/services/agentcore_runtime.py" \
                  "pellier/backend/services/agentcore_runtime.py" "AgentCore runtime"
    copy_solution "solutions/the-ledger/services/agentcore_memory.py" \
                  "pellier/backend/services/agentcore_memory.py" "AgentCore memory"
    copy_solution "solutions/the-ledger/services/agentcore_gateway.py" \
                  "pellier/backend/services/agentcore_gateway.py" "AgentCore gateway"
    copy_solution "solutions/the-ledger/services/agentcore_policy.py" \
                  "pellier/backend/services/agentcore_policy.py" "AgentCore policy (Cedar)"
    copy_solution "solutions/the-ledger/services/agentcore_identity.py" \
                  "pellier/backend/services/agentcore_identity.py" "AgentCore identity"
    copy_solution "solutions/the-ledger/services/cognito_auth.py" \
                  "pellier/backend/services/cognito_auth.py" "Cognito auth helper"
    copy_solution "solutions/the-ledger/services/otel_trace_extractor.py" \
                  "pellier/backend/services/otel_trace_extractor.py" "OTEL trace extractor"

    # ---- Frontend agent-identity hook ----
    # The Boutique chat drawer reads this to attach an identity claim
    # to every agent call. The auth.ts + AuthModal/PreferencesModal
    # solutions also live in solutions/the-ledger/frontend/ but
    # the 60-min Builder's Session runs in demo mode (AUTH_MODE=demo)
    # so we skip them.
    copy_solution "solutions/the-ledger/frontend/agentIdentity.ts" \
                  "pellier/frontend/src/utils/agentIdentity.ts" "Frontend agent identity"

    # ---- AgentCore Runtime pre-launch (~5 min, best-effort) ----
    log "Pre-launching AgentCore Runtime (pellier-agent)..."
    export REPO_PATH="$REPO_PATH"
    RUNTIME_ARN=""
    if command -v agentcore &>/dev/null && command -v python3.13 &>/dev/null; then
        RUNTIME_ARN=$(sudo -u "$CODE_EDITOR_USER" bash -c "
            export PATH=\"\$HOME/.local/bin:\$PATH\"
            export AWS_REGION=$AWS_REGION
            export AWS_DEFAULT_REGION=$AWS_REGION
            export REPO_PATH=$REPO_PATH
            python3.13 $REPO_PATH/scripts/provision_agentcore_runtime.py 2>/dev/null
        " 2>/dev/null || true)
    fi
    if [ -n "$RUNTIME_ARN" ]; then
        log "✅ AgentCore Runtime provisioned: $RUNTIME_ARN"
        grep -q '^AGENTCORE_RUNTIME_ENDPOINT=' "$REPO_PATH/.env" 2>/dev/null && \
            sed -i "s|^AGENTCORE_RUNTIME_ENDPOINT=.*|AGENTCORE_RUNTIME_ENDPOINT=$RUNTIME_ARN|" "$REPO_PATH/.env" || \
            echo "AGENTCORE_RUNTIME_ENDPOINT=$RUNTIME_ARN" >> "$REPO_PATH/.env"
        grep -q '^USE_AGENTCORE_RUNTIME=' "$REPO_PATH/.env" 2>/dev/null && \
            sed -i 's|^USE_AGENTCORE_RUNTIME=.*|USE_AGENTCORE_RUNTIME=true|' "$REPO_PATH/.env" || \
            echo "USE_AGENTCORE_RUNTIME=true" >> "$REPO_PATH/.env"
        chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.env"
    else
        warn "AgentCore Runtime pre-launch skipped — Runtime demo uses in-process fallback"
        grep -q '^USE_AGENTCORE_RUNTIME=' "$REPO_PATH/.env" 2>/dev/null || \
            echo "USE_AGENTCORE_RUNTIME=false" >> "$REPO_PATH/.env"
    fi

    chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/pellier/"

    # Builders format: run uvicorn with --reload instead of the systemd
    # service. Participants edit .py files → save → uvicorn auto-restarts.
    # Zero friction, no split terminals, no manual commands.
    systemctl stop pellier 2>/dev/null || true

    # Build frontend once (same as ExecStartPre in the systemd unit)
    log "Building frontend SPA for builders format..."
    cd "$REPO_PATH/pellier/backend" && sudo -u "$CODE_EDITOR_USER" python3 generate_mcp_config.py 2>/dev/null || true
    cd "$REPO_PATH/pellier/frontend" && VITE_BASE_PATH=/ports/8000/ sudo -u "$CODE_EDITOR_USER" npm run build
    cd "$REPO_PATH"

    # Start uvicorn with --reload as the workshop user. This runs in the
    # background and logs to /tmp/pellier/uvicorn.log. The terminal auto-open
    # (welcome script) will tail this log so participants see it live.
    log "Starting uvicorn with --reload (builders mode)..."
    sudo -u "$CODE_EDITOR_USER" bash -c "
        cd $REPO_PATH/pellier/backend
        source $REPO_PATH/.env
        export PATH=/home/$CODE_EDITOR_USER/.local/bin:\$PATH
        nohup uvicorn app:app --host 0.0.0.0 --port 8000 --reload \
            >> /tmp/pellier/uvicorn.log 2>&1 &
        echo \$! > /tmp/pellier/uvicorn.pid
    "

    sleep 5
    if [ -f /tmp/pellier/uvicorn.pid ] && kill -0 "$(cat /tmp/pellier/uvicorn.pid)" 2>/dev/null; then
        log "✅ Builders: uvicorn running with --reload (PID $(cat /tmp/pellier/uvicorn.pid))"
    else
        warn "uvicorn --reload failed to start — check /tmp/pellier/uvicorn.log"
    fi

    log "✅ Builders solutions applied, uvicorn running with --reload"
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
echo "✅ Pellier Backend (FastAPI + Strands) installed"
echo "✅ Pellier Frontend (React) dependencies installed"
echo "✅ Database setup complete (40 products + warehouse inventory)"
echo "✅ MCP server config written to pellier/config/mcp-server-config.json"
echo "✅ Bash environment configured (psql ready)"
if [ "${WORKSHOP_FORMAT:-workshop}" = "builders" ]; then
    echo "✅ Builder's Session: uvicorn --reload on :8000 (systemd unit not used)"
else
    echo "✅ pellier systemd service enabled (single process on :8000)"
fi
echo ""
echo "🌐 App is live at: https://<cloudfront>/ports/8000/"
echo "   Frontend + API both served by one uvicorn process."
echo "   Edits to pellier/frontend/src/ require a rebuild:"
if [ "${WORKSHOP_FORMAT:-workshop}" = "builders" ]; then
    echo "     rebuild-frontend    # npm run build + restart uvicorn (no sudo)"
else
    echo "     rebuild-frontend    # npm run build + sudo systemctl restart pellier (passwordless)"
fi
echo ""
echo "Quick Commands:"
echo "  psql                             # Connect to database"
if [ "${WORKSHOP_FORMAT:-workshop}" = "builders" ]; then
    echo "  tail -f /tmp/pellier/uvicorn.log   # Backend log (builders)"
else
    echo "  journalctl -fu pellier           # Service logs (workshop)"
fi
echo "  rebuild-frontend                 # Rebuild SPA + restart app"
echo ""
log "=========================================="

exit 0