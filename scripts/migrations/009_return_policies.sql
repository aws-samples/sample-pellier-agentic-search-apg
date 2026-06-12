-- Migration 009: Return-policy lookup table for the returns_and_care @tool
--
-- Why:
--   The Experience Guide's ``returns_and_care`` tool
--   (services/agent_tools.py) answers "what's the return window / refund
--   method for this category?" by SELECTing from pellier.return_policies.
--   The tool shipped, but no migration created the table — so any
--   return/refund/care question that routes through returns_and_care hit
--   a "relation does not exist" error. This migration creates and seeds
--   it, keeping the tool's SQL (category_name, return_window_days,
--   conditions, refund_method) unchanged.
--
-- Teaching shape:
--   This is a read-side reference table — the policy the Experience Guide
--   *cites* before process_return *writes*. The tool falls back to the
--   'default' row when a category has no specific policy, so the 'default'
--   row is required; the per-category rows make the answer feel curated.
--
-- Category names match seed_boutique_catalog.py CATEGORY_NAMES
-- (Apparel, Accessories, Home Decor, Footwear, ...), plus 'default'.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING.
-- Run: psql $DATABASE_URL -f scripts/migrations/009_return_policies.sql

\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS pellier.return_policies (
    category_name       TEXT PRIMARY KEY,
    return_window_days  INTEGER NOT NULL DEFAULT 30,
    conditions          TEXT    NOT NULL DEFAULT 'Unworn, with tags, in original packaging.',
    refund_method       TEXT    NOT NULL DEFAULT 'Original payment method'
);

-- Seed: a required 'default' row (the tool's fallback) plus per-category
-- rows for the curated catalog. ON CONFLICT keeps re-runs safe and lets a
-- maintainer hand-edit a row without the migration clobbering it.
INSERT INTO pellier.return_policies
    (category_name, return_window_days, conditions, refund_method)
VALUES
    ('default',     30, 'Unworn and unused, with original tags and packaging.',                 'Original payment method'),
    ('Apparel',     30, 'Unworn, with tags attached, in resaleable condition.',                 'Original payment method'),
    ('Accessories', 30, 'Unused, in original packaging; final sale on pierced jewelry.',        'Original payment method'),
    ('Home Decor',  45, 'Unused and undamaged; ceramics and glassware inspected on return.',    'Original payment method or store credit'),
    ('Footwear',    30, 'Unworn, in the original box, with no sole wear.',                       'Original payment method')
ON CONFLICT (category_name) DO NOTHING;

-- Confirm reachability so the bootstrap transcript shows the seed landed.
DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT count(*) INTO n FROM pellier.return_policies;
    RAISE NOTICE 'pellier.return_policies ready (% rows, incl. default)', n;
END $$;

COMMIT;
