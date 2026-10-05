#!/usr/bin/env bash
# Fresh Pellier database: the schema, then the catalog, then the seed.
# Called by scripts/bootstrap-labs.sh, by database-reset.sh, and by the fresh-setup
# test harness (pellier/backend/tests/fresh_cluster.py), so the harness proves these
# exact commands.
#
# Reads DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD PYTHON REPO. Exits non-zero on the
# first failure. PYTHON must be able to import psycopg: on a workshop box that is the
# participant's python3.14, which is why bootstrap runs this script as the participant.
set -euo pipefail
: "${DB_HOST:?}" "${DB_NAME:?}" "${DB_USER:?}"
DB_PORT="${DB_PORT:-5432}"
DB_PASSWORD="${DB_PASSWORD:-}"
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
PYTHON="${PYTHON:-python3}"
# The catalog seeder reads the same DB_* variables, so it reaches the same database.
export DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD
export PGPASSWORD="$DB_PASSWORD"

apply() {
  echo "Applying $1"
  psql -X -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 -q -f "$REPO/scripts/migrations/$1"
}

# 1. The whole schema: ten tables, the role and its row-level security.
apply 001_schema.sql

# 2. The 100 products in data/pellier_catalog.json, with the real Cohere Embed v4
# vectors from the committed cache (data/embeddings_cache.json), so bootstrap never
# calls Bedrock. After a catalog change, regenerate the cache on a machine with Bedrock
# access: `python scripts/seed_pellier_catalog.py --csv-only`.
echo "Seeding catalog from cache"
(cd "$REPO" && "$PYTHON" scripts/seed_pellier_catalog.py --from-cache)

# 3. Everything else: stock, customers, orders, policies, tickets. It reads the
# catalog, so it runs last.
apply 002_seed.sql
echo "Database setup complete"
