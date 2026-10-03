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
-- Membership is derived from trailing 12-month spend and then stored, so the
-- value a policy decision reads is stable and auditable rather than
-- recomputed per request. The verification block at the bottom asserts the
-- stored rung still agrees with its own thresholds, so the two can never
-- drift apart silently:
--   registered  under 1500
--   circle      1500 to 7500
--   maison      above 7500
--
-- The 15 named clients are balanced five to a rung, and the block at the bottom
-- asserts that too. An unbalanced book makes the operator console misleading: a
-- console showing nine Maison clients suggests membership barely discriminates,
-- which is the opposite of the point when it is an authorization input.
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

ALTER TABLE pellier.customers
    ADD COLUMN IF NOT EXISTS spend_12mo NUMERIC(10, 2) NOT NULL DEFAULT 0.00;

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
COMMENT ON COLUMN pellier.customers.spend_12mo IS
    'Trailing 12-month spend that the stored membership rung was derived from.';

CREATE INDEX IF NOT EXISTS customers_membership_idx
    ON pellier.customers (membership);

-- ---------------------------------------------------------------------
-- Hero personas gain a rung. They deliberately span all three, so the
-- storefront on its own demonstrates the whole ladder.
-- ---------------------------------------------------------------------
UPDATE pellier.customers SET membership = 'maison',     spend_12mo = 9240.00 WHERE id = 'CUST-MARCO';
UPDATE pellier.customers SET membership = 'circle',     spend_12mo = 3180.00 WHERE id = 'CUST-ANNA';
UPDATE pellier.customers SET membership = 'registered', spend_12mo =  940.00 WHERE id = 'CUST-THEO';
UPDATE pellier.customers SET membership = 'registered', spend_12mo =  940.00 WHERE id = 'theo';
UPDATE pellier.customers SET membership = 'registered', spend_12mo =    0.00 WHERE id = 'CUST-FRESH';

-- ---------------------------------------------------------------------
-- The client book. Operator-side clients: they have no storefront login
-- and are not switchable personas.
-- ---------------------------------------------------------------------
INSERT INTO pellier.customers (id, name, preferences_summary, membership, spend_12mo)
VALUES
    ('CUST-JESSICA', 'Jessica Nakamura',
     'Home and bath, warm coral and sage. Open return dispute on a catchall and a robe.',
     'circle', 3940.00),
    ('CUST-SARAH', 'Sarah Chen',
     'Relocating. Buys for a whole room at a time. Store credit on file.',
     'maison', 11600.00),
    ('CUST-CATHERINE', 'Catherine Dubois',
     'Building a tailored wardrobe across seasons. Prefers private appointments.',
     'maison', 14300.00),
    ('CUST-AMARA', 'Amara Okonkwo',
     'Highest spend in the book. Investment pieces, gold, hand-made objects.',
     'maison', 18900.00),
    ('CUST-JULIAN', 'Julian Hart',
     'Tailoring client. Every jacket and trouser goes to alterations.',
     'maison', 7980.00),
    ('CUST-DAVID', 'David Kim',
     'Buys the sustainable edit. Asks about materials and provenance first.',
     'circle', 5240.00),
    ('CUST-PRIYA', 'Priya Shah',
     'Gifts at volume for family and colleagues. Wants it wrapped and dated.',
     'circle', 4610.00),
    -- 80 short of the circle threshold, which is what "close to the next rung"
    -- is meant to describe. She was previously circle at 2050, where the same
    -- sentence pointed at maison, 5450 away.
    ('CUST-ELENA', 'Elena Rodriguez',
     'Close to the next rung. Responds to early access.',
     'registered', 1420.00),
    ('CUST-THOMAS', 'Thomas Anderson',
     'Press and editorial. Borrows and buys objects that photograph well.',
     'circle', 1890.00),
    ('CUST-MICHAEL', 'Michael Washington',
     'Repeat basics in the same size and colour. Low effort, reliable.',
     'registered', 1320.00),
    ('CUST-RACHEL', 'Rachel Green',
     'Fragrance and apothecary. One open ticket about a decanted bottle.',
     'registered', 1140.00),
    ('CUST-KEVIN', 'Kevin Patel',
     'New joiner. Two small orders, no preferences established yet.',
     'registered', 410.00)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    preferences_summary = EXCLUDED.preferences_summary,
    membership = EXCLUDED.membership,
    spend_12mo = EXCLUDED.spend_12mo;

-- ---------------------------------------------------------------------
-- Client order history. Joined on product name, exactly as 003 does, so a
-- renamed or missing SKU produces zero rows and the block below fails loud
-- rather than leaving an operator console full of empty records.
-- ---------------------------------------------------------------------
DELETE FROM pellier.orders
 WHERE customer_id IN (
    'CUST-JESSICA', 'CUST-SARAH', 'CUST-CATHERINE', 'CUST-AMARA', 'CUST-JULIAN',
    'CUST-DAVID', 'CUST-PRIYA', 'CUST-ELENA', 'CUST-THOMAS', 'CUST-MICHAEL',
    'CUST-RACHEL', 'CUST-KEVIN'
 );

WITH order_seed(customer_id, product_name, days_ago) AS (
    VALUES
        -- Jessica: the return dispute. The catchall and the robe are the two
        -- items the operator queue asks about, ordered on the same day.
        ('CUST-JESSICA', 'Coral Lacquer Catchall', 34),
        ('CUST-JESSICA', 'Waffle Bath Robe, Sage', 34),
        ('CUST-JESSICA', 'Stoneware Pour-Over Set', 120),
        ('CUST-JESSICA', 'Quilted Silk Vest', 210),
        ('CUST-JESSICA', 'Oat Merino Crew', 300),

        -- Sarah: buys a room at a time.
        ('CUST-SARAH', 'Wool Rug', 45),
        ('CUST-SARAH', 'Stonewashed Linen Set', 60),
        ('CUST-SARAH', 'Ivory Cashmere Throw', 150),
        ('CUST-SARAH', 'Blown Glass Decanter', 200),

        -- Catherine: tailored wardrobe across seasons.
        ('CUST-CATHERINE', 'Camel Wool Overcoat', 30),
        ('CUST-CATHERINE', 'Tailored Wool Blazer', 75),
        ('CUST-CATHERINE', 'Double-Pleat Wool Trouser', 75),
        ('CUST-CATHERINE', 'Silk Slip Dress', 140),
        ('CUST-CATHERINE', 'Suede Chelsea Boot', 190),

        -- Amara: investment pieces.
        ('CUST-AMARA', 'Wool Rug', 20),
        ('CUST-AMARA', 'Signet Ring, Brushed Gold', 55),
        ('CUST-AMARA', 'Camel Wool Overcoat', 110),
        ('CUST-AMARA', 'Ivory Cashmere Throw', 160),
        ('CUST-AMARA', 'Leather Market Tote', 240),

        -- Julian: everything goes to alterations.
        ('CUST-JULIAN', 'Tailored Wool Blazer', 25),
        ('CUST-JULIAN', 'Double-Pleat Wool Trouser', 25),
        ('CUST-JULIAN', 'Suede Chelsea Boot', 95),
        ('CUST-JULIAN', 'Quilted Silk Vest', 170),

        -- David: the sustainable edit.
        ('CUST-DAVID', 'Stonewashed Linen Set', 40),
        ('CUST-DAVID', 'Oat Merino Crew', 100),
        ('CUST-DAVID', 'Jute Placemats, Set of 4', 165),
        ('CUST-DAVID', 'Charcoal Soap Bar', 220),

        -- Priya: gifting at volume.
        ('CUST-PRIYA', 'Fig and Cedar Eau de Parfum', 28),
        ('CUST-PRIYA', 'Rose Absolute Body Oil', 28),
        ('CUST-PRIYA', 'Vetiver Eau de Parfum', 90),
        ('CUST-PRIYA', 'Blown Glass Decanter', 150),
        ('CUST-PRIYA', 'Gift Wrapping Kit', 150),

        -- Elena: one rung below, worth an early-access nudge.
        ('CUST-ELENA', 'Cashmere Travel Wrap', 35),
        ('CUST-ELENA', 'Oat Merino Crew', 105),
        ('CUST-ELENA', 'Vetiver Eau de Parfum', 180),

        -- Thomas: objects that photograph well.
        ('CUST-THOMAS', 'Suede Chelsea Boot', 50),
        ('CUST-THOMAS', 'Travertine Wall Clock', 130),
        ('CUST-THOMAS', 'Rectangular Leather Watch', 220),

        -- Michael: repeat basics.
        ('CUST-MICHAEL', 'Oat Merino Crew', 42),
        ('CUST-MICHAEL', 'Quilted Silk Vest', 125),
        ('CUST-MICHAEL', 'Washed Canvas Tote', 230),

        -- Rachel: fragrance, with an open ticket.
        ('CUST-RACHEL', 'Vetiver Eau de Parfum', 18),
        ('CUST-RACHEL', 'Rose Absolute Body Oil', 85),
        ('CUST-RACHEL', 'Santal & Fig Candle', 175),

        -- Kevin: new joiner, two small orders.
        ('CUST-KEVIN', 'Beeswax Pillar Candle', 12),
        ('CUST-KEVIN', 'Charcoal Soap Bar', 12)
)
INSERT INTO pellier.orders (customer_id, product_id, quantity, placed_at)
SELECT
    os.customer_id,
    pc."productId",
    1,
    now() - make_interval(days => os.days_ago)
FROM order_seed os
JOIN pellier.product_catalog pc
  ON pc.name = os.product_name;

-- ---------------------------------------------------------------------
-- Verification. Fail loud, in the same spirit as 003.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    n_clients INTEGER;
    n_orders INTEGER;
    n_jessica INTEGER;
    n_drift INTEGER;
    n_rungs INTEGER;
    n_registered INTEGER;
    n_circle INTEGER;
    n_maison INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_clients
      FROM pellier.customers
     WHERE id LIKE 'CUST-%' AND id <> 'CUST-FRESH';

    -- Scoped to the twelve client IDs this migration owns, so hero orders
    -- from 003 cannot mask a failed name JOIN here.
    SELECT COUNT(*) INTO n_orders
      FROM pellier.orders
     WHERE customer_id IN (
        'CUST-JESSICA', 'CUST-SARAH', 'CUST-CATHERINE', 'CUST-AMARA',
        'CUST-JULIAN', 'CUST-DAVID', 'CUST-PRIYA', 'CUST-ELENA',
        'CUST-THOMAS', 'CUST-MICHAEL', 'CUST-RACHEL', 'CUST-KEVIN'
     );

    -- The operator walkthrough asks about exactly these two items. If the
    -- catalog seeder did not load the house bucket, the JOIN above silently
    -- drops them and the console shows a dispute over nothing.
    SELECT COUNT(*) INTO n_jessica
      FROM pellier.orders o
      JOIN pellier.product_catalog pc ON pc."productId" = o.product_id
     WHERE o.customer_id = 'CUST-JESSICA'
       AND pc.name IN ('Coral Lacquer Catchall', 'Waffle Bath Robe, Sage');

    -- The stored rung must still agree with the thresholds documented at the
    -- top of this file. If someone edits a spend figure without moving the
    -- rung, a policy decision would be made on a contradiction.
    SELECT COUNT(*) INTO n_drift
      FROM pellier.customers
     WHERE id <> 'CUST-FRESH'
       AND (
             (spend_12mo <  1500 AND membership <> 'registered')
          OR (spend_12mo >= 1500 AND spend_12mo <= 7500 AND membership <> 'circle')
          OR (spend_12mo >  7500 AND membership <> 'maison')
       );

    SELECT COUNT(DISTINCT membership) INTO n_rungs FROM pellier.customers;

    -- The book is balanced on purpose: five clients on each rung, so the
    -- operator console shows a real distribution rather than a pile of one tier
    -- with two token examples. CUST-FRESH is the empty-state persona and has no
    -- rung to speak of, so it is excluded here exactly as it is from n_drift.
    SELECT COUNT(*) INTO n_registered FROM pellier.customers
     WHERE membership = 'registered' AND id NOT IN ('CUST-FRESH', 'theo');
    SELECT COUNT(*) INTO n_circle FROM pellier.customers
     WHERE membership = 'circle' AND id NOT IN ('CUST-FRESH', 'theo');
    SELECT COUNT(*) INTO n_maison FROM pellier.customers
     WHERE membership = 'maison' AND id NOT IN ('CUST-FRESH', 'theo');

    IF n_clients < 15 THEN
        RAISE EXCEPTION
            'Client book has only % customers (expected >= 15). '
            'Check that 003_persona_seed.sql ran before this migration.',
            n_clients;
    END IF;

    IF n_orders < 46 THEN
        RAISE EXCEPTION
            'Client book produced only % orders (expected 46). '
            'Most likely cause: pellier.product_catalog is missing the house '
            'and signature buckets (IDs 41-60), so the name JOIN matched '
            'nothing. Re-run scripts/seed_pellier_catalog.py.', n_orders;
    END IF;

    IF n_jessica < 2 THEN
        RAISE EXCEPTION
            'Jessica return-dispute orders missing (got % of 2). The operator '
            'walkthrough needs both "Coral Lacquer Catchall" and '
            '"Waffle Bath Robe, Sage" in pellier.product_catalog.', n_jessica;
    END IF;

    IF n_drift > 0 THEN
        RAISE EXCEPTION
            '% customer(s) have a membership rung that contradicts '
            'spend_12mo. Thresholds: registered < 1500, circle 1500-7500, '
            'maison > 7500.', n_drift;
    END IF;

    IF n_rungs < 3 THEN
        RAISE EXCEPTION
            'Only % distinct membership rung(s) present (expected 3). The '
            'storefront demonstrates the whole ladder through the three hero '
            'personas, so all of registered/circle/maison must exist.', n_rungs;
    END IF;

    IF n_registered <> 5 OR n_circle <> 5 OR n_maison <> 5 THEN
        RAISE EXCEPTION
            'Membership ladder is unbalanced: % registered, % circle, % maison '
            '(expected 5/5/5). Moving a client between rungs means moving '
            'spend_12mo into the matching band as well, or the n_drift check '
            'above fires instead.',
            n_registered, n_circle, n_maison;
    END IF;

    RAISE NOTICE 'Client book ready: % customers, % orders, % rungs (%/%/% split)',
        n_clients, n_orders, n_rungs, n_registered, n_circle, n_maison;
END $$;

COMMIT;
