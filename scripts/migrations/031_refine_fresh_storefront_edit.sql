-- Migration 031: refine the unsigned Pellier edit.
--
-- Everyday Runner remains a searchable catalog product, but it is not
-- part of the house's first-visit editorial floor. The nine-piece unsigned
-- edit stays material-led: leather, linen, ceramic, apothecary, and everyday
-- carry. This upgrade also changes the guided guest request, so Observatory
-- does not present an athletic product as the default workshop story.

\set ON_ERROR_STOP on

BEGIN;

UPDATE pellier.product_catalog
   SET storefront_rank = CASE
       WHEN "productId" = '10' THEN 9
       WHEN "productId" = '9' THEN NULL
       ELSE storefront_rank
   END
 WHERE persona_id = 'fresh'
   AND "productId" IN ('9', '10');

UPDATE pellier.workshop_scenarios
   SET prompt = 'A considered carry-all for a long weekend.',
       preview_product_id = '10'
 WHERE persona_id = 'fresh'
   AND ordinal = 1;

DO $$
DECLARE
    featured_grid_product TEXT;
    guided_prompt TEXT;
    guided_preview TEXT;
BEGIN
    SELECT "productId"
      INTO featured_grid_product
      FROM pellier.product_catalog
     WHERE persona_id = 'fresh'
       AND storefront_rank = 9;

    IF featured_grid_product IS DISTINCT FROM '10' THEN
        RAISE EXCEPTION
            'Fresh storefront rank 9 must be product 10, found %',
            COALESCE(featured_grid_product, '<none>');
    END IF;

    SELECT prompt, preview_product_id
      INTO guided_prompt, guided_preview
      FROM pellier.workshop_scenarios
     WHERE persona_id = 'fresh'
       AND ordinal = 1;

    IF guided_prompt IS DISTINCT FROM 'A considered carry-all for a long weekend.'
       OR guided_preview IS DISTINCT FROM '10' THEN
        RAISE EXCEPTION
            'Fresh guided scenario must point at the refined unsigned edit';
    END IF;
END $$;

COMMIT;
