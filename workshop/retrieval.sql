-- Lab 1: complete only the two marked blocks.
-- The workshop client supplies embedding, terms, and max_price as psql variables.
-- A stored candle vector is used only when a live query embedding is unavailable.
WITH query_vector AS (
    SELECT COALESCE(
        NULLIF(:'embedding', '')::vector,
        (SELECT embedding FROM pellier.product_catalog WHERE "productId" = '4')
    ) AS embedding
),
eligible AS (
    SELECT *
    FROM pellier.product_catalog
    WHERE embedding IS NOT NULL
      AND NOT (tags ? 'archive')
      -- === WORKSHOP: eligibility: START ===
      -- WORKSHOP_RETRIEVAL_FILTER_STUB
      -- Require price at or below :'max_price'::numeric and quantity above zero.
      AND TRUE
      -- === WORKSHOP: eligibility: END ===
),
vector_candidates AS (
    SELECT "productId" AS product_id,
           row_number() OVER (
               ORDER BY embedding <=> (SELECT embedding FROM query_vector),
                        "productId"
           ) AS rank
    FROM eligible
    ORDER BY embedding <=> (SELECT embedding FROM query_vector), "productId"
    LIMIT 20
),
keyword_candidates AS (
    SELECT "productId" AS product_id,
           row_number() OVER (
               ORDER BY ts_rank_cd(description_tsv, to_tsquery('english', :'terms')) DESC,
                        "productId"
           ) AS rank
    FROM eligible
    WHERE description_tsv @@ to_tsquery('english', :'terms')
    ORDER BY ts_rank_cd(description_tsv, to_tsquery('english', :'terms')) DESC,
             "productId"
    LIMIT 20
),
ranked AS (
    SELECT product_id, rank, 'vector' AS branch FROM vector_candidates
    UNION ALL
    SELECT product_id, rank, 'keyword' AS branch FROM keyword_candidates
),
fused AS (
    SELECT product_id,
           min(rank) FILTER (WHERE branch = 'vector') AS vector_rank,
           min(rank) FILTER (WHERE branch = 'keyword') AS keyword_rank,
           -- === WORKSHOP: rank fusion: START ===
           -- WORKSHOP_RETRIEVAL_RANK_STUB
           -- Sum 1 / (60 + rank) for each branch. Use decimal division.
           0.0::numeric AS rrf_score
           -- === WORKSHOP: rank fusion: END ===
    FROM ranked
    GROUP BY product_id
),
results AS (
    SELECT c."productId" AS "productId", c.name, c.price, c.quantity,
           f.vector_rank AS "vectorRank", f.keyword_rank AS "keywordRank",
           f.rrf_score AS "rrfScore"
    FROM fused f
    JOIN pellier.product_catalog c ON c."productId" = f.product_id
    ORDER BY f.rrf_score DESC, c."productId"
    LIMIT 5
)
SELECT json_build_object(
    'eligibleCount', (
        SELECT count(*) FROM pellier.product_catalog
        WHERE embedding IS NOT NULL AND NOT (tags ? 'archive')
          AND price <= :'max_price'::numeric AND quantity > 0
    ),
    'rows', COALESCE(
        (SELECT json_agg(r ORDER BY r."rrfScore" DESC, r."productId") FROM results r),
        '[]'::json
    )
);
