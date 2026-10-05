-- Pellier's starting data, after scripts/seed_pellier_catalog.py has loaded
-- the 100 products. Four customers and their orders, the stock in three
-- warehouses, the return policies and three support tickets.
--
-- Two cases the labs build on:
--   * Theo's Wabi-Sabi Bowl arrived chipped (ticket TKT-2026-5021).
--   * Jessica sent back the Waffle Bath Robe, Sage ($64) and the Reed
--     Diffuser ($36). Both were received; no credit has been given. Together
--     they are exactly $100.00, so Lab 4's inclusive $100 limit decides her
--     credit.
-- Theo and Jessica share a home, so their orders ship to one address.
--
-- No approval and no store credit is seeded: those happen in the labs.

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------------
-- Each storefront edit: twelve pieces in grid order
-- ---------------------------------------------------------------------------
-- Twelve fills complete rows at two, three, four or six cards across. A
-- piece joins the edit named on its row; most come from the catalog moment
-- of the same name.
WITH edit (persona_id, product_id, storefront_rank) AS (VALUES
    -- fresh: the signed-out edit, "This week at Pellier"
    ('fresh', '3', 1), ('fresh', '1', 2), ('fresh', '2', 3), ('fresh', '4', 4),
    ('fresh', '5', 5), ('fresh', '6', 6), ('fresh', '7', 7), ('fresh', '8', 8),
    ('fresh', '9', 9), ('fresh', '10', 10), ('fresh', '85', 11), ('fresh', '70', 12),
    -- marco: travel and linen
    ('marco', '11', 1), ('marco', '14', 2), ('marco', '17', 3), ('marco', '16', 4),
    ('marco', '13', 5), ('marco', '19', 6), ('marco', '18', 7), ('marco', '12', 8),
    ('marco', '15', 9), ('marco', '20', 10), ('marco', '98', 11), ('marco', '94', 12),
    -- anna: gifts
    ('anna', '21', 1), ('anna', '23', 2), ('anna', '27', 3), ('anna', '26', 4),
    ('anna', '29', 5), ('anna', '22', 6), ('anna', '25', 7), ('anna', '24', 8),
    ('anna', '28', 9), ('anna', '30', 10), ('anna', '62', 11), ('anna', '78', 12),
    -- theo: ceramics and slow craft
    ('theo', '31', 1), ('theo', '37', 2), ('theo', '36', 3), ('theo', '39', 4),
    ('theo', '35', 5), ('theo', '32', 6), ('theo', '34', 7), ('theo', '38', 8),
    ('theo', '33', 9), ('theo', '40', 10), ('theo', '65', 11), ('theo', '71', 12),
    -- house: Jessica's Home comforts edit, home and bath. The robe she sent
    -- back is not in it, so the body oil and the rug come from Made to last.
    ('house', '46', 1), ('house', '82', 2), ('house', '99', 3), ('house', '100', 4),
    ('house', '44', 5), ('house', '81', 6), ('house', '84', 7), ('house', '49', 8),
    ('house', '41', 9), ('house', '47', 10), ('house', '56', 11), ('house', '59', 12))
UPDATE pellier.product_catalog p
   SET persona_id = edit.persona_id,
       storefront_rank = edit.storefront_rank
  FROM edit
 WHERE p."productId" = edit.product_id;

-- ---------------------------------------------------------------------------
-- Stock: every product in all three warehouses
-- ---------------------------------------------------------------------------
-- 30% of a product's units sit in each of two warehouses and the rest in a
-- third, chosen by product id, so the 300 rows add up to the catalog quantity.
INSERT INTO pellier.warehouse_inventory
       (product_id, warehouse_code, warehouse_name, city, ship_window_min, ship_window_max, quantity)
SELECT p."productId", w.code, w.name, w.city, w.ship_min, w.ship_max,
       CASE WHEN w.position = p."productId"::int % 3
            THEN p.quantity - 2 * floor(p.quantity * 0.30)::int
            ELSE floor(p.quantity * 0.30)::int END
  FROM pellier.product_catalog p
 CROSS JOIN (VALUES
    (0, 'BK-01',  'Brooklyn', 'Brooklyn, NY', 1, 2),
    (1, 'ATX-02', 'Austin',   'Austin, TX',   2, 4),
    (2, 'PDX-01', 'Portland', 'Portland, OR', 3, 5)
 ) AS w (position, code, name, city, ship_min, ship_max);

-- The rows the labs quote. Marco's Hadley Linen Shirt (2) is sold out in
-- Brooklyn and in stock elsewhere; the Quilted Silk Vest (43) and product 79
-- are sold out everywhere.
UPDATE pellier.warehouse_inventory wi
   SET quantity = f.quantity
  FROM (VALUES
    ('2',  'BK-01', 0), ('2',  'ATX-02', 6), ('2',  'PDX-01', 14),
    ('14', 'BK-01', 3), ('14', 'ATX-02', 2), ('14', 'PDX-01', 0),
    ('43', 'BK-01', 0), ('43', 'ATX-02', 0), ('43', 'PDX-01', 0),
    ('79', 'BK-01', 0), ('79', 'ATX-02', 0), ('79', 'PDX-01', 0)
  ) AS f (product_id, warehouse_code, quantity)
 WHERE wi.product_id = f.product_id AND wi.warehouse_code = f.warehouse_code;

-- ---------------------------------------------------------------------------
-- Customers
-- ---------------------------------------------------------------------------
INSERT INTO pellier.customers (id, name, cognito_username, preferences_summary) VALUES
    ('CUST-MARCO', 'Marco', 'marco',
     'Brooklyn-based, partial to natural fibers. Linen, travel-ready pieces, warm neutrals.'),
    ('CUST-ANNA', 'Anna', 'anna',
     'Gift-giver. Buys for others, with milestone occasions and explicit budgets.'),
    ('CUST-THEO', 'Theo', 'theo',
     'Home + slow craft. Ceramics, linen throws, stoneware. Finishes what he buys, slowly.'),
    ('CUST-JESSICA', 'Jessica Nakamura', 'jessica',
     'Home and bath, warm coral and sage. Sent back the robe and the reed diffuser; no store credit recorded yet.');

-- ---------------------------------------------------------------------------
-- Orders
-- ---------------------------------------------------------------------------
INSERT INTO pellier.orders
       (id, customer_id, product_id, amount_paid_cents, ship_to, placed_at, return_status)
SELECT o.id, o.customer_id, o.product_id, o.amount_paid_cents, o.ship_to,
       now() - make_interval(days => o.days_ago), o.return_status
  FROM (VALUES
    -- Marco: linen and travel
    ( 1, 'CUST-MARCO', '2',   7200,  56, '41 Sterling Place, Brooklyn, NY 11217', NULL),  -- Hadley Linen Shirt
    ( 2, 'CUST-MARCO', '11',  6800,  48, '41 Sterling Place, Brooklyn, NY 11217', NULL),  -- Italian Linen Camp Shirt
    ( 3, 'CUST-MARCO', '14',  7800,  40, '41 Sterling Place, Brooklyn, NY 11217', NULL),  -- Linen Drawstring Trousers
    ( 4, 'CUST-MARCO', '16',  8800,  32, '41 Sterling Place, Brooklyn, NY 11217', NULL),  -- Linen Overshirt
    ( 5, 'CUST-MARCO', '18',  2600,  24, '41 Sterling Place, Brooklyn, NY 11217', NULL),  -- Cotton-Linen Crew Tee
    ( 6, 'CUST-MARCO', '17', 21900,  16, '41 Sterling Place, Brooklyn, NY 11217', NULL),  -- Leather Weekend Holdall
    ( 7, 'CUST-MARCO', '20',  1600,   8, '41 Sterling Place, Brooklyn, NY 11217', NULL),  -- Merino Travel Socks
    -- Anna: gifts across price bands
    ( 8, 'CUST-ANNA',  '7',   6800,  40, '9 Orchard Lane, Montclair, NJ 07042', NULL),    -- Jute Placemats, Set of 4
    ( 9, 'CUST-ANNA',  '4',   3800,  32, '9 Orchard Lane, Montclair, NJ 07042', NULL),    -- Santal & Fig Candle
    (10, 'CUST-ANNA',  '27',  2200,  24, '9 Orchard Lane, Montclair, NJ 07042', NULL),    -- Ceramic Bud Vase
    (11, 'CUST-ANNA',  '26',  3200,  16, '9 Orchard Lane, Montclair, NJ 07042', NULL),    -- Handmade Soap Set
    (12, 'CUST-ANNA',  '30',  1200,   8, '9 Orchard Lane, Montclair, NJ 07042', NULL),    -- Gift Wrapping Kit
    -- Theo: slow-craft ceramics, at the home he shares with Jessica
    (13, 'CUST-THEO',  '35',  1600,  90, '22 Alder Street, Portland, OR 97214', NULL),    -- Brass Incense Holder
    (14, 'CUST-THEO',  '36',  3000,  45, '22 Alder Street, Portland, OR 97214', NULL),    -- Ceramic Tumblers
    (15, 'CUST-THEO',  '31',  5800,  21, '22 Alder Street, Portland, OR 97214', NULL),    -- Stoneware Pour-Over Set
    (16, 'CUST-THEO',  '37',  2400,   8, '22 Alder Street, Portland, OR 97214', NULL),    -- Wabi-Sabi Bowl (arrived chipped)
    -- Jessica: home and bath. The robe and the diffuser came back.
    (17, 'CUST-JESSICA', '50', 10800, 300, '22 Alder Street, Portland, OR 97214', NULL),  -- Oat Merino Crew
    (18, 'CUST-JESSICA', '43', 12900, 210, '22 Alder Street, Portland, OR 97214', NULL),  -- Quilted Silk Vest
    (19, 'CUST-JESSICA', '31',  5800, 120, '22 Alder Street, Portland, OR 97214', NULL),  -- Stoneware Pour-Over Set
    (20, 'CUST-JESSICA', '42',  6400,  34, '22 Alder Street, Portland, OR 97214', 'received'),  -- Waffle Bath Robe, Sage
    (21, 'CUST-JESSICA', '25',  3600,  34, '22 Alder Street, Portland, OR 97214', 'received')   -- Reed Diffuser
  ) AS o (id, customer_id, product_id, amount_paid_cents, days_ago, ship_to, return_status);

-- New orders number on from the seeded ones.
DO $$ BEGIN
    PERFORM setval(pg_get_serial_sequence('pellier.orders', 'id'), (SELECT max(id) FROM pellier.orders));
END $$;

-- ---------------------------------------------------------------------------
-- Return policies
-- ---------------------------------------------------------------------------
INSERT INTO pellier.return_policies (category_name, return_window_days, conditions, refund_method) VALUES
    ('default',              30, 'Unworn and unused, with original tags and packaging.',              'Original payment method'),
    ('Clothing',             30, 'Unworn, with tags attached, in resaleable condition.',              'Original payment method'),
    ('Shoes',                30, 'Unworn, in the original box, with no sole wear.',                    'Original payment method'),
    ('Bags and travel',      30, 'Unused, with tags attached, in the original packaging.',            'Original payment method'),
    ('Accessories',          30, 'Unused, in original packaging; final sale on pierced jewelry.',     'Original payment method'),
    ('Home',                 45, 'Unused and undamaged; ceramics and glassware inspected on return.', 'Original payment method or store credit'),
    ('Kitchen and table',    45, 'Unused and undamaged; ceramics and glassware inspected on return.', 'Original payment method or store credit'),
    ('Bath and body',        30, 'Unopened and unused, in the original packaging.',                   'Original payment method'),
    ('Stationery and gifts', 30, 'Unused, in the original packaging.',                                'Original payment method');

-- ---------------------------------------------------------------------------
-- Support tickets
-- ---------------------------------------------------------------------------
INSERT INTO pellier.support_tickets
       (ticket_id, customer_id, subject, status, channel, last_note, opened_at, resolved_at) VALUES
    ('TKT-2026-3015', 'CUST-JESSICA', 'Two items went back, no credit yet', 'open', 'chat',
     'Sent back the Waffle Bath Robe, Sage and the Reed Diffuser last week. Both were received. No store credit has been recorded.',
     now() - interval '8 days', NULL),
    ('TKT-2026-5021', 'CUST-THEO', 'Wabi-Sabi Bowl arrived chipped', 'open', 'chat',
     'Customer reports a chip on the rim of the bowl from his last order. Awaiting an update.',
     now() - interval '3 days', NULL),
    ('TKT-2026-1874', 'CUST-THEO', 'Pour-over set delivery date moved', 'resolved', 'email',
     'Delivery moved by two days at the customer''s request and confirmed.',
     now() - interval '40 days', now() - interval '38 days');

-- ---------------------------------------------------------------------------
-- Checks: stop here, loudly, if the seed is not the dataset the labs expect.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    drift integer;
BEGIN
    IF (SELECT count(*) FROM pellier.product_catalog) <> 100 THEN
        RAISE EXCEPTION 'Expected 100 products; run scripts/seed_pellier_catalog.py first';
    END IF;
    IF (SELECT count(*) FROM pellier.warehouse_inventory) <> 300 THEN
        RAISE EXCEPTION 'Expected 300 warehouse rows';
    END IF;
    -- A product's catalog quantity is the sum of its warehouse rows.
    SELECT count(*) INTO drift
      FROM pellier.product_catalog p
      JOIN (SELECT product_id, sum(quantity) AS units
              FROM pellier.warehouse_inventory GROUP BY product_id) s
        ON s.product_id = p."productId"
     WHERE s.units <> p.quantity;
    IF drift <> 0 THEN
        RAISE EXCEPTION '% products disagree with their warehouse rows', drift;
    END IF;
    IF (SELECT sum(amount_paid_cents) FROM pellier.orders
         WHERE customer_id = 'CUST-JESSICA' AND return_status = 'received') <> 10000 THEN
        RAISE EXCEPTION 'Jessica''s two returned items must total exactly 10000 cents';
    END IF;
    IF (SELECT count(*) FROM (
            SELECT persona_id FROM pellier.product_catalog
             WHERE storefront_rank IS NOT NULL
             GROUP BY persona_id HAVING count(*) = 12) edits) <> 5
       OR (SELECT count(*) FROM pellier.product_catalog WHERE storefront_rank IS NOT NULL) <> 60 THEN
        RAISE EXCEPTION 'Expected five storefront edits of twelve pieces each';
    END IF;
END $$;

COMMIT;
