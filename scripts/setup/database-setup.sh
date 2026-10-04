#!/usr/bin/env bash
# Fresh Pellier database: schema, catalog from the committed cache, then every migration.
# Called by scripts/bootstrap-labs.sh and by the fresh-setup test harness
# (pellier/backend/tests/fresh_cluster.py), so the harness proves these exact commands.
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

# 1. Schema bootstrap (CREATE EXTENSION vector + schema + product_catalog table + HNSW
# index). pellier-database.yml provisions an empty Aurora cluster; this migration is what
# makes the cluster Pellier-ready. Runs first because the seeder INSERTs into
# pellier.product_catalog and assumes the vector(1024) column exists.
apply 001_schema.sql

# 2. Pellier catalog seeder: the 100 products in data/pellier_catalog.json.
# Authoritative source for pellier.product_catalog.
#
# Embeddings come from the COMMITTED cache (data/embeddings_cache.json) via --from-cache.
# The cache stores the real Cohere vectors. This keeps the slowest, most throttle-prone
# step off the bootstrap critical path and makes the seed a deterministic SQL load. To
# regenerate the cache after a catalog change, run
# `python scripts/seed_pellier_catalog.py --csv-only` on a machine with Bedrock access
# and commit the updated cache.
echo "Seeding catalog from cache"
(cd "$REPO" && "$PYTHON" scripts/seed_pellier_catalog.py --from-cache)

# 3. Required fresh-cluster migrations. These are intentionally idempotent and run after
# the catalog exists because several tables FK into pellier.product_catalog. Ordering
# matters: telemetry creates customers/orders, persona seed populates them, Theo returns
# references them, and warehouse inventory powers check_inventory.
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
  055_governance_boundary_observations.sql \
  056_align_required_lab_requests.sql
do
  apply "$migration"
done
echo "Database setup complete"
