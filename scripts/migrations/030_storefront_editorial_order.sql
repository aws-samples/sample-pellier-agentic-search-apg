-- Migration 030: durable storefront edit ordering.
--
-- The storefront has four intentionally composed edits. Fresh promotes nine
-- pieces in one unsigned discovery grid. Each named persona promotes all ten
-- cohort pieces: one featured item followed by a symmetric 3x3 grid.
-- This is merchandising state, not a browser fixture: the product data and
-- order must survive a fresh account, a restart, and a different browser.

\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE pellier.product_catalog
    ADD COLUMN IF NOT EXISTS storefront_rank SMALLINT;

-- Clear prior ranks for the shopper edits before replaying the source-owned
-- merchandising order. The remaining product in each ten-item persona cohort
-- remains searchable in Aurora but is not promoted into the nine-card floor.
UPDATE pellier.product_catalog
   SET storefront_rank = NULL
 WHERE persona_id IN ('fresh', 'marco', 'anna', 'theo');

WITH storefront_edit (persona_id, product_id, storefront_rank) AS (
    VALUES
        -- Fresh: Leather Weekender, then a material-led first-visit edit.
        ('fresh', '3', 1), ('fresh', '1', 2), ('fresh', '2', 3),
        ('fresh', '4', 4), ('fresh', '5', 5), ('fresh', '6', 6),
        ('fresh', '7', 7), ('fresh', '8', 8), ('fresh', '10', 9),

        -- Marco: the travel edit, ranked from linen core to accessories.
        ('marco', '11', 1), ('marco', '14', 2), ('marco', '17', 3),
        ('marco', '16', 4), ('marco', '13', 5), ('marco', '19', 6),
        ('marco', '18', 7), ('marco', '12', 8), ('marco', '15', 9),
        ('marco', '20', 10),

        -- Anna: giftable objects first, then the supporting considerations.
        ('anna', '21', 1), ('anna', '23', 2), ('anna', '27', 3),
        ('anna', '26', 4), ('anna', '29', 5), ('anna', '22', 6),
        ('anna', '25', 7), ('anna', '24', 8), ('anna', '28', 9),
        ('anna', '30', 10),

        -- Theo: the slow-living edit, led by the pour-over ritual.
        ('theo', '31', 1), ('theo', '37', 2), ('theo', '36', 3),
        ('theo', '39', 4), ('theo', '35', 5), ('theo', '32', 6),
        ('theo', '34', 7), ('theo', '38', 8), ('theo', '33', 9),
        ('theo', '40', 10)
)
UPDATE pellier.product_catalog AS product
   SET storefront_rank = storefront_edit.storefront_rank
  FROM storefront_edit
 WHERE product.persona_id = storefront_edit.persona_id
   AND product."productId" = storefront_edit.product_id;

CREATE INDEX IF NOT EXISTS product_catalog_storefront_edit_idx
    ON pellier.product_catalog (persona_id, storefront_rank)
 WHERE storefront_rank IS NOT NULL;

DO $$
DECLARE
    bad_edit_count INTEGER;
BEGIN
    SELECT count(*) INTO bad_edit_count
      FROM (
          SELECT persona_id
            FROM pellier.product_catalog
           WHERE persona_id IN ('fresh', 'marco', 'anna', 'theo')
             AND storefront_rank IS NOT NULL
           GROUP BY persona_id
          HAVING count(*) <> CASE WHEN persona_id = 'fresh' THEN 9 ELSE 10 END
              OR min(storefront_rank) <> 1
              OR max(storefront_rank) <> CASE WHEN persona_id = 'fresh' THEN 9 ELSE 10 END
              OR count(DISTINCT storefront_rank)
                    <> CASE WHEN persona_id = 'fresh' THEN 9 ELSE 10 END
      ) invalid;

    IF bad_edit_count <> 0 THEN
        RAISE EXCEPTION
            'Fresh must contain ranks 1-9; named persona edits must contain ranks 1-10';
    END IF;
END $$;

COMMIT;
