# Pellier database

Two SQL files build the whole `pellier` schema on an empty database.

1. **`001_schema.sql`** creates the `vector` and `pg_trgm` extensions, the
   `pellier` schema and its ten tables: `product_catalog`,
   `warehouse_inventory`, `customers`, `orders`, `return_policies`,
   `support_tickets`, `approvals`, `store_credits`, `tool_audit` and
   `retrieval_receipts`. It also creates their indexes, the
   `apply_store_credit` function that is the only way a credit is written,
   the fill-once trigger on `tool_audit`, the append-only trigger on
   `retrieval_receipts`, the `pellier_agent` role and the row-level security
   policies on `orders` and `support_tickets`. The comments are written for a
   participant reading the file.
2. **`scripts/seed_pellier_catalog.py --from-cache`** loads the 100 products in
   `data/pellier_catalog.json` with their committed Cohere Embed v4 vectors
   (`data/embeddings_cache.json`), so setup never calls Bedrock.
3. **`002_seed.sql`** loads everything that reads the catalog: the storefront
   edit order, 300 warehouse rows, the four customers (Anna, Marco, Theo and
   Jessica) and their orders, the return policies and three support tickets.
   It seeds no approval and no store credit, and it stops with an error if the
   catalog is not the 100 products it expects.

`scripts/setup/database-setup.sh` runs those three steps in that order.
`scripts/setup/database-reset.sh` drops the `pellier` schema and runs the same
setup again, so a reset database and a fresh one cannot differ. Neither file is
written to be applied twice: an existing database is rebuilt, never converged.

The persona profiles and guided prompts the storefront shows are files, not
tables: `data/personas.json` and `data/scenarios.json`.
