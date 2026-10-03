# Workshop Data

## Catalog seed data

`pellier_catalog_curated.csv` is the stable 60-product story catalog: 10 signed-out baseline products, 10 curated products per named persona, 10 house pieces the client book owns, and 10 signature investment pieces. It intentionally does not carry embeddings inline.

`pellier_catalog.json` is the source of the 100-product catalog. `embeddings_cache.json` stores the real Cohere Embed v4 1024-dimensional vectors for those products. `scripts/seed_pellier_catalog.py --from-cache` loads them without calling Bedrock during bootstrap.

Columns for CSV exports: `productId`, `product_description`, `imgUrl`, `productURL`, `stars`, `reviews`, `price`, `category_id`, `isBestSeller`, `boughtInLastMonth`, `category_name`, `quantity`, `embedding`.
