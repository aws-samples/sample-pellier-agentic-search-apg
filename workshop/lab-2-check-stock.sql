\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off
\pset null NULL

-- Lab 2, Task 2B: what check_stock says about a piece Pellier does not carry.
--
-- Both rails answer check_stock with this one function: the Stock agent's
-- in-process tool and the Gateway Lambda both run
--   SELECT * FROM pellier.check_stock(<the name the shopper used>)
-- and pellier/backend/services/store_tools.py turns its rows into the tool's
-- answer. No row is not_found; several rows are the pieces to ask about; one row
-- is that piece's stock.
--
-- As shipped, the function totals the stock of what matched without testing that
-- anything did. An aggregate over no rows still returns one row: sum(quantity) is
-- NULL, COALESCE makes it 0, and a piece Pellier does not carry reads as 0 in
-- stock. A missing product is a missing row, not a zero, so the function has to
-- test for the product before it aggregates. Write that test between the markers.
--
-- Run with:
--   psql -f workshop/lab-2-check-stock.sql
--
-- Everything below runs in one transaction. If every probe matches, it commits and
-- your function is the live one. If any probe differs, it rolls back and the live
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
SELECT 'Lab 2B function sha256 ' || hash AS stamp, left(hash, 12) AS stamp_short
  FROM (SELECT encode(sha256(convert_to(prosrc, 'UTF8')), 'hex') AS hash
          FROM pg_proc WHERE oid = 'pellier.check_stock(text)'::regprocedure) h
\gset
COMMENT ON FUNCTION pellier.check_stock(text) IS :'stamp';

-- The four cases. Each expected answer is read from the tables directly, with the
-- same every-word rule; each observed answer is what your function returns.
CREATE TEMP TABLE lab_2_cases (ord integer, probe text, query text) ON COMMIT DROP;
INSERT INTO lab_2_cases VALUES
    (1, 'not carried', 'Velvet Opera Cape'),
    (2, 'several', 'Linen shirt'),
    (3, 'sold out', 'Quilted Silk Vest'),
    (4, 'in stock', 'Hadley Linen Shirt');

CREATE TEMP TABLE lab_2_probes (ord integer, probe text, expected text, observed text,
                                 source text) ON COMMIT DROP;
INSERT INTO lab_2_probes
WITH named AS (
    SELECT c.ord, p."productId" AS id
      FROM lab_2_cases c
      JOIN pellier.product_catalog p
        ON NOT EXISTS (SELECT 1
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
SELECT c.ord, format('%s: "%s"', c.probe, c.query),
       CASE WHEN t.pieces = 0 THEN 'no row'
            WHEN t.pieces > 1 THEN least(t.pieces, 5) || ' rows, one per piece, no count'
            ELSE format('1 row: %s units; %s',
                        (SELECT coalesce(sum(w.quantity), 0) FROM pellier.warehouse_inventory w
                          WHERE w.product_id = t.one_id),
                        (SELECT coalesce(string_agg(w.warehouse_code || ' ' || w.quantity, ', '
                                                    ORDER BY w.warehouse_code),
                                         'no warehouse rows')
                           FROM pellier.warehouse_inventory w WHERE w.product_id = t.one_id))
       END,
       CASE WHEN r.n_rows = 0 THEN 'no row'
            WHEN r.n_rows > 1 AND r.n_pieces = r.n_rows AND r.no_counts
                 THEN r.n_rows || ' rows, one per piece, no count'
            WHEN r.n_rows > 1 THEN r.n_rows || ' rows, not one per piece'
            ELSE format('1 row: %s units; %s%s', coalesce(r.units::text, 'no count'),
                        coalesce((SELECT string_agg((e ->> 'warehouse_code') || ' '
                                                    || (e ->> 'quantity'), ', '
                                                    ORDER BY e ->> 'warehouse_code')
                                    FROM jsonb_array_elements(r.warehouses) AS e),
                                 'no warehouse rows'),
                        CASE WHEN r.no_product THEN ' (no product)' ELSE '' END)
       END,
       format('pellier.check_stock(''%s'')', c.query)
  FROM lab_2_cases c JOIN tables t USING (ord) JOIN returned r USING (ord);

\echo 'Lab 2B: check_stock, probed'
\echo 'Evidence  pellier.check_stock, rewritten inside this transaction'
\echo ''
\echo 'The aggregate for Marco''s Velvet Opera Cape, a piece Pellier does not carry:'
SELECT count(w.*) AS warehouse_rows, sum(w.quantity) AS "sum(quantity)",
       coalesce(sum(w.quantity), 0) AS "coalesce(sum(quantity), 0)"
  FROM pellier.warehouse_inventory w
 WHERE w.product_id IN (SELECT p."productId" FROM pellier.product_catalog p
                         WHERE strpos(lower(p.name), 'velvet') > 0
                           AND strpos(lower(p.name), 'opera') > 0
                           AND strpos(lower(p.name), 'cape') > 0);
-- One block per probe: the verdict and the probe, then what was expected, what was
-- observed and where it came from.
\pset tuples_only on
\pset format unaligned
SELECT format(E'%s  %s\n         expected  %s\n         observed  %s\n         source    %s\n',
              CASE WHEN expected = observed THEN 'matches' ELSE 'differs' END, probe,
              expected, observed, source)
  FROM lab_2_probes ORDER BY ord;
\pset format aligned
\pset tuples_only off
SELECT count(*) FILTER (WHERE expected = observed) AS matched, count(*) AS probes
  FROM lab_2_probes
\gset lab_2_

\echo 'Expected  every probe matches; then the transaction commits and your function is live'
SELECT :lab_2_matched = :lab_2_probes AS lab_2_passed \gset
\if :lab_2_passed
  COMMIT;
  \echo 'Observed ' :lab_2_matched 'of' :lab_2_probes 'probes match; committed, your function is live'
  \echo 'Deployed  pellier.check_stock, sha256' :stamp_short
  \echo 'Lab 2B function check passed'
\else
  ROLLBACK;
  \echo 'Observed ' :lab_2_matched 'of' :lab_2_probes 'probes match; rolled back, the live function is unchanged'
  \echo 'Next      what should a piece Pellier does not carry return? Read the aggregate above: over'
  \echo '          no rows it still returns one row, and COALESCE turns its NULL sum into 0.'
  \echo 'Lab 2B function check failed'
  DO $fail$ BEGIN RAISE EXCEPTION 'Lab 2B function check failed; see the lines above'; END $fail$;
\endif
