#!/usr/bin/env bash
# Workshop reset, database part: restore catalog quantities, re-apply the reset migrations,
# TRUNCATE the runtime and evidence tables, then re-seed what the TRUNCATE empties.
# Called by scripts/reset-governed-workshop.sh after it has quiesced the application and
# proved nothing is executing, and by the fresh-setup test harness
# (pellier/backend/tests/fresh_cluster.py), so the harness proves these exact commands.
#
# Reads DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD PYTHON REPO. Exits non-zero on the
# first failure. TRUNCATE, never DELETE: DELETE fires the ledger and receipt-immutability
# triggers, writing new history while trying to clear history.
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

echo "Restoring catalog quantities from cache"
"$PYTHON" "$REPO/scripts/seed_pellier_catalog.py" --from-cache

for migration in \
  006_warehouse_inventory.sql \
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
  055_governance_boundary_observations.sql \
  056_align_required_lab_requests.sql
do
  apply "$migration"
done

# "The guard above" in the statement is reset-governed-workshop.sh's
# _assert_no_active_execution, which refuses to run while any replacement record exists.
echo "Clearing runtime and evidence tables"
psql -X -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q -c "
TRUNCATE TABLE
    -- The guard above requires these to be empty. Naming every child keeps
    -- TRUNCATE referentially complete without CASCADE or a cloud-workflow reset.
    pellier.replacement_callbacks,
    pellier.replacement_simulator_operations,
    pellier.replacement_events,
    pellier.replacement_outbox,
    pellier.replacements,
    pellier.commerce_payment_events,
    pellier.commerce_receipts,
    pellier.commerce_outbox,
    pellier.commerce_inventory_reservations,
    pellier.commerce_payment_attempts,
    pellier.commerce_order_lines,
    pellier.commerce_orders,
    pellier.commerce_confirmation_grants,
    pellier.commerce_quote_lines,
    pellier.commerce_quotes,
    pellier.governed_receipts,
    pellier.governed_turn_receipts,
    pellier.governed_query_receipts,
    pellier.model_invocation_receipts,
    pellier.tool_audit,
    pellier.retrieval_receipts,
    pellier.inventory_ledger,
    pellier.write_operations,
    pellier.returns,
    pellier.store_credits,
    pellier.support_tickets,
    pellier.semantic_cache,
    -- Evidence and memory tables added after this script was first written. Each was
    -- absent from the list, so a reset cluster kept rows a fresh one has never had:
    --   execution_receipts  policy verdicts from engineering runs (migration 025)
    --   operator_episodes   derived memories of those runs (024/026)
    --   conversations       shopper AND Operator Concierge threads (007). Nothing
    --   messages            seeds these, so the fresh baseline is zero and every row
    --                       here is runtime state.
    --   observatory_spans   OTEL spans (002)
    --   session_metadata    per-session scratch (007)
    --   tool_uses           per-turn tool records (007)
    pellier.execution_receipts,
    pellier.operator_episodes,
    pellier.messages,
    pellier.conversations,
    pellier.observatory_spans,
    pellier.session_metadata,
    -- Persona profiles and workshop scenarios are provisioned source data.
    -- Shopper sessions are runtime state and must not survive a reset.
    pellier.shopper_sessions,
    pellier.tool_uses,
    -- Per-run evidence added by 048 and 049. Gateway Policy decision events are
    -- ingested per turn and a workshop run is minted per participant, so a fresh
    -- box has neither. (No semicolon in this comment: the contract test reads
    -- the statement up to the first one.)
    pellier.policy_decisions,
    pellier.governance_boundary_observations,
    pellier.workshop_runs,
    -- LAST in the list, because execution_receipts and operator_episodes reference it.
    -- One TRUNCATE covers them together, so no CASCADE is needed and nothing is
    -- orphaned. TRUNCATE also fires no row-level triggers: a DELETE here would run
    -- record_inventory_movement and reject_governed_turn_receipt_mutation, writing
    -- new ledger history while trying to clear history.
    pellier.approvals
RESTART IDENTITY;
"

apply 013_inventory_ledger.sql

# 019 is re-applied after the TRUNCATE above for the same reason 013 and 015
# are: the truncate empties the operator desk, and the seeded tickets plus
# Sarah's credit on file are the starting state the client book describes. The
# semantic cache is deliberately left empty, so the first paraphrase of the
# run is a real miss and the second is a real hit.
apply 019_operator_desk.sql

apply 015_proof_carrying_commerce.sql

apply 010_governed_receipts.sql

echo "Ensuring HNSW index product_catalog_embedding_hnsw"
psql -X -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q -c '
CREATE INDEX IF NOT EXISTS product_catalog_embedding_hnsw
    ON pellier.product_catalog
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
ANALYZE pellier.product_catalog;
'
echo "Database reset complete"
