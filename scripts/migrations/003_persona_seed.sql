-- Migration 003: Persona customers, orders, and memory seed.
--
-- Runs after:
--   001_schema.sql
--   scripts/seed_pellier_catalog.py
--   002_workshop_telemetry.sql
--
-- Why this is required:
--   * Marco / Anna / Theo / Fresh need customer rows for memory and
--     Observatory overlays.
--   * Theo's initiate_return tool checks ownership in pellier.orders
--     before it writes to pellier.returns.
--   * The memory surfaces read pellier.customer_episodic_seed directly.
--
-- Schema placement: every operational table lives under `pellier.*`.
-- Older revisions of this migration created `customer_episodic_seed`
-- at `public`; the relocation block at the top moves existing rows in
-- place when an older deploy is upgraded, and `IF NOT EXISTS` keeps
-- a fresh deploy idempotent.
--
-- Idempotent: customer rows upsert, order and seed rows are refreshed
-- for the canonical persona ids.

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------
-- One-time relocation: move legacy public.customer_episodic_seed into
-- pellier. ALTER TABLE ... SET SCHEMA preserves the FK to customers.
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'customer_episodic_seed'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'pellier' AND table_name = 'customer_episodic_seed'
    ) THEN
        ALTER TABLE public.customer_episodic_seed SET SCHEMA pellier;
        RAISE NOTICE 'Moved public.customer_episodic_seed → pellier.customer_episodic_seed';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS pellier.customer_episodic_seed (
    id             BIGSERIAL PRIMARY KEY,
    customer_id    TEXT NOT NULL
                   REFERENCES pellier.customers(id) ON DELETE CASCADE,
    summary_text   TEXT NOT NULL,
    ts_offset_days INTEGER NOT NULL CHECK (ts_offset_days <= 0),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS customer_episodic_seed_customer_idx
    ON pellier.customer_episodic_seed (customer_id, ts_offset_days DESC);

INSERT INTO pellier.customers (id, name, preferences_summary)
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

DELETE FROM pellier.orders
 WHERE customer_id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO', 'CUST-FRESH', 'theo');

WITH order_seed(customer_id, product_id, days_ago) AS (
    VALUES
        -- Marco: linen / travel wardrobe history.
        ('CUST-MARCO', '2', 56),  -- Hadley Linen Shirt
        ('CUST-MARCO', '11', 48),  -- Italian Linen Camp Shirt
        ('CUST-MARCO', '14', 40),  -- Linen Drawstring Trousers
        ('CUST-MARCO', '16', 32),  -- Linen Overshirt
        ('CUST-MARCO', '18', 24),  -- Cotton-Linen Crew Tee
        ('CUST-MARCO', '17', 16),  -- Leather Weekend Holdall
        ('CUST-MARCO', '20', 8),  -- Merino Travel Socks

        -- Anna: gift-shaped history across price bands.
        ('CUST-ANNA', '7', 40),  -- Jute Placemats, Set of 4
        ('CUST-ANNA', '4', 32),  -- Santal & Fig Candle
        ('CUST-ANNA', '27', 24),  -- Ceramic Bud Vase
        ('CUST-ANNA', '26', 16),  -- Handmade Soap Set
        ('CUST-ANNA', '30', 8),  -- Gift Wrapping Kit

        -- Theo: slow-craft home history. Wabi-Sabi Bowl is required
        -- for the chipped-return demo.
        ('CUST-THEO', '37', 8),  -- Wabi-Sabi Bowl
        ('CUST-THEO', '31', 21),  -- Stoneware Pour-Over Set
        ('CUST-THEO', '36', 45),  -- Ceramic Tumblers
        ('CUST-THEO', '35', 90),  -- Brass Incense Holder
        ('theo', '37', 8),  -- Wabi-Sabi Bowl
        ('theo', '31', 21),  -- Stoneware Pour-Over Set
        ('theo', '36', 45),  -- Ceramic Tumblers
        ('theo', '35', 90)  -- Brass Incense Holder
)
INSERT INTO pellier.orders (customer_id, product_id, quantity, placed_at)
SELECT
    os.customer_id,
    pc."productId",
    1,
    now() - make_interval(days => os.days_ago)
FROM order_seed os
JOIN pellier.product_catalog pc
  ON pc."productId" = os.product_id;

DELETE FROM pellier.customer_episodic_seed
 WHERE customer_id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO', 'CUST-FRESH');

INSERT INTO pellier.customer_episodic_seed (customer_id, summary_text, ts_offset_days)
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
    n_theo_orders INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_customers
      FROM pellier.customers
     WHERE id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO', 'CUST-FRESH', 'theo');
    SELECT COUNT(*) INTO n_orders
      FROM pellier.orders
     WHERE customer_id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO', 'theo');
    SELECT COUNT(*) INTO n_facts
      FROM pellier.customer_episodic_seed
     WHERE customer_id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO');

    -- Theo's initiate_return demo specifically requires the Wabi-Sabi Bowl
    -- order to exist for both 'CUST-THEO' and the 'theo' alias. If
    -- pellier.product_catalog is empty (e.g. the seeder failed silently
    -- earlier in bootstrap), the JOIN above produces zero rows and the
    -- demo dies at runtime with "product not found in your orders" —
    -- with no obvious connection to the bootstrap step. Fail loud here.
    SELECT COUNT(*) INTO n_theo_orders
      FROM pellier.orders o
      JOIN pellier.product_catalog pc ON pc."productId" = o.product_id
     WHERE o.customer_id IN ('CUST-THEO', 'theo')
       AND pc."productId" = '37';

    IF n_orders < 15 THEN
        RAISE EXCEPTION
            'Persona seed produced only % orders (expected >= 15). '
            'Most likely cause: pellier.product_catalog is empty or '
            'product IDs do not match the order_seed VALUES list. '
            'Check that scripts/seed_pellier_catalog.py succeeded before '
            'this migration ran.', n_orders;
    END IF;

    IF n_theo_orders < 2 THEN
        RAISE EXCEPTION
            'Theo Wabi-Sabi Bowl order missing (got % rows for CUST-THEO + theo). '
            'initiate_return demo will fail with "product not found in your orders". '
            'Verify pellier.product_catalog contains a row named "Wabi-Sabi Bowl".',
            n_theo_orders;
    END IF;

    RAISE NOTICE 'Persona seed ready: % customers, % orders, % memory facts',
        n_customers, n_orders, n_facts;
END $$;

COMMIT;
