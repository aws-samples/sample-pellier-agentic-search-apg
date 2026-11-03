#!/usr/bin/env bash
# Reset the governed two-hour Pellier workshop evidence path.
#
# Safe to re-run. It restores the participant Cedar state, makes sure the
# HNSW index exists, reseeds the deterministic forensic receipt, and then runs
# the normal health gate so facilitators get one readable verdict.

set -euo pipefail

REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
ENV_FILE="${REPO}/.env"
PYTHON="${REPO}/pellier/backend/.venv/bin/python"

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}[PASS]${NC} %s\n" "$1"; }
fail() { printf "  ${RED}[FAIL]${NC} %s\n" "$1"; }
warn() { printf "  ${YEL}[WARN]${NC} %s\n" "$1"; }

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
else
  fail "Missing env file: $ENV_FILE"
  exit 1
fi

cd "$REPO"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

# This script TRUNCATEs the evidence tables, so it must never guess which
# database to talk to. Require DB_NAME/DB_USER from the sourced .env rather
# than silently defaulting to the `postgres` maintenance database.
: "${DB_NAME:?DB_NAME is not set in $ENV_FILE — refusing to run a destructive reset against a guessed database}"
: "${DB_USER:?DB_USER is not set in $ENV_FILE — refusing to run a destructive reset against a guessed role}"

_psql_file() {
  local file="$1"
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -f "$file"
}

_psql_exec() {
  local sql="$1"
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -c "$sql"
}

echo "Pellier governed reset - $(date '+%H:%M:%S')"
echo "------------------------------------------------------------"

if ! "$PYTHON" "$REPO/scripts/seed_pellier_catalog.py" \
    --from-cache >/tmp/pellier-governed-reset-catalog.log 2>&1; then
  fail "Deterministic catalog reset failed; see /tmp/pellier-governed-reset-catalog.log"
  exit 1
fi
pass "Catalog quantities restored from committed embedding cache"

for migration in \
  006_warehouse_inventory.sql \
  011_governed_write_integrity.sql \
  012_retrieval_receipts.sql \
  013_inventory_ledger.sql
do
  if [[ ! -f "$REPO/scripts/migrations/$migration" ]]; then
    fail "Missing scripts/migrations/$migration"
    exit 1
  fi
  _psql_file "$REPO/scripts/migrations/$migration" \
    >>/tmp/pellier-governed-reset-db.log
done
pass "Exactly three warehouse rows per curated product reseeded"

_psql_exec "
TRUNCATE TABLE
    pellier.governed_receipts,
    pellier.tool_audit,
    pellier.retrieval_receipts,
    pellier.inventory_ledger,
    pellier.write_operations,
    pellier.returns
RESTART IDENTITY;
" >/tmp/pellier-governed-reset-evidence.log
pass "Live returns, stock movements, write keys, audits, and receipts cleared"

_psql_file "$REPO/scripts/migrations/013_inventory_ledger.sql" \
  >>/tmp/pellier-governed-reset-db.log
pass "Inventory ledger reseeded from deterministic warehouse state"

if [[ ! -f "$REPO/scripts/migrations/010_governed_receipts.sql" ]]; then
  fail "Missing scripts/migrations/010_governed_receipts.sql"
  exit 1
fi
_psql_file "$REPO/scripts/migrations/010_governed_receipts.sql" \
  >>/tmp/pellier-governed-reset-db.log
pass "Canonical governed forensic incident reseeded"

_psql_exec '
CREATE INDEX IF NOT EXISTS product_catalog_embedding_hnsw
    ON pellier.product_catalog
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
ANALYZE pellier.product_catalog;
' >/tmp/pellier-governed-reset-index.log
pass "HNSW index present: product_catalog_embedding_hnsw"

AGENTCORE_PROJECT="$REPO/.agentcore-project/pellier"
AGENTCORE_CONFIG="$AGENTCORE_PROJECT/agentcore/agentcore.json"
POLICY_ENGINE_NAME="pellier_policy_engine"

if [[ ! -f "$AGENTCORE_CONFIG" ]]; then
  fail "AgentCore CLI project missing: $AGENTCORE_CONFIG"
  exit 1
fi

_agentcore() {
  (
    cd "$AGENTCORE_PROJECT"
    if command -v agentcore >/dev/null 2>&1; then
      command agentcore "$@"
    else
      npx -y @aws/agentcore@0.29.0 "$@"
    fi
  )
}

policy_changed=false
for policy_name in workshop_identity_match_forbid workshop_final_sale_forbid; do
  if jq -e \
      --arg engine "$POLICY_ENGINE_NAME" \
      --arg policy "$policy_name" \
      '.policyEngines[] | select(.name == $engine) | .policies[]? | select(.name == $policy)' \
      "$AGENTCORE_CONFIG" >/dev/null; then
    _agentcore remove policy \
      --name "$policy_name" \
      --engine "$POLICY_ENGINE_NAME" \
      --yes \
      --json >>/tmp/pellier-governed-reset-policy.log
    policy_changed=true
  fi
done

if [[ "$policy_changed" == true ]]; then
  _agentcore validate --json >>/tmp/pellier-governed-reset-policy.log
  _agentcore deploy --yes --json >>/tmp/pellier-governed-reset-policy.log
  pass "Participant Cedar rule removed through AgentCore CLI"
else
  pass "Participant Cedar rule absent; shipped CLI project already restored"
fi

if [[ "$(jq -r \
    --arg name pellier-gateway \
    '.agentCoreGateways[] | select(.name == $name) | .policyEngineConfiguration.mode' \
    "$AGENTCORE_CONFIG")" != "ENFORCE" ]]; then
  fail "AgentCore project no longer pins Gateway Policy mode to ENFORCE"
  exit 1
fi
pass "Gateway Policy remains configured in ENFORCE mode"

if [[ -x "$REPO/scripts/health-gate.sh" ]]; then
  echo "------------------------------------------------------------"
  PELLIER_REPO="$REPO" bash "$REPO/scripts/health-gate.sh"
else
  warn "health-gate.sh missing"
fi
