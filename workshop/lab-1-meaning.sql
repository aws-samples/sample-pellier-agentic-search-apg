\set ON_ERROR_STOP on
\set QUIET on
\set VERBOSITY terse
\pset footer off
SET client_min_messages = warning;

-- Lab 1A: how far products sit from one product in meaning, in psql, before you
-- write the ranking into the app.
--
-- Every product in pellier.product_catalog carries a Cohere Embed v4 vector of
-- 1,024 numbers in its embedding column. pgvector's <=> operator is cosine
-- distance: 0 when two vectors point the same way, larger as their meanings drift
-- apart. The catalog's HNSW index is built with vector_cosine_ops, the operator
-- class for <=>. (A second, partial HNSW index over the photographed products uses
-- the same operator class; Lab 1's Go deeper measures it.)
--
-- The query vector is a product's own stored embedding, the kind
-- scripts/lab1_check.py --task 1A searches with, so that product sits at distance
-- 0 from itself. The eight products below are a fixed sample of nearby tableware
-- and more distant clothing and body care, listed in name order: which one a
-- search by meaning puts first, and which way its rows run, is Task 1A's to write.
-- No model is called and nothing changes.
--
-- Supplied and read-only. Run:
--   psql -f workshop/lab-1-meaning.sql

\set probe 'Stoneware Mugs, Set of 2'

\echo
\echo 'The query vector is the stored embedding of:' :'probe'
\echo
\echo '1. Eight products, in name order, with each one''s distance and similarity to it.'

WITH q AS (SELECT embedding AS emb FROM pellier.product_catalog WHERE name = :'probe')
SELECT p.name,
       round((p.embedding <=> q.emb)::numeric, 4) AS distance,
       round((1 - (p.embedding <=> q.emb))::numeric, 4) AS similarity
  FROM pellier.product_catalog p CROSS JOIN q
 WHERE p.name IN ('Ceramic Tumblers', 'Espresso Cups, Set of 4', 'Morning Run Shorts',
                  'Neroli Oil', 'Quilted Silk Vest', 'Stoneware Mugs, Set of 2',
                  'Stoneware Pour-Over Set', 'Wabi-Sabi Bowl')
 ORDER BY p.name;

\echo
\echo '2. The index the search can use, and the operator class it was built for.'

SELECT indexname AS index,
       substring(indexdef FROM 'USING (.*)$') AS definition
  FROM pg_indexes
 WHERE schemaname = 'pellier' AND indexname = 'product_catalog_embedding_hnsw';
