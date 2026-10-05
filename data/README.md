# Workshop data

## Catalog

`pellier_catalog.json` is the source of the 100-product catalog, product IDs 1
to 100. `embeddings_cache.json` stores the real Cohere Embed v4
1024-dimensional vector for each product, so
`scripts/seed_pellier_catalog.py --from-cache` seeds Aurora without calling
Bedrock.

`pellier_catalog_curated.csv` is a CSV export of the same 100 products with
their embeddings, written by `scripts/seed_pellier_catalog.py --csv-only`.
Columns: `productId`, `product_description`, `imgurl`, `producturl`, `stars`,
`reviews`, `price`, `category_id`, `isbestseller`, `boughtinlastmonth`,
`category_name`, `quantity`, `embedding`.

## Shoppers and prompts

`personas.json` holds the five shopper profiles the storefront shows (the
signed-out shopper, Anna, Marco, Theo and Jessica) and the customer each named
shopper maps to. `scenarios.json` holds each shopper's guided prompts in
order; the `required` ones are the lab prompts. Both are files, not tables
(`/api/personas` and `/api/scenarios` read them).
