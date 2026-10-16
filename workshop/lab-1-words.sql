\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off
SET client_min_messages = warning;

-- Lab 1A: what Anna's first sentence finds by its words alone.
--
-- Pellier's word search (the full-text branch, store_tools.fts_branch_sql) turns
-- the shopper's words into one OR query: a product matches if its name, brand,
-- department, colour, tags or description contain any of them, and ts_rank_cd
-- ranks the matches by how many it contains and how close together. This is the
-- query store_tools.or_tsquery builds from the sentence Task 1A sends:
--
--   "A housewarming gift for a friend who loves slow mornings."
--
-- Nothing here depends on a model: the words, the catalog and PostgreSQL's
-- English dictionary decide every row, so the output is the same on every
-- deployment. The search keeps the top 20 word matches, and the reranker only
-- sees the top 15 of what the search fused.
--
-- Supplied and read-only. Run:
--   psql -f workshop/lab-1-words.sql

\set words 'housewarming | gift | friend | slow | mornings'

\echo
\echo 'Her sentence as one word query:' :'words'
\echo
\echo '1. The ten best word matches. "matched on" lists her words each product contains.'

WITH q AS (SELECT to_tsquery('english', :'words') AS ts_q),
words AS (SELECT word FROM unnest(string_to_array(replace(:'words', ' ', ''), '|')) AS word
            WHERE numnode(to_tsquery('english', word)) > 0)
SELECT row_number() OVER (ORDER BY ts_rank_cd(p.description_tsv, q.ts_q) DESC, p.name) AS rank,
       p.name,
       (SELECT string_agg(w.word, ', ' ORDER BY w.word) FROM words w
         WHERE p.description_tsv @@ to_tsquery('english', w.word)) AS "matched on"
  FROM pellier.product_catalog p CROSS JOIN q
 WHERE p."imgUrl" IS NOT NULL AND p.description_tsv @@ q.ts_q
 ORDER BY rank
 LIMIT 10;

\echo
\echo '2. Where three products that fit a friend who loves slow mornings rank by words.'
\echo '   Equal scores share a rank. The reranker scores only the top 15 of the fused list.'

WITH q AS (SELECT to_tsquery('english', :'words') AS ts_q),
words AS (SELECT word FROM unnest(string_to_array(replace(:'words', ' ', ''), '|')) AS word
            WHERE numnode(to_tsquery('english', word)) > 0),
matches AS (
  SELECT p.name, p.description_tsv,
         rank() OVER (ORDER BY ts_rank_cd(p.description_tsv, q.ts_q) DESC) AS word_rank
    FROM pellier.product_catalog p CROSS JOIN q
   WHERE p."imgUrl" IS NOT NULL AND p.description_tsv @@ q.ts_q
)
SELECT f.name,
       coalesce(e.word_rank::text, 'no match') AS "word rank",
       (SELECT count(*) FROM matches) AS "of matches",
       coalesce((SELECT string_agg(w.word, ', ' ORDER BY w.word) FROM words w
                  WHERE e.description_tsv @@ to_tsquery('english', w.word)), '-') AS "matched on"
  FROM (VALUES ('Stoneware Mugs, Set of 2'), ('Stoneware Pour-Over Set'),
               ('Ceramic Tumblers')) AS f(name)
  LEFT JOIN matches e ON e.name = f.name
 ORDER BY e.word_rank NULLS LAST;
