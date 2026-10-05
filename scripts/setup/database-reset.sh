#!/usr/bin/env bash
# Workshop reset, database part: drop the pellier schema and build it again exactly as a
# fresh database is built, so a reset database and a fresh one cannot differ.
# Called by scripts/reset-governed-workshop.sh after it has stopped the application, and
# by the fresh-setup test harness (pellier/backend/tests/fresh_cluster.py), so the
# harness proves these exact commands.
#
# Reads DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD PYTHON REPO. Exits non-zero on the
# first failure.
set -euo pipefail
: "${DB_HOST:?}" "${DB_NAME:?}" "${DB_USER:?}"
DB_PORT="${DB_PORT:-5432}"
DB_PASSWORD="${DB_PASSWORD:-}"
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
export PGPASSWORD="$DB_PASSWORD"

echo "Dropping schema pellier"
psql -X -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
  -v ON_ERROR_STOP=1 -q -c 'DROP SCHEMA IF EXISTS pellier CASCADE;'

bash "$REPO/scripts/setup/database-setup.sh"
echo "Database reset complete"
