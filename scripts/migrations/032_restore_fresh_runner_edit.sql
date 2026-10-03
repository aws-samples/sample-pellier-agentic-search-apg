-- Migration 032: restore the reference unsigned storefront edit.
--
-- Migration 031 temporarily replaced Everyday Runner with the Washed
-- Canvas Tote. The accepted guest-storefront references retain the runner as
-- the ninth promoted piece. Both products remain searchable in the 60-product
-- curated catalog; this migration changes only durable merchandising rank.

\set ON_ERROR_STOP on

BEGIN;

UPDATE pellier.product_catalog
   SET storefront_rank = CASE
       WHEN "productId" = '9' THEN 9
       WHEN "productId" = '10' THEN NULL
       ELSE storefront_rank
   END
 WHERE persona_id = 'fresh'
   AND "productId" IN ('9', '10');

DO $$
DECLARE
    promoted_product TEXT;
    ranked_count INTEGER;
BEGIN
    SELECT "productId"
      INTO promoted_product
      FROM pellier.product_catalog
     WHERE persona_id = 'fresh'
       AND storefront_rank = 9;

    SELECT count(*)
      INTO ranked_count
      FROM pellier.product_catalog
     WHERE persona_id = 'fresh'
       AND storefront_rank IS NOT NULL;

    IF promoted_product IS DISTINCT FROM '9' OR ranked_count <> 9 THEN
        RAISE EXCEPTION
            'Fresh storefront must promote exactly nine products with product 9 at rank 9; found product %, count %',
            COALESCE(promoted_product, '<none>'),
            ranked_count;
    END IF;
END $$;

COMMIT;
