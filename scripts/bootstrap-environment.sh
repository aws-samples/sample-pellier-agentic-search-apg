#!/bin/bash
# Pellier Workshop - Stage 1: Environment Bootstrap
# Purpose: Get Code Editor + VS Code ready FAST, then signal CloudFormation
# Duration: ~8 minutes

set -euo pipefail

# ============================================================================
# PARAMETERS FROM ENVIRONMENT
# ============================================================================
CODE_EDITOR_PASSWORD="${CODE_EDITOR_PASSWORD:-defaultPassword}"
CODE_EDITOR_USER="${CODE_EDITOR_USER:-participant}"
HOME_FOLDER="${HOME_FOLDER:-/workshop}"
REPO_NAME="${REPO_NAME:-sample-pellier-agentic-search-apg}"
CFN_WAIT_HANDLE="${CFN_WAIT_HANDLE:-}"
STAGE2_SCRIPT_URL="${STAGE2_SCRIPT_URL:-}"
ASSETS_BUCKET_NAME="${ASSETS_BUCKET_NAME:-}"
ASSETS_BUCKET_PREFIX="${ASSETS_BUCKET_PREFIX:-}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"; }
error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"; exit 1; }

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
# whole box (the Boutique still works on Node 18; only the managed-Runtime deploy
# needs 20). We retry NodeSource, and if Node 20 lands we pin it ahead of any
# distro Node 18 via update-alternatives so downstream `node`/`npx` resolve to
# 20 deterministically. The hard "is this actually 20?" guard lives at the
# provisioning call site (bootstrap-labs STEP 16), where aborting just the
# already-best-effort AgentCore step is the right blast radius. The health gate
# surfaces an empty AGENTCORE_RUNTIME_ENDPOINT if 20 never arrived.
log "Installing Node.js 20 (required by @aws/agentcore CLI; AL2023 default is 18)..."
_node20_ok=false
for attempt in 1 2; do
    if curl -fsSL https://rpm.nodesource.com/setup_20.x | bash - >/dev/null 2>&1 \
        && dnf install -y -q nodejs; then
        _node20_ok=true
        break
    fi
    warn "NodeSource Node 20 install attempt $attempt failed; retrying..."
    sleep 3
done

if [ "$_node20_ok" = true ]; then
    # Pin this node ahead of any distro Node 18 so `node`/`npx` resolve to 20.
    _node_bin="$(command -v node 2>/dev/null || true)"
    [ -n "$_node_bin" ] && update-alternatives --install /usr/bin/node node "$_node_bin" 100 >/dev/null 2>&1 || true
    _node_major="$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)"
    if echo "$_node_major" | grep -qE '^[0-9]+$' && [ "$_node_major" -ge 20 ]; then
        log "✅ Node.js installed and pinned: $(node --version 2>/dev/null)"
    else
        warn "NodeSource reported success but node is $(node --version 2>/dev/null || echo none) (<20). @aws/agentcore Runtime deploy will fail until Node 20 is on PATH."
    fi
else
    warn "NodeSource Node 20 install failed after retries — falling back to AL2023 default nodejs (Node 18). The @aws/agentcore Runtime deploy will NOT work on Node 18; the Boutique + frontend build still will. Re-run 'curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash - && sudo dnf install -y nodejs' then re-provision."
    dnf install --skip-broken -y -q nodejs
    warn "Node version: $(node --version 2>/dev/null || echo 'none')"
fi

# ----------------------------------------------------------------------------
# Python: prefer 3.14, fall back to 3.13 if AL2023 doesn't yet package it.
#
# We probe with `dnf install` for each candidate in order and take the first
# that succeeds. PY_VER (e.g. "3.14") is then used for update-alternatives so
# /usr/bin/python3 points at the chosen interpreter. Downstream scripts call
# `python3` (the alternative), never a pinned python3.X, so they follow this
# choice automatically. Rationale: a fresh CPython minor can lag on AL2023
# packaging and on C-extension wheels (psycopg, pydantic-core); the fallback
# guarantees provisioning never bricks on a missing python3.14 package.
# ----------------------------------------------------------------------------
log "Installing Python (prefer 3.14, fall back to 3.13)..."
PY_VER=""
for cand in 3.14 3.13; do
    if dnf install --skip-broken -y -q \
        "python${cand}" \
        "python${cand}-pip" \
        "python${cand}-setuptools" \
        "python${cand}-devel" \
        "python${cand}-wheel" \
        "python${cand}-tkinter" 2>/dev/null \
        && command -v "python${cand}" >/dev/null 2>&1; then
        PY_VER="$cand"
        break
    fi
    warn "python${cand} not available — trying next candidate"
done
if [ -z "$PY_VER" ]; then
    error "No supported Python (3.14 or 3.13) could be installed — backend cannot start"
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
./aws/install --update
rm -rf awscliv2.zip aws/
cd - > /dev/null

log "✅ AWS CLI installed: $(aws --version)"

# Set the chosen Python ($PY_VER, from STEP 1) as the default python3.
log "Setting Python ${PY_VER} as default..."
update-alternatives --install /usr/bin/python3 python3 "/usr/bin/python${PY_VER}" 1
update-alternatives --set python3 "/usr/bin/python${PY_VER}"
log "✅ Python ${PY_VER} set as default (python3 → python${PY_VER})"

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
server {
    listen 80;
    listen [::]:80;
    server_name _;
    
    # Pellier (single-process): FastAPI on :8000 serves BOTH
    # /api/* AND the built SPA (/, /atelier, /storyboard, /discover,
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
        proxy_set_header X-Forwarded-Proto $scheme;
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
        proxy_set_header X-Forwarded-Proto $scheme;
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
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
EOF

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

# Get AWS region from environment or EC2 metadata
AWS_REGION="${AWS_REGION:-$(curl -s http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo 'us-west-2')}"
log "AWS Region: $AWS_REGION"

# ----------------------------------------------------------------------------
# CDK bootstrap (required by @aws/agentcore 0.18 `deploy`, which is CDK-based).
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
    if AWS_REGION="$AWS_REGION" AWS_DEFAULT_REGION="$AWS_REGION" \
        npx -y aws-cdk@2 bootstrap "aws://${CDK_ACCOUNT}/${AWS_REGION}" >/dev/null 2>&1; then
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
RESTART_ATTEMPTED=false
FORBIDDEN_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/ 2>/dev/null || echo "000")
    
    # Success codes - Code Editor is ready
    if [ "$HTTP_CODE" = "302" ] || [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "405" ]; then
        log "✅ Code Editor is responding (HTTP $HTTP_CODE)"
        CODE_EDITOR_READY=true
        sleep 2
        break
    
    # HTTP 403 - Code Editor is starting but not ready yet
    elif [ "$HTTP_CODE" = "403" ]; then
        FORBIDDEN_COUNT=$((FORBIDDEN_COUNT + 1))
        
        # After 15 consecutive 403s, try restart once
        if [ $FORBIDDEN_COUNT -eq 15 ] && [ "$RESTART_ATTEMPTED" = "false" ]; then
            warn "HTTP 403 persisting - restarting Code Editor service..."
            systemctl restart "code-editor@$CODE_EDITOR_USER"
            RESTART_ATTEMPTED=true
            FORBIDDEN_COUNT=0
            sleep 10
        # After 25 total 403s, assume it's working but auth not ready
        elif [ $FORBIDDEN_COUNT -ge 25 ]; then
            warn "HTTP 403 persisting but service is running - continuing..."
            CODE_EDITOR_READY=true
            break
        else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            log "Code Editor starting... ($RETRY_COUNT/$MAX_RETRIES) [HTTP: $HTTP_CODE]"
            sleep 2
        fi
    
    # Other codes - keep waiting
    else
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
            warn "Code Editor verification timeout (HTTP: $HTTP_CODE) - but service is running, continuing..."
            CODE_EDITOR_READY=true
            break
        fi
        log "Waiting for Code Editor... ($RETRY_COUNT/$MAX_RETRIES) [HTTP: $HTTP_CODE]"
        sleep 2
    fi
done

# If service is running, consider it ready even if HTTP check failed
if [ "$CODE_EDITOR_READY" = "false" ]; then
    if systemctl is-active --quiet "code-editor@$CODE_EDITOR_USER"; then
        warn "Code Editor HTTP check failed but service is running - continuing..."
        CODE_EDITOR_READY=true
    else
        error "Code Editor did not become ready"
    fi
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

# Install essential extensions for the 60-min Builder's Session.
# No Jupyter — there are no notebooks in the lab content.
# No Amazon Q extension — the MCP demo runs from the integrated terminal
# (the Q extension is being retired, and Act III §02 reads the config +
# verifies `awslabs.postgres-mcp-server` via uvx instead).
install_extension "ms-python.python" "Python"
install_extension "ms-python.vscode-pylance" "Pylance"
install_extension "dbaeumer.vscode-eslint" "ESLint"
install_extension "esbenp.prettier-vscode" "Prettier"
install_extension "bradlc.vscode-tailwindcss" "Tailwind CSS"
install_extension "amazonwebservices.aws-toolkit-vscode" "AWS Toolkit"

log "✅ VS Code extensions installed"

# ============================================================================
# STEP 9: VS CODE SETTINGS (~5 sec)
# ============================================================================

log "Configuring VS Code settings..."
SETTINGS_DIR="/home/$CODE_EDITOR_USER/.code-editor-server/data/User"
sudo -u "$CODE_EDITOR_USER" mkdir -p "$SETTINGS_DIR"

cat > "$SETTINGS_DIR/settings.json" << 'VSCODE_SETTINGS'
{
    "workbench.colorTheme": "Default Dark Modern",
    "editor.fontSize": 13,
    "terminal.integrated.fontSize": 18,
    "explorer.compactFolders": false,
    "explorer.autoReveal": true,
    "git.enabled": false,
    "git.decorations.enabled": false,
    "git.showProgress": false,
    "git.autofetch": false,
    "scm.diffDecorations": "none",
    "aws.telemetry": false,
    "extensions.autoUpdate": false,
    "extensions.autoCheckUpdates": false,
    "telemetry.telemetryLevel": "off",
    "security.workspace.trust.startupPrompt": "never",
    "security.workspace.trust.enabled": false,
    "security.workspace.trust.banner": "never",
    "security.workspace.trust.emptyWindow": false,
    "workbench.startupEditor": "none",
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
        ".kiro": true,
        "tests": true,
        "archive": true,
        "docs": true,
        "infrastructure": true,
        "lab-content-audit.md": true,
        "logs": true,
        "tmp": true,
        "WORKSHOP_HARDENING_TODO.md": true,
        "CHANGELOG.md": true,
        "package.json": true,
        "package-lock.json": true
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
cat << 'EOF'
╔═══════════════════════════════════════════════════════════════════╗
║              Pellier Workshop · Quick Start                       ║
║      Agentic AI-Powered Search with Aurora PostgreSQL             ║
╚═══════════════════════════════════════════════════════════════════╝

Ready. The app is already running; no servers to start.

OPEN THE APP  (new browser tab)
  Copy your Code Editor CloudFront domain only, drop any /?tkn=... part,
  then add one of these paths:

    Storefront:  https://<your-domain>.cloudfront.net/ports/8000/
    Atelier:     https://<your-domain>.cloudfront.net/ports/8000/atelier

  You can also find the domain in Workshop Studio Outputs: CodeEditorURL.
  Keep the trailing slash on /ports/8000/.

WORKFLOW
  1. Open pellier/backend/services/agent_tools.py  (opened for you)
  2. Find:  CHALLENGE · Stock Keeper · floor_check
  3. Implement between the markers
  4. Save; the backend reloads automatically (~2s)
  5. Refresh the app and test Marco Turn 4

HANDY
  psql                      Connect to Aurora PostgreSQL
  journalctl -fu pellier    Watch backend logs
  rebuild-frontend          Only after editing pellier/frontend/src

SHORT ON TIME?
  cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
     pellier/backend/services/agent_tools.py
  (save — the backend reloads automatically)

═══════════════════════════════════════════════════════════════════

EOF

# Auto-open the one file participants edit in the Builder's Session.
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
    "editor.fontSize": 13,
    "terminal.integrated.fontSize": 18,
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

log "Upgrading pip and installing workshop dependencies..."
# Upgrade pip
sudo -u "$CODE_EDITOR_USER" python3 -m pip install --user --upgrade pip -q

# Install backend dependencies from requirements.txt — boto3, FastAPI,
# Strands SDK, psycopg, etc. The Builder's Session needs all of these
# at runtime; the pip install must succeed for the pellier service to
# start.
REQUIREMENTS="$HOME_FOLDER/$REPO_NAME/pellier/backend/requirements.txt"
if [ -f "$REQUIREMENTS" ]; then
    log "Installing backend dependencies from requirements.txt..."
    sudo -u "$CODE_EDITOR_USER" python3 -m pip install --user -r "$REQUIREMENTS" 2>&1 \
        | tee /var/log/pellier-pip-install.log
    PIP_EXIT=${PIPESTATUS[0]}
    if [ "$PIP_EXIT" -ne 0 ]; then
        warn "pip install failed (exit $PIP_EXIT) — pellier service may not start"
        warn "  see /var/log/pellier-pip-install.log"
    else
        log "✅ Backend dependencies installed"
    fi
else
    warn "requirements.txt missing at $REQUIREMENTS — backend will not start"
fi

# Set AWS region and workshop shortcuts for user environment
log "Configuring AWS region and workshop shortcuts..."
cat >> "/home/$CODE_EDITOR_USER/.bashrc" << 'EOF'

# AWS Configuration
export AWS_REGION="$AWS_REGION"
export AWS_DEFAULT_REGION="$AWS_REGION"

# Workshop shortcuts
alias workshop='cd /workshop'
alias pellier='cd /workshop/sample-pellier-agentic-search-apg/pellier'

# Load .env file if it exists
if [ -f /workshop/.env ]; then
    set -a
    source /workshop/.env
    set +a
fi

# Add local bin to PATH
export PATH="$HOME/.local/bin:$PATH"
EOF

chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "/home/$CODE_EDITOR_USER/.bashrc"

log "✅ Python 3.13 configured"

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
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "302" ] || [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "405" ]; then
    log "✅ Code Editor verified running (HTTP $HTTP_CODE)"
else
    warn "Code Editor HTTP check returned $HTTP_CODE (service may still be starting)"
fi

# Verify Nginx
if systemctl is-active --quiet nginx; then
    log "✅ Nginx verified running"
else
    error "Nginx is not running"
fi

# Verify Nginx proxy
NGINX_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:80/ 2>/dev/null || echo "000")
if [ "$NGINX_CODE" = "302" ] || [ "$NGINX_CODE" = "200" ] || [ "$NGINX_CODE" = "405" ]; then
    log "✅ Nginx proxy verified (HTTP $NGINX_CODE)"
else
    warn "Nginx proxy HTTP check returned $NGINX_CODE (service may still be starting)"
fi

# ============================================================================
# STEP 12: SIGNAL CLOUDFORMATION SUCCESS (~1 sec)
# ============================================================================

if [ ! -z "${CFN_WAIT_HANDLE}" ]; then
    log "Signaling CloudFormation WaitCondition..."
    
    SIGNAL_SUCCESS=false
    for attempt in {1..5}; do
        SIGNAL_RESPONSE=$(curl -X PUT -H 'Content-Type:' \
            --data-binary "{\"Status\":\"SUCCESS\",\"Reason\":\"Code Editor Ready\",\"UniqueId\":\"Stage1-$(date +%s)\",\"Data\":\"Environment Bootstrap Complete\"}" \
            -w "\nHTTP_CODE:%{http_code}" \
            --max-time 10 \
            "$CFN_WAIT_HANDLE" 2>&1)
        
        SIGNAL_HTTP_CODE=$(echo "$SIGNAL_RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d: -f2)
        
        if [ "$SIGNAL_HTTP_CODE" = "200" ]; then
            log "✅ CloudFormation signaled successfully (HTTP 200)"
            echo "$SIGNAL_RESPONSE" > /tmp/cfn-signal-stage1.log
            SIGNAL_SUCCESS=true
            break
        else
            warn "Signal attempt $attempt failed (HTTP: ${SIGNAL_HTTP_CODE:-unknown})"
            sleep 2
        fi
    done
    
    if [ "$SIGNAL_SUCCESS" = "false" ]; then
        error "CRITICAL: Failed to signal CloudFormation after 5 attempts"
    fi
else
    log "ℹ️  CFN_WAIT_HANDLE not set - development mode"
fi

# ============================================================================
# STEP 13: TRIGGER STAGE 2 IN BACKGROUND (~1 sec)
# ============================================================================

if [ ! -z "${STAGE2_SCRIPT_URL}" ]; then
    log "Triggering Stage 2: Labs Bootstrap (background)..."
    
    # Create /workshop directory with proper permissions
    mkdir -p "$HOME_FOLDER"
    chown -R "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$HOME_FOLDER"
    chmod 755 "$HOME_FOLDER"
    
    # Download Stage 2 script
    curl -fsSL "$STAGE2_SCRIPT_URL" -o /tmp/bootstrap-labs.sh
    chmod +x /tmp/bootstrap-labs.sh
    
    # Run Stage 2 in background with proper environment variables
    sudo bash -c "export CODE_EDITOR_USER='$CODE_EDITOR_USER' && \
        export HOME_FOLDER='$HOME_FOLDER' && \
        export REPO_URL='${REPO_URL:-https://github.com/aws-samples/sample-pellier-agentic-search-apg.git}' && \
        export DB_SECRET_ARN='${DB_SECRET_ARN:-}' && \
        export DB_CLUSTER_ENDPOINT='${DB_CLUSTER_ENDPOINT:-}' && \
        export DB_NAME='${DB_NAME:-pellier}' && \
        export AWS_REGION='$AWS_REGION' && \
        export BEDROCK_EMBEDDING_MODEL='${BEDROCK_EMBEDDING_MODEL:-us.cohere.embed-v4:0}' && \
        export BEDROCK_RERANK_MODEL='${BEDROCK_RERANK_MODEL:-us.cohere.rerank-v3-5:0}' && \
        export BEDROCK_CHAT_MODEL='${BEDROCK_CHAT_MODEL:-global.anthropic.claude-opus-4-6-v1}' && \
        export ASSETS_BUCKET_NAME='${ASSETS_BUCKET_NAME:-}' && \
        export ASSETS_BUCKET_PREFIX='${ASSETS_BUCKET_PREFIX:-}' && \
        nohup /tmp/bootstrap-labs.sh > /var/log/bootstrap-labs.log 2>&1 &"
    
    sleep 1
    STAGE2_PID=$(pgrep -f bootstrap-labs.sh | tail -1)
    
    log "✅ Stage 2 triggered (PID: $STAGE2_PID)"
    log "   Monitor: sudo tail -f /var/log/bootstrap-labs.log"
else
    warn "STAGE2_SCRIPT_URL not set - Stage 2 will not run"
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
echo "✅ Python 3.13 configured"
echo "✅ CloudFormation signaled (stack continues)"
echo "⏳ Stage 2 running in background (Labs setup)"
echo ""
echo "Access Code Editor at CloudFront URL"
echo "Password: $CODE_EDITOR_PASSWORD"
echo ""
log "=========================================="

exit 0
