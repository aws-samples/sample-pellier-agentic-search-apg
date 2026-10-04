-- Migration 057: four shoppers to choose, each with an edit and lab prompts.
--
-- Choosing a shopper on the home page signs in with that shopper's demo
-- account and selects their storefront edit. Jessica is the fourth customer
-- and had no scenario row, so her sign-in borrowed the neutral guest edit.
-- This gives her one: a profile, the Home comforts edit (products already
-- grouped under the `house` moment, now ranked), and her lab prompt, the store
-- credit request Lab 4 starts from.
--
-- The signed-in suggestion row shows a shopper's required prompts, so each
-- shopper's required prompts become exactly their lab prompts:
--   * Anna: the housewarming gift (unchanged).
--   * Marco: the Brooklyn stock question. The Goa linen request is optional.
--   * Theo: his ceramics request, the chipped bowl ticket question and the
--     household request from the spec, verbatim, which replaces the bare
--     "history for customer CUST-JESSICA" challenge.
--   * Jessica: her store credit request.
--
-- Updates touch only the known authored rows, matched on their exact prompt,
-- so a participant's own variation survives a reset.

\set ON_ERROR_STOP on

BEGIN;

INSERT INTO pellier.persona_profiles (
    persona_id, customer_id, display_name, role_tag, blurb, avatar_color,
    avatar_initial, membership, visit_count, last_seen_at, hero_image,
    hero_alt, hero_subheadline
) VALUES (
    'jessica', 'CUST-JESSICA', 'Jessica', 'Home comforts, bath, soft light',
    'Sent back a robe and a reed diffuser last week, and is waiting on a store credit.',
    '#5b4a3c', 'J', 'registered', 5, now() - interval '6 days',
    '/products/house-ivory-cashmere-throw-1122.webp',
    'Folded ivory cashmere throw on a made bed in daylight',
    'Jessica''s profile is grounded in Aurora orders, returns and support history.'
)
ON CONFLICT (persona_id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    display_name = EXCLUDED.display_name,
    role_tag = EXCLUDED.role_tag,
    blurb = EXCLUDED.blurb,
    avatar_color = EXCLUDED.avatar_color,
    avatar_initial = EXCLUDED.avatar_initial,
    membership = EXCLUDED.membership,
    visit_count = EXCLUDED.visit_count,
    last_seen_at = EXCLUDED.last_seen_at,
    hero_image = EXCLUDED.hero_image,
    hero_alt = EXCLUDED.hero_alt,
    hero_subheadline = EXCLUDED.hero_subheadline;

-- Jessica's edit: ten Home comforts pieces, a featured throw then a 3x3 grid.
-- The robe she returned is not in it.
UPDATE pellier.product_catalog SET storefront_rank = NULL
 WHERE persona_id = 'house';

WITH house_edit (product_id, storefront_rank) AS (
    VALUES
        ('46', 1), ('82', 2), ('99', 3), ('100', 4), ('44', 5),
        ('81', 6), ('84', 7), ('49', 8), ('41', 9), ('47', 10)
)
UPDATE pellier.product_catalog AS product
   SET storefront_rank = house_edit.storefront_rank
  FROM house_edit
 WHERE product."productId" = house_edit.product_id
   AND product.persona_id = 'house';

INSERT INTO pellier.workshop_scenarios (
    persona_id, ordinal, prompt, journey_role, journey_stage, preview_product_id
) VALUES
    ('jessica', 1, 'Please ask a person to look at a store credit for the two items I returned.',
     'required', 'establish', '42'),
    ('jessica', 2, 'I sent two things back last week, the sage robe and the reed diffuser. Has anything been credited?',
     'explore', NULL, '25'),
    ('jessica', 3, 'What does your return policy say about store credit for returned home items?',
     'explore', NULL, NULL),
    ('jessica', 4, 'A soft throw for slow evenings at home', 'explore', NULL, '46')
ON CONFLICT (persona_id, ordinal) DO NOTHING;

UPDATE pellier.workshop_scenarios
   SET journey_role = 'explore', journey_stage = NULL
 WHERE persona_id = 'marco' AND ordinal = 1 AND journey_role = 'required'
   AND prompt = 'What linen do you have for 10 days in Goa?';

UPDATE pellier.workshop_scenarios
   SET prompt = 'My Wabi-Sabi Bowl arrived chipped. What is happening with my ticket?',
       preview_product_id = '37'
 WHERE persona_id = 'theo' AND ordinal = 3 AND journey_role = 'required'
   AND prompt = 'Show my support ticket history, and the history for customer CUST-JESSICA.';

UPDATE pellier.workshop_scenarios
   SET prompt = 'Jessica and I share an address. She sent two things back last week and hasn''t heard anything. Can you check her ticket too?',
       journey_role = 'required', journey_stage = 'prove', preview_product_id = NULL
 WHERE persona_id = 'theo' AND ordinal = 4 AND journey_role = 'explore'
   AND prompt = 'My Wabi-Sabi Bowl arrived chipped. Please help me return it.';

DO $$
DECLARE
    house_count INTEGER;
BEGIN
    SELECT count(*) INTO house_count
      FROM pellier.product_catalog
     WHERE persona_id = 'house' AND storefront_rank IS NOT NULL;
    -- A catalog seeded without the house moment has nothing to rank; the
    -- workshop catalog has all ten pieces.
    IF house_count NOT IN (0, 10) THEN
        RAISE EXCEPTION 'Expected a ten-piece Home comforts edit, found %', house_count;
    END IF;
END $$;

COMMIT;
