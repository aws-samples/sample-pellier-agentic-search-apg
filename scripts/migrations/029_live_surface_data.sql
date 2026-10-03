-- Migration 029: live storefront and Observatory surface data.
--
-- The participant UI must read one durable contract. Earlier revisions kept
-- persona cards, canonical shopper prompts, product grouping, and the active
-- persona session in separate browser or process-local fixtures. That made a
-- successful-looking workshop surface possible even when Aurora was absent.
--
-- This migration makes those records ordinary Aurora data:
--   * persona_profiles: presentation metadata tied to a real customer row
--   * workshop_scenarios: guided requests owned by the workshop database
--   * shopper_sessions: durable persona/session association
--   * product_catalog.persona_id: editorial grouping for the live floor
--
-- It is safe on a fresh account (after 003_persona_seed.sql) and upgrades an
-- existing account without deleting catalog, customer, or evidence rows.

\set ON_ERROR_STOP on

BEGIN;

CREATE SCHEMA IF NOT EXISTS pellier;

ALTER TABLE pellier.product_catalog
    ADD COLUMN IF NOT EXISTS persona_id TEXT;

UPDATE pellier.product_catalog
   SET persona_id = CASE
       WHEN "productId" ~ '^[0-9]+$'
            AND "productId"::integer BETWEEN 1 AND 10 THEN 'fresh'
       WHEN "productId" ~ '^[0-9]+$'
            AND "productId"::integer BETWEEN 11 AND 20 THEN 'marco'
       WHEN "productId" ~ '^[0-9]+$'
            AND "productId"::integer BETWEEN 21 AND 30 THEN 'anna'
       WHEN "productId" ~ '^[0-9]+$'
            AND "productId"::integer BETWEEN 31 AND 40 THEN 'theo'
       WHEN "productId" ~ '^[0-9]+$'
            AND "productId"::integer BETWEEN 41 AND 50 THEN 'house'
       WHEN "productId" ~ '^[0-9]+$'
            AND "productId"::integer BETWEEN 51 AND 60 THEN 'signature'
       ELSE persona_id
   END
 WHERE persona_id IS NULL
    OR persona_id = '';

-- PNG masters are deliberately not shipped. The catalog points at the
-- responsive WebP derivative, while the frontend adds the AVIF candidate via
-- <picture>. This update also repairs an already-provisioned account.
UPDATE pellier.product_catalog
   SET "imgUrl" = regexp_replace("imgUrl", '\.png$', '.webp')
 WHERE "imgUrl" ~ '\.png$';

CREATE INDEX IF NOT EXISTS product_catalog_persona_idx
    ON pellier.product_catalog (persona_id, tier, "productId");

CREATE TABLE IF NOT EXISTS pellier.persona_profiles (
    persona_id       TEXT PRIMARY KEY,
    customer_id      TEXT NOT NULL UNIQUE
                     REFERENCES pellier.customers(id) ON DELETE CASCADE,
    display_name     TEXT NOT NULL,
    role_tag         TEXT NOT NULL,
    blurb            TEXT NOT NULL,
    avatar_color     TEXT NOT NULL,
    avatar_initial   TEXT NOT NULL,
    membership       TEXT NOT NULL
                     CHECK (membership IN ('registered', 'circle', 'maison')),
    visit_count      INTEGER NOT NULL DEFAULT 0 CHECK (visit_count >= 0),
    last_seen_at     TIMESTAMPTZ,
    hero_image       TEXT NOT NULL,
    hero_alt         TEXT NOT NULL,
    hero_subheadline TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS persona_profiles_set_updated_at
    ON pellier.persona_profiles;
CREATE TRIGGER persona_profiles_set_updated_at
    BEFORE UPDATE ON pellier.persona_profiles
    FOR EACH ROW EXECUTE FUNCTION pellier.set_updated_at();

INSERT INTO pellier.persona_profiles (
    persona_id, customer_id, display_name, role_tag, blurb, avatar_color,
    avatar_initial, membership, visit_count, last_seen_at, hero_image,
    hero_alt, hero_subheadline
) VALUES
    (
        'fresh', 'CUST-FRESH', 'Pellier guest', 'New visitor',
        'A new visitor exploring the current Pellier collection.',
        '#4D3A30', 'P', 'registered', 0, NULL,
        '/products/landing-hero-weekender.webp',
        'Leather weekender on a travertine bench beside linen and an olive branch',
        'Explore the current collection, then ask the concierge about a piece or occasion.'
    ),
    (
        'marco', 'CUST-MARCO', 'Marco', 'Travel, utility, leather, linen',
        'Brooklyn-based, partial to natural fibers. Last visit, three weeks ago. Bought the oat Maren tunic.',
        '#5a3528', 'M', 'maison', 11, now() - interval '21 days',
        '/products/hero-marco.png',
        'Leather weekender with folded linen and brass travel details in warm daylight',
        'Marco’s profile is grounded in Aurora orders, preferences, and current inventory.'
    ),
    (
        'anna', 'CUST-ANNA', 'Anna', 'Gifting, ceremony, silk, glass',
        'Buys for others — partner, mother, friends. Recent searches lean milestone.',
        '#6b3d2a', 'A', 'circle', 6, now() - interval '9 days',
        '/products/hero-anna.png',
        'Ribbon-wrapped gift beside an amber candle, ceramic bud vase, and blank card',
        'Anna’s profile is grounded in Aurora orders, preferences, and current catalog signals.'
    ),
    (
        'theo', 'CUST-THEO', 'Theo', 'Slow living, craft, stoneware, natural materials',
        'Keeps a short list of quiet pieces — ceramics, linen throws, stoneware. Finishes what he buys, slowly.',
        '#5a4535', 'T', 'registered', 8, now() - interval '14 days',
        '/products/hero-theo.png',
        'Charcoal stoneware bowl beside natural linen, a beeswax candle, and olive branches',
        'Theo’s profile is grounded in Aurora orders, support history, and return policy.'
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

CREATE TABLE IF NOT EXISTS pellier.shopper_sessions (
    session_id TEXT PRIMARY KEY,
    persona_id TEXT NOT NULL
               REFERENCES pellier.persona_profiles(persona_id)
               ON DELETE RESTRICT,
    customer_id TEXT NOT NULL
                REFERENCES pellier.customers(id)
                ON DELETE RESTRICT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    CHECK (length(session_id) >= 33)
);

CREATE INDEX IF NOT EXISTS shopper_sessions_persona_started_idx
    ON pellier.shopper_sessions (persona_id, started_at DESC);

CREATE TABLE IF NOT EXISTS pellier.workshop_scenarios (
    scenario_id BIGSERIAL PRIMARY KEY,
    persona_id TEXT NOT NULL
               REFERENCES pellier.persona_profiles(persona_id)
               ON DELETE CASCADE,
    ordinal SMALLINT NOT NULL CHECK (ordinal BETWEEN 1 AND 5),
    prompt TEXT NOT NULL CHECK (length(trim(prompt)) > 0),
    journey_role TEXT NOT NULL DEFAULT 'explore'
                 CHECK (journey_role IN ('required', 'explore')),
    journey_stage TEXT
                  CHECK (journey_stage IN ('establish', 'exercise', 'prove')),
    preview_product_id TEXT
                       REFERENCES pellier.product_catalog("productId")
                       ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (persona_id, ordinal)
);

ALTER TABLE pellier.workshop_scenarios
    ADD COLUMN IF NOT EXISTS journey_role TEXT NOT NULL DEFAULT 'explore'
        CHECK (journey_role IN ('required', 'explore'));
ALTER TABLE pellier.workshop_scenarios
    ADD COLUMN IF NOT EXISTS journey_stage TEXT
        CHECK (journey_stage IN ('establish', 'exercise', 'prove'));

DROP TRIGGER IF EXISTS workshop_scenarios_set_updated_at
    ON pellier.workshop_scenarios;
CREATE TRIGGER workshop_scenarios_set_updated_at
    BEFORE UPDATE ON pellier.workshop_scenarios
    FOR EACH ROW EXECUTE FUNCTION pellier.set_updated_at();

INSERT INTO pellier.workshop_scenarios (
    persona_id, ordinal, prompt, journey_role, journey_stage, preview_product_id
) VALUES
    ('fresh', 1, 'A considered carry-all for a long weekend.', 'explore', NULL, '10'),
    ('fresh', 2, 'Pieces for slow Sunday mornings', 'explore', NULL, '8'),
    ('fresh', 3, 'Something to wear for warm evenings out', 'explore', NULL, '2'),
    ('fresh', 4, 'Linen pieces that travel well', 'explore', NULL, '3'),
    ('fresh', 5, 'A cozy layer for cooler nights', 'explore', NULL, '8'),
    ('marco', 1, 'What linen do you have for 10 days in Goa?', 'required', 'establish', '11'),
    ('marco', 2, 'What would go with the Hadley Linen Shirt?', 'required', 'exercise', '14'),
    ('marco', 3, 'How many Hadley Linen Shirts are available at the Brooklyn warehouse, and what ship window is recorded?', 'required', 'prove', '2'),
    ('marco', 4, 'What''s the price range for linen shirts?', 'explore', NULL, '2'),
    ('marco', 5, 'Can you connect me with a real Pellier stylist? I want a person to help me pick what to wear to my brother''s wedding – not product cards.', 'explore', NULL, '19'),
    ('anna', 1, 'A housewarming gift for someone who loves slow morning rituals.', 'required', 'establish', '22'),
    ('anna', 2, 'Keep it under $100 and in stock. Show me the strongest two options.', 'required', 'exercise', '28'),
    ('anna', 3, 'Which one should I choose? Compare the two options using their current prices and availability.', 'required', 'prove', NULL),
    ('anna', 4, 'Wrap-ready gifts with no extra effort', 'explore', NULL, '26'),
    ('anna', 5, 'Can you connect me with a real stylist? My friend just lost her mother and I want a person to help me pick a sympathy gift, not just see product cards.', 'explore', NULL, '28'),
    ('theo', 1, 'Hand-thrown ceramics for a slower morning routine', 'required', 'establish', '31'),
    ('theo', 2, 'What goes well with the pour-over set, keeping to the same materials and morning routine?', 'required', 'exercise', '34'),
    ('theo', 3, 'My Wabi-Sabi Bowl arrived chipped. Please help me return it.', 'required', 'prove', '37'),
    ('theo', 4, 'Without asking me to repeat the ritual or material, which pairing should I choose and why?', 'explore', NULL, '34'),
    ('theo', 5, 'The linen throw I bought 4 months ago developed a tear at the seam – I know the standard window closed but pieces like this should last. Can you handle this as an exception?', 'explore', NULL, '38')
ON CONFLICT (persona_id, ordinal) DO UPDATE SET
    prompt = EXCLUDED.prompt,
    journey_role = EXCLUDED.journey_role,
    journey_stage = EXCLUDED.journey_stage,
    preview_product_id = EXCLUDED.preview_product_id;

COMMIT;
