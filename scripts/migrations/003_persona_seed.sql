-- Migration 003: Persona customers, orders, and memory seed.
--
-- Runs after:
--   001_schema.sql
--   scripts/seed_boutique_catalog.py
--   002_workshop_telemetry.sql
--
-- Why this is required:
--   * Marco / Anna / Theo / Fresh need customer rows for memory and
--     Atelier overlays.
--   * Theo's process_return tool checks ownership in orders before it
--     writes to returns.
--   * The memory surfaces read public.customer_episodic_seed directly.
--
-- Idempotent: customer rows upsert, order and seed rows are refreshed
-- for the canonical persona ids.

\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS customer_episodic_seed (
    id             BIGSERIAL PRIMARY KEY,
    customer_id    TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    summary_text   TEXT NOT NULL,
    ts_offset_days INTEGER NOT NULL CHECK (ts_offset_days <= 0),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS customer_episodic_seed_customer_idx
    ON customer_episodic_seed (customer_id, ts_offset_days DESC);

INSERT INTO customers (id, name, preferences_summary)
VALUES
    ('CUST-MARCO', 'Marco',
     'Brooklyn-based, partial to natural fibers. Linen, travel-ready pieces, warm neutrals.'),
    ('CUST-ANNA', 'Anna',
     'Gift-giver. Buys for others, with milestone occasions and explicit budgets.'),
    ('CUST-THEO', 'Theo',
     'Home + slow craft. Ceramics, linen throws, stoneware. Finishes what he buys, slowly.'),
    ('CUST-FRESH', 'A new visitor',
     'Cold-start shopper with no prior orders or memory.'),
    -- The live Theo prompt says customer id is "theo"; keep a thin alias
    -- so the write-path demo lands even if the model passes that literal.
    ('theo', 'Theo',
     'Alias for Theo write-path demo prompts that pass customer id as theo.')
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    preferences_summary = EXCLUDED.preferences_summary;

DELETE FROM orders
 WHERE customer_id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO', 'CUST-FRESH', 'theo');

WITH order_seed(customer_id, product_name, days_ago) AS (
    VALUES
        -- Marco: linen / travel wardrobe history.
        ('CUST-MARCO', 'Hadley Linen Shirt', 56),
        ('CUST-MARCO', 'Italian Linen Camp Shirt', 48),
        ('CUST-MARCO', 'Linen Drawstring Trousers', 40),
        ('CUST-MARCO', 'Linen Overshirt', 32),
        ('CUST-MARCO', 'Cotton-Linen Crew Tee', 24),
        ('CUST-MARCO', 'Leather Weekend Holdall', 16),
        ('CUST-MARCO', 'Merino Travel Socks', 8),

        -- Anna: gift-shaped history across price bands.
        ('CUST-ANNA', 'Solstice Woven Mat Set', 40),
        ('CUST-ANNA', 'Santal & Fig Candle', 32),
        ('CUST-ANNA', 'Ceramic Bud Vase', 24),
        ('CUST-ANNA', 'Handmade Soap Set', 16),
        ('CUST-ANNA', 'Gift Wrapping Kit', 8),

        -- Theo: slow-craft home history. Wabi-Sabi Bowl is required
        -- for the chipped-return demo.
        ('CUST-THEO', 'Wabi-Sabi Bowl', 8),
        ('CUST-THEO', 'Stoneware Pour-Over Set', 21),
        ('CUST-THEO', 'Ceramic Tumblers', 45),
        ('CUST-THEO', 'Brass Incense Holder', 90),
        ('theo', 'Wabi-Sabi Bowl', 8),
        ('theo', 'Stoneware Pour-Over Set', 21),
        ('theo', 'Ceramic Tumblers', 45),
        ('theo', 'Brass Incense Holder', 90)
)
INSERT INTO orders (customer_id, product_id, quantity, placed_at)
SELECT
    os.customer_id,
    pc."productId",
    1,
    now() - make_interval(days => os.days_ago)
FROM order_seed os
JOIN pellier.product_catalog pc
  ON pc.name = os.product_name;

DELETE FROM customer_episodic_seed
 WHERE customer_id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO', 'CUST-FRESH');

INSERT INTO customer_episodic_seed (customer_id, summary_text, ts_offset_days)
VALUES
    ('CUST-MARCO', 'Prefers natural fibers, oat tones, and warm neutrals.', -60),
    ('CUST-MARCO', 'Browsed linen shirts for a warm-weather trip; saved travel-ready pieces.', -21),
    ('CUST-MARCO', 'Asked about wrinkle-resistance and pieces that pack flat.', -9),

    ('CUST-ANNA', 'Past orders skew gift-shaped across varied price bands.', -50),
    ('CUST-ANNA', 'Recent searches mention milestone occasions and ready-to-give packaging.', -20),
    ('CUST-ANNA', 'Responds well to pairings under a clear budget.', -9),

    ('CUST-THEO', 'Prefers ceramics, linen throws, stoneware, and slow craft objects.', -45),
    ('CUST-THEO', 'Bought Wabi-Sabi Bowl and Stoneware Pour-Over Set for home rituals.', -14),
    ('CUST-THEO', 'Values repair, patina, and durable system-of-record handling.', -6);

DO $$
DECLARE
    n_customers INTEGER;
    n_orders INTEGER;
    n_facts INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_customers
      FROM customers
     WHERE id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO', 'CUST-FRESH', 'theo');
    SELECT COUNT(*) INTO n_orders
      FROM orders
     WHERE customer_id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO', 'theo');
    SELECT COUNT(*) INTO n_facts
      FROM customer_episodic_seed
     WHERE customer_id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO');
    RAISE NOTICE 'Persona seed ready: % customers, % orders, % memory facts',
        n_customers, n_orders, n_facts;
END $$;

COMMIT;
