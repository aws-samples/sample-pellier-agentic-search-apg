\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off
SET client_min_messages = warning;

-- Lab 1A: what ranking by meaning looks like, in psql, before you write it into the app.
--
-- Every product in pellier.product_catalog carries a Cohere Embed v4 vector of
-- 1,024 numbers in its embedding column. pgvector's <=> operator is cosine
-- distance: 0 when two vectors point the same way, larger as their meanings drift
-- apart. The catalog's HNSW index is built with vector_cosine_ops, the operator
-- class for <=>.
--
-- To know the right answer in advance, this worksheet searches with a product's own
-- stored embedding, the way scripts/lab1_check.py --task 1A does: that product sits at
-- distance 0 from itself, so ranked by meaning it must come back first. No model is
-- called and nothing changes.
--
-- Supplied and read-only. Run:
--   psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-1-meaning.sql

\set probe 'Stoneware Mugs, Set of 2'

\echo
\echo 'Searching with the stored embedding of:' :'probe'
\echo
\echo '1. Closest first: ORDER BY embedding <=> the query vector. Similarity is 1 minus the distance.'

WITH q AS (SELECT embedding AS emb FROM pellier.product_catalog WHERE name = :'probe')
SELECT row_number() OVER (ORDER BY p.embedding <=> q.emb) AS rank,
       p.name,
       round((p.embedding <=> q.emb)::numeric, 4) AS distance,
       round((1 - (p.embedding <=> q.emb))::numeric, 4) AS similarity
  FROM pellier.product_catalog p CROSS JOIN q
 WHERE p."imgUrl" IS NOT NULL
 ORDER BY p.embedding <=> q.emb
 LIMIT 5;

\echo
\echo '2. The same distance, the wrong way round: ORDER BY ... DESC puts the furthest meaning first.'

WITH q AS (SELECT embedding AS emb FROM pellier.product_catalog WHERE name = :'probe')
SELECT row_number() OVER (ORDER BY p.embedding <=> q.emb DESC) AS rank,
       p.name,
       round((p.embedding <=> q.emb)::numeric, 4) AS distance,
       round((1 - (p.embedding <=> q.emb))::numeric, 4) AS similarity
  FROM pellier.product_catalog p CROSS JOIN q
 WHERE p."imgUrl" IS NOT NULL
 ORDER BY p.embedding <=> q.emb DESC
 LIMIT 3;

\echo
\echo '3. The index the search can use, and the operator class it was built for.'

SELECT indexname AS index,
       substring(indexdef FROM 'USING (.*)$') AS definition
  FROM pg_indexes
 WHERE schemaname = 'pellier' AND tablename = 'product_catalog' AND indexdef LIKE '%hnsw%';
