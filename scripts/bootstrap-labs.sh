#!/bin/bash
# Pellier Workshop - Stage 2: Labs Bootstrap
# Optimizations: Parallel pip installs, reduced redundancy, faster execution
# Duration: ~12-15 minutes

set -euo pipefail

# ============================================================================
# PARAMETERS & LOGGING
# ============================================================================
CODE_EDITOR_USER="${CODE_EDITOR_USER:-participant}"
HOME_FOLDER="${HOME_FOLDER:-/workshop}"
REPO_NAME="sample-pellier-agentic-search-apg"
REPO_PATH="$HOME_FOLDER/$REPO_NAME"
AWS_REGION="${AWS_REGION:-us-east-1}"
AGENTCORE_CLI_VERSION="${AGENTCORE_CLI_VERSION:-1.0.0-preview.26}"
PLAYWRIGHT_MCP_VERSION="${PLAYWRIGHT_MCP_VERSION:-0.0.79}"
PLAYWRIGHT_BROWSER_VERSION="${PLAYWRIGHT_BROWSER_VERSION:-1.63.0-alpha-2026-08-05}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"; }
fail() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"; exit 1; }
# Every component value below is probed, never asserted. This file used to
# hardcode all four as "ready" regardless of reality, so it reported a
# healthy workshop before the backend had even been launched. A status file
# that cannot be wrong is not a status file.
probe_component() {
    # probe_component <name> -> echoes "ready" or "not_ready"
    local what="$1"
    case "$what" in
        backend)
            curl -fs --max-time 5 http://localhost:8000/api/health 2>/dev/null \
                | grep -q '"status".*"healthy"' && echo ready || echo not_ready
            ;;
        frontend)
            # The backend answers /api even with no Vite bundle, so check that
            # / returns the SPA document a participant actually sees.
            curl -fs --max-time 5 http://localhost:8000/ 2>/dev/null \
                | grep -qiE '<!doctype html|<div id="root"' \
                && echo ready || echo not_ready
            ;;
        database)
            curl -fs --max-time 5 http://localhost:8000/api/health 2>/dev/null \
                | grep -q '"database".*"connected"' && echo ready || echo not_ready
            ;;
        memory)
            # Live means the control-plane resource is ACTIVE *and* the
            # backend resolved it; an id in .env alone is not readiness.
            curl -fs --max-time 5 \
                http://localhost:8000/api/agentcore/memory/status 2>/dev/null \
                | grep -q '"live":[[:space:]]*true' && echo ready || echo not_ready
            ;;
        *) echo not_ready ;;
    esac
}

write_status_json() {
    local status="$1"
    local managed_status="$2"
    local managed_path="$3"
    local c_backend c_frontend c_database c_memory
    c_backend="$(probe_component backend)"
    c_frontend="$(probe_component frontend)"
    c_database="$(probe_component database)"
    c_memory="$(probe_component memory)"
    cat > /tmp/workshop-ready.json << EOF
{
    "status": "${status}",
    "timestamp": "$(date -Iseconds)",
    "stage": "labs-bootstrap",
    "components_source": "probed at write time; not asserted",
    "components": {
        "pellier_backend": "${c_backend}",
        "pellier_frontend": "${c_frontend}",
        "database_config": "${c_database}",
        "agentcore_memory": "${c_memory}"
    },
    "builders_managed_path": {
        "status": "${managed_status}",
        "details_path": "${managed_path}"
    }
}
EOF
    chmod 644 /tmp/workshop-ready.json
}
upsert_env() {
    local key="$1"
    local value="$2"
    local env_file="$3"
    if grep -q "^${key}=" "$env_file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$env_file"
    else
        echo "${key}=${value}" >> "$env_file"
    fi
}

# .pgpass is colon-delimited; libpq requires a backslash before any literal
# ':' or '\' inside a field. Escape backslashes FIRST so the escape character
# introduced by the second substitution is never itself re-escaped.
pgpass_escape() {
  local value=$1
  value=${value//\\/\\\\}
  value=${value//:/\\:}
  printf '%s' "$value"
}

log "=========================================="
log "Pellier Stage 2: Labs Bootstrap (Optimized)"
log "=========================================="

# ============================================================================
# STEP 1: CLONE REPOSITORY (~30 sec)
# ============================================================================
# On a Workshop Studio box the CloudFormation UserData has already cloned the
# repo at an immutable pinned SHA (RepoRevision) into exactly this path, and it
# exports WORKSHOP_SOURCE_REVISION as the provenance record. So the branch below
# is NOT the event path -- it is the local-dev / manual-rerun fallback, which
# gets whatever origin/HEAD points at. Everything after the clone assumes the
# tree is present, so a failure here must stop rather than warn-and-continue.
REPO_URL="${REPO_URL:-https://github.com/aws-samples/sample-pellier-agentic-search-apg.git}"

log "Cloning repository..."
if [ ! -d "$REPO_PATH" ]; then
    # --depth 1: .git is deleted moments later, so full history is pure
    # download cost. 2>&1 into a variable, not 2>/dev/null: the old code
    # discarded the one line that says why the clone failed.
    clone_log=$(sudo -u "$CODE_EDITOR_USER" git clone --depth 1 \
        "$REPO_URL" "$REPO_PATH" 2>&1) \
        || fail "Clone of ${REPO_URL} failed: ${clone_log}"

    # Record what was delivered BEFORE .git is removed. Unlike the CFN path
    # there is no RepoRevision to consult, so this file is the only
    # post-provision answer to "which content is this box running?".
    resolved_sha=$(sudo -u "$CODE_EDITOR_USER" git -C "$REPO_PATH" rev-parse HEAD 2>/dev/null || echo unknown)
    sudo -u "$CODE_EDITOR_USER" tee "$REPO_PATH/.workshop-ref.json" >/dev/null << EOF
{
    "repo_url": "${REPO_URL}",
    "repo_ref": "<default-branch>",
    "resolved_sha": "${resolved_sha}",
    "cloned_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "clone_path": "bootstrap-fallback"
}
EOF

    rm -rf "$REPO_PATH/.git"
    log "✅ Repository cloned (default branch @ ${resolved_sha:0:8})"
else
    log "✅ Repository exists"
fi

# Remove .git on BOTH paths, not just the fallback.
#
# The fallback above always deleted it. The event path did not, so a Workshop
# Studio box shipped with a live detached checkout at the pinned SHA and the
# workspace stayed on live git. `"git.enabled": false` hides the Source Control
# panel, but the terminal is untouched: `git checkout -- .` silently reverts the
# floor_check exercise a participant is midway through, and `git stash` or
# `git reset --hard` loses it with no visible trace. Neither is a thing anyone
# does on purpose; both are things people type out of habit.
#
# Safe to remove here because nothing downstream reads it:
#   - the pinned-SHA assertion runs in CloudFormation UserData, before this
#     script (`git rev-parse HEAD` = RepoRevision),
#   - provenance on the event path is WORKSHOP_SOURCE_REVISION, exported by the
#     same UserData, and on the fallback path .workshop-ref.json written above,
#   - no application code shells out to git,
#   - no exercise instructs a participant to run git.
if [ -d "$REPO_PATH/.git" ]; then
    # Record provenance for the event path too, so "which content is this box
    # running?" has a file answer after .git is gone, not just an env var that
    # dies with the shell.
    if [ ! -f "$REPO_PATH/.workshop-ref.json" ]; then
        event_sha=$(sudo -u "$CODE_EDITOR_USER" git -C "$REPO_PATH" rev-parse HEAD 2>/dev/null || echo unknown)
        sudo -u "$CODE_EDITOR_USER" tee "$REPO_PATH/.workshop-ref.json" >/dev/null << EOF
{
    "repo_url": "${REPO_URL}",
    "repo_ref": "${WORKSHOP_SOURCE_REVISION:-<pinned>}",
    "resolved_sha": "${event_sha}",
    "cloned_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "clone_path": "cloudformation-userdata"
}
EOF
    fi
    rm -rf "$REPO_PATH/.git"
    log "✅ Workspace detached from git (participants cannot revert the exercise)"
fi

# ============================================================================
# STEP 2: FETCH DB CREDENTIALS (~10 sec)
# ============================================================================
log "Fetching database credentials..."
export DB_HOST="" DB_PORT="5432" DB_USER="" DB_PASSWORD="" DB_NAME="${DB_NAME:-pellier}"

if [ -n "${DB_SECRET_ARN:-}" ]; then
    DB_SECRET=$(aws secretsmanager get-secret-value --secret-id "$DB_SECRET_ARN" --region "$AWS_REGION" --query SecretString --output text 2>/dev/null || echo "")
    if [ -n "$DB_SECRET" ]; then
        export DB_HOST=$(echo "$DB_SECRET" | jq -r '.host // empty')
        export DB_USER=$(echo "$DB_SECRET" | jq -r '.username // empty')
        export DB_PASSWORD=$(echo "$DB_SECRET" | jq -r '.password // empty')
        export DB_NAME=$(echo "$DB_SECRET" | jq -r --arg default_db "${DB_NAME:-pellier}" '.dbname // .database // $default_db')
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
# VITE_COGNITO_* drive the real sign-in (no demo mode). They come from
# .pellier-env, which CloudFormation populated with the live pool/client.
# The redirect URI resolves from window.location.origin at runtime
# (AuthContext.tsx), so it is intentionally not baked in here.
[ -d "$REPO_PATH/pellier/frontend" ] && cat > "$REPO_PATH/pellier/frontend/.env" << EOF
VITE_API_URL=
VITE_BASE_PATH=/ports/8000/
VITE_AWS_REGION=$AWS_REGION
VITE_ENABLE_LAB2=true
VITE_COGNITO_DOMAIN=${VITE_COGNITO_DOMAIN:-}
VITE_COGNITO_CLIENT_ID=${VITE_COGNITO_CLIENT_ID:-}
EOF

# Backend/Root .env (if DB available)
if [ -n "$DB_HOST" ]; then
    DB_CLUSTER_ARN="${DB_CLUSTER_ARN:-}"
    if [ -z "$DB_CLUSTER_ARN" ]; then
        DB_CLUSTER_ARN="arn:aws:rds:${AWS_REGION}:$(aws sts get-caller-identity --query Account --output text):cluster:pellier-cluster"
    fi

    # URL-encode the password for DATABASE_URL. Aurora master secrets
    # routinely contain @ : / ? % which must be percent-encoded inside
    # a postgresql:// URL or psycopg will misparse the string.
    DB_PASSWORD_URLENC=$(python3 -c "import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=''))" "$DB_PASSWORD")

    # Write the .env with single-quoted values so a downstream
    # `set -a; source .env; set +a` reads them as literals. Without
    # the quotes, any $ in DB_PASSWORD would expand at source time
    # — a real failure mode where a generated password containing
    # `$Z…` triggered "unbound variable" errors under `set -u`.
    #
    # DB_PASSWORD and PGPASSWORD use bash's ${VAR@Q} quoting transform rather
    # than a hand-written '${DB_PASSWORD}' literal, so this line does not
    # depend on the master secret ever excluding a literal single quote. The
    # secret is in fact generated with ExcludeCharacters '"@/\'' (i.e. " @ /
    # \ ') — see MasterSecret.GenerateSecretString in assets/pellier-database.yml
    # in both Workshop Studio repos that consume this source. @Q removes the
    # dependency for every consumer that is a shell, which is most of them
    # (`source .env`). It does NOT remove it for systemd: the pellier.service
    # unit below reads this same file via EnvironmentFile=, and systemd parses
    # it with its own simple syntax, not a shell. For a value containing a
    # literal single quote, @Q emits the shell idiom 'a'\'''b', which systemd
    # does not understand. So the systemd path is still safe only because the
    # secret excludes '\'''. Measured: @Q emits plain single-quoted output for
    # $, backtick, ;, backslash and space, so those are genuinely covered.
    # Widening ExcludeCharacters to permit a quote would break the unit while
    # leaving every shell site correct — a hard failure to trace.
    #
    # The secret also does NOT exclude ':', which is why the .pgpass write
    # below goes through pgpass_escape instead of trusting the character set.
    cat > "$REPO_PATH/.env" << EOF
DB_SECRET_ARN='${DB_SECRET_ARN:-}'
DB_CLUSTER_ARN='${DB_CLUSTER_ARN}'
DB_HOST='${DB_HOST}'
DB_PORT='${DB_PORT}'
DB_NAME='${DB_NAME}'
DB_USER='${DB_USER}'
DB_PASSWORD=${DB_PASSWORD@Q}
DATABASE_URL='postgresql://${DB_USER}:${DB_PASSWORD_URLENC}@${DB_HOST}:${DB_PORT}/${DB_NAME}'
PGHOST='${DB_HOST}'
PGPORT='${DB_PORT}'
PGUSER='${DB_USER}'
PGPASSWORD=${DB_PASSWORD@Q}
PGDATABASE='${DB_NAME}'
AWS_REGION='${AWS_REGION}'
AWS_DEFAULT_REGION='${AWS_REGION}'
BEDROCK_EMBEDDING_MODEL='${BEDROCK_EMBEDDING_MODEL:-us.cohere.embed-v4:0}'
BEDROCK_RERANK_MODEL='${BEDROCK_RERANK_MODEL:-cohere.rerank-v3-5:0}'
BEDROCK_CHAT_MODEL='${BEDROCK_CHAT_MODEL:-global.anthropic.claude-opus-4-8}'
WORKSHOP_ID='${WORKSHOP_ID:-}'
WORKSHOP_FORMAT='${WORKSHOP_FORMAT:-builders}'
USE_AGENTCORE_RUNTIME='false'
AGENTCORE_MEMORY_ID=''
AUTH_MODE='${AUTH_MODE:-cognito}'
COGNITO_USER_POOL_ID='${COGNITO_USER_POOL_ID:-}'
COGNITO_POOL_ID='${COGNITO_USER_POOL_ID:-}'
COGNITO_CLIENT_ID='${COGNITO_CLIENT_ID:-}'
COGNITO_DOMAIN='${VITE_COGNITO_DOMAIN:-}'
APP_BASE_PATH='/ports/8000'
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
    # Route every field through pgpass_escape, not just the password. The
    # master secret's ExcludeCharacters (MasterSecret.GenerateSecretString in
    # assets/pellier-database.yml, both Workshop Studio repos that consume
    # this source) excludes " @ / \ ' but NOT ':', so an unescaped colon in a
    # generated password silently shifts every later field and psql fails
    # auth against a .pgpass that looks correct. This is a per-deploy coin
    # flip: the password regenerates on every stack.
    printf '%s:%s:%s:%s:%s\n' \
        "$(pgpass_escape "$DB_HOST")" \
        "$(pgpass_escape "$DB_PORT")" \
        "$(pgpass_escape "$DB_NAME")" \
        "$(pgpass_escape "$DB_USER")" \
        "$(pgpass_escape "$DB_PASSWORD")" \
        > "$PGPASS_DIR/.pgpass"
    chmod 600 "$PGPASS_DIR/.pgpass"
    chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$PGPASS_DIR/.pgpass"

    log "✅ Environment files created (.env, .pgpass)"

    # Prove the connection a participant will actually make, now, rather than
    # letting Lab 1 discover it. Deliberately run AS the participant with only
    # HOME and the PG* variables set: no PGPASSWORD, so a pass means .pgpass was
    # found, readable at 0600, and correct. Running this as root with the
    # script's own PGPASSWORD would prove something no participant does.
    if sudo -u "$CODE_EDITOR_USER" env -i \
            HOME="$PGPASS_DIR" \
            PATH="/usr/bin:/bin" \
            PGHOST="$DB_HOST" PGPORT="$DB_PORT" \
            PGUSER="$DB_USER" PGDATABASE="$DB_NAME" \
            PGSSLMODE=require PGCONNECT_TIMEOUT=15 \
            psql -X -Atc 'SELECT 1' >/dev/null 2>&1; then
        log "✅ Participant psql reaches Aurora over TLS via .pgpass"
    else
        # Not fatal: the labs that matter use the application, and a table lead
        # can recover a shell. But it must be loud, because every SQL proof in
        # the guide is typed as a bare `psql`.
        warn "Participant psql could NOT reach Aurora (checked as $CODE_EDITOR_USER with .pgpass, sslmode=require)"
        warn "  every bare 'psql' step in the guide will fail until this is fixed"
    fi
else
    warn "Database credentials not available - skipping DB configuration"
fi

# Fix permissions
chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH"

# ============================================================================
# STEP 4: VERIFY PYTHON DEPENDENCIES
# ============================================================================
# Stage 1 (bootstrap-environment.sh) already installed everything in
# pellier/backend/requirements.lock. Re-running the install here would
# either no-op (best case) or duplicate work without changing the
# environment. We just verify the critical packages reached
# /home/$CODE_EDITOR_USER/.local — if Stage 1's pip failed silently,
# we want to catch it here before the seeder runs and hits
# ModuleNotFoundError.
log "Verifying Python dependencies..."
if sudo -u "$CODE_EDITOR_USER" python3 -c "import boto3, fastapi, uvicorn, psycopg, strands" 2>/dev/null; then
    log "✅ Backend dependencies verified"
else
    warn "Some backend dependencies are missing — re-running pip install"
    if [ -f "$REPO_PATH/pellier/backend/requirements.lock" ]; then
        sudo -u "$CODE_EDITOR_USER" python3 -m pip install --user \
            -r "$REPO_PATH/pellier/backend/requirements.lock" 2>&1 \
            | tee -a /var/log/pellier-pip-install.log >/dev/null
        if sudo -u "$CODE_EDITOR_USER" python3 -c "import boto3, fastapi, uvicorn, psycopg, strands" 2>/dev/null; then
            log "✅ Backend dependencies recovered"
        else
            warn "Backend dependencies still missing after retry — pellier service will fail to start"
            warn "  see /var/log/pellier-pip-install.log"
        fi
    else
        fail "requirements.lock is missing; backend dependencies are not reproducible"
    fi
fi

# ============================================================================
# STEP 7: INSTALL UV (~30 sec)
# ============================================================================
log "Installing uv..."
if ! sudo -u "$CODE_EDITOR_USER" bash -c 'export PATH="$HOME/.local/bin:$PATH" && command -v uv' &>/dev/null; then
    sudo -u "$CODE_EDITOR_USER" bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' &>/dev/null || \
    sudo -u "$CODE_EDITOR_USER" python3 -m pip install --user uv &>/dev/null
fi
uv_bin="$(
    sudo -u "$CODE_EDITOR_USER" bash -c \
        'export PATH="$HOME/.local/bin:$PATH" && command -v uv' 2>/dev/null \
        || true
)"
if [ -n "$uv_bin" ] \
    && sudo -u "$CODE_EDITOR_USER" "$uv_bin" --version &>/dev/null; then
    ln -sf "$uv_bin" /usr/local/bin/uv
    /usr/local/bin/uv --version &>/dev/null \
        || fail "uv could not be exposed to bootstrap and participant shells"
    log "✅ uv installed and usable (${uv_bin})"
else
    fail "uv is missing or unusable; required participant Python commands cannot run"
fi

# ============================================================================
# STEP 8b: BEDROCK MODEL-ACCESS PREFLIGHT (~10 sec)
# ============================================================================
# Fail fast and loud if the runtime models aren't enabled in this account.
# Without this, a missing grant surfaces much later as an empty storefront
# or a dead chat turn mid-session. Cohere Embed v4 is hard-required because
# every shopper query is embedded live before the pgvector search (the cache
# only covers the catalog corpus). The same preflight also resolves the
# independent Claude Code CLI model for Lab 2.
log "Preflight: checking Bedrock model access (${AWS_REGION})..."
if [ -f "$REPO_PATH/scripts/check_model_access.py" ]; then
    if sudo -u "$CODE_EDITOR_USER" bash -c "
        export AWS_REGION='${AWS_REGION:-us-east-1}'
        cd '$REPO_PATH'
        python3 scripts/check_model_access.py --write-env '$REPO_PATH/pellier/backend/.env'
    " 2>&1 | tee /var/log/model-access-preflight.log; then
        log "✅ Bedrock model-access preflight passed"
        # The preflight writes the exact accessible Sonnet generation,
        # including AGENT_MODEL_ID for Runtime. Load it into this shell before
        # STEP 16 spawns the provisioner.
        set -a
        source "$REPO_PATH/.env"
        set +a
    else
        fail "Bedrock model-access preflight failed; see /var/log/model-access-preflight.log"
    fi
else
    fail "check_model_access.py not found; cannot verify required Bedrock models"
fi

# ============================================================================
# STEP 9-10: PARALLEL FRONTEND + DATABASE (~8 min vs 8.5 min)
# ============================================================================
log "Setting up frontend and database (parallel)..."

setup_frontend() {
    if [ -d "$REPO_PATH/pellier/frontend" ]; then
        cd "$REPO_PATH/pellier/frontend"
        # npm ci is reproducible (uses package-lock.json verbatim) and
        # fails loudly when the lock is out of sync — the right behavior
        # for a controlled workshop env. Output goes to a log file, not
        # /dev/null, so install failures aren't invisible.
        if [ -f package-lock.json ]; then
            sudo -u "$CODE_EDITOR_USER" npm ci \
                >> /var/log/pellier-npm-install.log 2>&1
        else
            warn "package-lock.json missing — falling back to npm install"
            sudo -u "$CODE_EDITOR_USER" npm install \
                >> /var/log/pellier-npm-install.log 2>&1
        fi
    fi
}

setup_database() {
    if [ -n "$DB_HOST" ] && [ -f "$REPO_PATH/scripts/seed_pellier_catalog.py" ]; then
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
        # makes the cluster Pellier-ready. Runs first because the
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

        # ---- 2. Pellier catalog seeder — 40 hand-curated products
        # across the four personas (Marco / Anna / Theo / Fresh).
        # Authoritative source for pellier.product_catalog.
        #
        # Embeddings come from the COMMITTED cache (data/embeddings_cache.json)
        # via --from-cache. The catalog never changes between runs, so we
        # generate Cohere Embed v4 vectors once (committed) instead of calling
        # Bedrock on every account. This removes the slowest, most
        # throttle-prone step from the bootstrap critical path and makes the
        # seed a deterministic SQL load. To regenerate the cache after a
        # catalog change, run `python scripts/seed_pellier_catalog.py --csv-only`
        # on a machine with Bedrock access and commit the updated cache.
        #
        # Must run as $CODE_EDITOR_USER: psycopg is installed via
        # `pip install --user` for that user in Stage 1, so root's python3
        # cannot import it. Without sudo -u the seeder dies with
        # ModuleNotFoundError and the catalog stays empty — cascading silent
        # failures into 003's persona-orders JOIN. ----
        # DB_USER/DB_PASSWORD are passed via `env NAME=value`, never
        # interpolated into the bash -c string, so a literal ' or \ in the
        # generated password cannot break out of shell quoting here. (The
        # master secret's ExcludeCharacters excludes " @ / \ ' today — see
        # MasterSecret.GenerateSecretString in assets/pellier-database.yml,
        # both Workshop Studio repos — but this site does not depend on it.)
        sudo -u "$CODE_EDITOR_USER" env \
            DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" \
            DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" \
            AWS_REGION="$AWS_REGION" \
            ASSETS_BUCKET_NAME="${ASSETS_BUCKET_NAME:-}" \
            ASSETS_BUCKET_PREFIX="${ASSETS_BUCKET_PREFIX:-}" \
            DATABASE_URL="$DATABASE_URL" \
            REPO_PATH="$REPO_PATH" \
            bash -c 'cd "$REPO_PATH" && python3 scripts/seed_pellier_catalog.py --from-cache' \
            2>&1 | tee /var/log/database-setup.log
        local seed_rc=${PIPESTATUS[0]}
        if [ "$seed_rc" -ne 0 ]; then
            warn "Pellier catalog seed failed (rc=$seed_rc) — see /var/log/database-setup.log"
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
            008_search_performance_indexes.sql \
            009_return_policies.sql \
            010_governed_receipts.sql \
            011_governed_write_integrity.sql \
            012_retrieval_receipts.sql \
            013_inventory_ledger.sql
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
                warn "Required migration $migration not found"
                return 1
            fi
        done

        # ---- 4. Tool registry seed — populates pellier.tools (created
        # empty by migration 002) with the 9 canonical Gateway tool names
        # plus their Cohere Embed v4 descriptions. Pellier Labs
        # Observatory's tool-registry tab and the pgvector
        # tool-discovery card both read from this table and silently
        # render zero rows if the seed is skipped. ----
        if [ -f "$REPO_PATH/scripts/seed_tool_registry.py" ]; then
            log "Seeding pellier.tools registry..."
            # Same env-passing rationale as the seeder call above — no
            # credential is interpolated into a string a nested shell parses.
            sudo -u "$CODE_EDITOR_USER" env \
                DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" \
                DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" \
                AWS_REGION="$AWS_REGION" \
                DATABASE_URL="$DATABASE_URL" \
                REPO_PATH="$REPO_PATH" \
                bash -c 'cd "$REPO_PATH" && python3 scripts/seed_tool_registry.py' \
                2>&1 | tee -a /var/log/database-setup.log
            local tool_rc=${PIPESTATUS[0]}
            if [ "$tool_rc" -ne 0 ]; then
                warn "Tool registry seed failed (rc=$tool_rc) — Pellier Labs tool-registry tab will show zero rows"
            fi
        fi

        return 0
    fi
    return 1
}

setup_frontend & PID_FE=$!
setup_database & PID_DB=$!
FRONTEND_SETUP_OK=true
wait "$PID_FE" || FRONTEND_SETUP_OK=false
if wait "$PID_DB"; then
    log "✅ Database setup complete (40 Pellier products, HNSW index, workshop tables)"
else
    fail "Database setup failed; see /var/log/database-setup.log"
fi
if [ "$FRONTEND_SETUP_OK" = "true" ]; then
    log "✅ Frontend dependencies installed"
else
    fail "Frontend dependency installation failed; see /var/log/pellier-npm-install.log"
fi

# ============================================================================
# STEP 10b: OPTIONAL BROWSER PREVIEW TOOLING
# ============================================================================
# Claude Code uses this MCP server only when a participant asks it to preview
# or test the running app. It is intentionally outside the required exercise
# path and must never make the storefront bootstrap fail.
log "Installing optional Playwright MCP browser tooling..."
PLAYWRIGHT_LOG="/var/log/pellier-playwright-mcp.log"
if sudo -u "$CODE_EDITOR_USER" bash -c "
    export HOME='/home/$CODE_EDITOR_USER'
    export PATH='/usr/local/bin:/usr/bin:/bin'
    mkdir -p \"\$HOME/.cache/ms-playwright\" /tmp/pellier-playwright
    npx -y 'playwright@${PLAYWRIGHT_BROWSER_VERSION}' install chromium
    claude mcp remove playwright --scope user >/dev/null 2>&1 || true
    claude mcp add --scope user playwright -- \
        npx -y '@playwright/mcp@${PLAYWRIGHT_MCP_VERSION}' \
        --headless --isolated --output-dir /tmp/pellier-playwright
" >>"$PLAYWRIGHT_LOG" 2>&1; then
    log "✅ Playwright MCP ready for Claude Code browser preview"
else
    warn "Playwright MCP setup failed; core workshop remains ready. See $PLAYWRIGHT_LOG"
fi

# ============================================================================
# STEP 10c: REQUIRED AGENTCORE MEMORY
# ============================================================================
# Runtime, Gateway, and Policy remain optional in the one-hour workshop.
# AgentCore Memory does not depend on those services, so provision it as an
# independent CLI resource and use it for storefront session turns.
log "Provisioning required AgentCore Memory..."
MEMORY_OUTPUT_JSON="/tmp/pellier-agentcore-memory.json"
MEMORY_LOG="/var/log/pellier-agentcore-memory.log"
if ! sudo -u "$CODE_EDITOR_USER" bash -c "
    export HOME='/home/$CODE_EDITOR_USER'
    export PATH='/usr/bin:/usr/local/bin:\$HOME/.local/bin:\$PATH'
    set -a
    source '$REPO_PATH/.env'
    set +a
    export AWS_REGION='$AWS_REGION'
    export AWS_DEFAULT_REGION='$AWS_REGION'
    export WORKSHOP_ID='${WORKSHOP_ID:-unknown}'
    export REPO_PATH='$REPO_PATH'
    python3 '$REPO_PATH/scripts/provision_agentcore_memory.py' \
        --repo-path '$REPO_PATH' \
        --output-json '$MEMORY_OUTPUT_JSON'
" 2>&1 | tee "$MEMORY_LOG"; then
    fail "Required AgentCore Memory provisioning failed; see $MEMORY_LOG"
fi

MEMORY_ID="$(jq -r '.memory.memory_id // empty' "$MEMORY_OUTPUT_JSON")"
MEMORY_STATUS="$(jq -r '.memory.resource_status // empty' "$MEMORY_OUTPUT_JSON")"
PROVISION_STATUS="$(jq -r '.status // empty' "$MEMORY_OUTPUT_JSON")"
if [ -z "$MEMORY_ID" ] \
    || [ "$MEMORY_STATUS" != "ACTIVE" ] \
    || [ "$PROVISION_STATUS" != "ready" ]; then
    fail "Required AgentCore Memory did not reach ACTIVE; see $MEMORY_OUTPUT_JSON"
fi

upsert_env "AGENTCORE_MEMORY_ID" "$MEMORY_ID" "$REPO_PATH/.env"
upsert_env "USE_AGENTCORE_RUNTIME" "false" "$REPO_PATH/.env"
chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.env"
if [ -d "$REPO_PATH/.agentcore-project" ]; then
    chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.agentcore-project/"
fi
log "Required AgentCore Memory is ACTIVE: $MEMORY_ID"

# ============================================================================
# STEP 11: CREATE START SCRIPTS (~5 sec)
# ============================================================================
log "Creating start scripts..."

# Single-process model: FastAPI on :8000 serves both /api/* and the
# built SPA. The legacy start-frontend.sh / http-server on 5173 is
# gone — attendees point their browser at /ports/8000/* only.
# Single source of truth for the restart command is
# scripts/start-backend-builders.sh (safe `set -a; source .env` env
# loading — avoids the unquoted-env word-splitting bug that bit us with
# special chars in DB passwords). This convenience wrapper just delegates
# so there is exactly ONE definition of "how the backend restarts".
cat > "$REPO_PATH/pellier/start-backend.sh" << EOF
#!/bin/bash
# Convenience wrapper — delegates to the canonical builders start script.
# Do not duplicate the uvicorn invocation here; edit
# scripts/start-backend-builders.sh instead.
exec "$REPO_PATH/scripts/start-backend-builders.sh" "\$@"
EOF

chmod +x "$REPO_PATH/pellier/start-backend.sh"
chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/pellier/start-backend.sh"
log "✅ Start scripts created"

# ============================================================================
# STEP 12: BASH ENVIRONMENT (~5 sec)
# ============================================================================
log "Configuring bash environment..."

# Managed block, not a bare `cat >>`. A second bootstrap run (a stack
# update, or a manual re-run to recover from a failed step) used to
# duplicate every export and alias below verbatim. Stripping any
# previously-installed block before re-appending makes this idempotent.
# Reference pattern: setup_code_editor_bashrc() and its atomic_write helper in
# self-service-workshop-on-pgvector-for-generative-ai-use-cases/assets/prereq.sh
# (~line 492 and ~line 876) — adapted here rather than copied verbatim.
BASHRC="/home/$CODE_EDITOR_USER/.bashrc"
BASHRC_BEGIN='# BEGIN PELLIER WORKSHOP ENV'
BASHRC_END='# END PELLIER WORKSHOP ENV'
BASHRC_TMP="${BASHRC}.tmp.$$"

if [ -f "$BASHRC" ]; then
    awk -v b="$BASHRC_BEGIN" -v e="$BASHRC_END" '
        $0 == b { inblock = 1; next }
        $0 == e { inblock = 0; next }
        !inblock { print }
    ' "$BASHRC" > "$BASHRC_TMP"
else
    : > "$BASHRC_TMP"
fi

{
printf '%s\n' "$BASHRC_BEGIN"
cat << 'EOF'

# ============================================================================
# Pellier Workshop Environment
# ============================================================================

# Readable colored prompt (matches the dat403 workshop look): bold-green
# user, bold-blue path, then reset to default (light) for the $ and
# everything you type. The green/white contrast makes the active command
# line easy to find when scrolling back through output during the lab.
export PS1='\[\033[01;32m\]\u:\[\033[01;34m\]\w\[\033[00m\]\$ '

if [ -f /workshop/sample-pellier-agentic-search-apg/.env ]; then
    set -a
    source /workshop/sample-pellier-agentic-search-apg/.env
    set +a

    # Explicitly export PostgreSQL variables for psql
    export PGHOST
    export PGPORT
    export PGUSER
    export PGDATABASE
    # PGPASSWORD is deliberately NOT exported here. .pgpass (written by
    # bootstrap-labs.sh, mode 0600, fields escaped via pgpass_escape) is what
    # psql actually uses; exporting the password too would leak it into every
    # child process's environment for no benefit, and would mask a broken
    # .pgpass instead of surfacing it — the whole point of the participant
    # env -i proof run during bootstrap.
    #
    # Aurora accepts TLS but does not force it unless rds.force_ssl is set on
    # the cluster parameter group, so ask for it here rather than trusting
    # that setting alone.
    export PGSSLMODE=require
fi

# Workshop Navigation Aliases
alias workshop='cd /workshop/sample-pellier-agentic-search-apg'
alias pellier='cd /workshop/sample-pellier-agentic-search-apg/pellier'
alias backend='cd /workshop/sample-pellier-agentic-search-apg/pellier/backend'
alias frontend='cd /workshop/sample-pellier-agentic-search-apg/pellier/frontend'

# One-shot readiness check for the required participant path
alias health='bash /workshop/sample-pellier-agentic-search-apg/scripts/health-gate.sh'

# AgentCore CLI (pinned preview release). The one-hour agent runtime stays
# in-process, while required Memory and optional managed resources share the
# same declarative CLI project.
# Running from the project root lets the CLI resolve deployed-state.json.
agentcore() {
    ( cd /workshop/sample-pellier-agentic-search-apg/.agentcore-project/pellier 2>/dev/null \
        && if _ac_bin="$(type -P agentcore)"; then "$_ac_bin" "$@"; else npx -y @aws/agentcore@1.0.0-preview.26 "$@"; fi )
}

# Pellier service shortcuts — see FORMAT_ALIASES below (workshop vs builders).

# Database Shortcut (psql uses PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE from .env)
alias psql='psql'

# AWS Region for boto3
export AWS_DEFAULT_REGION=${AWS_REGION:-us-east-1}

# Claude Code CLI → Amazon Bedrock (Claude Code lane, Ex 1).
# CLAUDE_CODE_USE_BEDROCK=1 makes the CLI authenticate through THIS box's IAM
# instance role (the same ambient-credential chain used elsewhere in the lab)
# - no Anthropic API key, per-participant login, or secret to paste.
# Model: pinned to the global Sonnet 4.6 inference profile. Workshop Studio
# accounts do not expose the Claude 5 family, so the floating `sonnet` alias
# (which a current CLI resolves to Sonnet 5 on Bedrock) would be DENIED at the
# event. The pin matches the app's tested Sonnet profile.
export CLAUDE_CODE_USE_BEDROCK=1
export ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-global.anthropic.claude-sonnet-4-6}
export AWS_REGION=${AWS_REGION:-us-east-1}
# The CLI is installed globally as root (/usr/bin/claude) but runs as the
# participant user, so its auto-updater can't write the root-owned npm prefix
# and warns once at startup ("Auto-update failed: no write permission..."). The
# warning is harmless, but this composite flag suppresses it at the source by
# disabling all non-essential phone-home (auto-updater + telemetry + error
# reporting + feedback) — the right posture for a root-managed workshop box.
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

# Ensure participant-installed Python tools are in PATH.
export PATH="$HOME/.local/bin:$PATH"

# Auto-navigate to workshop directory on terminal open
if [ "$PWD" = "$HOME" ] || [ "$PWD" = "/workshop" ]; then
    cd /workshop/sample-pellier-agentic-search-apg 2>/dev/null || true
fi
EOF
# Format-specific aliases (builders: no sudo; workshop: systemctl — passwordless via STEP 14 sudoers)
# Both formats run the backend via the pellier systemd unit (builders gets
# --reload baked into ExecStart). The backend is ALWAYS running, so
# `start-backend` is really "restart" and most participants never need it.
# `rebuild-frontend` is only for the rare .tsx edit (the lab is backend Python).
cat << 'ALS'
# --- Pellier aliases (systemd unit ``pellier``, serves SPA + /api on :8000) ---
# Backend runs automatically and (builders) reloads on .py save — you normally
# never run these. Restart only if you want a clean bounce.
alias start-backend='sudo systemctl restart pellier && journalctl -fu pellier --no-pager'
alias rebuild-frontend='bash /workshop/sample-pellier-agentic-search-apg/scripts/rebuild-frontend-builders.sh'
ALS
printf '%s\n' "$BASHRC_END"
} >> "$BASHRC_TMP"

mv "$BASHRC_TMP" "$BASHRC"
chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$BASHRC"
chmod 644 "$BASHRC"

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
if sudo -u "$CODE_EDITOR_USER" python3 -c "import fastapi, uvicorn, strands" 2>/dev/null; then
    log "✅ Pellier Backend dependencies verified"
else
    warn "⚠️  Some Pellier Backend dependencies may be missing"
fi

# ============================================================================
# STEP 14: AUTO-START PELLIER SERVICE (single-process, port 8000)
# ============================================================================
# Single systemd service. FastAPI serves:
#   - the built SPA at /, /pellier-labs, /storyboard, /discover, ...
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

# --- pellier.service: build frontend (best-effort), then run uvicorn ---
#
# ONE unit for BOTH formats. The only per-format difference is whether
# uvicorn carries --reload: builders participants edit .py files and want
# live restarts on save; workshop format runs static. Everything else —
# Restart=always, boot-survival, best-effort frontend build — is identical.
#
# RELOAD_ARGS is computed here so there is a single heredoc, not two.
# --reload-dir pins the watch to the backend dir (avoids watching
# frontend/node_modules and re-triggering on dist/ writes).
if [ "${WORKSHOP_FORMAT:-builders}" = "builders" ]; then
    UVICORN_RELOAD_ARGS="--reload --reload-dir $REPO_PATH/pellier/backend"
else
    UVICORN_RELOAD_ARGS=""
fi

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
# ExecStartPre is BEST-EFFORT (leading '-' tells systemd to ignore a
# non-zero exit; '|| true' keeps the bash -c itself at 0). A frontend
# build failure must NEVER block the backend: app.py serves /api/* even
# when dist/ is absent (the SPA 404s with a clear log line). This is the
# fix for the prior failure mode where an unguarded npm run build under
# set -e aborted bootstrap before uvicorn ever started.
ExecStartPre=-/bin/bash -c 'cd $REPO_PATH/pellier/frontend && npm run build || true'
ExecStart=/home/$CODE_EDITOR_USER/.local/bin/uvicorn app:app --host 0.0.0.0 --port 8000 $UVICORN_RELOAD_ARGS
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

# Enable + start the single service for BOTH formats. builders gets
# --reload (baked into ExecStart above); workshop runs static. The
# frontend build is best-effort inside ExecStartPre, so the backend
# always comes up on :8000 even if the build or AgentCore provisioning
# fails. No format branch, no separate nohup path.
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
write_status_json "in_progress" "pending" ""
log "✅ Status marker created"

# ============================================================================
# STEP 16: WORKSHOP FORMAT — Pre-apply everything participants don't build
# ============================================================================
#
# Lab 2 wires the floor_check tool body in services/agent_tools.py,
# grants it to Stock Keeper, and observes the live Strands call. Both gaps are
# installed and verified below before provisioning may report success.
#
# This block copies finished reference files from solutions/ into
# their runtime locations under pellier/backend/ and pellier/frontend/.
# Every src path is verified against the actual repo layout — if
# you add new pre-applies, double-check both src and dest exist.
#
# Solutions directory layout:
#   solutions/the-quiet-search/   — retrieval reference (observe-only)
#   solutions/closing-marcos-gap/ — the required-path (the only edited module)
#   solutions/the-ledger/    — governance reference (observe-only)
#
# Files participants complete:
#   agent_tools.py — the floor_check tool body
#   stock_keeper.py — the floor_check entry in INVENTORY_AGENT_TOOLS
if [ "${WORKSHOP_FORMAT:-builders}" = "builders" ]; then
    log "=========================================="
    log "Workshop: pre-applying reference files"
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
    # Curator handles recommendation turns (find_pieces_hybrid, style_match).
    # Experience Guide handles returns/care (returns_and_care, process_return,
    # escalate_to_stylist). Orchestrator is the dispatcher that routes between them.
    copy_solution "solutions/closing-marcos-gap/agents/curator.py" \
                  "pellier/backend/agents/curator.py" "Curator agent"
    copy_solution "solutions/closing-marcos-gap/agents/experience_guide.py" \
                  "pellier/backend/agents/experience_guide.py" "Experience Guide agent"
    copy_solution "solutions/closing-marcos-gap/agents/orchestrator.py" \
                  "pellier/backend/agents/orchestrator.py" "Orchestrator"

    # ---- Required starter state: fail closed ----
    #
    # Do not use the warning-only copy helper for participant gaps. A missing
    # starter overlay must fail UserData rather than silently ship completed
    # source to one or more accounts.
    python3 "$REPO_PATH/scripts/builders_starter.py" \
        --repo "$REPO_PATH" apply
    python3 "$REPO_PATH/scripts/builders_starter.py" \
        --repo "$REPO_PATH" verify --expect starter
    log "  builders: verified floor_check body + Stock Keeper grant are incomplete"

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
    # Policy is managed by the pinned AgentCore CLI project. The old local
    # policy emulator was removed; services/managed_policy.py is a read-only
    # inspection adapter, so there is no policy service to copy here.
    copy_solution "solutions/the-ledger/services/agentcore_identity.py" \
                  "pellier/backend/services/agentcore_identity.py" "AgentCore identity"
    copy_solution "solutions/the-ledger/services/cognito_auth.py" \
                  "pellier/backend/services/cognito_auth.py" "Cognito auth helper"
    copy_solution "solutions/the-ledger/services/otel_trace_extractor.py" \
                  "pellier/backend/services/otel_trace_extractor.py" "OTEL trace extractor"

    # ---- Frontend agent-identity hook ----
    # The Pellier chat drawer reads this to attach an identity claim to
    # every agent call. auth.ts + AuthModal + PreferencesModal +
    # AuthContext already ship complete in the live frontend tree (real
    # Cognito sign-in, no demo mode), so only the agent-identity hook is
    # dropped in here; the rest are not overwritten.
    copy_solution "solutions/the-ledger/frontend/agentIdentity.ts" \
                  "pellier/frontend/src/utils/agentIdentity.ts" "Frontend agent identity"

    if [ "${ENABLE_BUILDERS_MANAGED_PATH:-false}" = "true" ]; then
    # ---- AgentCore full managed path (explicit opt-in only) ----
    #
    # AgentCore provisioning is best-effort, NOT a hard gate. A failure here
    # must never abort the bootstrap: the backend still launches below and the
    # app degrades gracefully (STM falls back to Aurora session tables, and the
    # optional Runtime lab shows a clear "Runtime not provisioned" state
    # rather than the whole environment coming up with no backend and no logs).
    # The health gate at the end reports AgentCore readiness explicitly.
    log "Provisioning full AgentCore managed path (Lambdas + Gateway + Runtime)..."
    export REPO_PATH="$REPO_PATH"
    MANAGED_OUTPUT_JSON="/tmp/pellier-agentcore-managed.json"
    AGENTCORE_OK=true

    # Keep both variable names during the transition; backend config resolves
    # either COGNITO_POOL_ID or COGNITO_USER_POOL_ID.
    export COGNITO_POOL="${COGNITO_POOL:-${COGNITO_POOL_ID:-${COGNITO_USER_POOL_ID:-}}}"
    export COGNITO_CLIENT="${COGNITO_CLIENT:-${COGNITO_CLIENT_ID:-}}"

    # Persist every provisioning INPUT to a recovery file so an operator can
    # re-run scripts/deploy/deploy_all.sh by hand if STEP 16 fails. These come
    # from CFN outputs and are in scope only here in UserData — they are NOT in
    # backend/.env (which holds runtime config, not provisioning inputs) and
    # vanish from an interactive shell. deploy_all.sh auto-sources this file.
    # Written BEFORE provisioning runs so it exists even on a failed deploy.
    PROVISION_ENV="$REPO_PATH/.provision.env"
    cat > "$PROVISION_ENV" << EOF
# Pellier provisioning inputs (CFN outputs) — auto-sourced by scripts/deploy/deploy_all.sh.
# Written by bootstrap-labs.sh STEP 16. Safe to re-source; contains no secrets
# beyond ARNs (the actual DB password lives in Secrets Manager, referenced by ARN).
export AWS_REGION='${AWS_REGION}'
export AWS_DEFAULT_REGION='${AWS_REGION}'
export STACKNAME='${STACKNAME:-${WORKSHOP_STACK_NAME:-}}'
export PGHOSTARN='${DB_CLUSTER_ARN:-}'
export PGSECRET='${DB_SECRET_ARN:-}'
export PGDATABASE='${DB_NAME:-pellier}'
export DB_CLUSTER_ARN='${DB_CLUSTER_ARN:-}'
export DB_SECRET_ARN='${DB_SECRET_ARN:-}'
export DB_NAME='${DB_NAME:-pellier}'
export COGNITO_POOL='${COGNITO_POOL:-}'
export COGNITO_CLIENT='${COGNITO_CLIENT:-}'
export COGNITO_TEST_CREDENTIALS_SECRET_ARN='${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}'
export COGNITO_CLIENT_SECRET_ARN='${COGNITO_CLIENT_SECRET_ARN:-}'
export WORKSHOP_ID='${WORKSHOP_ID:-unknown}'
export AGENT_MODEL_ID='${AGENT_MODEL_ID:-}'
EOF
    chmod 600 "$PROVISION_ENV" 2>/dev/null || true
    chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$PROVISION_ENV" 2>/dev/null || true
    log "Wrote provisioning recovery file: $PROVISION_ENV"

    if ! command -v npx &>/dev/null || ! command -v python3 &>/dev/null; then
        warn "Missing npx or python3 — skipping managed AgentCore provisioning (backend will still start)"
        write_status_json "failed" "failed" "$MANAGED_OUTPUT_JSON"
        AGENTCORE_OK=false
    fi

    # The pinned CLI requires Node 20 or newer. Fail the optional managed
    # provisioning beat cleanly if the base image fell back to an older runtime.
    if [ "$AGENTCORE_OK" = true ]; then
        _ac_node_major="$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)"
        if ! echo "$_ac_node_major" | grep -qE '^[0-9]+$' || [ "$_ac_node_major" -lt 20 ]; then
            warn "Node $(node --version 2>/dev/null || echo 'none') (<20) — @aws/agentcore Runtime deploy cannot run. Skipping managed AgentCore provisioning; Pellier still starts. Fix: install Node 20 (see bootstrap-environment.sh) and re-run scripts/deploy/deploy_all.sh."
            write_status_json "failed" "failed" "$MANAGED_OUTPUT_JSON"
            AGENTCORE_OK=false
        fi
    fi

    # Tee the full provisioning run (incl. `agentcore deploy` stdout/stderr) to
    # a dedicated log so a failed run has a single, predictable place to look —
    # /var/log/pellier-agentcore.log — instead of grepping the master bootstrap
    # log. pipefail propagates the python3 exit status through the pipe.
    AGENTCORE_LOG="/var/log/pellier-agentcore.log"
    if [ "$AGENTCORE_OK" = true ] && ! sudo -u "$CODE_EDITOR_USER" bash -c "
        export PATH=\"/usr/bin:/usr/local/bin:\$HOME/.local/bin:\$PATH\"
        set -a
        source '$REPO_PATH/.env'
        set +a
        node --version  # log the node the CLI will actually use
        export AWS_REGION='$AWS_REGION'
        export AWS_DEFAULT_REGION='$AWS_REGION'
        export REPO_PATH='$REPO_PATH'
        export DB_CLUSTER_ARN='${DB_CLUSTER_ARN:-}'
        export DB_SECRET_ARN='${DB_SECRET_ARN:-}'
        export DB_NAME='${DB_NAME:-pellier}'
        export COGNITO_POOL='${COGNITO_POOL:-}'
        export COGNITO_CLIENT='${COGNITO_CLIENT:-}'
        export COGNITO_TEST_CREDENTIALS_SECRET_ARN='${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}'
        export COGNITO_CLIENT_SECRET_ARN='${COGNITO_CLIENT_SECRET_ARN:-}'
        export WORKSHOP_ID='${WORKSHOP_ID:-unknown}'
        export AGENT_MODEL_ID='${AGENT_MODEL_ID:-}'
        python3 '$REPO_PATH/scripts/provision_agentcore_end_to_end.py' \
            --repo-path '$REPO_PATH' \
            --output-json '$MANAGED_OUTPUT_JSON'
    " 2>&1 | tee "$AGENTCORE_LOG"; then
        warn "Managed AgentCore provisioning failed; see $AGENTCORE_LOG and $MANAGED_OUTPUT_JSON (backend will still start)"
        write_status_json "failed" "failed" "$MANAGED_OUTPUT_JSON"
        AGENTCORE_OK=false
    fi

    if [ "$AGENTCORE_OK" = true ]; then
        RUNTIME_ARN="$(jq -r '.runtime.runtime_arn // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        MEMORY_ID="$(jq -r '.memory.memory_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        GATEWAY_ID="$(jq -r '.gateway.gateway_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        GATEWAY_URL="$(jq -r '.gateway.gateway_url // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        GATEWAY_ARN="$(jq -r '.gateway.gateway_arn // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        POLICY_ENGINE_ID="$(jq -r '.policy.policy_engine_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        MANAGED_STATUS="$(jq -r '.status // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        if [ -z "$RUNTIME_ARN" ] || [ -z "$MEMORY_ID" ] \
            || [ -z "$GATEWAY_ID" ] || [ -z "$GATEWAY_URL" ] \
            || [ -z "$GATEWAY_ARN" ] || [ -z "$POLICY_ENGINE_ID" ] \
            || [ "$MANAGED_STATUS" != "ready" ]; then
            warn "Managed provisioning output missing Runtime/Memory/Gateway/Policy readiness (backend will still start)"
            write_status_json "failed" "failed" "$MANAGED_OUTPUT_JSON"
            AGENTCORE_OK=false
        fi
    fi

    if [ "$AGENTCORE_OK" = true ]; then
        upsert_env "AGENTCORE_RUNTIME_ENDPOINT" "$RUNTIME_ARN" "$REPO_PATH/.env"
        upsert_env "AGENTCORE_MEMORY_ID" "$MEMORY_ID" "$REPO_PATH/.env"
        upsert_env "AGENTCORE_GATEWAY_ID" "$GATEWAY_ID" "$REPO_PATH/.env"
        upsert_env "AGENTCORE_GATEWAY_ARN" "$GATEWAY_ARN" "$REPO_PATH/.env"
        upsert_env "AGENTCORE_GATEWAY_URL" "$GATEWAY_URL" "$REPO_PATH/.env"
        # The storefront rail is format-dependent.
        #
        # On the builders format the managed path is an OPTIONAL flex, not the
        # required path. Flipping USE_AGENTCORE_RUNTIME=true here would route
        # every shopper turn through the Runtime container, whose tools execute
        # in the Gateway's Lambda target (scripts/deploy/pellier_search_server.py)
        # — NOT the in-process services/agent_tools.py the participant edits in
        # Lab 2, and NOT the stock_keeper.py grant they add. Lab 2's two edits
        # would silently become no-ops while the lab still reported success.
        # Keep the storefront in-process; the flex invokes the Runtime directly
        # with `uv run scripts/builders_lab.py runtime`, which reads
        # AGENTCORE_RUNTIME_ENDPOINT written just above.
        if [ "${WORKSHOP_FORMAT:-builders}" = "builders" ]; then
            upsert_env "USE_AGENTCORE_RUNTIME" "false" "$REPO_PATH/.env"
            log "Runtime recorded for the optional flex; storefront stays in-process"
        else
            upsert_env "USE_AGENTCORE_RUNTIME" "true" "$REPO_PATH/.env"
        fi
        if [ -n "$POLICY_ENGINE_ID" ]; then
            upsert_env "AGENTCORE_POLICY_ENGINE_ID" "$POLICY_ENGINE_ID" "$REPO_PATH/.env"
            log "✅ Managed AgentCore Policy engine: $POLICY_ENGINE_ID"
        fi
        chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.env"
        write_status_json "complete" "ready" "$MANAGED_OUTPUT_JSON"
        log "✅ AgentCore managed path ready"
    else
        warn "AgentCore managed path NOT ready — continuing so the backend launches. The health gate will flag this; see $AGENTCORE_LOG, then re-run provisioning to recover the Runtime/Gateway path."
        # Preserve CLI-created resources for diagnosis, but never set the
        # Runtime endpoint after a failed live proof.
        PARTIAL_MEMORY_ID="$(jq -r '.memory.memory_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        PARTIAL_GATEWAY_ID="$(jq -r '.gateway.gateway_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        PARTIAL_GATEWAY_URL="$(jq -r '.gateway.gateway_url // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        PARTIAL_GATEWAY_ARN="$(jq -r '.gateway.gateway_arn // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        PARTIAL_POLICY_ID="$(jq -r '.policy.policy_engine_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        if [ -n "$PARTIAL_MEMORY_ID" ]; then
            upsert_env "AGENTCORE_MEMORY_ID" "$PARTIAL_MEMORY_ID" "$REPO_PATH/.env"
            log "Recorded CLI-managed Memory id despite failed proof"
        fi
        if [ -n "$PARTIAL_GATEWAY_ID" ]; then
            upsert_env "AGENTCORE_GATEWAY_ID" "$PARTIAL_GATEWAY_ID" "$REPO_PATH/.env"
        fi
        if [ -n "$PARTIAL_GATEWAY_URL" ]; then
            upsert_env "AGENTCORE_GATEWAY_URL" "$PARTIAL_GATEWAY_URL" "$REPO_PATH/.env"
            log "Recorded live Gateway endpoint despite failed proof"
        fi
        if [ -n "$PARTIAL_GATEWAY_ARN" ]; then
            upsert_env "AGENTCORE_GATEWAY_ARN" "$PARTIAL_GATEWAY_ARN" "$REPO_PATH/.env"
        fi
        if [ -n "$PARTIAL_POLICY_ID" ]; then
            upsert_env "AGENTCORE_POLICY_ENGINE_ID" "$PARTIAL_POLICY_ID" "$REPO_PATH/.env"
            log "Salvaged live Policy engine id into .env despite failed provisioning"
        fi
        chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.env" 2>/dev/null || true
    fi

    # Recursively re-own the app tree as the participant.
    chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/pellier/"

    # The AgentCore project lives at REPO level (.agentcore-project/), OUTSIDE
    # backend_dir — the CodeZip packager copies the whole code-location, so a
    # project rooted inside it copied itself recursively (ENAMETOOLONG,
    # box-verified 2026-06-12). Own it for the participant so the `agentcore`
    # function can read agentcore/.cli/deployed-state.json — the file
    # `agentcore status` needs. If you ever narrow this chown, keep the
    # .agentcore-project subtree participant-owned or the cloud-inspection beat breaks.
    if [ -d "$REPO_PATH/.agentcore-project" ]; then
        chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.agentcore-project/"
    fi

    if [ "$(command agentcore --version 2>/dev/null || true)" != "$AGENTCORE_CLI_VERSION" ]; then
        fail "Pinned AgentCore CLI $AGENTCORE_CLI_VERSION is unavailable"
    fi
    else
        write_status_json "complete" "not_applicable" ""
        log "Required Memory is ready; skipping optional Runtime, Gateway, and Policy"
    fi

    # Participant edits and service reloads need ownership regardless of
    # whether the managed path was explicitly enabled.
    chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/pellier/"

    # The pellier.service unit (STEP 14) already runs uvicorn with --reload
    # for builders format and rebuilds the frontend in ExecStartPre. Now
    # that the solution files are in place, restart the unit
    # once so it picks them up. systemd owns the process - no nohup, no PID
    # file, no second backend fighting for :8000. A restart failure is
    # non-fatal (the health gate reports it); --reload keeps the live-edit DX.
    log "Restarting pellier service to pick up builders solutions..."
    systemctl restart pellier || warn "pellier restart failed — check: journalctl -u pellier"

    sleep 8
    if systemctl is-active --quiet pellier; then
        log "✅ Builders: pellier service running with --reload (systemd)"
    else
        warn "pellier service not active after restart — check: journalctl -u pellier"
    fi

    log "✅ Builders solutions applied, pellier service restarted"
fi

if [ "${WORKSHOP_FORMAT:-builders}" != "builders" ]; then
    write_status_json "complete" "not_applicable" ""
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
# STEP 17b: PRE-BAKE THE OPTIONAL BEARER TOKEN HELPER
# ============================================================================
# The optional managed-Policy exercise runs on the authenticated Gateway rail and
# needs a Cognito access token. In a self-paced room (no facilitator to unblock
# a failed `admin-initiate-auth`), typing that command is the #1 friction +
# failure mode. So we pre-bake a one-command helper that mints a FRESH token
# (tokens expire ~1h, so we generate on demand rather than bake a stale one):
#
#     source ~/pellier-token.sh      # sets $PELLIER_TOKEN for the curl below
#
# The participant never types Cognito plumbing — they get the learning (managed
# Cedar gates at the Gateway), not the auth ceremony. Identity is still REAL:
# the token is a genuine Cognito JWT the Gateway validates.
if [ "${ENABLE_BUILDERS_MANAGED_PATH:-false}" = "true" ] \
    && [ -n "${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}" ] \
    && [ -n "${COGNITO_POOL:-${COGNITO_POOL_ID:-}}" ]; then
    log "Writing optional token helper (~/pellier-token.sh)..."
    _TOKEN_POOL="${COGNITO_POOL:-${COGNITO_POOL_ID}}"
    _TOKEN_CLIENT="${COGNITO_CLIENT:-${COGNITO_CLIENT_ID:-}}"
    # The participant's ~ is /home/$CODE_EDITOR_USER, NOT $HOME_FOLDER
    # (/workshop) — writing only to $HOME_FOLDER made `source
    # ~/pellier-token.sh` a No-such-file (box-verified 2026-06-12). Write to
    # the real home; symlink at $HOME_FOLDER for any content that used it.
    _TOKEN_HELPER="/home/$CODE_EDITOR_USER/pellier-token.sh"
    cat > "$_TOKEN_HELPER" <<TOKENEOF
#!/usr/bin/env bash
# Mint a fresh Cognito access token for the optional authenticated beat.
# Usage:  source ~/pellier-token.sh          # default persona (Marco)
#         source ~/pellier-token.sh anna     # mint Anna's token instead
#         source ~/pellier-token.sh theo     # mint Theo's
# The Cognito users are named after the personas, so the access token carries
# the chosen name (the access token's \`username\` claim, lowercased — NOT
# cognito:username, that's the ID token; box-verified 2026-06-12) through the
# JWT-gated Gateway – identity passthrough you can see. Case-insensitive match;
# an unknown/no arg falls back to the first user (Marco). Sets \$PELLIER_TOKEN.
_want="\${1:-}"
_creds=\$(aws secretsmanager get-secret-value \\
  --secret-id "$COGNITO_TEST_CREDENTIALS_SECRET_ARN" --region "$AWS_REGION" \\
  --query SecretString --output text 2>/dev/null)
_u=\$(echo "\$_creds" | python3 -c 'import sys,json;w=(sys.argv[1] if len(sys.argv)>1 else "").strip().lower();us=json.load(sys.stdin)["users"];print(next((x for x in us if x["username"].lower()==w), us[0])["username"])' "\$_want" 2>/dev/null)
_p=\$(echo "\$_creds" | python3 -c 'import sys,json;w=(sys.argv[1] if len(sys.argv)>1 else "").strip().lower();us=json.load(sys.stdin)["users"];print(next((x for x in us if x["username"].lower()==w), us[0])["password"])' "\$_want" 2>/dev/null)
# The app client is configured WITH a secret, so admin-initiate-auth must
# send SECRET_HASH = b64(hmac-sha256(client_secret, username+client_id)) or
# Cognito rejects with NotAuthorizedException (box-verified 2026-06-12).
_ap="USERNAME=\$_u,PASSWORD=\$_p"
_csarn='${COGNITO_CLIENT_SECRET_ARN:-}'
if [ -n "\$_csarn" ]; then
  _csec=\$(aws secretsmanager get-secret-value --secret-id "\$_csarn" --region "$AWS_REGION" --query SecretString --output text 2>/dev/null)
  _csec=\$(echo "\$_csec" | python3 -c 'import sys,json;s=sys.stdin.read().strip();print(json.loads(s).get("client_secret",s) if s.startswith("{") else s)' 2>/dev/null)
  _sh=\$(python3 -c 'import sys,hmac,hashlib,base64;u,c,k=sys.argv[1:4];print(base64.b64encode(hmac.new(k.encode(),(u+c).encode(),hashlib.sha256).digest()).decode())' "\$_u" "$_TOKEN_CLIENT" "\$_csec" 2>/dev/null)
  [ -n "\$_sh" ] && _ap="\$_ap,SECRET_HASH=\$_sh"
fi
export PELLIER_TOKEN=\$(aws cognito-idp admin-initiate-auth \\
  --user-pool-id "$_TOKEN_POOL" --client-id "$_TOKEN_CLIENT" \\
  --auth-flow ADMIN_USER_PASSWORD_AUTH \\
  --auth-parameters "\$_ap" \\
  --query 'AuthenticationResult.AccessToken' --output text 2>/dev/null)
if [ -n "\$PELLIER_TOKEN" ] && [ "\$PELLIER_TOKEN" != "None" ]; then
  echo "✅ \$PELLIER_TOKEN minted for \$_u (use: -H \"Authorization: Bearer \\\$PELLIER_TOKEN\")"
else
  echo "✗ Token mint failed – check Cognito provisioning (/var/log/pellier-agentcore.log)"
fi
TOKENEOF
    chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$_TOKEN_HELPER" 2>/dev/null || true
    ln -sf "$_TOKEN_HELPER" "$HOME_FOLDER/pellier-token.sh" 2>/dev/null || true
    log "✅ Optional token helper ready: source ~/pellier-token.sh"
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
echo "✅ Bash environment configured (psql ready)"
if [ "${WORKSHOP_FORMAT:-builders}" = "builders" ]; then
    echo "✅ pellier systemd service enabled — uvicorn --reload on :8000 (live .py edits)"
else
    echo "✅ pellier systemd service enabled (single process on :8000)"
fi
echo ""
echo "🌐 App is live at: https://<cloudfront>/ports/8000/"
echo "   Frontend + API both served by one uvicorn process (systemd)."
echo "   Edits to pellier/backend/*.py reload automatically (builders)."
echo "   Edits to pellier/frontend/src/ require: rebuild-frontend"
echo ""
echo "Quick Commands:"
echo "  psql                             # Connect to database"
echo "  journalctl -fu pellier           # Backend service log (both formats)"
echo "  rebuild-frontend                 # Rebuild SPA + restart app"
echo "  health                           # One-shot core readiness check"
echo ""

# ============================================================================
# STEP 19: POST-BOOT HEALTH GATE
# ============================================================================
# One consolidated PASS/FAIL summary so the facilitator sees readiness at a
# glance. Non-fatal: bootstrap already finished; this only reports. Give the
# backend a moment to come up first (builders launches uvicorn in STEP 16).
if [ -x "$REPO_PATH/scripts/health-gate.sh" ]; then
    log "Running post-boot health gate..."
    sleep 5
    sudo -u "$CODE_EDITOR_USER" bash -c "
        export PELLIER_REPO='$REPO_PATH'
        bash '$REPO_PATH/scripts/health-gate.sh'
    " 2>&1 | tee /var/log/pellier-health-gate.log || \
        warn "Core health gate reported NOT READY — see /var/log/pellier-health-gate.log"
fi

log "=========================================="

exit 0
