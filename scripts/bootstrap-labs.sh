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
# This branch is the governed flagship. Every in-script branch below reads this one
# value, so an operator who runs bootstrap without exporting it gets the governed
# path rather than silently taking the builders path on a governed checkout.
WORKSHOP_FORMAT="${WORKSHOP_FORMAT:-governed}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"; }
fail() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"; set_provision_state FAILED; exit 1; }

# ----------------------------------------------------------------------------
# Provisioning state machine.
#
# One word in one file answers "how far did bootstrap actually get" for
# CloudFormation, for the health gate, and for an operator on the box:
#
#   PROVISIONING   bootstrap has started
#   APP_READY      the pellier service answered /api/health
#   MANAGED_READY  the managed Runtime, Gateway, Memory and Policy proof passed
#   E2E_PROVED     the post-boot health gate passed in the governed format
#   FAILED         any fatal path (every one of them goes through fail() above)
#
# bootstrap-environment.sh signals CloudFormation SUCCESS only from E2E_PROVED
# (governed) or APP_READY and later (builders). health-gate.sh requires
# E2E_PROVED in the governed format outside bootstrap's own proving runs.
# The directory is shared with the reset's quarantine marker and is
# group-writable by the participant so reset can write and clear that marker
# without a sudoers entry naming the file.
# ----------------------------------------------------------------------------
PELLIER_STATE_DIR="/var/lib/pellier"
PROVISION_STATE_FILE="${PELLIER_PROVISION_STATE_FILE:-/var/lib/pellier/provision-state}"
set_provision_state() {
    local state="$1"
    mkdir -p "$(dirname "$PROVISION_STATE_FILE")" 2>/dev/null || true
    if printf '%s\n' "$state" > "$PROVISION_STATE_FILE" 2>/dev/null; then
        chmod 0644 "$PROVISION_STATE_FILE" 2>/dev/null || true
        log "Provision state: ${state}"
    else
        warn "Could not record provision state ${state} at $PROVISION_STATE_FILE"
    fi
}
mkdir -p "$PELLIER_STATE_DIR"
chown "root:$CODE_EDITOR_USER" "$PELLIER_STATE_DIR" 2>/dev/null \
    || warn "Could not group-own $PELLIER_STATE_DIR for $CODE_EDITOR_USER; reset cannot write its quarantine marker"
chmod 0775 "$PELLIER_STATE_DIR"
set_provision_state PROVISIONING

write_status_json() {
    local status="$1"
    local managed_status="$2"
    local managed_path="$3"
    cat > /tmp/workshop-ready.json << EOF
{
    "status": "${status}",
    "timestamp": "$(date -Iseconds)",
    "stage": "labs-bootstrap",
    "components": {
        "pellier_backend": "ready",
        "pellier_frontend": "ready",
        "database_config": "ready"
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

# The branch IS the workshop: `governed` carries the flagship two-hour lab set,
# `main` the one-hour builders session. Deriving the branch from WORKSHOP_FORMAT
# is what stops the two from ever disagreeing -- the clone used to pass no
# --branch at all, so it took whatever origin/HEAD resolved to. That is `main`,
# which has no workshop/, no WORKSHOP.md and no VOICE.md, so a governed run on
# this path installed the wrong workshop, warn-and-skipped ~30 migrations, and
# still printed a success line.
case "${WORKSHOP_FORMAT}" in
    governed) WORKSHOP_BRANCH="${WORKSHOP_BRANCH:-governed}" ;;
    *)        WORKSHOP_BRANCH="${WORKSHOP_BRANCH:-main}" ;;
esac

log "Cloning repository..."
if [ ! -d "$REPO_PATH" ]; then
    # --depth 1: .git is deleted moments later, so full history is pure
    # download cost. 2>&1 into a variable, not 2>/dev/null: the old code
    # discarded the one line that says why the clone failed.
    clone_log=$(sudo -u "$CODE_EDITOR_USER" git clone --depth 1 \
        --branch "$WORKSHOP_BRANCH" \
        "$REPO_URL" "$REPO_PATH" 2>&1) \
        || fail "Clone of ${REPO_URL} (branch ${WORKSHOP_BRANCH}) failed: ${clone_log}"

    # Record what was delivered BEFORE .git is removed. This is the only
    # post-provision answer to "which content is this box running?". It records
    # the branch actually requested, not a placeholder: a provenance file that
    # says `<default-branch>` is recording that it does not know.
    resolved_sha=$(sudo -u "$CODE_EDITOR_USER" git -C "$REPO_PATH" rev-parse HEAD 2>/dev/null || echo unknown)
    sudo -u "$CODE_EDITOR_USER" tee "$REPO_PATH/.workshop-ref.json" >/dev/null << EOF
{
    "repo_url": "${REPO_URL}",
    "repo_ref": "${WORKSHOP_BRANCH}",
    "resolved_sha": "${resolved_sha}",
    "cloned_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "clone_path": "bootstrap-fallback"
}
EOF

    log "✅ Repository cloned (${WORKSHOP_BRANCH} @ ${resolved_sha:0:8})"
else
    log "✅ Repository exists"
fi

# Assert the tree carries the workshop this run is configured for, on BOTH the
# event path and the fallback. The event path is pinned by CloudFormation, but
# a pinned SHA on the wrong branch is exactly as wrong as an unpinned clone, and
# every step below assumes the content is present. Checking one governed-only
# path is cheaper than discovering it thirty warn-and-skipped migrations later.
if [ "${WORKSHOP_FORMAT}" = "governed" ] && [ ! -d "$REPO_PATH/workshop/starters" ]; then
    fail "WORKSHOP_FORMAT=governed but ${REPO_PATH} has no workshop/starters. \
This tree is not the governed workshop (branch requested: ${WORKSHOP_BRANCH}). \
Re-run with WORKSHOP_BRANCH=governed, or set WORKSHOP_FORMAT to match the tree."
fi

# Remove .git on BOTH paths, not just the fallback.
#
# The fallback above always deleted it. The event path did not, so a Workshop
# Studio box shipped with a live detached checkout at the pinned SHA and the
# workspace stayed on live git. `"git.enabled": false` hides the Source Control
# panel, but the terminal is untouched: `git checkout -- .` silently reverts the
# check_inventory exercise a participant is midway through, and `git stash` loses it
# with no visible trace. Neither is a thing anyone does on purpose; both are
# things people type out of habit.
#
# Safe to remove here because nothing downstream reads it:
#   - the pinned-SHA assertion runs in CloudFormation UserData, before this
#     script (`git rev-parse HEAD` = RepoRevision),
#   - provenance on the event path is WORKSHOP_SOURCE_REVISION, exported by the
#     same UserData, and on the fallback path .workshop-ref.json written above,
#   - no application code shells out to git,
#   - no lab instructs a participant to run git.
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
        DB_HOST=$(echo "$DB_SECRET" | jq -r '.host // empty')
        DB_USER=$(echo "$DB_SECRET" | jq -r '.username // empty')
        DB_PASSWORD=$(echo "$DB_SECRET" | jq -r '.password // empty')
        DB_NAME=$(echo "$DB_SECRET" | jq -r --arg default_db "${DB_NAME:-pellier}" '.dbname // .database // $default_db')
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

    # Cognito's hosted-UI client is confidential. The browser never receives
    # this value, but the server-side authorization-code exchange, refresh, and
    # revoke calls must authenticate with it. CloudFormation exports the
    # Secrets Manager ARN rather than the value itself, so resolve it only on
    # the workshop host and write it only to the private root/backend .env.
    # Never echo the secret or its payload.
    COGNITO_CLIENT_SECRET=""
    if [ -n "${COGNITO_CLIENT_SECRET_ARN:-}" ]; then
        _cognito_secret_payload="$(aws secretsmanager get-secret-value \
            --secret-id "$COGNITO_CLIENT_SECRET_ARN" \
            --region "$AWS_REGION" \
            --query SecretString \
            --output text 2>/dev/null || true)"
        if [ -n "$_cognito_secret_payload" ]; then
            COGNITO_CLIENT_SECRET="$(printf '%s' "$_cognito_secret_payload" | python3 -c '
import json
import sys

raw = sys.stdin.read().strip()
try:
    value = json.loads(raw)
except json.JSONDecodeError:
    value = raw
print(value.get("client_secret", "") if isinstance(value, dict) else value)
' 2>/dev/null || true)"
        fi
        if [ -n "$COGNITO_CLIENT_SECRET" ]; then
            log "✅ Cognito Hosted UI client secret resolved for server-side token exchange"
        else
            warn "⚠️  Cognito Hosted UI client secret could not be resolved; sign-in callback will fail closed"
        fi
    fi

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
    # does not understand, so that path is still safe only because the secret
    # excludes the quote. Measured on bash 5.3: @Q emits plain single-quoted
    # output for $, backtick, ;, backslash and space, so those are covered.
    # Widening ExcludeCharacters to permit a quote would leave every shell site
    # correct and silently break the unit.
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
BEDROCK_CHAT_MODEL='${BEDROCK_CHAT_MODEL:-global.anthropic.claude-opus-4-6-v1}'
BEDROCK_FAST_MODEL='${BEDROCK_FAST_MODEL:-global.anthropic.claude-haiku-4-5-20251001-v1:0}'
WORKSHOP_ID='${WORKSHOP_ID:-dat416}'
WORKSHOP_FORMAT='${WORKSHOP_FORMAT:-governed}'
AUTH_MODE='${AUTH_MODE:-cognito}'
COGNITO_USER_POOL_ID='${COGNITO_USER_POOL_ID:-}'
COGNITO_POOL_ID='${COGNITO_USER_POOL_ID:-}'
COGNITO_CLIENT_ID='${COGNITO_CLIENT_ID:-}'
COGNITO_CLIENT_SECRET=${COGNITO_CLIENT_SECRET@Q}
COGNITO_CLIENT_SECRET_ARN='${COGNITO_CLIENT_SECRET_ARN:-}'
COGNITO_TEST_CREDENTIALS_SECRET_ARN='${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}'
COGNITO_DOMAIN='${COGNITO_DOMAIN:-${VITE_COGNITO_DOMAIN:-}}'
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

else
    warn "Database credentials not available - skipping DB configuration"
fi

# Fix permissions
chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH"

# Install workshop-wide Claude Code guidance without overwriting unrelated
# participant preferences. Re-running bootstrap replaces only this managed
# block, so the file is both idempotent and safe to extend.
CLAUDE_HOME="/home/$CODE_EDITOR_USER/.claude"
GLOBAL_CLAUDE="$CLAUDE_HOME/CLAUDE.md"
GLOBAL_CLAUDE_TMP=$(mktemp)
mkdir -p "$CLAUDE_HOME"

if [ -f "$GLOBAL_CLAUDE" ]; then
    awk '
        $0 == "<!-- PELLIER WORKSHOP GUIDANCE:START -->" { managed = 1; next }
        $0 == "<!-- PELLIER WORKSHOP GUIDANCE:END -->" { managed = 0; next }
        !managed { print }
    ' "$GLOBAL_CLAUDE" > "$GLOBAL_CLAUDE_TMP"
else
    : > "$GLOBAL_CLAUDE_TMP"
fi

cat >> "$GLOBAL_CLAUDE_TMP" << 'CLAUDEEOF'
<!-- PELLIER WORKSHOP GUIDANCE:START -->
# Pellier workshop guidance

- Read the repository `CLAUDE.md` and the nearest nested `CLAUDE.md` before editing.
- Treat Lab 1, Inventory Agent, `check_inventory`, or workshop-marker requests as participant mode. Edit only the named marker block and never inspect `solutions/`.
- In participant mode, do not run git, install packages, change configuration, or restart services. Stop after one failed attempt and use the guide's escape hatch.
- `.claude/skills/*/SKILL.md` contains coding workflows. `skills/*/SKILL.md` contains Pellier runtime prompt overlays; do not treat runtime skills as coding instructions.
- Read `VOICE.md` before changing shopper-facing copy or model prompts.
- Never expose or commit credentials, tokens, customer data, or copied `.env` values. Do not copy account IDs, ARNs, or private endpoints into tracked files.
- Ask before destructive commands or changes outside the current repository.
<!-- PELLIER WORKSHOP GUIDANCE:END -->
CLAUDEEOF

install -o "$CODE_EDITOR_USER" -g "$CODE_EDITOR_USER" -m 0644 \
    "$GLOBAL_CLAUDE_TMP" "$GLOBAL_CLAUDE"
rm -f "$GLOBAL_CLAUDE_TMP"
log "✅ Participant Claude Code guidance installed at $GLOBAL_CLAUDE"

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
if sudo -u "$CODE_EDITOR_USER" python3 -c "import boto3, fastapi, psycopg, strands, uvicorn" 2>/dev/null; then
    log "✅ Backend dependencies verified"
else
    warn "Some backend dependencies are missing — re-running pip install"
    if [ -f "$REPO_PATH/pellier/backend/requirements.lock" ]; then
        sudo -u "$CODE_EDITOR_USER" python3 -m pip install --user \
            --require-hashes -r "$REPO_PATH/pellier/backend/requirements.lock" 2>&1 \
            | tee -a /var/log/pellier-pip-install.log >/dev/null
        if sudo -u "$CODE_EDITOR_USER" python3 -c "import boto3, fastapi, psycopg, strands, uvicorn" 2>/dev/null; then
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
    sudo -u "$CODE_EDITOR_USER" python3 -m pip install --user uv &>/dev/null
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
            python3 generate_mcp_config.py" 2>&1 | tee /var/log/mcp-config-generation.log
        
        if [ -f "$REPO_PATH/pellier/config/mcp-server-config.json" ]; then
            log "✅ MCP config generated at pellier/config/mcp-server-config.json"
            log "   MCP reference ready: awslabs.postgres-mcp-server via uvx"
        else
            warn "MCP config generation failed - will be generated on backend startup"
        fi
    fi
    cd "$REPO_PATH"
else
    log "ℹ️  MCP config will be generated on backend startup"
fi

# ============================================================================
# STEP 8b: BEDROCK MODEL-ACCESS PREFLIGHT (~10 sec)
# ============================================================================
# Fail fast and loud if the runtime models aren't enabled in this account.
# Without this, a missing grant surfaces much later as an empty storefront
# or a dead chat turn mid-session. Cohere Embed v4 is hard-required because
# every shopper query is embedded live before the pgvector search (the cache
# only covers the catalog corpus). The same preflight also resolves the
# independent Claude Code CLI model for Lab 1.
log "Preflight: checking Bedrock model access (${AWS_REGION})..."
if [ -f "$REPO_PATH/scripts/check_model_access.py" ]; then
    if sudo -u "$CODE_EDITOR_USER" bash -c "
        export AWS_REGION='${AWS_REGION:-us-east-1}'
        cd '$REPO_PATH'
        python3 scripts/check_model_access.py --write-env '$REPO_PATH/pellier/backend/.env'
    " 2>&1 | tee /var/log/model-access-preflight.log; then
        log "✅ Bedrock model-access preflight passed"
    else
        warn "❌ Bedrock model-access preflight FAILED — required models not enabled."
        warn "   See /var/log/model-access-preflight.log and enable models at:"
        warn "   https://console.aws.amazon.com/bedrock/home#/modelaccess"
        warn "   Continuing bootstrap so the IDE is usable, but the session will"
        warn "   not work until model access is granted and the seed is re-run."
    fi
else
    warn "check_model_access.py not found — skipping model preflight"
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
            # Bootstrap runs as root and owns this log; npm runs as the participant.
            # shellcheck disable=SC2024
            sudo -u "$CODE_EDITOR_USER" npm ci \
                >> /var/log/pellier-npm-install.log 2>&1
        else
            warn "package-lock.json missing — falling back to npm install"
            # shellcheck disable=SC2024
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

        # ---- 2. Pellier catalog seeder - 60 hand-curated products
        # across the four personas (Marco / Anna / Theo / Fresh), plus
        # generated high-ID archive distractors for retrieval measurement.
        # Authoritative source for pellier.product_catalog.
        #
        # Embeddings come from the COMMITTED cache (data/embeddings_cache.json)
        # via --from-cache. The cache stores the 40 real Cohere vectors; the
        # archive distractors derive deterministic vectors from that committed
        # cache. This removes the slowest, most throttle-prone step from the
        # bootstrap critical path and makes the seed a deterministic SQL load.
        # To regenerate the cache after a curated catalog change, run
        # `python scripts/seed_pellier_catalog.py --csv-only --no-distractors`
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
        # check_inventory. ----
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
            013_inventory_ledger.sql \
            014_governed_turn_receipts.sql \
            015_proof_carrying_commerce.sql \
            016_runtime_roles_rls.sql \
            017_governed_query_receipts.sql \
            018_client_book.sql \
            019_operator_desk.sql \
            020_operator_review.sql \
            021_governed_execution.sql \
            022_write_operation_vocabulary.sql \
            023_idempotency_claims_release_on_failure.sql \
            024_operator_episodes.sql \
            025_execution_receipts.sql \
            026_episode_outcome_lineage.sql \
            027_canonical_span_table.sql \
            028_shopper_operator_handoff.sql \
            029_live_surface_data.sql \
            030_storefront_editorial_order.sql \
            031_refine_fresh_storefront_edit.sql \
            032_restore_fresh_runner_edit.sql \
            033_extend_curated_inventory.sql \
            034_refine_persona_personalities.sql \
            035_expand_persona_discovery_grids.sql \
            036_refresh_persona_hero_alt_text.sql \
            037_serve_persona_hero_masters.sql \
            038_principal_customer_cardinality.sql \
            039_return_replay_scope.sql \
            040_resequence_theo_governed_turn.sql \
            041_align_theo_pairing_preview.sql \
            042_align_anna_guided_previews.sql \
            043_evidence_ledger.sql \
            044_operator_lifecycle_ledger.sql \
            045_persona_blurbs.sql \
            046_retrieval_citation_snapshots.sql \
            047_evidence_immutability.sql \
            048_policy_decisions.sql \
            049_workshop_runs.sql \
            050_refine_guided_questions.sql \
            051_review_requester.sql \
            052_replacement_recovery.sql \
            053_replacement_follow_up.sql \
            054_query_statistics.sql \
            055_governance_boundary_observations.sql
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
        # empty by migration 002) with the 15 canonical Gateway tool names
        # plus their Cohere Embed v4 descriptions. The Observatory
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
                warn "Tool registry seed failed (rc=$tool_rc) — Observatory tool-registry tab will show zero rows"
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
    log "✅ Database setup complete (expanded catalog, HNSW index, workshop tables)"
else
    # Stop before later application/managed milestones can overwrite FAILED.
    fail "Database setup failed; see /var/log/database-setup.log"
fi
if [ "$FRONTEND_SETUP_OK" = "true" ]; then
    log "✅ Frontend dependencies installed"
else
    fail "Frontend dependency installation failed; see /var/log/pellier-npm-install.log"
fi

# Verify the participant connection after database setup has finished and Aurora
# is accepting SQL. A probe before setup can time out while the cluster wakes.
# The clean environment deliberately omits PGPASSWORD: this proves .pgpass and
# the same TLS connection that participants use in every SQL lab.
if sudo -u "$CODE_EDITOR_USER" env -i \
        HOME="$PGPASS_DIR" \
        PATH="/usr/bin:/bin" \
        PGHOST="$DB_HOST" PGPORT="$DB_PORT" \
        PGUSER="$DB_USER" PGDATABASE="$DB_NAME" \
        PGSSLMODE=require PGCONNECT_TIMEOUT=15 \
        psql -X -Atc 'SELECT 1' >/dev/null 2>&1; then
    log "✅ Participant psql reaches Aurora over TLS via .pgpass"
elif [ "$WORKSHOP_FORMAT" = "governed" ]; then
    fail "Participant psql could not reach Aurora after database setup; check .pgpass and connectivity"
else
    warn "Participant psql could not reach Aurora after database setup"
fi

# ============================================================================
# Memory is created once in STEP 16 as part of the same AgentCore CLI project
# as Runtime, Gateway, targets, and Policy. Data-plane seed events are added
# only after the CLI-managed Memory and USER_PREFERENCE strategy are ACTIVE.

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
    # Aurora accepts TLS but does not force it unless rds.force_ssl is set, so
    # ask for it here rather than relying on the cluster parameter group.
    export PGSSLMODE=require
fi

# Workshop Navigation Aliases
alias workshop='cd /workshop/sample-pellier-agentic-search-apg'
alias pellier='cd /workshop/sample-pellier-agentic-search-apg/pellier'
alias backend='cd /workshop/sample-pellier-agentic-search-apg/pellier/backend'
alias frontend='cd /workshop/sample-pellier-agentic-search-apg/pellier/frontend'

# One-shot readiness check (catalog / warehouse / memory id / runtime / health)
alias health='bash /workshop/sample-pellier-agentic-search-apg/scripts/health-gate.sh'

# What this run has actually proved, assembled from the durable evidence the
# four labs leave behind. Also the fastest table-lead diagnostic: it names the
# boundary a stuck participant has not crossed, and distinguishes "no row yet"
# from "could not look", which are different problems.
alias receipt='python3 /workshop/sample-pellier-agentic-search-apg/scripts/build_receipt.py'

# AgentCore CLI (pinned 0.29.0). Labs inspect the managed resources, then add,
# validate, deploy, and remove one participant Cedar policy in the same
# declarative project. A FUNCTION (not an alias) ensures every command runs
# from the project root that owns agentcore/.cli/deployed-state.json.
# It cd's into the deployed project root so the CLI finds
# agentcore/.cli/deployed-state.json from wherever you are, prefers the
# global binary warmed at bootstrap (no registry call), and falls back to the
# pinned npx form if the global install is missing. The app and authenticated
# CLI probes both preserve the workshop's Cognito bearer-token contract.
# The pinned release contract. A fresh deployment must be reproducible no matter
# what happens to be installed on the box, so the pin is ENFORCED rather than
# merely preferred.
AGENTCORE_CLI_PINNED_VERSION="0.29.0"

# Resolve the AgentCore CLI, honouring the pin.
#
# An unrelated global version must not silently replace the workshop's tested
# CLI. Command and generated-project contracts can change between releases.
#
# Order: use a global binary ONLY if its version matches exactly; otherwise fall
# back to the pinned npx invocation. The effective version is printed into
# bootstrap evidence either way, so a deploy can always be attributed.
_agentcore_resolve() {
    local bin observed
    if bin="$(type -P agentcore)"; then
        observed="$("$bin" --version 2>/dev/null | tr -d '[:space:]')"
        if [ "$observed" = "$AGENTCORE_CLI_PINNED_VERSION" ]; then
            printf 'binary\t%s\t%s\n' "$bin" "$observed"
            return 0
        fi
        printf 'pinned\tnpx\t%s (ignoring global %s at %s)\n' \
            "$AGENTCORE_CLI_PINNED_VERSION" "${observed:-unreadable}" "$bin"
        return 0
    fi
    printf 'pinned\tnpx\t%s (no global binary)\n' "$AGENTCORE_CLI_PINNED_VERSION"
}

agentcore() {
    local resolution source effective
    resolution="$(_agentcore_resolve)"
    source="$(printf '%s' "$resolution" | cut -f1)"
    effective="$(printf '%s' "$resolution" | cut -f3-)"
    log "AgentCore CLI: ${source} — ${effective}"
    ( cd /workshop/sample-pellier-agentic-search-apg/.agentcore-project/pellier 2>/dev/null \
        && if [ "$source" = "binary" ]; then
               "$(printf '%s' "$resolution" | cut -f2)" "$@"
           else
               npx -y "@aws/agentcore@${AGENTCORE_CLI_PINNED_VERSION}" "$@"
           fi )
        # type -P, NOT command -v: command -v matches THIS function (always
        # true), then `command agentcore` finds no binary when the global npm
        # install was skipped -> "command not found" instead of the npx
        # fallback (box-verified 2026-06-12). type -P searches PATH only.
}

# Pellier service shortcuts — see FORMAT_ALIASES below (workshop vs builders).

# Database Shortcut (psql uses PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE from .env)
alias psql='psql'

# AWS Region for boto3
export AWS_DEFAULT_REGION=${AWS_REGION:-us-east-1}

# Claude Code CLI → Amazon Bedrock (Claude Code lane, Lab 1).
# CLAUDE_CODE_USE_BEDROCK=1 makes the CLI authenticate through THIS box's IAM
# instance role (the same ambient-credential chain psql/boto3/agentcore already
# use) — no Anthropic API key, no per-participant login, nothing to paste.
# Model: pin the global Sonnet 4.6 profile. Workshop Studio accounts do not
# expose the Claude 5 family, so the floating `sonnet` alias (which a current
# CLI resolves to Sonnet 5 on Bedrock) fails with AccessDenied on the event
# account. This is the same profile the app's Sonnet tier already requires.
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

# Ensure uv is in PATH (required for MCP)
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
alias reset-governed='bash /workshop/sample-pellier-agentic-search-apg/scripts/reset-governed-workshop.sh'
# One word per lab entry point. `workshop-start` mints the run id before Lab 1,
# `lab3-start` switches the storefront to the managed rail and proves it, and
# `doctor --lab N` names the prerequisite a stuck participant has not met.
alias workshop-start='bash /workshop/sample-pellier-agentic-search-apg/scripts/workshop-start.sh'
alias lab3-start='bash /workshop/sample-pellier-agentic-search-apg/scripts/lab3-start.sh'
alias doctor='python3 /workshop/sample-pellier-agentic-search-apg/scripts/workshop_doctor.py'
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
        warn "⚠️  Warehouse inventory missing — check_inventory exercise will not land"
    fi
fi

# Verify Python packages
if sudo -u "$CODE_EDITOR_USER" python3 -c "import fastapi, strands, uvicorn" 2>/dev/null; then
    log "✅ Pellier Backend dependencies verified"
else
    warn "⚠️  Some Pellier Backend dependencies may be missing"
fi

# ============================================================================
# STEP 13b: CLOUDWATCH TRANSACTION SEARCH (observability prerequisite)
# ============================================================================
# The governed workshop reconstructs one agent turn from CloudWatch spans plus
# Aurora evidence. Spans only reach CloudWatch once Transaction Search routes
# trace segments to CloudWatch Logs, and AWS requires that to be enabled
# BEFORE the OTLP traces endpoint will accept data.
#
# Idempotent by design: this checks first and only mutates what is missing, so
# re-running bootstrap on an account that already has it is a no-op.
#
# Start activation here without blocking application setup. The governed
# managed provisioner later waits for ACTIVE and fails readiness if activation
# never completes; an accepted update alone does not prove span delivery.
log "Verifying CloudWatch Transaction Search..."

TS_DESIRED_SAMPLING=100

ts_account_id="$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")"

if [ -z "$ts_account_id" ]; then
    warn "⚠️  Transaction Search: no AWS credentials resolved — skipping."
    warn "    Observability proof will read: unavailable (credentials)"
else
    # 1. Resource policy so X-Ray may write spans into CloudWatch Logs.
    if aws logs describe-resource-policies --region "$AWS_REGION" \
        --query "resourcePolicies[?policyName=='TransactionSearchXRayAccess'].policyName" \
        --output text 2>/dev/null | grep -q "TransactionSearchXRayAccess"; then
        log "✅ Transaction Search resource policy present"
    else
        log "Creating Transaction Search resource policy..."
        if aws logs put-resource-policy \
            --region "$AWS_REGION" \
            --policy-name TransactionSearchXRayAccess \
            --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"TransactionSearchXRayAccess\",\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"xray.amazonaws.com\"},\"Action\":\"logs:PutLogEvents\",\"Resource\":[\"arn:aws:logs:${AWS_REGION}:${ts_account_id}:log-group:aws/spans:*\",\"arn:aws:logs:${AWS_REGION}:${ts_account_id}:log-group:/aws/application-signals/data:*\"],\"Condition\":{\"ArnLike\":{\"aws:SourceArn\":\"arn:aws:xray:${AWS_REGION}:${ts_account_id}:*\"},\"StringEquals\":{\"aws:SourceAccount\":\"${ts_account_id}\"}}}]}" \
            >/dev/null 2>&1; then
            log "✅ Transaction Search resource policy created"
        else
            warn "⚠️  Could not create Transaction Search resource policy (needs logs:PutResourcePolicy)"
        fi
    fi

    # 2. Route trace segments to CloudWatch Logs. This is the actual switch.
    ts_destination="$(aws xray get-trace-segment-destination --region "$AWS_REGION" \
        --query Destination --output text 2>/dev/null || echo "")"
    ts_status="$(aws xray get-trace-segment-destination --region "$AWS_REGION" \
        --query Status --output text 2>/dev/null || echo "")"

    if [ "$ts_destination" = "CloudWatchLogs" ] && [ "$ts_status" = "ACTIVE" ]; then
        log "✅ Transaction Search active (destination=CloudWatchLogs)"
    elif [ "$ts_destination" = "CloudWatchLogs" ]; then
        log "Transaction Search activation in progress (status=${ts_status:-UNKNOWN}); managed provisioning will wait for ACTIVE"
    else
        log "Enabling Transaction Search (destination=CloudWatchLogs)..."
        # Capture the API error rather than discarding it. On a fresh account this
        # warned "needs xray:UpdateTraceSegmentDestination" while the instance role
        # already granted that action, so the guessed cause sent the next reader to the
        # wrong place and the real error was gone. Managed provisioning below
        # enforces this prerequisite for governed readiness.
        ts_err="$(aws xray update-trace-segment-destination \
            --region "$AWS_REGION" --destination CloudWatchLogs 2>&1 >/dev/null)" \
            && ts_rc=0 || ts_rc=$?
        if [ "${ts_rc:-1}" -eq 0 ]; then
            log "Transaction Search activation requested; managed provisioning will wait for ACTIVE"
        else
            warn "⚠️  Could not enable Transaction Search; observability proof will read: unavailable"
            warn "    aws xray update-trace-segment-destination said: ${ts_err:-<no output>}"
        fi
    fi

    # 3. Index every workshop span. Participant proof must be deterministic, so
    #    probabilistic sampling below 100% is not acceptable here even though
    #    production guidance differs.
    ts_sampling="$(aws xray get-indexing-rules --region "$AWS_REGION" \
        --query "IndexingRules[?Name=='Default'].Rule.Probabilistic.DesiredSamplingPercentage | [0]" \
        --output text 2>/dev/null || echo "")"

    if [ "${ts_sampling%.*}" = "$TS_DESIRED_SAMPLING" ]; then
        log "✅ Span indexing at ${TS_DESIRED_SAMPLING}% (deterministic capture)"
    else
        log "Setting span indexing to ${TS_DESIRED_SAMPLING}% (was: ${ts_sampling:-unset})..."
        idx_err="$(aws xray update-indexing-rule --region "$AWS_REGION" --name "Default" \
            --rule "{\"Probabilistic\":{\"DesiredSamplingPercentage\":${TS_DESIRED_SAMPLING}}}" \
            2>&1 >/dev/null)" && idx_rc=0 || idx_rc=$?
        if [ "${idx_rc:-1}" -eq 0 ]; then
            log "✅ Span indexing set to ${TS_DESIRED_SAMPLING}%"
        else
            warn "⚠️  Could not set span indexing to ${TS_DESIRED_SAMPLING}% — workshop turns may not all be indexed"
            warn "    aws xray update-indexing-rule said: ${idx_err:-<no output>}"
            warn "    Check xray:GetIndexingRules and xray:UpdateIndexingRule permissions on the instance role."
        fi
    fi
fi

# ============================================================================
# STEP 14: AUTO-START PELLIER SERVICE (single-process, port 8000)
# ============================================================================
# Single systemd service. FastAPI serves:
#   - the built SPA at /, /observatory, /storyboard, /discover, ...
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

# --- pellier.service: build frontend (best-effort), then run python -m uvicorn ---
#
# ONE unit for BOTH formats. The only per-format difference is whether
# uvicorn carries --reload: builders participants edit .py files and want
# live restarts on save; workshop format runs static. Everything else —
# Restart=always, boot-survival, best-effort frontend build — is identical.
#
# RELOAD_ARGS is computed here so there is a single heredoc, not two.
# --reload-dir pins the watch to the backend dir (avoids watching
# frontend/node_modules and re-triggering on dist/ writes).
if [ "${WORKSHOP_FORMAT}" = "builders" ] || [ "${WORKSHOP_FORMAT}" = "governed" ]; then
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
# workshop-start.sh and lab3-start.sh prefer /etc/pellier/run.env for the
# run id and the managed-rail switch and fall back to the repo .env when
# that path is not writable. Load it after .env so a value written there
# reaches the service instead of being silently ignored; '-' tolerates
# its absence.
EnvironmentFile=-/etc/pellier/run.env
Environment=PATH=/home/$CODE_EDITOR_USER/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=HOME=/home/$CODE_EDITOR_USER
Environment=PYTHONUNBUFFERED=1
# VITE_BASE_PATH is baked into the built bundle so asset URLs match
# the CloudFront /ports/8000/* reverse-proxy prefix.
Environment=VITE_BASE_PATH=/ports/8000/
# ExecStartPre is BEST-EFFORT (leading '-' tells systemd to ignore a
# non-zero exit; '|| true' keeps the bash -c itself at 0). A frontend
# build failure must NEVER block the backend: app.py serves /api/* even
# when dist/ is absent (the SPA 404s with a clear log line). This is the
# fix for the prior failure mode where an unguarded npm run build under
# set -e aborted bootstrap before uvicorn ever started.
ExecStartPre=-/bin/bash -c 'cd $REPO_PATH/pellier/backend && python3 generate_mcp_config.py 2>/dev/null || true'
ExecStartPre=-/bin/bash -c 'cd $REPO_PATH/pellier/frontend && npm run build || true'
ExecStart=/usr/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 $UVICORN_RELOAD_ARGS
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

# Verify it answers, not merely that systemd spawned it. ExecStartPre builds the
# frontend first, so the unit sits in "activating" for the length of a Vite
# build before uvicorn binds :8000; `is-active` after a fixed sleep read that as
# a failed start. APP_READY is recorded only once /api/health reports healthy,
# which is the same probe the health gate and the reset use.
APP_HEALTH_OK=false
for _attempt in {1..150}; do
    if curl -fs --max-time 3 http://localhost:8000/api/health 2>/dev/null \
        | grep -q '"status".*"healthy"'; then
        APP_HEALTH_OK=true
        break
    fi
    sleep 2
done
if [ "$APP_HEALTH_OK" = true ]; then
    log "✅ pellier service answers /api/health (port 8000, serves SPA + /api)"
    set_provision_state APP_READY
else
    warn "pellier service did not answer /api/health as healthy within 300s; check: journalctl -u pellier"
fi

log "✅ Auto-start service configured"
log "   App URL (Workshop Studio): https://<cloudfront>/ports/8000/"
log "   App URL (local):           http://localhost:8000/"
log "   Frontend rebuild: run 'rebuild-frontend' alias or restart the service"

# The CloudFormation template owns the Hosted UI callback registration. It
# runs a custom resource after the CloudFront distribution exists, so a stack
# cannot reach CREATE_COMPLETE with an unregistered callback. Keeping that
# dependency in the stack avoids the old detached-oneshot race: the instance
# necessarily booted before the distribution existed, and a failed background
# retry could leave browser sign-in broken while bootstrap still reported ready.
log "✅ OAuth callback registration is a CloudFormation readiness dependency"

# ============================================================================
# STEP 15: STATUS MARKER
# ============================================================================
write_status_json "in_progress" "pending" ""
log "✅ Status marker created"

# Seed identity before the managed deployment snapshots these mappings into
# Cognito's pre-token trigger. Seeding after deployment leaves every shopper
# token without its customer claim, even when the SQL rows are later correct.
if [ -n "${COGNITO_USER_POOL_ID:-${COGNITO_POOL_ID:-}}" ] \
   && [ -f "$REPO_PATH/scripts/seed_principal_mappings.py" ]; then
    log "Seeding RLS principal mappings (Cognito subject -> customer scope)..."
    export COGNITO_POOL_ID="${COGNITO_POOL_ID:-$COGNITO_USER_POOL_ID}"
    export COGNITO_REGION="${COGNITO_REGION:-$AWS_REGION}"
    # Dependencies belong to the participant's Python installation.
    if sudo -u "$CODE_EDITOR_USER" env \
         PATH="/usr/bin:/usr/local/bin:$PATH" \
         AWS_REGION="$AWS_REGION" AWS_DEFAULT_REGION="$AWS_REGION" \
         COGNITO_POOL_ID="$COGNITO_POOL_ID" COGNITO_REGION="$COGNITO_REGION" \
         python3 "$REPO_PATH/scripts/seed_principal_mappings.py" 2>&1 \
         | tee /var/log/pellier-seed-principal-mappings.log; then
        log "✅ Principal mappings seeded"
    elif [ "$WORKSHOP_FORMAT" = "governed" ]; then
        fail "Principal mapping seed failed; managed deployment requires customer identity mappings"
    else
        warn "seed_principal_mappings.py reported issues — RLS will deny signed-in shoppers until it succeeds"
    fi
elif [ "$WORKSHOP_FORMAT" = "governed" ]; then
    fail "Cognito pool and seed_principal_mappings.py are required before managed deployment"
fi

# ============================================================================
# STEP 16: WORKSHOP FORMAT — Pre-apply everything participants don't build
# ============================================================================
#
# The required path wires the check_inventory tool body in
# services/agent_tools.py and then proves the same production path
# through retrieval, memory, Runtime, Gateway, Policy, and the Aurora
# audit ledger. Inventory Agent's system prompt and orchestrator are
# already in place before participants arrive.
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
# Files we explicitly do NOT copy (participants build these):
#   inside agent_tools.py            — the check_inventory tool body only
#   inside agentcore_gateway.py      — Lab 3b's support reconcile region
#   inside gateway_tool_schemas.py   — Lab 3a's published-tools decision
if [ "${WORKSHOP_FORMAT}" = "builders" ] || [ "${WORKSHOP_FORMAT}" = "governed" ]; then
    log "=========================================="
    log "Workshop: processing ${WORKSHOP_FORMAT} managed path"
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

    if [ "${WORKSHOP_FORMAT}" = "builders" ]; then

    # ---- Specialist agents that aren't Inventory Agent ----
    # Personalization Agent handles recommendation turns (search_products_hybrid, get_related_products).
    # Customer Service Agent handles returns/care (get_return_policy, initiate_return,
    # escalate_to_human). Orchestrator is the dispatcher that routes between them.
    copy_solution "solutions/closing-marcos-gap/agents/personalization_agent.py" \
                  "pellier/backend/agents/personalization_agent.py" "Personalization Agent"
    copy_solution "solutions/closing-marcos-gap/agents/customer_service_agent.py" \
                  "pellier/backend/agents/customer_service_agent.py" "Customer Service Agent"
    copy_solution "solutions/closing-marcos-gap/agents/orchestrator.py" \
                  "pellier/backend/agents/orchestrator.py" "Orchestrator"

    # ---- agent_tools.py builders variant ----
    # Wires restock_inventory + get_low_stock (everything Inventory Agent-adjacent
    # except check_inventory itself). Participants will edit this file in
    # the required-path to add the check_inventory body — and only that body.
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
    # Policy is managed at the Gateway by the AgentCore CLI project. The old
    # local fake-Cedar service was removed; services/managed_policy.py is the
    # read side used by the operator surface.
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
    else
        log "Governed format: preserving Inventory Agent and check_inventory scaffolds for participant build"
        if (
            cd "$REPO_PATH"
            python3 scripts/reset_participant_exercises.py --repo "$REPO_PATH"
        ); then
            log "✅ Governed format: all four participant exercises restored to starter state"
        else
            fail "Governed participant exercise reset failed"
        fi
    fi

    # ---- AgentCore full managed path ----
    #
    # Keep provisioning failures non-fatal until the backend has launched so
    # facilitators retain logs and a recoverable shell. The final health gate is
    # strict for WORKSHOP_FORMAT=governed and exits bootstrap non-zero unless
    # Memory, Runtime, Gateway, and Policy are all ready. Builders format keeps
    # the managed path optional.
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
export AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN='${AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN:-}'
export AGENTCORE_RUNTIME_LOG_RETENTION_DAYS='${AGENTCORE_RUNTIME_LOG_RETENTION_DAYS:-30}'
EOF
    chmod 600 "$PROVISION_ENV" 2>/dev/null || true
    chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$PROVISION_ENV" 2>/dev/null || true
    log "Wrote provisioning recovery file: $PROVISION_ENV"

    if ! command -v npx &>/dev/null || ! command -v python3 &>/dev/null; then
        warn "Missing npx or python3 — skipping managed AgentCore provisioning (backend will still start)"
        write_status_json "failed" "failed" "$MANAGED_OUTPUT_JSON"
        AGENTCORE_OK=false
    fi

    # The pinned CLI requires Node 20 or newer. Fail this managed provisioning
    # beat cleanly if the base image fell back to an older runtime.
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
        export AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN='${AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN:-}'
        export AGENTCORE_RUNTIME_LOG_RETENTION_DAYS='${AGENTCORE_RUNTIME_LOG_RETENTION_DAYS:-30}'
        # sudo strips the parent environment, so anything the provisioner requires has to
        # be re-exported HERE. AGENT_MODEL_ID was missing and killed the whole managed
        # path: check_model_access.py resolves it at bootstrap time and writes it to
        # pellier/backend/.env, because it is not static (an account without Opus access
        # gets a documented fallback). Passed explicitly so the dependency is visible at
        # the call site; the provisioner also reads that .env as a safety net.
        export AGENT_MODEL_ID='${AGENT_MODEL_ID:-}'
        export BEDROCK_FAST_MODEL='${BEDROCK_FAST_MODEL:-global.anthropic.claude-haiku-4-5-20251001-v1:0}'
        export WORKSHOP_ID='${WORKSHOP_ID:-dat416}'
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
        OPERATOR_RUNTIME_ARN="$(jq -r '.operator_runtime.runtime_arn // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        MEMORY_ID="$(jq -r '.memory.memory_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        GATEWAY_ID="$(jq -r '.gateway.gateway_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        GATEWAY_URL="$(jq -r '.gateway.gateway_url // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        GATEWAY_ARN="$(jq -r '.gateway.gateway_arn // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        POLICY_ENGINE_ID="$(jq -r '.policy.policy_engine_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        MANAGED_STATUS="$(jq -r '.status // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        if [ -z "$RUNTIME_ARN" ] || [ -z "$OPERATOR_RUNTIME_ARN" ] || [ -z "$MEMORY_ID" ] \
            || [ -z "$GATEWAY_ID" ] || [ -z "$GATEWAY_URL" ] \
            || [ -z "$GATEWAY_ARN" ] || [ -z "$POLICY_ENGINE_ID" ] \
            || [ "$MANAGED_STATUS" != "ready" ]; then
            warn "Managed provisioning output missing shopper Runtime/Operator Runtime/Memory/Gateway/Policy readiness (backend will still start)"
            write_status_json "failed" "failed" "$MANAGED_OUTPUT_JSON"
            AGENTCORE_OK=false
        fi
    fi

    if [ "$AGENTCORE_OK" = true ]; then
        upsert_env "AGENTCORE_RUNTIME_ENDPOINT" "$RUNTIME_ARN" "$REPO_PATH/.env"
        upsert_env "AGENTCORE_OPERATOR_RUNTIME_ENDPOINT" "$OPERATOR_RUNTIME_ARN" "$REPO_PATH/.env"
        upsert_env "AGENTCORE_MEMORY_ID" "$MEMORY_ID" "$REPO_PATH/.env"
        upsert_env "AGENTCORE_GATEWAY_ID" "$GATEWAY_ID" "$REPO_PATH/.env"
        upsert_env "AGENTCORE_GATEWAY_ARN" "$GATEWAY_ARN" "$REPO_PATH/.env"
        upsert_env "AGENTCORE_GATEWAY_URL" "$GATEWAY_URL" "$REPO_PATH/.env"
        if [ "${WORKSHOP_FORMAT}" = "governed" ]; then
            # Labs 1 and 2 must exercise the participant's local Inventory
            # Agent and hybrid retrieval code. Lab 3 deliberately switches
            # the storefront to this already-provisioned Runtime, after the
            # participant has proved the in-process rail.
            upsert_env "USE_AGENTCORE_RUNTIME" "false" "$REPO_PATH/.env"
        else
            upsert_env "USE_AGENTCORE_RUNTIME" "true" "$REPO_PATH/.env"
        fi
        # Managed AgentCore Policy engine (4th pillar). The provisioner cannot
        # report ready without this id; keep the explicit guard because Lab 4
        # and the Pellier Observatory Policy surface both read it.
        if [ -n "$POLICY_ENGINE_ID" ]; then
            upsert_env "AGENTCORE_POLICY_ENGINE_ID" "$POLICY_ENGINE_ID" "$REPO_PATH/.env"
            log "✅ Managed AgentCore Policy engine: $POLICY_ENGINE_ID"
        fi
        chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_PATH/.env"
        write_status_json "complete" "ready" "$MANAGED_OUTPUT_JSON"
        log "✅ AgentCore managed path ready"
        # MANAGED_READY builds on APP_READY. A managed proof over an application
        # that never answered /api/health is not a later milestone, so the state
        # stays where it is and the health gate reports the gap.
        if [ "${APP_HEALTH_OK:-false}" = true ]; then
            set_provision_state MANAGED_READY
        else
            warn "Managed path proved but the application never answered /api/health; provision state not advanced"
        fi
    else
        warn "AgentCore managed path NOT ready — continuing so the backend launches. The health gate will flag this; see $AGENTCORE_LOG, then re-run provisioning to recover the Runtime/Gateway path."
        # Preserve CLI-created resources in backend configuration even when a
        # later live proof fails. AGENTCORE_RUNTIME_ENDPOINT stays unset on
        # purpose so the health gate cannot report the Runtime as ready.
        PARTIAL_MEMORY_ID="$(jq -r '.memory.memory_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        PARTIAL_GATEWAY_ID="$(jq -r '.gateway.gateway_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        PARTIAL_GATEWAY_URL="$(jq -r '.gateway.gateway_url // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        PARTIAL_GATEWAY_ARN="$(jq -r '.gateway.gateway_arn // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        PARTIAL_POLICY_ID="$(jq -r '.policy.policy_engine_id // empty' "$MANAGED_OUTPUT_JSON" 2>/dev/null || true)"
        if [ -n "$PARTIAL_MEMORY_ID" ]; then
            upsert_env "AGENTCORE_MEMORY_ID" "$PARTIAL_MEMORY_ID" "$REPO_PATH/.env"
            log "Salvaged CLI-managed Memory id into .env despite failed proof"
        fi
        if [ -n "$PARTIAL_GATEWAY_ID" ]; then
            upsert_env "AGENTCORE_GATEWAY_ID" "$PARTIAL_GATEWAY_ID" "$REPO_PATH/.env"
        fi
        if [ -n "$PARTIAL_GATEWAY_URL" ]; then
            upsert_env "AGENTCORE_GATEWAY_URL" "$PARTIAL_GATEWAY_URL" "$REPO_PATH/.env"
            log "Salvaged live Gateway endpoint into .env despite failed provisioning"
        fi
        if [ -n "$PARTIAL_GATEWAY_ARN" ]; then
            upsert_env "AGENTCORE_GATEWAY_ARN" "$PARTIAL_GATEWAY_ARN" "$REPO_PATH/.env"
            log "Salvaged live Gateway ARN into .env despite failed provisioning"
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

    # Install the exact AgentCore CLI used by provisioning. Lab 4 deploys one
    # participant policy, so an npx registry fetch cannot sit on the room clock.
    # NOT gated on AGENTCORE_OK: a Runtime-only failure still leaves Gateway +
    # Policy independently usable, and `agentcore status` is exactly the tool
    # for diagnosing the failed beat (box-verified cascade 2026-06-12: gating
    # this on AGENTCORE_OK left the participant with no CLI at all).
    if command -v npm &>/dev/null; then
        log "Installing pinned AgentCore CLI globally (@aws/agentcore@0.29.0)..."
        npm install -g @aws/agentcore@0.29.0 >/dev/null 2>&1 \
            && log "✅ agentcore CLI installed globally ($(command agentcore --version 2>/dev/null || echo 'version check skipped'))" \
            || warn "Global @aws/agentcore@0.29.0 install failed — the agentcore function will fall back to npx; see npm logs."
    fi

    # The pellier.service unit (STEP 14) already runs uvicorn with --reload
    # for builders format and rebuilds the frontend in ExecStartPre. Now
    # that the solution files + AgentCore env are in place, restart the unit
    # once so it picks them up. systemd owns the process — no nohup, no PID
    # file, no second backend fighting for :8000. A restart failure is
    # non-fatal (the health gate reports it); --reload keeps the live-edit DX.
    log "Restarting pellier service to pick up ${WORKSHOP_FORMAT} env..."
    systemctl restart pellier || warn "pellier restart failed — check: journalctl -u pellier"

    sleep 8
    if systemctl is-active --quiet pellier; then
        log "✅ ${WORKSHOP_FORMAT}: pellier service running (systemd)"
    else
        warn "pellier service not active after restart — check: journalctl -u pellier"
    fi

    if [ "${WORKSHOP_FORMAT}" = "governed" ] && [ "$AGENTCORE_OK" = true ]; then
        log "Restoring canonical governed state after live Runtime and Policy proof..."
        # The reset ends with the health gate, which requires E2E_PROVED in the
        # governed format. That state is written after STEP 19, so this run is
        # marked as bootstrap's own proving phase.
        if sudo -u "$CODE_EDITOR_USER" bash -c "
            export PELLIER_REPO='$REPO_PATH'
            export PELLIER_PROVISION_PHASE=bootstrap
            bash '$REPO_PATH/scripts/reset-governed-workshop.sh'
        " 2>&1 | tee /var/log/pellier-governed-reset.log; then
            log "✅ Governed database, evidence, and Policy state reset"
        else
            fail "Governed reset failed; see /var/log/pellier-governed-reset.log"
        fi
    fi

    if [ "$AGENTCORE_OK" = true ]; then
        log "✅ ${WORKSHOP_FORMAT} managed path ready, pellier service restarted"
    else
        warn "${WORKSHOP_FORMAT} managed path incomplete; backend restarted for diagnostics"
    fi
fi

if [ "${WORKSHOP_FORMAT}" != "builders" ] && [ "${WORKSHOP_FORMAT}" != "governed" ]; then
    write_status_json "complete" "not_applicable" ""
fi

# ============================================================================
# STEP 17: WRITE TEST CREDENTIALS FILE
# ============================================================================
# The path is deliberately stable and participant-visible through the
# Workshop Studio stack output. The file itself remains on the participant's
# Code Editor volume; stack outputs must never expose a Cognito password.
CREDENTIALS_FILE="$HOME_FOLDER/test-credentials.txt"
if [ -z "${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}" ]; then
    fail "COGNITO_TEST_CREDENTIALS_SECRET_ARN is required to create participant sign-in credentials"
fi
if [ ! -x "$REPO_PATH/scripts/write-test-credentials.sh" ]; then
    fail "Missing credential writer: $REPO_PATH/scripts/write-test-credentials.sh"
fi
log "Writing participant test credentials..."
export COGNITO_TEST_CREDENTIALS_SECRET_ARN COGNITO_HOSTED_UI_URL AWS_REGION \
       CODE_EDITOR_USER HOME_FOLDER CREDENTIALS_FILE
if ! OUT_FILE="$CREDENTIALS_FILE" \
    bash "$REPO_PATH/scripts/write-test-credentials.sh" 2>&1 \
    | tee /var/log/pellier-write-credentials.log; then
    fail "Could not write participant sign-in credentials to $CREDENTIALS_FILE"
fi
if [ ! -s "$CREDENTIALS_FILE" ]; then
    fail "Participant credential file is missing or empty: $CREDENTIALS_FILE"
fi

# ============================================================================
# STEP 17b: PRE-BAKE THE GOVERNED BEARER TOKEN HELPER
# ============================================================================
# Labs 3 and 4 run on the authenticated managed rail and
# needs a Cognito access token. In a self-paced room (no facilitator to unblock
# a failed `admin-initiate-auth`), typing that command is the #1 friction +
# failure mode. So we pre-bake a one-command helper that mints a FRESH token
# (tokens expire ~1h, so we generate on demand rather than bake a stale one):
#
#     source ~/pellier-token.sh theo  # sets $PELLIER_TOKEN for AgentCore CLI
#
# The participant never types Cognito plumbing — they get the learning (managed
# Cedar gates at the Gateway), not the auth ceremony. Identity is still REAL:
# the token is a genuine Cognito JWT the Gateway validates.
if [ -n "${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}" ] && [ -n "${COGNITO_POOL:-${COGNITO_POOL_ID:-}}" ]; then
    log "Writing governed token helper (~/pellier-token.sh)..."
    _TOKEN_POOL="${COGNITO_POOL:-${COGNITO_POOL_ID}}"
    _TOKEN_CLIENT="${COGNITO_CLIENT:-${COGNITO_CLIENT_ID:-}}"
    # The participant's ~ is /home/$CODE_EDITOR_USER, NOT $HOME_FOLDER
    # (/workshop) — writing only to $HOME_FOLDER made `source
    # ~/pellier-token.sh` a No-such-file (box-verified 2026-06-12). Write to
    # the real home; symlink at $HOME_FOLDER for any content that used it.
    _TOKEN_HELPER="/home/$CODE_EDITOR_USER/pellier-token.sh"
    cat > "$_TOKEN_HELPER" <<TOKENEOF
#!/usr/bin/env bash
# Mint a fresh Cognito access token for the governed Runtime and Policy proof.
# Usage:  source ~/pellier-token.sh          # default persona (Marco)
#         source ~/pellier-token.sh anna     # mint Anna's token instead
#         source ~/pellier-token.sh theo     # mint Theo's
#         source ~/pellier-token.sh jessica  # mint Jessica's Lab 4 token
# The Cognito users are named after the workshop anchors, so the access token carries
# the chosen name (the access token's \`username\` claim, lowercased — NOT
# cognito:username, that's the ID token; box-verified 2026-06-12) through the
# JWT-gated Gateway – identity passthrough you can see. Case-insensitive match;
# no argument selects Marco, while an unknown named principal fails closed.
# Sets \$PELLIER_TOKEN.
_want="\${1:-}"
_creds=\$(aws secretsmanager get-secret-value \\
  --secret-id "$COGNITO_TEST_CREDENTIALS_SECRET_ARN" --region "$AWS_REGION" \\
  --query SecretString --output text 2>/dev/null)
_pair=\$(echo "\$_creds" | python3 -c 'import sys,json;w=(sys.argv[1] if len(sys.argv)>1 else "").strip().lower();us=[x for x in json.load(sys.stdin).get("users",[]) if str(x.get("username","")).strip()];matches=[x for x in us if x["username"].strip().lower()==w];chosen=(us[0] if not w and us else matches[0] if len(matches)==1 else None);print((chosen["username"]+"\\t"+chosen["password"]) if chosen else "")' "\$_want" 2>/dev/null)
if [ -z "\$_pair" ]; then
  echo "✗ Unknown Cognito username '\$_want'. Expected marco, anna, theo, or jessica."
  unset PELLIER_TOKEN
  return 1 2>/dev/null || exit 1
fi
IFS=\$'\\t' read -r _u _p <<< "\$_pair"
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
    log "✅ Governed token helper ready: source ~/pellier-token.sh"
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
# STEP 18b: OPERATOR AUTHORIZATION GROUP
#
# The Pellier Operator desk is authorized by membership in one Cognito group, not by
# holding any valid token. Before this existed, `require_operator` stopped at "the token
# verifies and carries a subject", so `marco` could confirm, decline and execute any
# review and call `issue_credit` directly. The application forbade a shopper-facing agent
# from issuing itself store credit while handing the same shopper the capability through
# the desk.
#
# Seeded here rather than in the CloudFormation template so the group and its member
# travel with the source revision the box checks out, and so a fix does not require an
# asset re-sync. The pool and its four customer principals are created by the template; this
# adds the group and the one account that belongs to it.
#
# NOT best-effort. A failed seeding leaves a console nobody can open, which is the correct
# failure but must be loud: the health gate refuses readiness below.
# ============================================================================
OPERATOR_GROUP="pellier-operators"
OPERATOR_USERNAME="${PELLIER_OPERATOR_USERNAME:-operator}"
OPERATOR_GROUP_OK=false

_pool_id() { echo "${COGNITO_USER_POOL_ID:-${COGNITO_POOL_ID:-}}"; }

if [ -n "$(_pool_id)" ]; then
    log "Seeding the $OPERATOR_GROUP Cognito group and its member..."
    POOL="$(_pool_id)"
    # A public workshop ID must never determine a staff credential.
    OPERATOR_PASSWORD="$(python3 -c 'import secrets; print("Pellier-" + secrets.token_urlsafe(24) + "-1aA")')"
    OPERATOR_PASSWORD_SET=false

    aws cognito-idp create-group --user-pool-id "$POOL" \
        --group-name "$OPERATOR_GROUP" --region "$AWS_REGION" \
        --description "Authorizes the Pellier Operator desk" >/dev/null 2>&1 || true
    aws cognito-idp admin-create-user --user-pool-id "$POOL" \
        --username "$OPERATOR_USERNAME" --message-action SUPPRESS \
        --region "$AWS_REGION" \
        --user-attributes Name=email,Value="operator@pellier.example.com" \
                          Name=email_verified,Value=true >/dev/null 2>&1 || true
    if aws cognito-idp admin-set-user-password --user-pool-id "$POOL" \
        --username "$OPERATOR_USERNAME" --password "$OPERATOR_PASSWORD" \
        --permanent --region "$AWS_REGION" >/dev/null 2>&1; then
        OPERATOR_PASSWORD_SET=true
    fi
    aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL" \
        --username "$OPERATOR_USERNAME" --group-name "$OPERATOR_GROUP" \
        --region "$AWS_REGION" >/dev/null 2>&1 || true

    # VERIFY, do not assume. Every call above tolerates "already exists", so success of
    # the calls says nothing; membership is the only fact that matters.
    if [ "$OPERATOR_PASSWORD_SET" = true ] && aws cognito-idp admin-list-groups-for-user --user-pool-id "$POOL" \
         --username "$OPERATOR_USERNAME" --region "$AWS_REGION" \
         --query "Groups[?GroupName=='${OPERATOR_GROUP}'].GroupName" --output text 2>/dev/null \
         | grep -q "$OPERATOR_GROUP"; then
        if ! OPERATOR_USERNAME="$OPERATOR_USERNAME" OPERATOR_PASSWORD="$OPERATOR_PASSWORD" \
            python3 "$REPO_PATH/scripts/store_operator_credential.py"; then
            fail "Could not persist the staff credential for readiness and Lab 4"
        fi
        OPERATOR_GROUP_OK=true
        log "✅ $OPERATOR_USERNAME is in $OPERATOR_GROUP"
        if ! printf 'Operator console (Pellier Operator)\n  Username: %s\n  Password: %s\n  Group:    %s\n\n' \
            "$OPERATOR_USERNAME" "$OPERATOR_PASSWORD" "$OPERATOR_GROUP" \
            >> "$CREDENTIALS_FILE"; then
            fail "Could not add Pellier Operator credentials to $CREDENTIALS_FILE"
        fi
        chmod 600 "$CREDENTIALS_FILE"
        chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$CREDENTIALS_FILE"
    else
        warn "Could not verify $OPERATOR_USERNAME in $OPERATOR_GROUP — the Operator desk will refuse every caller with 403"
    fi

    # A shopper must NOT be in the group. Asserted rather than assumed, because the whole
    # point is that a valid token is not authorization.
    for SHOPPER in marco anna theo jessica; do
        if aws cognito-idp admin-list-groups-for-user --user-pool-id "$POOL" \
             --username "$SHOPPER" --region "$AWS_REGION" \
             --query "Groups[?GroupName=='${OPERATOR_GROUP}'].GroupName" --output text 2>/dev/null \
             | grep -q "$OPERATOR_GROUP"; then
            fail "$SHOPPER is in $OPERATOR_GROUP — a shopper must never authorize the desk"
            OPERATOR_GROUP_OK=false
        fi
    done
else
    warn "No Cognito pool id — skipped the $OPERATOR_GROUP seeding; the Operator desk will refuse every caller"
fi
export OPERATOR_GROUP_SEEDED="$OPERATOR_GROUP_OK"

# ============================================================================
# SUMMARY
# ============================================================================
log "=========================================="
log "Stage 2: Running final workshop readiness checks"
log "=========================================="
echo ""
echo "✅ Pellier Backend (FastAPI + Strands) installed"
echo "✅ Pellier Frontend (React) dependencies installed"
echo "✅ Database setup complete (expanded product corpus + warehouse inventory)"
echo "✅ MCP server config written to pellier/config/mcp-server-config.json"
echo "✅ Bash environment configured (psql ready)"
if [ "${WORKSHOP_FORMAT}" = "builders" ]; then
    echo "✅ pellier systemd service enabled — python3 -m uvicorn --reload on :8000 (live .py edits)"
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
echo "  cat /var/log/pellier-agentcore.log # AgentCore deploy log (Gateway + Runtime)"
echo "  rebuild-frontend                 # Rebuild SPA + restart app"
echo "  health                           # One-shot readiness check (catalog/memory/runtime)"
echo ""

# ============================================================================
# STEP 19: POST-BOOT HEALTH GATE
# ============================================================================
# One consolidated PASS/FAIL summary so the facilitator sees readiness at a
# glance. Give the backend a moment to come up first. A failed gate is fatal for
# the governed workshop and warning-only for the one-hour builders format.
# FALSE until a gate actually runs and passes. Initialised true, a health-gate.sh
# that is missing or not executable skipped the `if` below and left the flag true:
# governed bootstrap then wrote E2E_PROVED and CloudFormation reported a proved
# environment with no gate evidence behind it. Absence of evidence is not a pass.
HEALTH_GATE_OK=false
if [ -x "$REPO_PATH/scripts/health-gate.sh" ]; then
    log "Running post-boot health gate..."
    sleep 5
    # This is the proving run: E2E_PROVED is written only after it passes, so the
    # gate's own E2E_PROVED requirement is relaxed for it (a FAILED state is not).
    # `set -o pipefail` is on, so the gate's status survives the pipe into tee.
    if sudo -u "$CODE_EDITOR_USER" bash -c "
        export PELLIER_REPO='$REPO_PATH'
        export WORKSHOP_FORMAT='${WORKSHOP_FORMAT}'
        export PELLIER_PROVISION_PHASE=bootstrap
        bash '$REPO_PATH/scripts/health-gate.sh'
    " 2>&1 | tee /var/log/pellier-health-gate.log; then
        HEALTH_GATE_OK=true
    else
        warn "Health gate reported NOT READY — see /var/log/pellier-health-gate.log"
    fi
else
    warn "No health gate to run at $REPO_PATH/scripts/health-gate.sh; readiness is unproven"
fi

log "=========================================="

if [ "$HEALTH_GATE_OK" != true ] && [ "${WORKSHOP_FORMAT}" = "governed" ]; then
    fail "Governed workshop readiness failed; CloudFormation must not report this environment ready"
fi

# The gate that just passed covers the seeded Operator token mint, an
# authenticated call through the application, the managed invocation receipt
# and the evidence receipt. A literal browser session is not run on the box.
if [ "$HEALTH_GATE_OK" = true ] && [ "${WORKSHOP_FORMAT}" = "governed" ]; then
    set_provision_state E2E_PROVED
fi

exit 0
