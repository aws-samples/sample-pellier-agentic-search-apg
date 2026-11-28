\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off \pset border 2 \pset linestyle unicode \pset expanded off \pset format wrapped
\pset null NULL

-- Lab 2, Task 2B: what check_stock says about a piece Pellier does not carry.
--
-- Both callers answer check_stock with this one function: the Stock agent's
-- in-process tool and the Gateway Lambda both run
--   SELECT * FROM pellier.check_stock(<the name the shopper used>)
-- and pellier/backend/services/store_tools.py turns its rows into the tool's
-- answer. No row is not_found; several rows are the pieces to ask about; one row
-- is that piece's stock.
--
-- Without a test for the product, the function totals the stock of what matched
-- even when nothing did. An aggregate over no rows still returns one row: sum is
-- NULL, COALESCE makes it 0, and a piece Pellier does not carry reads as 0 in
-- stock. A missing product is a missing row, not a zero, so the function has to
-- test for the product before it aggregates. Write that test between the markers.
--
-- Run with:
--   psql -f workshop/lab-2-check-stock.sql
--
-- Everything below runs in one transaction. If every test passes, it commits and
-- your function is the live one. If any test fails, it rolls back and the live
-- function stays.

SET client_min_messages TO warning;
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';

CREATE OR REPLACE FUNCTION pellier.check_stock(product_query text)
RETURNS TABLE (product_id text, name text, brand text, color text, price numeric,
               total_units integer, warehouses jsonb)
LANGUAGE plpgsql STABLE
AS $check_stock$
#variable_conflict use_column
DECLARE
    matched text[];
    piece pellier.product_catalog%ROWTYPE;
BEGIN
    -- The pieces whose name holds every word asked for, best rated first, at most
    -- five. The shopper's %, _ and \ match only themselves.
    SELECT array_agg(hit."productId" ORDER BY hit.rating DESC, hit."productId")
      INTO matched
      FROM (SELECT p."productId", p.rating
              FROM pellier.product_catalog p
             WHERE regexp_replace(product_query, '[[:space:]]', '', 'g') <> ''
               AND NULLIF(btrim(p."imgUrl"), '') IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1
                     FROM regexp_split_to_table(lower(product_query), '[[:space:]]+') AS word
                    WHERE lower(p.name) NOT LIKE '%' || replace(replace(replace(word,
                              chr(92), chr(92) || chr(92)), '%', chr(92) || '%'),
                              '_', chr(92) || '_') || '%' ESCAPE chr(92))
             ORDER BY p.rating DESC, p."productId"
             LIMIT 5) AS hit;

    -- Several pieces match: one row each and no count, so the agent asks which.
    IF cardinality(matched) > 1 THEN
        RETURN QUERY
            SELECT p."productId", p.name, p.brand, p.color, p.price,
                   NULL::integer, NULL::jsonb
              FROM unnest(matched) WITH ORDINALITY AS m(id, ord)
              JOIN pellier.product_catalog p ON p."productId" = m.id
             ORDER BY m.ord;
        RETURN;
    END IF;

    SELECT * INTO piece FROM pellier.product_catalog p WHERE p."productId" = matched[1];

    -- === WORKSHOP - Stock check - not carried: START ===
    -- Task 2B: what should a piece Pellier does not carry return?
    IF NOT FOUND THEN
        RETURN;  -- no piece matched: no row, rather than a total of nothing
    END IF;
    -- === WORKSHOP - Stock check - not carried: END ===

    -- One piece: its units at each warehouse, and their total.
    RETURN QUERY
        SELECT piece."productId", piece.name, piece.brand, piece.color, piece.price,
               coalesce(sum(w.quantity), 0)::integer,
               coalesce(jsonb_agg(jsonb_build_object(
                            'warehouse_code', w.warehouse_code,
                            'warehouse_name', w.warehouse_name,
                            'city', w.city,
                            'ship_window_min', w.ship_window_min,
                            'ship_window_max', w.ship_window_max,
                            'quantity', w.quantity)
                        ORDER BY w.quantity DESC, w.warehouse_code), '[]'::jsonb)
          FROM pellier.warehouse_inventory w
         WHERE w.product_id = piece."productId";
END
$check_stock$;

-- Stamp the function with its source's sha256, so scripts/lab2_check.py can tell the
-- function you committed from the one the database shipped with.
SELECT 'Lab 2B function sha256 ' || hash AS stamp
  FROM (SELECT encode(sha256(convert_to(prosrc, 'UTF8')), 'hex') AS hash
          FROM pg_proc WHERE oid = 'pellier.check_stock(text)'::regprocedure) h
\gset
COMMENT ON FUNCTION pellier.check_stock(text) IS :'stamp';

-- The four cases. Each expected answer is read from the tables directly, by the function's
-- rules (every word, a photo); each observed answer is what your function returns.
CREATE TEMP TABLE lab_2_cases (ord integer, probe text, query text) ON COMMIT DROP;
INSERT INTO lab_2_cases VALUES
    (1, 'not carried', 'Velvet Opera Cape'),
    (2, 'several', 'Linen shirt'),
    (3, 'sold out', 'Quilted Silk Vest'),
    (4, 'in stock', 'Hadley Linen Shirt');

CREATE TEMP TABLE lab_2_probes (ord integer, probe text, expected text, observed text)
    ON COMMIT DROP;
INSERT INTO lab_2_probes
WITH named AS (
    SELECT c.ord, p."productId" AS id
      FROM lab_2_cases c
      JOIN pellier.product_catalog p
        ON NULLIF(btrim(p."imgUrl"), '') IS NOT NULL AND NOT EXISTS (SELECT 1
                         FROM regexp_split_to_table(lower(c.query), '[[:space:]]+') AS word
                        WHERE strpos(lower(p.name), word) = 0)
), tables AS (
    SELECT c.ord, count(n.id) AS pieces, min(n.id) AS one_id
      FROM lab_2_cases c LEFT JOIN named n ON n.ord = c.ord
     GROUP BY c.ord
), returned AS (
    SELECT c.ord, count(f.*) AS n_rows, count(DISTINCT f.product_id) AS n_pieces,
           bool_and(f.total_units IS NULL AND f.warehouses IS NULL) AS no_counts,
           bool_or(f.product_id IS NULL) AS no_product,
           min(f.total_units) AS units, (array_agg(f.warehouses))[1] AS warehouses
      FROM lab_2_cases c
      LEFT JOIN LATERAL pellier.check_stock(c.query) f ON true
     GROUP BY c.ord
)
SELECT c.ord, format('%s: %s', c.probe, c.query),
       CASE WHEN t.pieces = 0 THEN 'no row'
            WHEN t.pieces > 1 THEN least(t.pieces, 5) || ' rows, one per piece, no count'
            ELSE format('1 row: %s units; %s',
                        (SELECT coalesce(sum(w.quantity), 0) FROM pellier.warehouse_inventory w
                          WHERE w.product_id = t.one_id),
                        (SELECT coalesce(string_agg(w.warehouse_name || ' ' || w.quantity, ', '
                                                    ORDER BY w.ship_window_min, w.warehouse_name),
                                         'no warehouse rows')
                           FROM pellier.warehouse_inventory w WHERE w.product_id = t.one_id))
       END,
       CASE WHEN r.n_rows = 0 THEN 'no row'
            WHEN r.n_rows > 1 AND r.n_pieces = r.n_rows AND r.no_counts
                 THEN r.n_rows || ' rows, one per piece, no count'
            WHEN r.n_rows > 1 THEN r.n_rows || ' rows, not one per piece'
            WHEN r.no_product THEN format('1 row, %s units, no product',
                                          coalesce(r.units::text, 'no count'))
            ELSE format('1 row: %s units; %s', coalesce(r.units::text, 'no count'),
                        coalesce((SELECT string_agg((e ->> 'warehouse_name') || ' '
                                                    || (e ->> 'quantity'), ', '
                                                    ORDER BY (e ->> 'ship_window_min')::integer,
                                                             e ->> 'warehouse_name')
                                    FROM jsonb_array_elements(r.warehouses) AS e),
                                 'no warehouse rows'))
       END
  FROM lab_2_cases c JOIN tables t USING (ord) JOIN returned r USING (ord);

\echo 'Lab 2B: not carried is different from sold out'
\echo ''
-- One row per test. A test that passes shows the answer in a few words in both columns, so
-- the function's answer is in view; one that fails shows both answers whole, side by side.
SELECT probe AS "Test",
       CASE WHEN expected = observed THEN brief ELSE expected END AS "Should return",
       CASE WHEN expected = observed THEN brief ELSE observed END AS "Is now",
       CASE WHEN expected = observed THEN '✓' ELSE '✗' END AS "OK"
  FROM (SELECT *, regexp_replace(regexp_replace(expected, '^1 row: ([0-9]+ units); .*$', '\1'),
                                 '^([0-9]+ rows), .*$', '\1') AS brief
          FROM lab_2_probes) shown
 ORDER BY ord;
SELECT count(*) FILTER (WHERE expected = observed) AS matched, count(*) AS probes,
       coalesce(bool_or(expected <> observed) FILTER (WHERE ord > 1), false) AS others_differ
  FROM lab_2_probes
\gset lab_2_

SELECT :lab_2_matched = :lab_2_probes AS lab_2_passed \gset
\if :lab_2_passed
  COMMIT;
  \echo :lab_2_matched 'of' :lab_2_probes 'tests passed. Saved, your function is live.'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[32m' || true`
  \echo 'Lab 2B function check passed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  -- A catch-up (lab_run.py finish) runs the next step itself, so it asks for no Next.
  \if :{?quiet_next}
  \else
    \echo ''
    \echo 'Next  In the guide, read "Prove the fix".'
    \echo '      Then run: uv run scripts/lab2_check.py --task 2B'
  \endif
\else
  ROLLBACK;
  \echo :lab_2_matched 'of' :lab_2_probes 'tests passed. Your change was undone.'
  \echo 'The live function is unchanged.'
  \echo ''
  \echo 'Next  In Task 2B, build the fix for a product Pellier does not carry.'
  \if :lab_2_others_differ
    \echo '      Another test fails too. Compare its two answers above.'
  \else
    \echo '      A piece Pellier does not carry must return no row, not 0 units.'
  \endif
  \echo '      Then run: psql -f labs/02-ground/2B-check-stock.sql'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[31m' || true`
  \echo 'Lab 2B function check failed'
  \echo -n `[ -t 2 ] && [ -z "${NO_COLOR+x}" ] && printf '\033[0m' || true`
  DO $fail$ BEGIN RAISE EXCEPTION 'stopped on purpose; see Next'; END $fail$;
\endif
