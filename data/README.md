# Workshop data

## Catalog

`pellier_catalog.json` is the authoritative synthetic catalog: 50,000 products,
IDs 1 through 50,000, across eight departments. Each row has its own name,
description, price, materials, tags and stock. `catalog_manifest.json` records
its SHA-256, counts, authorship and stock distribution.

The original 100 products keep their IDs and lab facts. IDs 101 through 1,000
add 90 designs, each in five colors and two sizes. IDs 1,001 through 50,000 are
separately authored products, checked for duplicate names/descriptions, known
materials, bounded copy and conflicts with the lab's named-product examples.
The data is fictional workshop merchandise; it is not a real retailer's inventory.

Photography covers the first 1,000 products. The 900 additions use 450 photographs:
a photograph belongs to one design and color and serves its two size options.
Together with the original 100 photos, that is 550 distinct photographs:
100 original products + (450 new design/color photos x 2 sizes) = 1,000 products.
The second size uses the same product photograph; it is not a missing-image entry.
`catalog_photography.json` records those product IDs and the exact generation
prompts. Responsive WebP and AVIF assets live in
`pellier/frontend/public/products/`. Products after ID 1,000 have `image: null`;
the seeder publishes an empty image URL. These 49,000 rows remain in the real
PostgreSQL tables and vector/full-text indexes for scale exercises, but are
excluded from participant-facing browsing, search, stock lookup, comparison,
product links and related products. The visible catalog contains 1,000 products.
The 49,000 background rows are labeled **Scale dataset records**: **Text and embeddings only;
product photography is not part of this dataset.** An absent photograph is
intentional for this subset. A missing asset for one of the photographed 1,000
is still a defect and must fail the asset checks.
Visibility is a SQL eligibility predicate applied before ranking and pagination.
Vector search reads it through a partial HNSW index that holds only the
photographed rows (`product_catalog_visible_hnsw`), so a department or price
limit is not left with a short list by the 49,000 rows it cannot show.
Vector distances, full-text ranks, RRF and reranking are computed from real data;
the UI does not manufacture results or discard hidden candidates after ranking.

To validate or rederive a delivery of named PNG masters, use
`python scripts/import_product_photos.py --source <folder> --only-supplied --check`,
then remove `--check` to write the derivatives. Omit `--only-supplied` when the
folder should contain all 550 masters. The importer validates image ownership
against the catalog and photography manifest, encodes shared size photos once,
and leaves catalog content unchanged.

## Embeddings and loading

`embeddings_cache.json` is a manifest for the real Cohere Embed v4,
1,024-dimensional document embeddings in `embeddings/*.f32.gz`. Each compressed
shard contains little-endian float32 vectors in its manifest ID order. Float32
matches PostgreSQL's `vector` storage precision. The manifest binds each vector
to the SHA-256 of its exact search text and each shard to a checksum. Loading
rejects changed text, missing vectors, duplicate IDs, corrupt shards, wrong
models/dimensions and nonfinite or zero vectors.

Seed from the committed cache; no catalog-embedding Bedrock calls are made:

```bash
python scripts/seed_pellier_catalog.py --from-cache
```

Cache loading is also the default when no mode is supplied. A missing or stale
cache stops setup; it never triggers paid embedding generation as a fallback.
Only the explicit maintainer command `--cache-only` generates document vectors.

The loader uses PostgreSQL COPY into a temporary table followed by a transactional
merge. On an empty catalog, it builds both HNSW indexes after the bulk load, using
512 MB of session-local index-build memory. An existing catalog keeps its indexes
throughout the merge, and a row whose values are unchanged is not rewritten. The ordinary setup then creates three warehouse rows per product,
150,000 in total, with quantities summing to each catalog row's stock. Existing
named lab inventory exceptions and the 60 editorial placements are preserved.

Maintainers can regenerate the cache using authoring credentials:

```bash
python scripts/seed_pellier_catalog.py --cache-only
```

This makes paid Bedrock requests in batches of at most 96 texts. Commit the
manifest and every shard it names together. CSV is an optional local export,
ignored by Git because it duplicates the catalog and expands the vectors:

```bash
python scripts/seed_pellier_catalog.py --from-cache --csv-only
```

Do not substitute the historical 100-product CSV for the catalog. It is no
longer shipped. The previous 50K long-tail benchmark used a separate corpus;
its recorded latency and relevance results do not measure this catalog. The
original golden retrieval judgments cover the original products only and are
not exhaustive labels for the expanded catalog. The supplied read-only
`workshop/lab-1-index.sql` now measures this catalog directly: exact search and
HNSW plans, execution time, buffer activity, result counts and recall@20. Run it
with `psql -f workshop/lab-1-index.sql` for the full dataset, or add
`-v storefront_only=on` for the photographed subset: through the 50,000-row index,
then through the photographed-only partial index.

## Shoppers and prompts

`personas.json` holds the five shopper profiles the storefront shows (the
signed-out shopper, Anna, Marco, Theo and Jessica) and the customer each named
shopper maps to. `scenarios.json` holds each shopper's guided prompts in
order; the `required` ones are the lab prompts. Both are files, not tables
(`/api/personas` and `/api/scenarios` read them).
