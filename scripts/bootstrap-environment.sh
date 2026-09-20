#!/bin/bash
# Pellier Workshop - Stage 1: Environment Bootstrap
# Purpose: Get Code Editor + VS Code ready FAST, then signal CloudFormation
# Duration: ~8 minutes

set -euo pipefail

# ============================================================================
# PARAMETERS FROM ENVIRONMENT
# ============================================================================
CODE_EDITOR_PASSWORD="${CODE_EDITOR_PASSWORD:?CODE_EDITOR_PASSWORD must be supplied by the deployment}"
CODE_EDITOR_USER="${CODE_EDITOR_USER:-participant}"
HOME_FOLDER="${HOME_FOLDER:-/workshop}"
REPO_NAME="${REPO_NAME:-sample-pellier-agentic-search-apg}"
ORIGIN_VERIFY_TOKEN="${ORIGIN_VERIFY_TOKEN:-}"
CFN_WAIT_HANDLE="${CFN_WAIT_HANDLE:-}"
STAGE2_SCRIPT_URL="${STAGE2_SCRIPT_URL:-}"
ASSETS_BUCKET_NAME="${ASSETS_BUCKET_NAME:-}"
ASSETS_BUCKET_PREFIX="${ASSETS_BUCKET_PREFIX:-}"
CLAUDE_CODE_VERSION="${CLAUDE_CODE_VERSION:-2.1.233}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"; }
error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"; exit 1; }

probe_editor_http() {
    local url="$1"
    shift
    # The token is required even for localhost. A 302 response confirms the
    # authenticated entry point without following a browser-cookie redirect.
    curl -s --max-time 5 -o /dev/null -w "%{http_code}" \
        --get --data-urlencode "tkn=$CODE_EDITOR_PASSWORD" \
        "$@" "$url" 2>/dev/null || true
}

log "=========================================="
log "Pellier Stage 1: Environment Bootstrap"
log "=========================================="
log "Assets Bucket: ${ASSETS_BUCKET_NAME:-<not set>}"
log "Assets Prefix: ${ASSETS_BUCKET_PREFIX:-<not set>}"

# ============================================================================
# STEP 1: ESSENTIAL SYSTEM PACKAGES (~2 min)
# ============================================================================

log "Installing essential system packages..."
dnf update -y -q
dnf install --skip-broken -y -q \
    curl \
    gnupg \
    whois \
    argon2 \
    unzip \
    nginx \
    openssl \
    jq \
    git \
    wget \
    gcc \
    gcc-c++ \
    make \
    postgresql17

log "✅ System packages installed"

# ----------------------------------------------------------------------------
# Node.js 20+ (required by the @aws/agentcore CLI).
#
# AL2023's default `nodejs` package is Node 18, but @aws/agentcore (>=0.18)
# declares `engines.node: ">=20"` and its bundled code uses the regex `v`
# (unicodeSets) flag, which Node 18 does NOT parse — `npx @aws/agentcore deploy`
# crashes at module load with "SyntaxError: Invalid regular expression flags"
# BEFORE doing any work, so the managed Runtime never deploys. We therefore
# install Node 20 from NodeSource (the supported path for a pinned major on
# AL2023). Falls back to the distro nodejs only if NodeSource is unreachable,
# so provisioning still gets a Node for the frontend build even if Runtime
# deploy can't run. Everything downstream calls `node`/`npx` on PATH, so it
# follows whichever got installed.
# ----------------------------------------------------------------------------
# This step is intentionally NON-fatal: a NodeSource hiccup must not abort the
# whole box (Pellier still works on Node 18; only the managed-Runtime deploy
# needs 20). We retry NodeSource and verify by the ACTUAL major version.
# Removing the distro Node 18 stack first is what makes `node` resolve to 20:
# erasing `nodejs` unregisters node-18 from the /usr/bin/node `alternatives`
# group, which leaves Node 20 as the only candidate there. Both distro Node
# packages register that group at the SAME priority (100), so while node-18 is
# installed no amount of `update-alternatives --install` can outrank it - only
# `--set` selects, and removal is what we rely on here.
# The hard "is this actually 20?" guard lives at the
# provisioning call site (bootstrap-labs STEP 16), where aborting just the
# already-best-effort AgentCore step is the right blast radius. The health gate
# surfaces an empty AGENTCORE_RUNTIME_ENDPOINT if 20 never arrived.
log "Installing Node.js 20 (required by @aws/agentcore CLI; AL2023 default is 18)..."

# Why this is more than "dnf install nodejs":
#   On a fresh AL2023 box the distro `nodejs` (18) is often ALREADY installed
#   (it satisfies build deps). In that state, adding the NodeSource repo and
#   running `dnf install nodejs` is a NO-OP — dnf sees nodejs as already
#   present and exits 0 WITHOUT upgrading to 20. The previous logic trusted
#   that exit 0 and left the box on Node 18 (observed on a fresh-account run:
#   `node --version` → v18.20.8, every `agentcore` command silently empty).
#   Fix: (1) remove the distro nodejs first so NodeSource's package is the
#   only candidate, (2) verify success by the ACTUAL major version, never by
#   dnf's exit code.
_node_major() { node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1; }
_node20_ok=false
for attempt in 1 2; do
    # Drop any distro Node (18) so the NodeSource module installs clean rather
    # than being short-circuited as "already satisfied". Non-fatal if absent.
    dnf remove -y -q nodejs npm >/dev/null 2>&1 || true
    if curl -fsSL https://rpm.nodesource.com/setup_20.x | bash - >/dev/null 2>&1; then
        # NodeSource ships nodejs-20 as the `nodejs` package once its repo is
        # enabled; --allowerasing lets it replace any lingering distro bits.
        dnf install -y -q --allowerasing nodejs >/dev/null 2>&1 || true
    fi
    _maj="$(_node_major)"
    if echo "$_maj" | grep -qE '^[0-9]+$' && [ "$_maj" -ge 20 ]; then
        _node20_ok=true
        break
    fi
    warn "Node 20 not active after attempt $attempt (node=$(node --version 2>/dev/null || echo none)); retrying..."
    sleep 3
done

if [ "$_node20_ok" = true ]; then
    log "✅ Node.js installed: $(node --version 2>/dev/null) ($(readlink -f /usr/bin/node 2>/dev/null))"

    # TypeScript compiler (tsc), global. The @aws/agentcore CLI is itself a
    # TypeScript/Node tool, and its `deploy` build step shells out to `tsc`
    # (`sh: line 1: tsc: command not found` aborts the Runtime deploy on a box
    # that only has Node). AL2023 doesn't preinstall it. Our agent is Python,
    # but the CLI's own build needs tsc regardless. Pinned major to avoid a
    # surprise tsc behavior change. Non-fatal: only the managed-Runtime deploy
    # needs it; Pellier + frontend build don't.
    if command -v npm >/dev/null 2>&1; then
        log "Installing TypeScript compiler globally (tsc – required by @aws/agentcore deploy)..."
        if npm install -g typescript@5 >/dev/null 2>&1; then
            # The CLI's deploy build runs `sh -c tsc` as the PARTICIPANT user
            # (provisioning is `sudo -u $CODE_EDITOR_USER`). npm's global prefix
            # may not be on that user's PATH, so symlink tsc into /usr/bin
            # (always on PATH) rather than trust the prefix location – same
            # defensive pattern as the aws-v2 symlink above.
            _tsc_bin="$(command -v tsc 2>/dev/null || true)"
            if [ -n "$_tsc_bin" ] && [ "$_tsc_bin" != "/usr/bin/tsc" ]; then
                ln -sf "$_tsc_bin" /usr/bin/tsc 2>/dev/null || true
            fi
            log "✅ tsc installed: $(tsc --version 2>/dev/null || echo 'version check skipped') ($(command -v tsc 2>/dev/null))"
        else
            warn "Global typescript install failed – @aws/agentcore deploy may fail with 'tsc: command not found'. Recover: 'sudo npm install -g typescript' then re-run scripts/deploy/deploy_all.sh."
        fi

        # Claude Code CLI (global), for the primary build lane in Lab 1.
        # It runs entirely against Bedrock via the box's instance
        # role (CLAUDE_CODE_USE_BEDROCK=1 + ANTHROPIC_MODEL are exported in the
        # participant .bashrc by bootstrap-labs), so there is NO per-participant
        # login — the same ambient-credential model the rest of the lab uses.
        # Intentionally NON-fatal: the pacing fallback copies the two checked-in
        # references and then runs the same live proof.
        # Pin the event-rehearsed release. A floating install re-introduces
        # CLI-behaviour drift on a date nobody chose - the same class of failure
        # that made the floating `sonnet` alias resolve to a denied model.
        # Updating this version is a deliberate release action followed by a
        # provisioned-environment rehearsal.
        log "Installing Claude Code CLI ${CLAUDE_CODE_VERSION} globally for Lab 1..."
        if npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" >/dev/null 2>&1; then
            # Same /usr/bin symlink defense as tsc above: the CLI runs as the
            # PARTICIPANT user, whose PATH may not include npm's global prefix.
            _claude_bin="$(command -v claude 2>/dev/null || true)"
            if [ -n "$_claude_bin" ] && [ "$_claude_bin" != "/usr/bin/claude" ]; then
                ln -sf "$_claude_bin" /usr/bin/claude 2>/dev/null || true
            fi
            log "✅ Claude Code CLI installed: $(claude --version 2>/dev/null || echo 'version check skipped') ($(command -v claude 2>/dev/null))"
        else
            warn "Claude Code CLI ${CLAUDE_CODE_VERSION} install failed - use the copy-reference pacing fallback in Lab 1. Recover: 'sudo npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}'."
        fi
    fi
else
    # Last resort: ensure SOME node exists for the frontend build. Managed
    # Runtime/Gateway/Policy deploy will be skipped (STEP 16 guards on Node>=20).
    if ! command -v node >/dev/null 2>&1; then
        dnf install --skip-broken -y -q nodejs >/dev/null 2>&1 || true
    fi
    warn "Node 20 install failed after retries — node is $(node --version 2>/dev/null || echo 'none') (<20). The @aws/agentcore Runtime/Gateway/Policy deploy will be SKIPPED (Pellier + frontend build still work). Recover: 'sudo dnf remove -y nodejs && curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash - && sudo dnf install -y --allowerasing nodejs' then re-run scripts/deploy/deploy_all.sh."
fi

# ----------------------------------------------------------------------------
# Python 3.14 — the single supported interpreter for this workshop.
#
# PY_VER is used for update-alternatives so /usr/bin/python3 points at the
# chosen interpreter. Downstream scripts call `python3` (the alternative),
# never a pinned python3.X, so they follow this choice automatically.
# ----------------------------------------------------------------------------
log "Installing Python 3.14..."
PY_VER="3.14"
if ! dnf install --skip-broken -y -q \
    "python${PY_VER}" \
    "python${PY_VER}-pip" \
    "python${PY_VER}-setuptools" \
    "python${PY_VER}-devel" \
    "python${PY_VER}-wheel" \
    "python${PY_VER}-tkinter" 2>/dev/null \
    || ! command -v "python${PY_VER}" >/dev/null 2>&1; then
    error "Python ${PY_VER} could not be installed — backend cannot start"
fi
log "✅ Python ${PY_VER} installed"

# ============================================================================
# STEP 2: AWS CLI V2 (~1 min)
# ============================================================================

log "Installing AWS CLI v2..."
cd /tmp
if [ "$(uname -m)" = "aarch64" ]; then
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip"
else
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
fi
unzip -q awscliv2.zip
./aws/install --update --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli
rm -rf awscliv2.zip aws/
cd - > /dev/null

# CRITICAL ordering fix: AL2023 preinstalls AWS CLI **v1** at /usr/bin/aws – a
# Python script whose shebang runs the SYSTEM python3 and does `import awscli`.
# The official v2 bundle we just installed is self-contained (its own embedded
# python, no `import awscli`) and lands at /usr/local/bin/aws. But /usr/bin
# precedes /usr/local/bin on the provisioning PATH, so `aws` would still resolve
# to the v1 shim – and the moment we repoint python3 -> 3.14 below, that v1 shim
# breaks with "ModuleNotFoundError: No module named 'awscli'" (awscli was
# installed for 3.9, not 3.14). That silently kills every `aws` subprocess in
# AgentCore provisioning (observed: `aws lambda get-function` → ModuleNotFound →
# no Lambdas/Gateway/Runtime/Policy deploy). Force /usr/bin/aws to point at the
# python-independent v2 binary so it survives the python switch and wins on PATH.
if [ -x /usr/local/bin/aws ]; then
    ln -sf /usr/local/bin/aws /usr/bin/aws
    ln -sf /usr/local/bin/aws_completer /usr/bin/aws_completer 2>/dev/null || true
fi

# Set the chosen Python ($PY_VER, from STEP 1) as the default python3.
log "Setting Python ${PY_VER} as default..."
update-alternatives --install /usr/bin/python3 python3 "/usr/bin/python${PY_VER}" 1
update-alternatives --set python3 "/usr/bin/python${PY_VER}"
log "✅ Python ${PY_VER} set as default (python3 → python${PY_VER})"

# Verify AWS CLI AFTER the python switch – this is the check that would have
# caught the v1/python3.14 breakage. Must report aws-cli/2.x; v1 (aws-cli/1.x)
# or a ModuleNotFoundError here means the symlink above didn't take.
_aws_ver="$(aws --version 2>&1 || true)"
if echo "$_aws_ver" | grep -q 'aws-cli/2'; then
    log "✅ AWS CLI v2 active after python switch: $_aws_ver"
else
    warn "AWS CLI is NOT v2 after the python switch (got: ${_aws_ver:-no output}). AgentCore provisioning shells out to 'aws' and will fail. Recover: 'sudo ln -sf /usr/local/bin/aws /usr/bin/aws' then re-run scripts/deploy/deploy_all.sh."
fi

# ============================================================================
# STEP 3: USER SETUP (~10 sec)
# ============================================================================

log "Setting up user: $CODE_EDITOR_USER"
if ! id "$CODE_EDITOR_USER" &>/dev/null; then
    adduser -c '' "$CODE_EDITOR_USER"
    echo "$CODE_EDITOR_USER:$CODE_EDITOR_PASSWORD" | chpasswd
    usermod -aG wheel "$CODE_EDITOR_USER"
    # Uncomment NOPASSWD wheel line so workshop user can sudo without password.
    # Amazon Linux /etc/sudoers has two wheel lines; we want only the NOPASSWD one.
    sed -i 's/^# %wheel\tALL=(ALL)\tNOPASSWD: ALL/%wheel\tALL=(ALL)\tNOPASSWD: ALL/' /etc/sudoers
    sed -i 's/^# %wheel ALL=(ALL) NOPASSWD: ALL/%wheel ALL=(ALL) NOPASSWD: ALL/' /etc/sudoers
    log "✅ User created"
else
    log "✅ User already exists"
fi

# Create workspace
mkdir -p "$HOME_FOLDER"
chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$HOME_FOLDER"

# ============================================================================
# STEP 4: CODE EDITOR INSTALLATION (~1 min)
# ============================================================================

log "Installing Code Editor..."
export CodeEditorUser="$CODE_EDITOR_USER"
curl -fsSL https://code-editor.amazonaws.com/content/code-editor-server/dist/aws-workshop-studio/install.sh | bash -s --

# Find Code Editor binary
if [ -f "/home/$CODE_EDITOR_USER/.local/bin/code-editor-server" ]; then
    CODE_EDITOR_CMD="/home/$CODE_EDITOR_USER/.local/bin/code-editor-server"
    log "✅ Code Editor installed at: $CODE_EDITOR_CMD"
else
    error "Code Editor binary not found"
fi

# Configure authentication token
log "Configuring authentication token..."
sudo -u "$CODE_EDITOR_USER" mkdir -p "/home/$CODE_EDITOR_USER/.code-editor-server/data"
echo -n "$CODE_EDITOR_PASSWORD" > "/home/$CODE_EDITOR_USER/.code-editor-server/data/token"
chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "/home/$CODE_EDITOR_USER/.code-editor-server/data/token"
chmod 600 "/home/$CODE_EDITOR_USER/.code-editor-server/data/token"
log "✅ Token configured"

# ============================================================================
# STEP 5: NGINX CONFIGURATION (~10 sec)
# ============================================================================

log "Configuring Nginx..."
mkdir -p /etc/nginx/conf.d
cat > /etc/nginx/conf.d/code-editor.conf << 'EOF'
map $http_x_forwarded_proto $pellier_forwarded_proto {
    default $http_x_forwarded_proto;
    "" $scheme;
}

server {
    listen 80;
    listen [::]:80;
    server_name _;
    # __PELLIER_ORIGIN_VERIFY__
    
    # Pellier (single-process): FastAPI on :8000 serves BOTH
    # /api/* AND the built SPA (/, /observatory, /storyboard, /discover,
    # /assets/*, /fonts/*). Code-server's /ports/<n>/* reverse proxy
    # (or the standalone /app/ alias below) routes the whole app
    # there.
    #
    # SSE-critical: proxy_buffering off + proxy_read_timeout 300 so
    # streaming tokens reach the browser as they arrive. gzip off at
    # the nginx layer so content_delta events aren't collapsed into
    # a single post-compressed chunk.
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $pellier_forwarded_proto;
        proxy_buffering off;
        proxy_read_timeout 300;
        gzip off;
    }

    # /app/ shortcut for browsers that don't go through
    # code-server's built-in /ports/<n>/* proxy. Forwards to the
    # same FastAPI origin that /api/ hits — one process, one port.
    location /app/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $pellier_forwarded_proto;
        proxy_buffering off;
        proxy_read_timeout 300;
        gzip off;
    }

    # /ports/8000/* – the canonical participant URL. It matches the baked
    # SPA base path (VITE_BASE_PATH=/ports/8000/) and the PellierURL /
    # ObservatoryURL CFN outputs. Serve it DIRECTLY here (nginx then FastAPI),
    # bypassing code-server's port-forward proxy.
    #
    # WHY this block exists: code-server only forwards a port that has been
    # REGISTERED in an authenticated, live IDE session. A cold or incognito
    # hit to /ports/8000/ has no such registration, so when it falls to the
    # catch-all `location /` (which proxies to code-server :8080) code-server
    # rejects it with HTTP 400 ("This page isn't working"). That made the
    # storefront reachable only from inside an open, authenticated IDE tab –
    # fragile, and the first thing a participant trips on. Owning the prefix
    # here makes Pellier and Pellier Observatory load token-free in any browser, with
    # no dependency on the IDE. Trailing slashes on both location and
    # proxy_pass strip the prefix: /ports/8000/assets/x serves /assets/x,
    # /ports/8000/api/... serves /api/... (SSE-safe: buffering + gzip off).
    location /ports/8000/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $pellier_forwarded_proto;
        proxy_buffering off;
        proxy_read_timeout 300;
        gzip off;
    }

    # Frontend/IDE proxy (Code Editor)
    location / {
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $http_host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection upgrade;
        proxy_set_header Accept-Encoding gzip;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $pellier_forwarded_proto;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
EOF

if [ -n "$ORIGIN_VERIFY_TOKEN" ]; then
    sed -i "s|# __PELLIER_ORIGIN_VERIFY__|if (\\\$http_x_pellier_origin_verify != \"$ORIGIN_VERIFY_TOKEN\") { return 403; }|" \
        /etc/nginx/conf.d/code-editor.conf
else
    sed -i '/# __PELLIER_ORIGIN_VERIFY__/d' /etc/nginx/conf.d/code-editor.conf
fi

nginx -t
systemctl enable nginx
systemctl start nginx
log "✅ Nginx configured and running"

# ============================================================================
# STEP 6: CODE EDITOR SERVICE (~10 sec)
# ============================================================================

log "Creating Code Editor systemd service..."

# Stop and disable the installer's default service
if systemctl is-active --quiet "code-editor@$CODE_EDITOR_USER"; then
    log "Stopping installer's default Code Editor service..."
    systemctl stop "code-editor@$CODE_EDITOR_USER" || true
    systemctl disable "code-editor@$CODE_EDITOR_USER" || true
    sleep 2
fi

# Remove any cached token from installer
rm -rf "/home/$CODE_EDITOR_USER/.code-editor-server" 2>/dev/null || true

# Get AWS region from the environment, else from EC2 metadata.
#
# IMDSv2, token first. The unauthenticated v1 GET this replaced returns 401 on an
# instance configured with HttpTokens=required, and the `|| echo 'us-east-1'` fallback
# then hides that behind a plausible-looking default. A workshop in any other region
# would have been configured for the wrong one with nothing in the log to say so.
imds_region() {
    local token
    token="$(curl -sS --max-time 5 -X PUT \
        'http://169.254.169.254/latest/api/token' \
        -H 'X-aws-ec2-metadata-token-ttl-seconds: 300' 2>/dev/null)" || return 1
    [ -n "$token" ] || return 1
    curl -sS --max-time 5 \
        -H "X-aws-ec2-metadata-token: $token" \
        'http://169.254.169.254/latest/meta-data/placement/region' 2>/dev/null
}

if [ -z "${AWS_REGION:-}" ]; then
    AWS_REGION="$(imds_region || true)"
    if [ -z "$AWS_REGION" ]; then
        warn "Could not read the region from IMDSv2; defaulting to us-east-1"
        AWS_REGION="us-east-1"
    fi
fi
log "AWS Region: $AWS_REGION"

# ----------------------------------------------------------------------------
# CDK bootstrap (required by @aws/agentcore 0.29.0 `deploy`).
#
# `agentcore deploy` synthesizes a CloudFormation stack and deploys it via the
# CDK toolkit. CDK requires the account/region to be "bootstrapped" first — a
# one-time CDKToolkit stack that provisions the assets S3 bucket, the
# cdk-hnb659fds-* execution roles, and the SSM version parameter the deploy
# reads. Without it, `agentcore deploy` fails on the missing toolkit. This is
# idempotent (re-running is a no-op if already bootstrapped), runs as root in
# UserData with the instance-profile credentials, and is best-effort: a failure
# is logged but does not abort the box (the AgentCore provisioning step later
# surfaces it via the health gate). Requires Node 20 (installed above).
# ----------------------------------------------------------------------------
log "Bootstrapping CDK for AgentCore Runtime deploy (region $AWS_REGION)..."
CDK_ACCOUNT="$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo '')"
if [ -n "$CDK_ACCOUNT" ]; then
if env AWS_REGION="$AWS_REGION" AWS_DEFAULT_REGION="$AWS_REGION" \
    npx -y aws-cdk@2 bootstrap "aws://${CDK_ACCOUNT}/$AWS_REGION" >/dev/null 2>&1; then
        log "✅ CDK bootstrapped for aws://${CDK_ACCOUNT}/${AWS_REGION}"
    else
        warn "CDK bootstrap failed — @aws/agentcore Runtime deploy may fail until 'npx aws-cdk@2 bootstrap' succeeds for aws://${CDK_ACCOUNT}/${AWS_REGION}"
    fi
else
    warn "Could not resolve account id (sts get-caller-identity) — skipping CDK bootstrap; AgentCore Runtime deploy will need it run manually"
fi

cat > /etc/systemd/system/code-editor@.service << EOF
[Unit]
Description=AWS Code Editor Server
After=network.target

[Service]
Type=simple
User=%i
Group=%i
WorkingDirectory=$HOME_FOLDER
Environment=PATH=/usr/local/bin:/usr/bin:/bin:/home/$CODE_EDITOR_USER/.local/bin
Environment=HOME=/home/$CODE_EDITOR_USER
Environment=AWS_REGION=$AWS_REGION
Environment=AWS_DEFAULT_REGION=$AWS_REGION
ExecStart=$CODE_EDITOR_CMD --accept-server-license-terms --host 127.0.0.1 --port 8080 --default-workspace $HOME_FOLDER/$REPO_NAME --default-folder $HOME_FOLDER/$REPO_NAME --connection-token $CODE_EDITOR_PASSWORD
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Create token file BEFORE enabling/starting service
systemctl daemon-reload
systemctl enable "code-editor@$CODE_EDITOR_USER"
systemctl start "code-editor@$CODE_EDITOR_USER"
log "✅ Code Editor service started"

# ============================================================================
# STEP 7: WAIT FOR CODE EDITOR TO FULLY START
# ============================================================================

log "Waiting for Code Editor to initialize..."
sleep 15

MAX_RETRIES=30
RETRY_COUNT=0
CODE_EDITOR_READY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    HTTP_CODE=$(probe_editor_http http://127.0.0.1:8080/)
    
    if [ "$HTTP_CODE" = "302" ] || [ "$HTTP_CODE" = "200" ]; then
        log "✅ Code Editor is responding (HTTP $HTTP_CODE)"
        CODE_EDITOR_READY=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    log "Waiting for authenticated Code Editor... ($RETRY_COUNT/$MAX_RETRIES) [HTTP: $HTTP_CODE]"
    sleep 2
done

if [ "$CODE_EDITOR_READY" = "false" ]; then
    error "Code Editor did not pass its authenticated HTTP check"
fi

# ============================================================================
# STEP 8: VS CODE EXTENSIONS (~3 min)
# ============================================================================

log "Installing VS Code extensions..."

install_extension() {
    local EXT_ID=$1
    local EXT_NAME=$2
    
    log "Installing extension: $EXT_NAME ($EXT_ID)..."
    
    if [ -f "$CODE_EDITOR_CMD" ]; then
        sudo -u "$CODE_EDITOR_USER" "$CODE_EDITOR_CMD" --install-extension "$EXT_ID" --force 2>&1 | tee -a /tmp/extension_install.log || true
        
        if grep -q "successfully installed" /tmp/extension_install.log 2>/dev/null; then
            log "  ✅ $EXT_NAME"
            return 0
        fi
    fi
    
    warn "  ⚠️  $EXT_NAME may require manual install"
    return 1
}

# Install essential extensions for the hands-on workshop.
# No Jupyter — there are no notebooks in the lab content.
# No Amazon Q extension - it is not used by the participant path.
# No AWS Toolkit extension — it is the source of the Amazon Q "end-of-support",
# "Dismiss", and "Sign-In" first-run pop-ups participants had to clear, and no
# lab step opens the AWS Explorer panel (every "sign in" in the content refers
# to pellier-token.sh / the storefront, never the Toolkit UI). Leaving it
# uninstalled removes the pop-ups at the source; the amazonQ.*/aws.suppressPrompts
# settings below are kept as defense-in-depth in case it's ever re-enabled.
install_extension "ms-python.python" "Python"
install_extension "ms-python.vscode-pylance" "Pylance"
install_extension "dbaeumer.vscode-eslint" "ESLint"
install_extension "esbenp.prettier-vscode" "Prettier"
install_extension "bradlc.vscode-tailwindcss" "Tailwind CSS"

log "✅ VS Code extensions installed"

# ============================================================================
# STEP 9: VS CODE SETTINGS (~5 sec)
# ============================================================================

log "Configuring VS Code settings..."
SETTINGS_DIR="/home/$CODE_EDITOR_USER/.code-editor-server/data/User"
sudo -u "$CODE_EDITOR_USER" mkdir -p "$SETTINGS_DIR"

# files.exclude keeps the Explorer on what the flagship lab guide actually
# opens: pellier/, policies/, skills/, solutions/, README.md, and CLAUDE.md.
# Repo meta (licenses, VOICE.md, .claude/, data/) stays on disk for Claude
# Code and the terminal but is hidden from the tree and from editor search.
# Do NOT hide policies/, skills/, or solutions/ here - Lab 4 and the
# documented fallback lane direct participants to files inside them.
# Room-tested Code Editor appearance, identical across the two Pellier formats
# and Mosaic: 16/18 reads at arm's length on a laptop, zoomLevel 1 lifts the
# whole chrome without breaking the layout, and the forced white terminal
# foreground is the same value Mosaic already ships on this AMI, so it is known
# to render here. Keep this block strict JSON - the readiness contract parses it
# with json.loads, not a JSONC reader.
cat > "$SETTINGS_DIR/settings.json" << 'VSCODE_SETTINGS'
{
    "workbench.colorTheme": "Default Dark Modern",
    "workbench.colorCustomizations": {
        "terminal.foreground": "#FFFFFF"
    },
    "editor.fontSize": 16,
    "terminal.integrated.fontSize": 18,
    "window.zoomLevel": 1,
    "explorer.compactFolders": false,
    "explorer.autoReveal": true,
    "git.enabled": false,
    "git.decorations.enabled": false,
    "git.showProgress": false,
    "git.autofetch": false,
    "scm.diffDecorations": "none",
    "aws.telemetry": false,
    "aws.suppressPrompts": {
        "minIdeVersion": true,
        "ssoCacheError": true,
        "createCredentialsProfile": true,
        "remoteConnected": true,
        "codeCatalystConnectionExpired": true,
        "yamlExtPrompt": true,
        "regionAddAutomatically": true
    },
    "amazonQ.telemetry": false,
    "amazonQ.shareContentWithAWS": false,
    "amazonQ.disableNotifications": true,
    "amazonQ.suppressPrompts": {
        "codeWhispererNewWelcomeMessage": true,
        "amazonQWelcomePage": true,
        "codeWhispererConnectionExpired": true,
        "createCredentialsProfile": true,
        "amazonQSessionConfigurationMessage": true,
        "minIdeVersion": true,
        "ssoCacheError": true
    },
    "extensions.autoUpdate": false,
    "extensions.autoCheckUpdates": false,
    "extensions.ignoreRecommendations": true,
    "redhat.telemetry.enabled": false,
    "telemetry.telemetryLevel": "off",
    "security.workspace.trust.startupPrompt": "never",
    "security.workspace.trust.enabled": false,
    "security.workspace.trust.banner": "never",
    "security.workspace.trust.emptyWindow": false,
    "workbench.startupEditor": "none",
    "workbench.welcomePage.walkthroughs.openOnInstall": false,
    "workbench.tips.enabled": false,
    "update.showReleaseNotes": false,
    "terminal.integrated.defaultProfile.linux": "bash",
    "task.allowAutomaticTasks": "on",
    "python.defaultInterpreterPath": "/usr/bin/python3",
    "python.testing.pytestEnabled": true,
    "files.autoSave": "afterDelay",
    "files.autoSaveDelay": 1000,
    "files.exclude": {
        "**/.git": true,
        "**/.github": true,
        "**/.vscode": true,
        "**/scripts": true,
        "**/.venv": true,
        "**/__pycache__": true,
        "**/.pytest_cache": true,
        "**/node_modules": true,
        "**/dist": true,
        "tests": true,
        "archive": true,
        "docs": true,
        "infrastructure": true,
        "logs": true,
        "tmp": true,
        "package.json": true,
        "package-lock.json": true,
        ".claude": true,
        ".gitignore": true,
        "LICENSE": true,
        "NOTICE": true,
        "VOICE.md": true,
        "data": true
    }
}
VSCODE_SETTINGS

chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$SETTINGS_DIR"

log "✅ VS Code user settings configured"

# NOTE: workspace (.vscode) settings + tasks.json are written below into
# the REPO folder code-editor actually opens ($HOME_FOLDER/$REPO_NAME),
# not $HOME_FOLDER. A folderOpen task only fires from the opened folder's
# .vscode/, so writing them here (the unopened parent) had no effect.
log "✅ VS Code user settings configured"

# ============================================================================
# AUTO-OPEN TERMINAL CONFIGURATION
# ============================================================================

log "Configuring auto-open terminal with welcome message..."

# Create scripts directory
mkdir -p "$HOME_FOLDER/scripts"

# Create welcome script that exits cleanly
cat > "$HOME_FOLDER/scripts/welcome.sh" << 'WELCOME_EOF'
#!/bin/bash

# Display welcome message once and exit
clear

cat << EOF
  Pellier agentic AI-powered search
  Build, measure, and prove search with Aurora PostgreSQL

  START       Keep the lab guide open. Work primarily in this terminal and
              the Pellier storefront.

  BUILD       Required path: wire check_inventory in
              pellier/backend/services/agent_tools.py.

  MEASURE     Compare retrieval strategies for Anna's query.

  PROVE       Lab 4: query pellier.tool_audit from psql.

  OBSERVATORY Use Pellier Observatory only when a step names a specific verification
              or comparison view.

  FILE        agent_tools.py is open. Find the check_inventory WORKSHOP markers,
              implement, save, then test in Pellier.

EOF

# Auto-open the one file participants edit in the workshop.
code /workshop/sample-pellier-agentic-search-apg/pellier/backend/services/agent_tools.py 2>/dev/null || true

# Exit cleanly so task completes
exit 0
WELCOME_EOF

chmod +x "$HOME_FOLDER/scripts/welcome.sh"
chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$HOME_FOLDER/scripts/welcome.sh"

# Create VS Code tasks.json for auto-open terminal.
#
# CRITICAL: a `folderOpen` task only fires from the .vscode/ of the
# folder code-editor actually OPENS, which is $HOME_FOLDER/$REPO_NAME
# (see --default-folder in the systemd ExecStart), NOT $HOME_FOLDER.
# A prior revision wrote this to $HOME_FOLDER/.vscode and the task
# silently never ran on fresh accounts. Write it to the repo's .vscode/.
# (Pairs with "task.allowAutomaticTasks": "on" in user settings above,
# without which code-editor PROMPTS instead of auto-running.)
REPO_VSCODE="$HOME_FOLDER/$REPO_NAME/.vscode"
sudo -u "$CODE_EDITOR_USER" mkdir -p "$REPO_VSCODE"
cat > "$REPO_VSCODE/tasks.json" << 'TASKS_EOF'
{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "Welcome Terminal",
            "type": "shell",
            "command": "bash",
            "args": ["-c", "/workshop/scripts/welcome.sh && exec bash"],
            "presentation": {
                "echo": false,
                "reveal": "always",
                "focus": true,
                "panel": "dedicated",
                "showReuseMessage": false,
                "clear": true,
                "close": false
            },
            "runOptions": {
                "runOn": "folderOpen"
            },
            "isBackground": false,
            "problemMatcher": []
        }
    ]
}
TASKS_EOF

# Workspace settings live in the SAME folder code-editor opens (the repo),
# alongside tasks.json — so task.autoDetect applies to the folder whose
# folderOpen task we want to fire. (Earlier this was written to
# $HOME_FOLDER/.vscode, the unopened parent, so it had no effect.)
cat > "$REPO_VSCODE/settings.json" << 'WORKSPACE_SETTINGS'
{
    "workbench.colorTheme": "Default Dark Modern",
    "editor.fontSize": 16,
    "terminal.integrated.fontSize": 18,
    "window.zoomLevel": 1,
    "python.defaultInterpreterPath": "/usr/bin/python3",
    "task.autoDetect": "on",
    "task.allowAutomaticTasks": "on",
    "task.problemMatchers.neverPrompt": true,
    "explorer.autoReveal": true,
    "explorer.expandSingleFolderWorkspaces": true
}
WORKSPACE_SETTINGS

chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$REPO_VSCODE"
chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$HOME_FOLDER/scripts"

log "✅ Auto-open terminal configured (repo .vscode/, auto-tasks enabled)"

# ============================================================================
# STEP 10: PYTHON SETUP (~10 sec)
# ============================================================================

log "Installing locked workshop dependencies..."

# Install backend dependencies from requirements.lock — boto3, FastAPI,
# Strands SDK, psycopg, etc. The workshop app needs all of these
# at runtime; the pip install must succeed for the pellier service to
# start.
REQUIREMENTS="$HOME_FOLDER/$REPO_NAME/pellier/backend/requirements.lock"
if [ -f "$REQUIREMENTS" ]; then
    log "Installing backend dependencies from requirements.lock..."
    sudo -u "$CODE_EDITOR_USER" python3 -m pip install --user --require-hashes -r "$REQUIREMENTS" 2>&1 \
        | tee /var/log/pellier-pip-install.log
    PIP_EXIT=${PIPESTATUS[0]}
    if [ "$PIP_EXIT" -ne 0 ]; then
        error "Locked dependency install failed (exit $PIP_EXIT); see /var/log/pellier-pip-install.log"
    else
        log "✅ Backend dependencies installed"
        log "✅ Locked backend dependency set is available to Python"
    fi
else
    error "requirements.lock missing at $REQUIREMENTS"
fi

# Set AWS region and workshop shortcuts for user environment
log "Configuring AWS region and workshop shortcuts..."
# Write the resolved region literally (the prior single-quoted heredoc wrote
# the string "$AWS_REGION" verbatim → a self-referential, empty export). The
# aliases below stay literal, so emit the AWS block separately (unquoted) then
# the shortcuts block (quoted).
cat >> "/home/$CODE_EDITOR_USER/.bashrc" << EOF

# AWS Configuration
export AWS_REGION="$AWS_REGION"
export AWS_DEFAULT_REGION="$AWS_REGION"
EOF
cat >> "/home/$CODE_EDITOR_USER/.bashrc" << 'EOF'

# Workshop shortcuts
alias workshop='cd /workshop'
alias pellier='cd /workshop/sample-pellier-agentic-search-apg/pellier'

# Load .env file if it exists. The repo .env is written by the labs stage
# (bootstrap-labs.sh) at REPO_PATH/.env, NOT /workshop/.env — match that path
# so this stage-1 block isn't a dead no-op. bootstrap-labs.sh appends its own
# (richer, PG*-exporting) source block after this one; this is the defensive
# floor if that stage doesn't run.
if [ -f /workshop/sample-pellier-agentic-search-apg/.env ]; then
    set -a
    source /workshop/sample-pellier-agentic-search-apg/.env
    set +a
fi

# Add local bin to PATH
export PATH="$HOME/.local/bin:$PATH"
EOF

chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "/home/$CODE_EDITOR_USER/.bashrc"

log "✅ Python ${PY_VER} configured"

# ============================================================================
# STEP 11: FINAL VERIFICATION (~5 sec)
# ============================================================================

log "Performing final verification..."

# Verify Code Editor service
if systemctl is-active --quiet "code-editor@$CODE_EDITOR_USER"; then
    log "✅ Code Editor service is active"
else
    error "Code Editor service is not running"
fi

# Verify Code Editor responding
HTTP_CODE=$(probe_editor_http http://127.0.0.1:8080/)
if [ "$HTTP_CODE" = "302" ] || [ "$HTTP_CODE" = "200" ]; then
    log "✅ Code Editor verified running (HTTP $HTTP_CODE)"
else
    error "Code Editor authenticated HTTP check returned $HTTP_CODE"
fi

# Verify Nginx
if systemctl is-active --quiet nginx; then
    log "✅ Nginx verified running"
else
    error "Nginx is not running"
fi

# Verify Nginx proxy
NGINX_CODE=$(probe_editor_http http://127.0.0.1:80/ \
    -H "X-Pellier-Origin-Verify: $ORIGIN_VERIFY_TOKEN" \
    -H "X-Forwarded-Proto: https")
if [ "$NGINX_CODE" = "302" ] || [ "$NGINX_CODE" = "200" ]; then
    log "✅ Nginx proxy verified (HTTP $NGINX_CODE)"
else
    error "Nginx authenticated proxy HTTP check returned $NGINX_CODE"
fi

# ============================================================================
# STEP 12: RUN STAGE 2 AND PROVE READINESS
# ============================================================================
#
# CloudFormation must not report the box ready while the workshop application is
# still building in a detached process. Stage 2 owns the deployed application,
# authenticated Operator sign-in, managed Runtime smoke, and durable receipt
# checks, so it is the readiness boundary.
#
# The manifest is deliberately root-owned and mode 0600. It carries the
# CloudFormation inputs Stage 2 needs without embedding an ever-growing,
# shell-quoted sudo command in this script.
STAGE2_ENV_MANIFEST="/etc/pellier/bootstrap-stage2.env"

write_stage2_manifest() {
    local manifest_dir temp_manifest name value
    manifest_dir="$(dirname "$STAGE2_ENV_MANIFEST")"
    mkdir -p "$manifest_dir"
    chmod 700 "$manifest_dir"
    temp_manifest="$(mktemp "${manifest_dir}/bootstrap-stage2.XXXXXX")"

    for name in \
        CODE_EDITOR_USER HOME_FOLDER REPO_NAME REPO_URL \
        WORKSHOP_FORMAT WORKSHOP_BRANCH WORKSHOP_ID WORKSHOP_STACK_NAME \
        WORKSHOP_SOURCE_REVISION AWS_REGION AWS_DEFAULT_REGION \
        DB_SECRET_ARN DB_CLUSTER_ARN DB_CLUSTER_ENDPOINT DB_NAME \
        ASSETS_BUCKET_NAME ASSETS_BUCKET_PREFIX \
        BEDROCK_EMBEDDING_MODEL BEDROCK_RERANK_MODEL \
        BEDROCK_CHAT_MODEL BEDROCK_FAST_MODEL \
        COGNITO_USER_POOL_ID COGNITO_POOL_ID COGNITO_POOL \
        COGNITO_CLIENT_ID COGNITO_CLIENT COGNITO_DOMAIN COGNITO_REGION \
        COGNITO_TEST_CREDENTIALS_SECRET_ARN COGNITO_CLIENT_SECRET_ARN \
        AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN \
        AGENTCORE_RUNTIME_LOG_RETENTION_DAYS TS_DESIRED_SAMPLING \
        ORIGIN_VERIFY_TOKEN
    do
        value="${!name:-}"
        printf 'export %s=%q\n' "$name" "$value" >> "$temp_manifest"
    done

    chown root:root "$temp_manifest"
    chmod 600 "$temp_manifest"
    mv -f "$temp_manifest" "$STAGE2_ENV_MANIFEST"
}

signal_cloudformation() {
    local status="$1" reason="$2" data="$3"
    local attempt response http_code

    if [ -z "${CFN_WAIT_HANDLE}" ]; then
        log "ℹ️  CFN_WAIT_HANDLE not set - development mode"
        return 0
    fi

    for attempt in {1..5}; do
        response="$(curl -X PUT -H 'Content-Type:' \
            --data-binary "{\"Status\":\"${status}\",\"Reason\":\"${reason}\",\"UniqueId\":\"Pellier-$(date +%s)\",\"Data\":\"${data}\"}" \
            -w "\nHTTP_CODE:%{http_code}" \
            --max-time 10 \
            "$CFN_WAIT_HANDLE" 2>&1)"
        http_code="$(echo "$response" | grep -o "HTTP_CODE:[0-9]*" | cut -d: -f2)"
        if [ "$http_code" = "200" ]; then
            log "✅ CloudFormation ${status,,} signal accepted (HTTP 200)"
            printf '%s\n' "$response" > "/tmp/cfn-signal-${status,,}.log"
            return 0
        fi
        warn "CloudFormation ${status,,} signal attempt $attempt failed (HTTP: ${http_code:-unknown})"
        sleep 2
    done
    return 1
}

if [ -z "${STAGE2_SCRIPT_URL}" ]; then
    if [ -n "${CFN_WAIT_HANDLE}" ]; then
        signal_cloudformation "FAILURE" "Stage 2 bootstrap URL missing" "Pellier workshop did not reach readiness" || true
        error "STAGE2_SCRIPT_URL is required when Stage 1 owns the CloudFormation signal"
    fi
    # The governed CloudFormation UserData runs both checked-out scripts and
    # its own final health gate. Return control without sending any signal.
    log "Environment ready; the calling UserData must run bootstrap-labs.sh and the governed health gate"
    exit 0
fi

log "Running Stage 2: Labs Bootstrap and governed readiness gate..."
mkdir -p "$HOME_FOLDER"
chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$HOME_FOLDER"
chmod 755 "$HOME_FOLDER"
write_stage2_manifest

curl -fsSL "$STAGE2_SCRIPT_URL" -o /tmp/bootstrap-labs.sh
chmod 700 /tmp/bootstrap-labs.sh

stage2_ok=true
if bash -c 'source "$1"; exec /tmp/bootstrap-labs.sh' -- "$STAGE2_ENV_MANIFEST" \
    2>&1 | tee /var/log/bootstrap-labs.log; then
    log "✅ Stage 2 and governed readiness gate completed"
else
    stage2_ok=false
fi

# Stage 2's exit status says the script ended. Its provisioning state file says
# how far it proved: PROVISIONING -> APP_READY -> MANAGED_READY -> E2E_PROVED,
# or FAILED. A governed box is ready only at E2E_PROVED; the builders format is
# ready once the application answered /api/health. Anything else, including an
# absent file from a Stage 2 that never started, is reported to CloudFormation
# as a failure with the state in the reason.
PROVISION_STATE_FILE="${PELLIER_PROVISION_STATE_FILE:-/var/lib/pellier/provision-state}"
provision_state="$(cat "$PROVISION_STATE_FILE" 2>/dev/null | tr -d '[:space:]' || true)"
log "Provision state after Stage 2: ${provision_state:-absent}"

if [ "$stage2_ok" != true ]; then
    signal_cloudformation "FAILURE" \
        "Stage 2 or governed readiness failed (provision state ${provision_state:-absent})" \
        "See /var/log/bootstrap-labs.log" || true
    error "Stage 2 did not prove an application-ready governed workshop"
fi

case "${WORKSHOP_FORMAT:-governed}:${provision_state}" in
    governed:E2E_PROVED)
        log "✅ Governed provisioning reached E2E_PROVED"
        ;;
    builders:APP_READY|builders:MANAGED_READY|builders:E2E_PROVED)
        log "✅ Builders provisioning reached ${provision_state}"
        ;;
    *)
        signal_cloudformation "FAILURE" \
            "Provision state is ${provision_state:-absent}, not proved for the ${WORKSHOP_FORMAT:-governed} format" \
            "See /var/log/bootstrap-labs.log" || true
        error "Stage 2 ended in provision state ${provision_state:-absent}; refusing to report the workshop ready"
        ;;
esac

# ============================================================================
# STEP 13: SIGNAL CLOUDFORMATION SUCCESS
# ============================================================================

if ! signal_cloudformation \
    "SUCCESS" \
    "Stage 2 plus governed readiness succeeded" \
    "Authenticated sign-in, managed invocation, and durable evidence receipt passed"; then
    error "CRITICAL: Failed to signal CloudFormation readiness after 5 attempts"
fi

# ============================================================================
# SUMMARY
# ============================================================================

log "=========================================="
log "Stage 1: Environment Bootstrap Complete!"
log "=========================================="
echo ""
echo "✅ Code Editor ready and accessible"
echo "✅ VS Code extensions installed"
echo "✅ Python ${PY_VER} configured"
echo "✅ Stage 2 application and governed readiness checks passed"
echo "✅ CloudFormation signaled after the workshop proved ready"
echo ""
echo "Use the CloudFormation Code Editor URL and password output to connect."
echo ""
log "=========================================="

exit 0
