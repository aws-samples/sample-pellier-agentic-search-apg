#!/usr/bin/env python3
"""
Seed workshop tables — customers, orders, customer_episodic_seed, tools, return_policies.

Uses the boutique catalog's integer productIds. Idempotent — safe to re-run.
Reads DB credentials from Secrets Manager or environment variables.
"""
import json
import logging
import os
import sys

import boto3
import psycopg

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def get_conn_string() -> str:
    """Build a psycopg connection string from env or Secrets Manager."""
    # Try direct env first
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    # Try Secrets Manager
    secret_arn = os.getenv("DB_SECRET_ARN")
    region = os.getenv("AWS_REGION", "us-west-2")
    host = os.getenv("DB_HOST", "")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "postgres")

    if secret_arn:
        client = boto3.client("secretsmanager", region_name=region)
        resp = client.get_secret_value(SecretId=secret_arn)
        creds = json.loads(resp["SecretString"])
        host = host or creds.get("host", "")
        return f"host={host} port={port} dbname={dbname} user={creds['username']} password={creds['password']}"

    # Fallback: try RDS managed secret pattern
    if host:
        # Assume env has DB_USER / DB_PASSWORD
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        return f"host={host} port={port} dbname={dbname} user={user} password={password}"

    # Last resort: localhost
    return f"host=localhost port=5432 dbname=postgres user=postgres"



DDL = """
-- customers table
CREATE TABLE IF NOT EXISTS customers (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    preferences_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- orders table
CREATE TABLE IF NOT EXISTS orders (
    id          BIGSERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1,
    placed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (customer_id, product_id, placed_at)
);
CREATE INDEX IF NOT EXISTS orders_customer_idx ON orders (customer_id, placed_at DESC);

-- episodic seed table
CREATE TABLE IF NOT EXISTS customer_episodic_seed (
    id              BIGSERIAL PRIMARY KEY,
    customer_id     TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    summary_text    TEXT NOT NULL,
    ts_offset_days  INTEGER NOT NULL CHECK (ts_offset_days <= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS customer_episodic_seed_customer_idx
    ON customer_episodic_seed (customer_id, ts_offset_days DESC);

-- tools table for tool registry discovery
CREATE TABLE IF NOT EXISTS tools (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    description     TEXT NOT NULL,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
    owner           TEXT NOT NULL DEFAULT 'orchestrator',
    description_emb vector(1024)
);
CREATE INDEX IF NOT EXISTS tools_emb_hnsw_idx
    ON tools USING hnsw (description_emb vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- return policies table
CREATE TABLE IF NOT EXISTS pellier.return_policies (
    category_name VARCHAR(50) PRIMARY KEY,
    return_window_days INTEGER NOT NULL,
    conditions TEXT,
    refund_method TEXT
);
"""

CUSTOMERS = [
    ("CUST-MARCO", "Marco",          "Linen and summer staples. Travel-friendly. Warm neutrals."),
    ("CUST-ANNA",  "Anna",           "Buys for others. Gift-giver. Milestone occasions."),
    ("CUST-FRESH", "A new visitor",  ""),
]

# Orders use real integer productIds from the boutique catalog.
ORDERS = [
    # Marco — linen / summer / travel (7 orders)
    ("CUST-MARCO", 1, 1, "56 days"),   # Italian Linen Camp Shirt
    ("CUST-MARCO", 4, 1, "48 days"),   # Relaxed Oxford Shirt
    ("CUST-MARCO", 9, 1, "40 days"),   # Linen Utility Jacket
    ("CUST-MARCO", 6, 1, "32 days"),   # Leather Slide Sandal
    ("CUST-MARCO", 3, 1, "24 days"),   # Signature Straw Tote
    ("CUST-MARCO", 8, 1, "16 days"),   # Ceramic Tumbler Set
    ("CUST-MARCO", 7, 1, "8 days"),    # Cashmere-Blend Cardigan

    # Anna — gift-giver (5 orders, varied recipients + price bands)
    ("CUST-ANNA", 5, 1, "40 days"),    # Sundress in Washed Linen (birthday gift)
    ("CUST-ANNA", 7, 1, "32 days"),    # Cashmere-Blend Cardigan (anniversary)
    ("CUST-ANNA", 3, 1, "24 days"),    # Signature Straw Tote (housewarming)
    ("CUST-ANNA", 8, 1, "16 days"),    # Ceramic Tumbler Set (housewarming)
    ("CUST-ANNA", 6, 1, "8 days"),     # Leather Slide Sandal (birthday)

    # Fresh visitor — no orders
]

EPISODES = [
    # Marco — linen / summer / travel
    ("CUST-MARCO", "Prefers natural fibers, oat tones", -60),
    ("CUST-MARCO", "Bought Maren tunic oat last August", -45),
    ("CUST-MARCO", "Sizes consistently in M", -40),
    ("CUST-MARCO", "Browsed mens linen shirts for a Lisbon trip; added one to bag.", -14),
    ("CUST-MARCO", "Asked about wrinkle-resistance in travel fabrics.", -9),
    ("CUST-MARCO", "Compared two camp shirts; saved a sage-green one.", -3),

    # Anna — gift-giver
    ("CUST-ANNA", "Past orders skew gift-shaped — multiple recipients, varied price bands", -50),
    ("CUST-ANNA", "Recent searches mention 'for my mother'", -20),
    ("CUST-ANNA", "Price bands range $140 to $310, milestone-leaning", -15),
    ("CUST-ANNA", "Bought a sundress as a birthday gift last month", -30),
    ("CUST-ANNA", "Asked about gift wrapping and delivery timing for an anniversary", -9),

    # Fresh visitor — no episodes
]

RETURN_POLICIES = [
    ("Linen",       30, "Unworn, tags attached, original packaging", "Original payment method within 5-7 business days"),
    ("Dresses",     30, "Unworn, tags attached, original packaging", "Original payment method within 5-7 business days"),
    ("Outerwear",   30, "Unworn, tags attached, original packaging", "Original payment method within 5-7 business days"),
    ("Footwear",    30, "Unworn, in original box with tags", "Original payment method within 5-7 business days"),
    ("Accessories", 14, "Unused, original packaging", "Store credit or exchange"),
    ("Bags",        30, "Unused, original packaging, no marks", "Original payment method within 5-7 business days"),
    ("Home",        14, "Unopened, original packaging", "Store credit or exchange"),
    ("Tops",        30, "Unworn, tags attached", "Original payment method within 5-7 business days"),
    ("Bottoms",     30, "Unworn, tags attached", "Original payment method within 5-7 business days"),
]

TOOLS = [
    ("search_products",   "Search the product catalog using semantic similarity. Finds products matching natural language descriptions, styles, occasions, or moods.", False, "search_agent"),
    ("trending_products", "Get trending and popular products. Returns best-sellers ranked by recent purchase velocity and review momentum.", False, "recommendation_agent"),
    ("compare_products",  "Compare two or more products side by side on price, rating, category, and description.", False, "search_agent"),
    ("price_analysis",    "Analyze pricing across categories. Returns min, max, average, and percentile breakdowns.", False, "pricing_agent"),
    ("inventory_health",  "Check inventory levels and stock health. Flags low-stock and out-of-stock items.", False, "inventory_agent"),
    ("restock_product",   "Restock a product by adding units to inventory. Requires approval for quantities over 50.", True, "inventory_agent"),
    ("return_policy",     "Look up the return policy for a product category. Returns window, conditions, and refund method.", False, "support_agent"),
    ("low_stock",         "List products with critically low inventory that may need restocking.", False, "inventory_agent"),
    ("browse_category",   "Browse products filtered by category name. Returns all items in the specified category.", False, "search_agent"),
]


def run(conn_string: str) -> None:
    log.info("Connecting to database...")
    with psycopg.connect(conn_string) as conn:
        with conn.cursor() as cur:
            # 1. DDL — create tables
            log.info("Creating tables (customers, orders, customer_episodic_seed, tools, return_policies)...")
            cur.execute(DDL)
            conn.commit()

            # 2. Customers — upsert
            log.info("Seeding %d customers...", len(CUSTOMERS))
            for cid, name, prefs in CUSTOMERS:
                cur.execute(
                    """INSERT INTO customers (id, name, preferences_summary)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (id) DO UPDATE
                         SET name = EXCLUDED.name,
                             preferences_summary = EXCLUDED.preferences_summary""",
                    (cid, name, prefs),
                )
            conn.commit()

            # 3. Orders — clear and reinsert (idempotent)
            log.info("Seeding %d orders...", len(ORDERS))
            cust_ids = tuple(set(o[0] for o in ORDERS))
            cur.execute(
                "DELETE FROM orders WHERE customer_id = ANY(%s)",
                (list(cust_ids),),
            )
            inserted = 0
            for cid, pid, qty, offset in ORDERS:
                cur.execute(
                    f"""INSERT INTO orders (customer_id, product_id, quantity, placed_at)
                        VALUES (%s, %s, %s, now() - interval '{offset}')
                        ON CONFLICT DO NOTHING""",
                    (cid, pid, qty),
                )
                inserted += cur.rowcount
            log.info("  -> %d order rows inserted", inserted)
            conn.commit()

            # 4. Episodic seed — clear and reinsert
            log.info("Seeding %d episodic memory rows...", len(EPISODES))
            cur.execute(
                "DELETE FROM customer_episodic_seed WHERE customer_id = ANY(%s)",
                (list(cust_ids),),
            )
            for cid, text, offset in EPISODES:
                cur.execute(
                    """INSERT INTO customer_episodic_seed (customer_id, summary_text, ts_offset_days)
                       VALUES (%s, %s, %s)""",
                    (cid, text, offset),
                )
            conn.commit()

            # 5. Return policies — upsert
            log.info("Seeding %d return policies...", len(RETURN_POLICIES))
            for cat, days, cond, refund in RETURN_POLICIES:
                cur.execute(
                    """INSERT INTO pellier.return_policies (category_name, return_window_days, conditions, refund_method)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (category_name) DO UPDATE
                         SET return_window_days = EXCLUDED.return_window_days,
                             conditions = EXCLUDED.conditions,
                             refund_method = EXCLUDED.refund_method""",
                    (cat, days, cond, refund),
                )
            conn.commit()

            # 6. Tools — upsert (without embeddings; those get added by seed_tool_registry.py)
            log.info("Seeding %d tools...", len(TOOLS))
            for name, desc, approval, owner in TOOLS:
                cur.execute(
                    """INSERT INTO tools (name, description, requires_approval, owner)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (name) DO UPDATE
                         SET description = EXCLUDED.description,
                             requires_approval = EXCLUDED.requires_approval,
                             owner = EXCLUDED.owner""",
                    (name, desc, approval, owner),
                )
            conn.commit()

            # 7. Verify
            cur.execute("SELECT COUNT(*) FROM customers")
            log.info("  customers: %d", cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM orders")
            log.info("  orders: %d", cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM customer_episodic_seed")
            log.info("  episodic seeds: %d", cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM pellier.return_policies")
            log.info("  return policies: %d", cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM tools")
            log.info("  tools: %d", cur.fetchone()[0])

    log.info("Done.")


if __name__ == "__main__":
    conn_str = get_conn_string()
    run(conn_str)
