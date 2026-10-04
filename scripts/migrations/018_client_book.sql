-- Migration 018: Membership ladder and the operator client book.
--
-- Runs after:
--   002_workshop_telemetry.sql   (pellier.customers, pellier.orders)
--   scripts/seed_pellier_catalog.py  (product_catalog IDs 1-60)
--   003_persona_seed.sql         (the three hero personas)
--
-- Why this is required:
--   * Pellier Operator needs a book of clients to be worth opening. Before
--     this migration the only customers were the three hero personas plus
--     CUST-FRESH and the 'theo' alias.
--   * Membership is not decoration. It is an authorization input: a goodwill
--     credit that is automatic for a Maison client and needs operator
--     approval for a Registered one is a policy decision that has to read an
--     authoritative column, not a number the browser sent.
--   * Client order history has to reference real product_catalog rows. The
--     pellier.orders FK enforces that, and an order that cannot be joined is
--     not evidence.
--
-- Naming: the column is `membership`, deliberately NOT `tier`.
--   * product_catalog.tier already means editorial rank 1/2/3.
--   * services/agentcore_gateway.py already defines TIER_READ and
--     TIER_OPERATOR_MUTATION for tool capability.
-- A third meaning of that word in one schema would be a landmine.
--
-- Membership is a stored label (registered, circle, maison; shown as Member,
-- Silver, Gold). It has no spend thresholds. Spend is never stored: readers
-- compute it from pellier.orders.amount_paid_cents.
--
-- The book is the four story customers (Marco, Anna, Theo, Jessica) plus the
-- anonymous CUST-FRESH profile and the 'theo' alias row.
--
-- Idempotent: columns are added IF NOT EXISTS, customer rows upsert, and
-- order rows are refreshed for exactly the client IDs this migration owns.

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------
-- Membership columns.
-- ---------------------------------------------------------------------
ALTER TABLE pellier.customers
    ADD COLUMN IF NOT EXISTS membership TEXT NOT NULL DEFAULT 'registered';

ALTER TABLE pellier.customers DROP COLUMN IF EXISTS spend_12mo;

-- A bad rung must fail at write time, not surface later as a policy
-- decision made on a value nothing recognises.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'customers_membership_check'
    ) THEN
        ALTER TABLE pellier.customers
            ADD CONSTRAINT customers_membership_check
            CHECK (membership IN ('registered', 'circle', 'maison'));
    END IF;
END $$;

COMMENT ON COLUMN pellier.customers.membership IS
    'Loyalty rung: registered | circle | maison. Authorization input, not display sugar.';

CREATE INDEX IF NOT EXISTS customers_membership_idx
    ON pellier.customers (membership);

-- ---------------------------------------------------------------------
-- Hero personas gain a rung. They deliberately span all three, so the
-- storefront on its own demonstrates the whole ladder.
-- ---------------------------------------------------------------------
UPDATE pellier.customers SET membership = 'maison'     WHERE id = 'CUST-MARCO';
UPDATE pellier.customers SET membership = 'circle'     WHERE id = 'CUST-ANNA';
UPDATE pellier.customers SET membership = 'registered' WHERE id = 'CUST-THEO';
UPDATE pellier.customers SET membership = 'registered' WHERE id = 'theo';
UPDATE pellier.customers SET membership = 'registered' WHERE id = 'CUST-FRESH';

-- ---------------------------------------------------------------------
-- The client book. Operator-side clients: they have no storefront login
-- and are not switchable personas.
-- ---------------------------------------------------------------------
INSERT INTO pellier.customers (id, name, preferences_summary, membership)
VALUES
    ('CUST-JESSICA', 'Jessica Nakamura',
     'Home and bath, warm coral and sage. Sent back the robe and the reed diffuser; no store credit recorded yet.',
     'circle')
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    preferences_summary = EXCLUDED.preferences_summary,
    membership = EXCLUDED.membership;

-- ---------------------------------------------------------------------
-- Client order history. Joined on product name, exactly as 003 does, so a
-- renamed or missing SKU produces zero rows and the block below fails loud
-- rather than leaving an operator console full of empty records.
-- ---------------------------------------------------------------------
DELETE FROM pellier.orders WHERE customer_id = 'CUST-JESSICA';

WITH order_seed(customer_id, product_id, days_ago, amount_paid_cents) AS (
    VALUES
        -- Jessica: the store-credit case. The robe and the reed diffuser are
        -- the two items that went back, ordered on the same day. Together they
        -- total exactly 10000 cents, so Lab 4's inclusive $100 limit decides
        -- her real credit.
        ('CUST-JESSICA', '42', 34, 6400),  -- Waffle Bath Robe, Sage
        ('CUST-JESSICA', '25', 34, 3600),  -- Reed Diffuser
        ('CUST-JESSICA', '31', 120, 5800),  -- Stoneware Pour-Over Set
        ('CUST-JESSICA', '43', 210, 12900),  -- Quilted Silk Vest
        ('CUST-JESSICA', '50', 300, 10800)  -- Oat Merino Crew
)
INSERT INTO pellier.orders (customer_id, product_id, quantity, placed_at, amount_paid_cents)
SELECT
    os.customer_id,
    pc."productId",
    1,
    now() - make_interval(days => os.days_ago),
    os.amount_paid_cents
FROM order_seed os
JOIN pellier.product_catalog pc
  ON pc."productId" = os.product_id;

-- ---------------------------------------------------------------------
-- Verification. Fail loud, in the same spirit as 003.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    n_clients INTEGER;
    n_jessica INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_clients
      FROM pellier.customers
     WHERE id LIKE 'CUST-%' AND id <> 'CUST-FRESH';

    -- The operator walkthrough asks about exactly these two items. If the
    -- catalog seeder did not load the house bucket, the JOIN above silently
    -- drops them and the desk shows a case over nothing.
    SELECT COUNT(*) INTO n_jessica
      FROM pellier.orders o
      JOIN pellier.product_catalog pc ON pc."productId" = o.product_id
     WHERE o.customer_id = 'CUST-JESSICA'
       AND pc."productId" IN ('42', '25');

    IF n_clients <> 4 THEN
        RAISE EXCEPTION
            'Client book has % customers (expected exactly 4: Marco, Anna, '
            'Theo, Jessica). Check that 003_persona_seed.sql ran before this '
            'migration.', n_clients;
    END IF;

    IF n_jessica < 2 THEN
        RAISE EXCEPTION
            'Jessica store-credit orders missing (got % of 2). The operator '
            'walkthrough needs both "Waffle Bath Robe, Sage" and '
            '"Reed Diffuser" in pellier.product_catalog.', n_jessica;
    END IF;

    RAISE NOTICE 'Client book ready: % customers', n_clients;
END $$;

COMMIT;
