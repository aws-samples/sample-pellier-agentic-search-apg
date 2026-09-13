# Pellier fresh-cluster migrations

Idempotent SQL migrations for the Pellier workshop app.
Numbered in apply order; running a migration twice is safe.

Every operational table lives under the `pellier` schema. Older
deploys that created `tool_audit` / `customers` / `orders` /
`approvals` / `customer_episodic_seed` / `returns` / `tools` /
`observatory_spans` at `public` are auto-relocated by the
`ALTER TABLE ... SET SCHEMA pellier` blocks at the top of migrations
002, 003, 005, and 006. The schema move preserves rows, indexes, and
FKs.

## Apply order

1. **`001_schema.sql`** — creates `vector`, the `pellier` schema,
   `pellier.product_catalog`, the `product_id` SQL alias for the public
   `productId` field, the HNSW index, and the `updated_at` trigger. Run
   before `scripts/seed_pellier_catalog.py`.
2. **`002_workshop_telemetry.sql`** — creates `pellier.{observatory_spans,
   tools, tool_audit, customers, orders, approvals}`. Run after the
   catalog seed because `pellier.orders.product_id` references
   `pellier.product_catalog`.
3. **`003_persona_seed.sql`** — seeds Marco / Anna / Theo / Fresh
   customers, persona order history, and
   `pellier.customer_episodic_seed`. Theo's return flow depends on
   the Wabi-Sabi Bowl order here.
4. **`004_anna_hybrid_search.sql`** — adds the generated `tsvector`
   column and GIN index for Anna's Postgres FTS branch.
5. **`005_theo_returns.sql`** — creates `pellier.returns` for Theo's
   write path.
6. **`006_warehouse_inventory.sql`** — creates `pellier.warehouses` and
   `pellier.warehouse_inventory` for Marco's `check_inventory` exercise.
7. **`007_chat_session_tables.sql`** — creates chat/session persistence
   tables in the `pellier` schema.
8. **`008_search_performance_indexes.sql`** — adds `pg_trgm` + GIN trigram
   indexes on `lower(name)` and `lower(category)` for fuzzy ILIKE paths.
9. **`009_return_policies.sql`** — creates and seeds
   `pellier.return_policies` for the `get_return_policy` tool.
10. **`010_governed_receipts.sql`** — creates
   `pellier.governed_receipts` and seeds the deterministic governed
   forensic incident used by the two-hour workshop.
11. **`011_governed_write_integrity.sql`** — creates the idempotency
   ledger and the transactional return/restock functions that keep
   warehouse and catalog quantities synchronized.
12. **`012_retrieval_receipts.sql`** — creates durable retrieval receipts
   that explain constraints, ranking stages, memory use, latency, and cost.
13. **`013_inventory_ledger.sql`** — adds return quantity integrity and an
   append-only stock ledger, then captures every warehouse quantity change
   at the database boundary.
14. **`014_governed_turn_receipts.sql`** — links identity, retrieval,
   citations, policy events, Aurora audit rows, and managed trace evidence in
   an append-only receipt for each governed turn.
15. **`015_proof_carrying_commerce.sql`** — adds server-authoritative quotes,
    explicit confirmation grants, idempotent commerce orders, inventory
    reservations, sandbox payment state, a transactional outbox, and immutable
    purchase receipts. The seeded `pellier.orders` persona history remains
    separate.
28. **`028_shopper_operator_handoff.sql`** — adds the bounded, explicitly
    untrusted shopper context captured with an immutable turn receipt when a
    proposed action reaches the operator checkpoint.
29. **`029_live_surface_data.sql`** — persists storefront persona profiles,
    guided shopper scenarios, and editorial catalog grouping in Aurora; it also
    upgrades catalog image URLs to the shipped WebP contract.
30. **`030_storefront_editorial_order.sql`** — stores each featured item and
    exact storefront edit order in Aurora.
31. **`031_refine_fresh_storefront_edit.sql`** — keeps the unsigned edit
    material-led by promoting the Washed Canvas Tote and aligns its guided
    Observatory request with that Aurora-owned edit.
32. **`032_restore_fresh_runner_edit.sql`** — restores Cloudform Studio Runner
    as the ninth promoted guest piece while keeping the full ten-product Fresh
    cohort searchable.
33. **`033_extend_curated_inventory.sql`** — converges existing clusters on
    three warehouse rows for all 60 curated products without rewriting prior
    inventory movements.
34. **`034_refine_persona_personalities.sql`** — replaces lifecycle-oriented
    persona labels with concise editorial taste and material descriptors.
35. **`035_expand_persona_discovery_grids.sql`** — promotes the tenth product
    in each named persona cohort so one feature is followed by nine distinct
    discovery cards.
36. **`036_refresh_persona_hero_alt_text.sql`** — aligns Aurora-owned hero
    descriptions with the approved Marco, Anna, and Theo full-bleed masters.
37. **`037_serve_persona_hero_masters.sql`** — serves the approved persona
    hero PNG masters directly while retaining derivatives for secondary use.
38. **`038_principal_customer_cardinality.sql`** — rejects an ambiguous
    principal-to-customer mapping before constraining each verified subject to
    one customer scope; multiple principals may still map to one customer.
39. **`039_return_replay_scope.sql`** — re-checks the caller's RLS-scoped
    order ownership before returning an idempotent replay.
40. **`040_resequence_theo_governed_turn.sql`** — makes Theo's damaged
    Wabi-Sabi Bowl return the required Lab 3 outcome while retaining the
    managed-memory continuity prompt as an optional follow-up.
41. **`041_align_theo_pairing_preview.sql`** — aligns Theo's pairing
    preview with the first novel companion from the verified pour-over
    similarity result, rather than a product already in his order history.
42. **`042_align_anna_guided_previews.sql`** — aligns Anna's retrieval preview
    with the live result and leaves the intentionally unbuilt inventory proof
    without a fabricated catalog result.
43. **`043_evidence_ledger.sql`** — adds append-only, metadata-only model
    invocation receipts and a typed read-only projection over the canonical
    receipt tables. Prompt, completion, tool argument, and tool result content
    are intentionally absent.
44. **`044_operator_lifecycle_ledger.sql`** — adds the durable Operator
    review and governed-execution lifecycle to that projection. The shopper
    turn remains terminal before the later human and execution events appear.
45. **`045_persona_blurbs.sql`** — refines the concise persona descriptions
    shown in the participant-facing storefront.
46. **`046_retrieval_citation_snapshots.sql`** — stores a hashed, ordered
    catalog citation snapshot with each retrieval receipt and makes retrieval
    receipts append-only, so a later catalog edit cannot rewrite prior turn
    evidence.
47. **`047_evidence_immutability.sql`** makes `governed_receipts` and
    `execution_receipts` append-only, allows `tool_audit` and `write_operations`
    rows to be completed exactly once, and narrows the runtime role's UPDATE
    grant on `write_operations` to the completion columns.
48. **`048_policy_decisions.sql`** creates `pellier.policy_decisions`, the
    per-turn record of Gateway Policy decision events (ALLOW, DENY, WOULD_DENY,
    EVALUATION_INCOMPLETE, POLICY_INFERRED) with the link from a later decision
    to the one it reverses.
49. **`049_workshop_runs.sql`** creates `pellier.workshop_runs` and stamps
    every evidence table with the current run id from the session setting
    `pellier.run_id`, so one participant run can be reconstructed end to end.
50. **`050_refine_guided_questions.sql`** refines the guided persona questions
    the storefront offers.
51. **`051_review_requester.sql`** binds each review to the verified subject
    whose turn opened it, or records that none was present, so an anonymous
    persona session can never read as the customer it named.
52. **`052_replacement_recovery.sql`** adds an approval-bound replacement
    transaction, durable result, outbox, and a separate fulfillment worker role.
    It does not seed a damage report or reserve any stock.
53. **`053_replacement_follow_up.sql`** records workflow follow-up separately
    from provider state and supports bounded observation of terminal executions.
54. **`054_query_statistics.sql`** creates the `pg_stat_statements` database
    extension required by facilitator readiness. Workshop Studio separately
    preloads the module through its cluster parameter group. This migration
    does not change that parameter group or restart the cluster.

The replacement path also needs its Gateway target, Cedar policy, and worker.
Follow `scripts/deploy/REPLACEMENT_RECOVERY.md` for that activation order.
The local workshop reset refuses when replacement records exist, because it
cannot quiesce their scheduled worker or Step Functions executions.

## Run

```sh
# From repo root, with .env loaded:
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
    -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -f scripts/migrations/001_schema.sql

python3 scripts/seed_pellier_catalog.py

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
    054_query_statistics.sql
do
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
        -U "$DB_USER" -d "$DB_NAME" \
        -v ON_ERROR_STOP=1 \
        -f "scripts/migrations/$migration"
done
```

Every file sets `ON_ERROR_STOP`, and bootstrap also passes
`-v ON_ERROR_STOP=1`, so failures stop the setup.

## Quick catalog read

Use the backend Python environment for small catalog checks instead of
hand-quoting the legacy public `productId` column:

```sh
python3 scripts/read_catalog_product.py --name-like beeswax
python3 scripts/read_catalog_product.py --product-id 37
```

The helper reads `pellier.product_catalog.product_id`, the generated
snake_case SQL alias created by `001_schema.sql`.

## `pg_cron` note

If `pg_cron` isn't installed, `002_workshop_telemetry.sql` emits a
`WARNING` and continues. The shipped runtime does not write the reserved
`pellier.observatory_spans` cache; CloudWatch/AgentCore telemetry remains the
managed span authority. If an experiment enables an Aurora span-cache writer,
install `pg_cron` or schedule equivalent retention:

```sql
CREATE EXTENSION pg_cron;  -- must run in postgres database as superuser
```

## Testing

The bootstrap and integrity gates apply these migrations. Verify the resulting
workshop state with:

```sql
\dt pellier.customers
\dt pellier.orders
\dt pellier.observatory_spans
\dt pellier.tools
\dt pellier.tool_audit
\dt pellier.approvals
\dt pellier.retrieval_receipts
\dt pellier.governed_turn_receipts
\dt pellier.model_invocation_receipts
\dv pellier.evidence_ledger_event_refs
\dt pellier.commerce_receipts
\dt pellier.commerce_payment_events
\dt pellier.policy_decisions
\dt pellier.workshop_runs

SELECT COUNT(*) FROM pellier.product_catalog;          -- 1000 by default
SELECT COUNT(*) FROM pellier.customers;                -- at least 5
SELECT COUNT(*) FROM pellier.orders;                   -- at least 20
SELECT COUNT(*) FROM pellier.customer_episodic_seed;   -- 9
SELECT COUNT(*) FROM pellier.warehouse_inventory;      -- 180
SELECT COUNT(*) FROM pellier.governed_receipts
 WHERE session_id = 'gateway-marco-for-theo-incident'; -- 1
SELECT COUNT(*) FROM pellier.reconcile_inventory();     -- 0
```
