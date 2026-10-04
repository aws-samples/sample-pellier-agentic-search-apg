-- Migration 057: what each shopper requires, kept across chat turns.
-- The agent writes search words; this table keeps the shopper's requirements,
-- and the search tools enforce the revision written for their turn. One row per
-- turn, append-only, so every receipt can cite the requirements it enforced.
\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS pellier.shopping_requirements (
    session_id    text        NOT NULL,
    revision      integer     NOT NULL CHECK (revision > 0),
    request_id    integer     NOT NULL CHECK (request_id > 0),
    turn_id       text,
    status        text        NOT NULL
                  CHECK (status IN ('parsed', 'unclear', 'extraction_failed')),
    requirements  jsonb       NOT NULL,
    ignored_changes jsonb     NOT NULL DEFAULT '[]'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, revision)
);

COMMENT ON TABLE pellier.shopping_requirements IS
    'One revision per storefront chat turn: the budget, stock, exclusions, '
    'required departments and preferences the shopper stated, with changes the '
    'shopper''s words did not support recorded in ignored_changes.';

COMMIT;
