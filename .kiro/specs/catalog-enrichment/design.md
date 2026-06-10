# Technical Design Document

## Overview

This design describes the catalog enrichment pipeline for Pellier — a set of offline Python scripts and SQL that transform the existing 1,008-product catalog into a curated ~444-product catalog optimized for workshop demos. The pipeline runs once before the workshop, producing a CSV that the existing database load script consumes. Zero changes to the application runtime code.

## Architecture

### System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                    Enrichment Pipeline (offline, run once)       │
│                                                                 │
│  ┌──────────────┐    ┌─────────────────┐    ┌───────────────┐  │
│  │ trim-catalog │───▶│ add-new-products │───▶│ enrich-descs  │  │
│  │    .py       │    │      .py         │    │     .py       │  │
│  └──────┬───────┘    └────────┬─────────┘    └──────┬────────┘  │
│         │                     │                      │          │
│    reads from            calls APIs             calls API       │
│         │              ┌──────┴──────┐               │          │
│         ▼              ▼             ▼               ▼          │
│  ┌────────────┐  ┌──────────┐ ┌──────────┐  ┌────────────────┐ │
│  │ source CSV │  │ Unsplash │ │ Bedrock  │  │ Bedrock        │ │
│  │ (1,008)    │  │ API      │ │ Embed v4 │  │ Embed v4       │ │
│  └────────────┘  └──────────┘ └──────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ produces
                    ┌───────────────────┐
                    │ enriched CSV      │
                    │ (~444 products)   │
                    └────────┬──────────┘
                             │ loaded by
                             ▼
              ┌──────────────────────────────┐
              │ load-database-fast.sh         │
              │  ├─ COPY CSV → temp table    │
              │  ├─ INSERT INTO product_catalog│
              │  ├─ CREATE indexes            │
              │  ├─ \i post-load-adjustments  │
              │  └─ VACUUM ANALYZE            │
              └──────────────┬───────────────┘
                             ▼
              ┌──────────────────────────────┐
              │ Aurora PostgreSQL + pgvector  │
              │ pellier schema    │
              └──────────────────────────────┘
```

### Data Flow

```
data/product-catalog-cohere-v4.csv (1,008 products)
        │
        ▼  scripts/trim-catalog.py
data/product-catalog-trimmed.csv (431 products)
        │
        ▼  scripts/add-new-products.py
data/product-catalog-trimmed-added.csv (444 products)
        │
        ▼  scripts/enrich-descriptions.py
data/product-catalog-enriched.csv (444 products, ~75 re-embedded)
        │
        ▼  scripts/load-database-fast.sh
Aurora PostgreSQL (444 products loaded)
        │
        ▼  scripts/post-load-adjustments.sql (invoked by load script)
Aurora PostgreSQL (stars + inventory redistributed)
```

## Detailed Component Design

### Component 1: Trim Script (`scripts/trim-catalog.py`)

Standalone Python script. No API calls. Reads the source CSV, scores unlocked products, keeps the best per category.

#### Dependencies

- `pandas` (already in project environment)

#### Constants

```python
DEMO_CRITICAL = {
    'Laptops', 'Smartphones', 'Mobile Accessories', 'Mens Shoes',
    'Womens Shoes', 'Beauty', 'Skin Care', 'Kitchen Accessories',
    'Sports Accessories', 'Mens Watches', 'Womens Watches'
}  # 11 categories → 25 products each

# 13 Supporting categories → 12 products each

LOCKED_IDS = {
    'PLAPT0001', 'PLAPT0016', 'PLAPT0007', 'PLAPT0026', 'PLAPT0033',
    'PLAPT0010', 'PSMRT0001', 'PSMRT0009', 'PSMRT0039', 'PMOBI0002',
    'PMOBI0004', 'PKITC0010', 'PKITC0005', 'PSPRT0022', 'PSPRT0027',
    'PMSHO0011', 'PMSHO0016', 'PMSHO0017', 'PMSHO0018', 'PMSHO0021',
    'PMSHO0036', 'PWSHO0019', 'PWSHO0009', 'PWSHO0022', 'PWSHO0028',
    'PSUNG0007', 'PMWAT0001', 'PWBAG0001', 'PWBAG0002'
}  # 29 locked products
```

#### Scoring Algorithm

For each category, locked products are kept unconditionally. Remaining slots filled by scoring unlocked products:

```
score = 0.4 × (reviews / max_reviews_in_category)
      + 0.3 × min(description_length / 200, 1.0)
      + 0.2 × (1.0 if isBestSeller else 0.0)
      + 0.1 × price_diversity
```

Price diversity uses inverse percentile rank — products at price extremes (cheapest, most expensive) score higher than mid-range to preserve price spread within each category.

#### I/O

- Input: `data/product-catalog-cohere-v4.csv`
- Output: `data/product-catalog-trimmed.csv`
- All original CSV columns preserved including embedding column
- Expected output: exactly 431 rows

#### Validation

Script prints summary: total before/after, per-category counts, locked product verification.

---

### Component 2: Add New Products Script (`scripts/add-new-products.py`)

Creates 13 new products (headphones, drinkware, gift sets), fetches Unsplash images, generates Cohere Embed v4 embeddings, and appends them to the trimmed CSV.

#### Dependencies

- `pandas`, `boto3`, `requests` (for Unsplash API)
- Environment variables: `AWS_REGION`, `UNSPLASH_ACCESS_KEY`

#### New Product Data

All 13 products are hardcoded as a list of dicts in the script. Each entry contains: productId, product_description, price, stars, reviews, quantity, category_name, category_id, isBestSeller, boughtInLastMonth, and an Unsplash search query.

Headphones (Mobile Accessories, category_id from source CSV):

| productId | Name                     | Price  | Stars | Reviews | Qty | Unsplash Query                    |
| --------- | ------------------------ | ------ | ----- | ------- | --- | --------------------------------- |
| PMOBI0043 | Sony WH-1000XM5          | 348.00 | 4.8   | 5421    | 312 | sony headphones wireless over ear |
| PMOBI0044 | Apple AirPods Pro 2      | 249.00 | 4.7   | 8932    | 8   | airpods pro white case            |
| PMOBI0045 | JBL Tune 510BT           | 29.95  | 4.4   | 3241    | 445 | blue wireless headphones flat lay |
| PMOBI0046 | Samsung Galaxy Buds3 Pro | 229.99 | 4.6   | 2876    | 6   | wireless earbuds charging case    |
| PMOBI0047 | Beats Solo 4             | 199.99 | 4.5   | 4102    | 203 | beats headphones red              |
| PMOBI0048 | Anker Soundcore Q20+     | 49.99  | 4.4   | 6543    | 538 | black over ear headphones minimal |

Drinkware (Sports Accessories):

| productId | Name                   | Price | Stars | Reviews | Qty | Unsplash Query                   |
| --------- | ---------------------- | ----- | ----- | ------- | --- | -------------------------------- |
| PSPRT0043 | YETI Rambler 26oz      | 40.00 | 4.8   | 7891    | 267 | yeti water bottle outdoor        |
| PSPRT0044 | Stanley Quencher 40oz  | 35.00 | 4.7   | 12453   | 4   | stanley tumbler cup holder       |
| PSPRT0045 | Owala FreeSip 24oz     | 27.99 | 4.6   | 9234    | 389 | colorful water bottle stainless  |
| PSPRT0046 | Corkcicle Canteen 16oz | 32.95 | 4.5   | 3456    | 156 | insulated canteen bottle minimal |

Gift Sets (various categories):

| productId | Name                     | Price | Stars | Reviews | Qty | Category            | Unsplash Query                  |
| --------- | ------------------------ | ----- | ----- | ------- | --- | ------------------- | ------------------------------- |
| PBEAU0043 | Burt's Bees Gift Set     | 14.99 | 4.7   | 5621    | 711 | Beauty              | skincare gift set box           |
| PKITC0043 | Lodge Cast Iron Gift Set | 79.99 | 4.8   | 4321    | 0   | Kitchen Accessories | cast iron skillet cooking       |
| PSKCA0043 | CeraVe Skincare Gift Set | 34.99 | 4.6   | 3892    | 423 | Skin Care           | skincare products minimal white |

#### Unsplash Integration

```python
def fetch_unsplash_image(query: str, access_key: str) -> str:
    """Fetch one image URL from Unsplash search API."""
    url = "https://api.unsplash.com/search/photos"
    params = {"query": query, "per_page": 1, "orientation": "squarish"}
    headers = {"Authorization": f"Client-ID {access_key}"}

    response = requests.get(url, params=params, headers=headers, timeout=10)
    if response.status_code == 200:
        results = response.json().get("results", [])
        if results:
            raw_url = results[0]["urls"]["raw"]
            return f"{raw_url}?w=400&q=80&fit=crop"  # match existing catalog style

    # Fallback placeholder
    logger.warning(f"Unsplash failed for '{query}', using placeholder")
    return "https://via.placeholder.com/400x400?text=Product+Image"
```

Total Unsplash calls: 13 (well within 50/hour free-tier limit). Sequential calls, no parallelism needed.

#### Embedding Generation

Uses the same Bedrock API pattern as `scripts/generate_and_store_embeddings.py`:

```python
def generate_embedding(text: str) -> list:
    """Generate 1024-dim embedding via Cohere Embed v4."""
    bedrock = boto3.client('bedrock-runtime', region_name=os.getenv('AWS_REGION', 'us-east-1'))
    response = bedrock.invoke_model(
        modelId='us.cohere.embed-v4:0',
        contentType='application/json',
        accept='*/*',
        body=json.dumps({
            'texts': [text],
            'input_type': 'search_document',
            'embedding_types': ['float'],
            'output_dimension': 1024,
        })
    )
    body = json.loads(response['body'].read())
    return body['embeddings']['float'][0]
```

Key: uses `input_type: 'search_document'` (not `search_query`) since these are product descriptions being indexed. This matches the existing `generate_and_store_embeddings.py` and the runtime `EmbeddingService.embed_document()`.

#### Category ID Resolution

The script reads the trimmed CSV to extract the `category_id` for each category_name, ensuring new products use the correct category_id values from the existing catalog.

#### I/O

- Input: `data/product-catalog-trimmed.csv`
- Output: `data/product-catalog-trimmed-added.csv`
- Expected output: 444 rows (431 + 13)

---

### Component 3: Enrich Descriptions Script (`scripts/enrich-descriptions.py`)

Modifies existing product descriptions with color, material, and clearance attributes. Re-embeds only modified products.

#### Dependencies

- `pandas`, `boto3`
- Environment variable: `AWS_REGION`

#### Color Enrichment

Hardcoded `COLOR_MAP` dict mapping productId → color string. Applied as suffix: `" Available {color}."` appended to existing description.

```python
COLOR_MAP = {
    # Mens Shoes (8 products)
    'PMSHO0011': 'in Black',
    'PMSHO0016': 'in Navy Blue',
    'PMSHO0017': 'in Grey',
    'PMSHO0018': 'in White',
    'PMSHO0021': 'in Orange',
    'PMSHO0024': 'in All Black',
    'PMSHO0031': 'in Core Black',
    'PMSHO0036': 'in Charcoal',
    # Womens Shoes (6 products)
    'PWSHO0010': 'in Grey',
    'PWSHO0019': 'in Navy',
    'PWSHO0022': 'in Black',
    'PWSHO0028': 'in Blue',
    'PWSHO0032': 'in Lavender',
    'PWSHO0039': 'in All White',
    # Womens Bags (5 products)
    'PWBAG0001': 'in Black Leather',
    'PWBAG0002': 'in Brown Leather',
    'PWBAG0004': 'in Signature Canvas',
    'PWBAG0006': 'in Tan Suede',
    'PWBAG0010': 'in Navy Nylon',
    # Mens Shirts (4 products)
    'PMSHR0001': 'in White',
    'PMSHR0003': 'in Light Blue',
    'PMSHR0005': 'in Navy Stripe',
    'PMSHR0008': 'in Charcoal',
    # Sunglasses (4 products)
    'PSUNG0001': 'in Matte Black',
    'PSUNG0003': 'in Tortoise',
    'PSUNG0007': 'in Black',
    'PSUNG0010': 'in Gold',
    # Womens Dresses (4 products)
    'PWDRS0001': 'in Black',
    'PWDRS0003': 'in Floral Print',
    'PWDRS0005': 'in Navy',
    'PWDRS0008': 'in Burgundy',
    # Tops (4 products)
    'PTOPS0001': 'in White',
    'PTOPS0003': 'in Grey Heather',
    'PTOPS0005': 'in Black',
    'PTOPS0008': 'in Olive',
}
# Total: 39 products with color enrichment
```

If a productId from COLOR_MAP is not found in the trimmed-added CSV (removed during trim), the script logs a warning and skips it.

#### Material Enrichment

Hardcoded `MATERIAL_MAP` dict. Applied as suffix appended to description.

```python
MATERIAL_MAP = {
    'PWBAG0008': ' — crafted from premium full-grain leather',
    'PWBAG0012': ' — made with recycled nylon fabric',
    'PFURN0001': ' — solid walnut wood frame',
    'PFURN0005': ' — Italian leather upholstery',
    'PKITC0015': ' — forged from Japanese VG-10 stainless steel',
}
# Total: 5 products with material enrichment
```

Same skip-and-warn behavior for missing productIds.

Note: Some products (e.g., PWBAG0001, PWBAG0002) appear in both COLOR_MAP and could theoretically appear in MATERIAL_MAP. The script applies color first, then material, so both suffixes accumulate. In practice, the current maps have no overlap between COLOR_MAP and MATERIAL_MAP productIds.

#### Clearance Enrichment

The script selects ~15 products for clearance tagging using these criteria:

1. Must have quantity > 100 (well-stocked)
2. Must NOT be a locked product
3. Spread across multiple categories for variety
4. Prefer products with mid-range prices (clearance on cheap items isn't interesting)

For each clearance product:

- Prefix description with `"CLEARANCE — "`
- Multiply price by 0.4 (60% reduction)

The clearance selection is deterministic: the script sorts eligible products by category then productId and picks the first ~15 that meet criteria, ensuring consistent results across runs.

#### Re-embedding

All products whose descriptions were modified (color + material + clearance) get new embeddings. Uses the same `generate_embedding()` function as Component 2.

Estimated re-embedding calls: ~60 (39 color + 5 material + ~15 clearance, minus any overlap with trimmed products ≈ 55-60 actual calls). Combined with Component 2's 13 calls, total is ~73-75 Bedrock API calls.

#### I/O

- Input: `data/product-catalog-trimmed-added.csv`
- Output: `data/product-catalog-enriched.csv`
- Expected output: 444 rows (same count, ~60 descriptions modified)

---

### Component 4: Post-Load SQL (`scripts/post-load-adjustments.sql`)

Pure SQL executed after CSV import. Redistributes star ratings and inventory quantities to create realistic distributions for demo purposes. No API calls, no re-embedding (stars and quantity are not part of the embedding vector).

#### Star Rating Redistribution

Uses a CTE with `ROW_NUMBER()` ordered by random seed for reproducibility, then assigns star ratings by percentile bucket:

```sql
WITH ranked AS (
    SELECT "productId",
           ROW_NUMBER() OVER (ORDER BY md5("productId")) as rn,
           COUNT(*) OVER () as total
    FROM pellier.product_catalog
    WHERE "productId" NOT IN (
        -- 29 locked products preserved at original ratings
        'PLAPT0001','PLAPT0016','PLAPT0007','PLAPT0026','PLAPT0033','PLAPT0010',
        'PSMRT0001','PSMRT0009','PSMRT0039','PMOBI0002','PMOBI0004',
        'PKITC0010','PKITC0005','PSPRT0022','PSPRT0027',
        'PMSHO0011','PMSHO0016','PMSHO0017','PMSHO0018','PMSHO0021','PMSHO0036',
        'PWSHO0019','PWSHO0009','PWSHO0022','PWSHO0028',
        'PSUNG0007','PMWAT0001','PWBAG0001','PWBAG0002',
        -- 13 new products preserved at specified ratings
        'PMOBI0043','PMOBI0044','PMOBI0045','PMOBI0046','PMOBI0047','PMOBI0048',
        'PSPRT0043','PSPRT0044','PSPRT0045','PSPRT0046',
        'PBEAU0043','PKITC0043','PSKCA0043'
    )
)
UPDATE pellier.product_catalog pc
SET stars = CASE
    WHEN r.rn <= r.total * 0.03 THEN 2.0 + (random() * 0.9)::numeric(2,1)   -- 3%: 2.0-2.9
    WHEN r.rn <= r.total * 0.10 THEN 3.0 + (random() * 0.4)::numeric(2,1)   -- 7%: 3.0-3.4
    WHEN r.rn <= r.total * 0.25 THEN 3.5 + (random() * 0.4)::numeric(2,1)   -- 15%: 3.5-3.9
    WHEN r.rn <= r.total * 0.60 THEN 4.0 + (random() * 0.4)::numeric(2,1)   -- 35%: 4.0-4.4
    ELSE                              4.5 + (random() * 0.5)::numeric(2,1)   -- 40%: 4.5-5.0
END
FROM ranked r
WHERE pc."productId" = r."productId";
```

Target distribution (~444 products, ~402 unlocked):

- 40% at 4.5–5.0★ (~180 products) — premium tier
- 35% at 4.0–4.4★ (~155 products) — good tier
- 15% at 3.5–3.9★ (~65 products) — passes `WHERE stars >= 3.5` filter
- 7% at 3.0–3.4★ (~30 products) — below filter threshold
- 3% at 2.0–2.9★ (~16 products) — clearly filtered out

Teaching impact: ~46 products fall below the 3.5★ threshold used in `_vector_search()`, demonstrating the value of quality filtering.

#### Inventory Redistribution

Similar CTE approach for stock quantities:

```sql
WITH ranked AS (
    SELECT "productId",
           ROW_NUMBER() OVER (ORDER BY md5("productId" || 'inv')) as rn,
           COUNT(*) OVER () as total
    FROM pellier.product_catalog
    WHERE "productId" NOT IN (
        -- All 13 new products preserved at specified quantities
        'PMOBI0043','PMOBI0044','PMOBI0045','PMOBI0046','PMOBI0047','PMOBI0048',
        'PSPRT0043','PSPRT0044','PSPRT0045','PSPRT0046',
        'PBEAU0043','PKITC0043','PSKCA0043',
        -- Existing locked stock product
        'PSUNG0007'
    )
)
UPDATE pellier.product_catalog pc
SET quantity = CASE
    WHEN r.rn <= r.total * 0.06 THEN 0                                       -- 6%: out of stock
    WHEN r.rn <= r.total * 0.14 THEN 1 + (random() * 4)::int                 -- 8%: critical (1-5)
    WHEN r.rn <= r.total * 0.26 THEN 6 + (random() * 9)::int                 -- 12%: low (6-15)
    WHEN r.rn <= r.total * 0.60 THEN 16 + (random() * 84)::int               -- 34%: healthy (16-100)
    ELSE                              101 + (random() * 899)::int             -- 40%: well-stocked (101-1000)
END
FROM ranked r
WHERE pc."productId" = r."productId";
```

Preserved quantities (excluded from the UPDATE — 13 new products + 1 existing locked product):

- PSUNG0007: qty 1 (restock demo target — existing product)
- PMOBI0043: qty 312 (Sony WH-1000XM5)
- PMOBI0044: qty 8 (AirPods Pro 2 — low stock)
- PMOBI0045: qty 445 (JBL Tune 510BT)
- PMOBI0046: qty 6 (Galaxy Buds3 Pro — low stock)
- PMOBI0047: qty 203 (Beats Solo 4)
- PMOBI0048: qty 538 (Anker Soundcore Q20+)
- PSPRT0043: qty 267 (YETI Rambler)
- PSPRT0044: qty 4 (Stanley Quencher — critical stock)
- PSPRT0045: qty 389 (Owala FreeSip)
- PSPRT0046: qty 156 (Corkcicle Canteen)
- PBEAU0043: qty 711 (Burt's Bees Gift Set)
- PKITC0043: qty 0 (Lodge Cast Iron — deliberately out-of-stock)
- PSKCA0043: qty 423 (CeraVe Gift Set)

Teaching impact: `get_inventory_health()` returns ~74% health score. `get_low_stock_products()` returns ~90 products (qty 1-15).

#### Deterministic Ordering

Both CTEs use `md5("productId")` as the ordering key instead of `random()`. This means the same productIds always land in the same percentile buckets across runs. The `random()` within each bucket only varies the exact value within the bucket range, which is acceptable variance.

---

### Component 5: Load Script (`scripts/load-database-fast.sh`)

Modified version of the existing `scripts/seed-database.sh`. Changes are minimal — swap the CSV path and add post-load SQL execution.

#### Changes from existing `seed-database.sh`

1. CSV file resolution: look for `data/product-catalog-enriched.csv` first, fall back to `data/product-catalog-cohere-v4.csv` with a warning
2. After the `INSERT INTO ... FROM temp_products` and index creation, execute: `\i '$SCRIPT_DIR/post-load-adjustments.sql'`
3. VACUUM ANALYZE moves to after post-load adjustments (currently it runs before session tables)

#### Preserved behavior

Everything else stays identical to `seed-database.sh`:

- Schema creation (`pellier`)
- Table schema (same columns, same types, same constraints)
- Temp table approach for CSV loading with column name mapping
- All 7 indexes (HNSW, FTS GIN, category, price, stars, category-price composite, bestseller)
- HNSW parameters: m=16, ef_construction=128, vector_cosine_ops
- Session management tables (conversations, messages, session_metadata, tool_uses)
- Permission grants
- Environment variable loading from `.env`

#### Fallback logic

```bash
# Look for enriched catalog first
CSV_FILE=""
for path in "$PROJECT_ROOT/data/product-catalog-enriched.csv" \
            "$PROJECT_ROOT/data/product-catalog-cohere-v4.csv" \
            "/workshop/.../data/product-catalog-cohere-v4.csv"; do
    if [ -f "$path" ]; then
        CSV_FILE="$path"
        break
    fi
done

if [[ "$CSV_FILE" == *"cohere-v4"* ]]; then
    log "⚠️  Enriched catalog not found, falling back to original catalog"
fi
```

---

## API Budget

| API                       | Calls   | Limit       | Script                 |
| ------------------------- | ------- | ----------- | ---------------------- |
| Unsplash                  | 13      | 50/hour     | add-new-products.py    |
| Cohere Embed v4 (Bedrock) | ~13     | pay-per-use | add-new-products.py    |
| Cohere Embed v4 (Bedrock) | ~60     | pay-per-use | enrich-descriptions.py |
| **Total Bedrock**         | **~73** | —           | ~$0.001 total cost     |
| **Total Unsplash**        | **13**  | 50/hour     | single batch           |

## Embedding Model Contract

All scripts use the identical Bedrock invocation pattern established in `scripts/generate_and_store_embeddings.py` and `pellier/backend/services/embeddings.py`:

- Model ID: `us.cohere.embed-v4:0`
- Input type: `search_document` (for product descriptions being indexed)
- Embedding types: `['float']`
- Output dimension: `1024`
- Region: from `AWS_REGION` env var (default `us-east-1`)

This ensures new/modified embeddings are in the same vector space as existing ones and compatible with the HNSW index and the runtime `embed_query()` calls that use `input_type: 'search_query'`.

## Database Schema Compatibility

The enriched catalog preserves the exact schema from `seed-database.sh`:

```sql
CREATE TABLE pellier.product_catalog (
    "productId"        CHAR(10) PRIMARY KEY,
    product_description VARCHAR(500) NOT NULL,
    "imgUrl"           VARCHAR(200),
    "productURL"       VARCHAR(40),
    stars              NUMERIC(2,1),
    reviews            INTEGER,
    price              NUMERIC(8,2),
    category_id        SMALLINT,
    "isBestSeller"     BOOLEAN DEFAULT FALSE NOT NULL,
    "boughtInLastMonth" INTEGER,
    category_name      VARCHAR(50) NOT NULL,
    quantity           SMALLINT,
    embedding          vector(1024)
);
```

No column additions, no type changes, no schema migrations. The application code (`hybrid_search.py`, `agent_tools.py`, `business_logic.py`) requires zero modifications.

## CSV Column Order

The enriched CSV maintains the exact column order of the source CSV:

```
productId, product_description, imgUrl, productURL, stars, reviews, price,
category_id, isBestSeller, boughtInLastMonth, category_name, quantity, embedding
```

This is critical because the load script uses `\copy` with `HEADER true` which maps by position via the temp table.

## ProductId Format

All productIds follow the existing pattern: `P` + 2-4 letter uppercase category prefix + zero-padded 4-digit number.

| Category            | Prefix | Example   |
| ------------------- | ------ | --------- |
| Laptops             | LAPT   | PLAPT0001 |
| Smartphones         | SMRT   | PSMRT0001 |
| Mobile Accessories  | MOBI   | PMOBI0043 |
| Sports Accessories  | SPRT   | PSPRT0043 |
| Beauty              | BEAU   | PBEAU0043 |
| Kitchen Accessories | KITC   | PKITC0043 |
| Skin Care           | SKCA   | PSKCA0043 |

New products use the next available number after the highest existing ID in each category (0043+ since existing catalog goes up to 0042).

---

## Correctness Properties

These properties define the formal correctness criteria for the enrichment pipeline. Each can be validated with automated checks.

### P1: Trim Preserves Locked Products

For every productId in LOCKED_IDS, the trimmed CSV must contain that productId. Violation means a demo query will fail.

```
∀ id ∈ LOCKED_IDS: id ∈ trimmed_csv.productId
```

### P2: Category Counts Are Exact

Each Demo_Critical_Category has exactly 25 products. Each Supporting_Category has exactly 12 products. Total is exactly 431.

```
∀ cat ∈ DEMO_CRITICAL: count(trimmed_csv, cat) = 25
∀ cat ∈ SUPPORTING: count(trimmed_csv, cat) = 12
sum = 11×25 + 13×12 = 275 + 156 = 431
```

### P3: New Products Have Valid Embeddings

Every new product (13 total) has a non-null embedding of exactly 1024 dimensions.

```
∀ p ∈ NEW_PRODUCTS: len(p.embedding) = 1024 ∧ p.embedding ≠ null
```

### P4: Enriched Descriptions Are Supersets

For every product modified by color/material/clearance enrichment, the new description contains the original description as a substring (nothing removed, only appended/prefixed).

```
∀ p modified: original_description ⊂ enriched_description
```

Exception: clearance products have "CLEARANCE — " prefixed, so the check is: `enriched_description.contains(original_description)`.

### P5: New Product Quantities Preserved

After post-load SQL, all 13 new products retain their specified quantities (the inventory CTE excludes all 13).

```
PMOBI0043.quantity = 312   (Sony WH-1000XM5)
PMOBI0044.quantity = 8     (AirPods Pro 2 — locked stock)
PMOBI0045.quantity = 445   (JBL Tune 510BT)
PMOBI0046.quantity = 6     (Galaxy Buds3 Pro — locked stock)
PMOBI0047.quantity = 203   (Beats Solo 4)
PMOBI0048.quantity = 538   (Anker Soundcore Q20+)
PSPRT0043.quantity = 267   (YETI Rambler)
PSPRT0044.quantity = 4     (Stanley Quencher — locked stock)
PSPRT0045.quantity = 389   (Owala FreeSip)
PSPRT0046.quantity = 156   (Corkcicle Canteen)
PBEAU0043.quantity = 711   (Burt's Bees Gift Set)
PKITC0043.quantity = 0     (Lodge Cast Iron — locked stock, intentionally OOS)
PSKCA0043.quantity = 423   (CeraVe Gift Set)
```

### P6: Star Distribution Within Bounds

After post-load SQL, the star rating distribution falls within acceptable ranges:

```
count(stars < 3.5) ∈ [40, 55]     # ~46 target, allows ±6
count(stars ≥ 4.5) ∈ [160, 200]   # ~180 target, allows ±20
```

### P7: Inventory Distribution Produces Expected Health Score

After post-load SQL:

```
count(quantity = 0) ∈ [20, 30]           # ~25 out of stock
count(1 ≤ quantity ≤ 15) ∈ [75, 105]     # ~90 low stock (for get_low_stock_products)
```

### P8: CSV Column Integrity

The enriched CSV has exactly 13 columns in the correct order, matching the source CSV header.

```
enriched_csv.columns = source_csv.columns
len(enriched_csv.columns) = 13
```

### P9: No Duplicate ProductIds

```
len(enriched_csv.productId) = len(set(enriched_csv.productId))
```

### P10: Clearance Price Reduction

For every clearance-tagged product, the enriched price equals 40% of the original price (60% reduction).

```
∀ p ∈ CLEARANCE: enriched_price(p) = round(original_price(p) × 0.4, 2)
```

## Testing Strategy

### Unit Tests (per script)

Each script includes a `--dry-run` flag that validates logic without making API calls:

- `trim-catalog.py --dry-run`: Runs scoring, prints what would be kept/removed, validates locked products and counts
- `add-new-products.py --dry-run`: Prints product data, skips Unsplash and Bedrock calls, uses placeholder values
- `enrich-descriptions.py --dry-run`: Shows which descriptions would be modified, skips re-embedding

### Integration Validation

After running the full pipeline and loading the database, a validation SQL script checks:

```sql
-- P2: Category counts
SELECT category_name, COUNT(*) FROM pellier.product_catalog GROUP BY category_name ORDER BY category_name;

-- P5: Locked stock
SELECT "productId", quantity FROM pellier.product_catalog WHERE "productId" IN ('PSUNG0007','PSPRT0044','PMOBI0044','PMOBI0046','PKITC0043');

-- P6: Star distribution
SELECT
    COUNT(*) FILTER (WHERE stars < 3.0) as below_3,
    COUNT(*) FILTER (WHERE stars >= 3.0 AND stars < 3.5) as range_3_35,
    COUNT(*) FILTER (WHERE stars >= 3.5 AND stars < 4.0) as range_35_4,
    COUNT(*) FILTER (WHERE stars >= 4.0 AND stars < 4.5) as range_4_45,
    COUNT(*) FILTER (WHERE stars >= 4.5) as range_45_5
FROM pellier.product_catalog;

-- P7: Inventory distribution
SELECT
    COUNT(*) FILTER (WHERE quantity = 0) as out_of_stock,
    COUNT(*) FILTER (WHERE quantity BETWEEN 1 AND 5) as critical,
    COUNT(*) FILTER (WHERE quantity BETWEEN 6 AND 15) as low,
    COUNT(*) FILTER (WHERE quantity BETWEEN 16 AND 100) as healthy,
    COUNT(*) FILTER (WHERE quantity > 100) as well_stocked
FROM pellier.product_catalog;

-- P9: No duplicates
SELECT COUNT(*), COUNT(DISTINCT "productId") FROM pellier.product_catalog;
```

### Query Verification

After database load, the 21 scripted demo queries from the verification matrix (Requirements 14-17) should be tested manually or via a verification script that runs each query and checks for expected products in results.

## File Manifest

| File                                     | Action    | Description                                    |
| ---------------------------------------- | --------- | ---------------------------------------------- |
| `scripts/trim-catalog.py`                | Create    | Trim 1,008 → 431 products                      |
| `scripts/add-new-products.py`            | Create    | Add 13 new products with images + embeddings   |
| `scripts/enrich-descriptions.py`         | Create    | Color/material/clearance enrichment + re-embed |
| `scripts/post-load-adjustments.sql`      | Create    | Star + inventory redistribution SQL            |
| `scripts/load-database-fast.sh`          | Create    | New load script (based on seed-database.sh)    |
| `data/product-catalog-trimmed.csv`       | Generated | Intermediate: 431 products                     |
| `data/product-catalog-trimmed-added.csv` | Generated | Intermediate: 444 products                     |
| `data/product-catalog-enriched.csv`      | Generated | Final: 444 enriched products                   |

Note: `scripts/seed-database.sh` is not modified — it remains as the original loader. `scripts/load-database-fast.sh` is a new file that replaces it for enriched catalog loading.

## What Does NOT Change

- `pellier/backend/` — zero application code changes
- `pellier/frontend/` — zero frontend changes
- Database schema — identical table structure
- Embedding model — same Cohere Embed v4, same 1024 dimensions
- HNSW index config — same m=16, ef_construction=128
- Category names — all 24 preserved exactly
- ProductId format — same PXXXX0NNN pattern
- Search queries in `hybrid_search.py` — unchanged
- Agent tools in `agent_tools.py` — unchanged
- Business logic — unchanged
