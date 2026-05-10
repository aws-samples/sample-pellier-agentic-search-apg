#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"; }
error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"; exit 1; }

log "==================== Pellier Database Setup ===================="

# Find project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Find CSV file
CSV_FILE=""
for path in "$PROJECT_ROOT/data/product-catalog-cohere-v4.csv" \
            "/workshop/sample-pellier-agentic-search-apg/data/product-catalog-cohere-v4.csv"; do
    if [ -f "$path" ]; then
        CSV_FILE="$path"
        break
    fi
done

# Download from S3 if not found locally
if [ -z "$CSV_FILE" ]; then
    log "CSV not found locally, downloading from S3..."
    mkdir -p "$PROJECT_ROOT/data"
    CSV_FILE="$PROJECT_ROOT/data/product-catalog-cohere-v4.csv"

    # Use Workshop Studio assets bucket (variables set by CloudFormation)
    if [ -n "${ASSETS_BUCKET_NAME:-}" ] && [ -n "${ASSETS_BUCKET_PREFIX:-}" ]; then
        S3_URL="s3://${ASSETS_BUCKET_NAME}/${ASSETS_BUCKET_PREFIX}product-catalog-cohere-v4.csv"
    else
        S3_URL="s3://ws-assets-prod-iad-r-pdx-f3b3f9f1a7d6a3d0/YOUR-EVENT-ID/product-catalog-cohere-v4.csv"
    fi

    if command -v aws &> /dev/null; then
        log "Downloading from: $S3_URL"
        aws s3 cp "$S3_URL" "$CSV_FILE" || error "Failed to download CSV from S3"
    else
        error "AWS CLI not found and CSV not present locally"
    fi
fi

log "Using CSV: $CSV_FILE"

# Load environment
for env_path in "$PROJECT_ROOT/.env" "/workshop/sample-pellier-agentic-search-apg/.env"; do
    if [ -f "$env_path" ]; then
        source "$env_path"
        break
    fi
done

# Verify variables
for var in DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD; do
    if [ -z "${!var:-}" ]; then error "Missing $var"; fi
done

log "Loading data into $DB_HOST:$DB_PORT/$DB_NAME..."

# Execute SQL with embedded CSV path
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" << SQL
\set ON_ERROR_STOP on

-- Create extension and schema
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS pellier;
DROP TABLE IF EXISTS pellier.product_catalog CASCADE;

-- Create optimized table
CREATE TABLE pellier.product_catalog (
    "productId" CHAR(10) PRIMARY KEY,
    product_description VARCHAR(500) NOT NULL,
    "imgUrl" VARCHAR(200),
    "productURL" VARCHAR(40),
    stars NUMERIC(2,1) CHECK (stars >= 1.0 AND stars <= 5.0),
    reviews INTEGER CHECK (reviews >= 0),
    price NUMERIC(8,2) CHECK (price >= 0),
    category_id SMALLINT CHECK (category_id > 0),
    "isBestSeller" BOOLEAN DEFAULT FALSE NOT NULL,
    "boughtInLastMonth" INTEGER CHECK ("boughtInLastMonth" >= 0),
    category_name VARCHAR(50) NOT NULL,
    quantity SMALLINT CHECK (quantity >= 0 AND quantity <= 1000),
    embedding vector(1024)
);

\echo 'Loading data from CSV...'
-- Create temporary table matching CSV column names (lowercase)
CREATE TEMP TABLE temp_products (
    "productId" VARCHAR(10),
    product_description TEXT,
    imgurl TEXT,
    producturl TEXT,
    stars NUMERIC,
    reviews INTEGER,
    price NUMERIC,
    category_id INTEGER,
    isbestseller BOOLEAN,
    boughtinlastmonth INTEGER,
    category_name VARCHAR(255),
    quantity INTEGER,
    embedding vector(1024)
);

-- Load CSV into temp table
\copy temp_products FROM '$CSV_FILE' WITH (FORMAT csv, HEADER true);

-- Copy from temp to final table with column name mapping
INSERT INTO pellier.product_catalog
    ("productId", product_description, "imgUrl", "productURL", stars, reviews,
     price, category_id, "isBestSeller", "boughtInLastMonth", category_name, quantity, embedding)
SELECT
    "productId", product_description, imgurl, producturl, stars, reviews,
    price, category_id, isbestseller, boughtinlastmonth, category_name, quantity, embedding
FROM temp_products;

DROP TABLE temp_products;

\echo 'Creating indexes...'

-- Vector similarity index (HNSW)
CREATE INDEX idx_product_embedding_hnsw
ON pellier.product_catalog
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 128);

-- Full-text search index
CREATE INDEX idx_product_fts
ON pellier.product_catalog
USING GIN (to_tsvector('english', product_description));

-- Category index
CREATE INDEX idx_product_category_name
ON pellier.product_catalog(category_name);

-- Price index (partial - only valid prices)
CREATE INDEX idx_product_price
ON pellier.product_catalog(price) WHERE price > 0;

-- Stars index (partial - highly rated)
CREATE INDEX idx_product_stars
ON pellier.product_catalog(stars) WHERE stars >= 4.0;

-- Composite index for common queries
CREATE INDEX idx_product_category_price
ON pellier.product_catalog(category_name, price)
WHERE price > 0 AND quantity > 0;

-- Bestseller index (partial)
CREATE INDEX idx_product_bestseller
ON pellier.product_catalog("isBestSeller")
WHERE "isBestSeller" = TRUE;

-- ======================================================================
-- Post-Load Adjustments — Star Rating & Inventory Redistribution
-- IMPORTANT: The star and inventory exclusion lists are intentionally
-- different. Do NOT unify them.
--   Stars:     excludes 42 products (29 locked + 13 new)
--   Inventory: excludes 14 products (13 new + PSUNG0007)
-- ======================================================================

\echo 'Applying star rating redistribution...'
-- Target: 3% at 2.0-2.9, 7% at 3.0-3.4, 15% at 3.5-3.9, 35% at 4.0-4.4, 40% at 4.5-5.0
-- Excludes: 29 locked products + 13 new products = 42 total
WITH ranked AS (
    SELECT "productId",
        ROW_NUMBER() OVER (ORDER BY md5("productId")) AS rn,
        COUNT(*) OVER () AS total
    FROM pellier.product_catalog
    WHERE "productId" NOT IN (
            'PLAPT0001', 'PLAPT0016', 'PLAPT0007', 'PLAPT0026', 'PLAPT0033',
            'PLAPT0010', 'PSMRT0001', 'PSMRT0009', 'PSMRT0039', 'PMOBI0002',
            'PMOBI0004', 'PKITC0010', 'PKITC0005', 'PSPRT0022', 'PSPRT0027',
            'PMSHO0011', 'PMSHO0016', 'PMSHO0017', 'PMSHO0018', 'PMSHO0021',
            'PMSHO0036', 'PWSHO0019', 'PWSHO0009', 'PWSHO0022', 'PWSHO0028',
            'PSUNG0007', 'PMWAT0001', 'PWBAG0001', 'PWBAG0002',
            'PMOBI0043', 'PMOBI0044', 'PMOBI0045', 'PMOBI0046', 'PMOBI0047',
            'PMOBI0048', 'PSPRT0043', 'PSPRT0044', 'PSPRT0045', 'PSPRT0046',
            'PBEAU0043', 'PKITC0043', 'PSKCA0043'
        )
)
UPDATE pellier.product_catalog pc
SET stars = CASE
        WHEN r.rn <= r.total * 0.03 THEN ROUND(2.0 + (random() * 0.9)::numeric, 1)
        WHEN r.rn <= r.total * 0.10 THEN ROUND(3.0 + (random() * 0.4)::numeric, 1)
        WHEN r.rn <= r.total * 0.25 THEN ROUND(3.5 + (random() * 0.4)::numeric, 1)
        WHEN r.rn <= r.total * 0.60 THEN ROUND(4.0 + (random() * 0.4)::numeric, 1)
        ELSE ROUND(4.5 + (random() * 0.5)::numeric, 1)
    END
FROM ranked r
WHERE pc."productId" = r."productId";

\echo 'Applying inventory redistribution...'
-- Target: 6% at 0, 8% at 1-5, 12% at 6-15, 34% at 16-100, 40% at 101-1000
-- Excludes: 13 new products + PSUNG0007 = 14 total
WITH ranked AS (
    SELECT "productId",
        ROW_NUMBER() OVER (ORDER BY md5("productId" || 'inv')) AS rn,
        COUNT(*) OVER () AS total
    FROM pellier.product_catalog
    WHERE "productId" NOT IN (
            'PMOBI0043', 'PMOBI0044', 'PMOBI0045', 'PMOBI0046', 'PMOBI0047',
            'PMOBI0048', 'PSPRT0043', 'PSPRT0044', 'PSPRT0045', 'PSPRT0046',
            'PBEAU0043', 'PKITC0043', 'PSKCA0043', 'PSUNG0007'
        )
)
UPDATE pellier.product_catalog pc
SET quantity = CASE
        WHEN r.rn <= r.total * 0.06 THEN 0
        WHEN r.rn <= r.total * 0.14 THEN 1 + (random() * 4)::int
        WHEN r.rn <= r.total * 0.26 THEN 6 + (random() * 9)::int
        WHEN r.rn <= r.total * 0.60 THEN 16 + (random() * 84)::int
        ELSE 101 + (random() * 899)::int
    END
FROM ranked r
WHERE pc."productId" = r."productId";

-- Analyze for query planner (after all adjustments)
VACUUM ANALYZE pellier.product_catalog;

\echo 'Creating return policies table...'
-- Return policies (queried by customer support agent)
CREATE TABLE IF NOT EXISTS pellier.return_policies (
    category_name VARCHAR(50) PRIMARY KEY,
    return_window_days INTEGER NOT NULL,
    conditions TEXT NOT NULL,
    refund_method TEXT NOT NULL
);

INSERT INTO pellier.return_policies (category_name, return_window_days, conditions, refund_method) VALUES
    ('Beauty',              30, 'Unopened and sealed in original packaging', 'Original payment method or store credit within 5-7 business days'),
    ('Fragrances',          30, 'Unopened and sealed in original packaging', 'Original payment method or store credit within 5-7 business days'),
    ('Furniture',           14, 'Unassembled or in original condition, original packaging required', 'Original payment method within 10-14 business days'),
    ('Groceries',            7, 'Unopened, non-perishable items only', 'Store credit within 3-5 business days'),
    ('Home Decoration',     30, 'Unused, in original packaging', 'Original payment method within 5-7 business days'),
    ('Kitchen Accessories', 30, 'Unused, in original packaging', 'Original payment method within 5-7 business days'),
    ('Laptops',             15, 'Factory reset, original packaging, all accessories included', 'Original payment method within 5-7 business days'),
    ('Mens Shirts',         30, 'Unworn, with tags attached, in original packaging', 'Original payment method within 5-7 business days'),
    ('Mens Shoes',          30, 'Unworn, in original box with tags attached', 'Original payment method within 5-7 business days'),
    ('Mens Watches',        30, 'Unworn, with tags and original packaging', 'Original payment method within 5-7 business days'),
    ('Mobile Accessories',  30, 'Unused, in original packaging', 'Original payment method within 5-7 business days'),
    ('Motorcycle',          14, 'Unused, uninstalled, in original packaging with all hardware', 'Original payment method within 10-14 business days'),
    ('Skin Care',           30, 'Unopened and sealed in original packaging', 'Original payment method or store credit within 5-7 business days'),
    ('Smartphones',         15, 'Factory reset, original packaging, all accessories included', 'Original payment method within 5-7 business days'),
    ('Sports Accessories',  30, 'Unused, in original packaging with all parts', 'Original payment method within 5-7 business days'),
    ('Sunglasses',          30, 'Unworn, with case and original packaging', 'Original payment method within 5-7 business days'),
    ('Tablets',             15, 'Factory reset, original packaging, all accessories included', 'Original payment method within 5-7 business days'),
    ('Tops',                30, 'Unworn, with tags attached, in original packaging', 'Original payment method within 5-7 business days'),
    ('Vehicle',             14, 'Unused, uninstalled, in original condition with all documentation', 'Original payment method within 10-14 business days'),
    ('Womens Bags',         30, 'Unused, with tags and original packaging', 'Original payment method within 5-7 business days'),
    ('Womens Dresses',      30, 'Unworn, with tags attached, in original packaging', 'Original payment method within 5-7 business days'),
    ('Womens Jewellery',    30, 'Unworn, with tags and original packaging, certificate of authenticity if applicable', 'Original payment method within 7-10 business days'),
    ('Womens Shoes',        30, 'Unworn, in original box with tags attached', 'Original payment method within 5-7 business days'),
    ('Womens Watches',      30, 'Unworn, with tags and original packaging', 'Original payment method within 5-7 business days'),
    ('default',             30, 'Item must be in original condition with packaging', 'Original payment method or store credit within 5-10 business days')
ON CONFLICT (category_name) DO NOTHING;

GRANT SELECT ON pellier.return_policies TO postgres;

-- Session management is handled by AgentCore Memory (STM) — no Aurora session tables needed.

-- ======================================================================
-- Validation
-- ======================================================================

\echo ''
\echo '=========================================='
\echo 'Product count and category breakdown'
\echo '=========================================='
SELECT COUNT(*) as product_count FROM pellier.product_catalog;
SELECT category_name, COUNT(*) AS product_count
FROM pellier.product_catalog
GROUP BY category_name
ORDER BY category_name;

\echo ''
\echo '=========================================='
\echo 'Locked product quantities preserved?'
\echo '=========================================='
SELECT "productId", quantity,
    CASE
        WHEN "productId" = 'PSUNG0007' AND quantity = 1 THEN 'PASS'
        WHEN "productId" = 'PMOBI0043' AND quantity = 312 THEN 'PASS'
        WHEN "productId" = 'PMOBI0044' AND quantity = 8 THEN 'PASS'
        WHEN "productId" = 'PMOBI0045' AND quantity = 445 THEN 'PASS'
        WHEN "productId" = 'PMOBI0046' AND quantity = 6 THEN 'PASS'
        WHEN "productId" = 'PMOBI0047' AND quantity = 203 THEN 'PASS'
        WHEN "productId" = 'PMOBI0048' AND quantity = 538 THEN 'PASS'
        WHEN "productId" = 'PSPRT0043' AND quantity = 267 THEN 'PASS'
        WHEN "productId" = 'PSPRT0044' AND quantity = 4 THEN 'PASS'
        WHEN "productId" = 'PSPRT0045' AND quantity = 389 THEN 'PASS'
        WHEN "productId" = 'PSPRT0046' AND quantity = 156 THEN 'PASS'
        WHEN "productId" = 'PBEAU0043' AND quantity = 711 THEN 'PASS'
        WHEN "productId" = 'PKITC0043' AND quantity = 0 THEN 'PASS'
        WHEN "productId" = 'PSKCA0043' AND quantity = 423 THEN 'PASS'
        ELSE 'FAIL'
    END AS status
FROM pellier.product_catalog
WHERE "productId" IN (
        'PSUNG0007', 'PMOBI0043', 'PMOBI0044', 'PMOBI0045', 'PMOBI0046',
        'PMOBI0047', 'PMOBI0048', 'PSPRT0043', 'PSPRT0044', 'PSPRT0045',
        'PSPRT0046', 'PBEAU0043', 'PKITC0043', 'PSKCA0043'
    )
ORDER BY "productId";

\echo ''
\echo '=========================================='
\echo 'Star rating distribution'
\echo '=========================================='
SELECT COUNT(*) AS total_products,
    COUNT(*) FILTER (WHERE stars < 3.0) AS "2.0-2.9",
    COUNT(*) FILTER (WHERE stars >= 3.0 AND stars < 3.5) AS "3.0-3.4",
    COUNT(*) FILTER (WHERE stars >= 3.5 AND stars < 4.0) AS "3.5-3.9",
    COUNT(*) FILTER (WHERE stars >= 4.0 AND stars < 4.5) AS "4.0-4.4",
    COUNT(*) FILTER (WHERE stars >= 4.5) AS "4.5-5.0"
FROM pellier.product_catalog;

\echo ''
\echo '=========================================='
\echo 'Inventory distribution'
\echo '=========================================='
SELECT COUNT(*) AS total_products,
    COUNT(*) FILTER (WHERE quantity = 0) AS out_of_stock,
    COUNT(*) FILTER (WHERE quantity BETWEEN 1 AND 5) AS critical,
    COUNT(*) FILTER (WHERE quantity BETWEEN 6 AND 15) AS low,
    COUNT(*) FILTER (WHERE quantity BETWEEN 16 AND 100) AS healthy,
    COUNT(*) FILTER (WHERE quantity > 100) AS well_stocked
FROM pellier.product_catalog;

\echo ''
\echo 'Validation complete.'
SQL

if [ $? -eq 0 ]; then
    log "✅ Database loaded successfully"
    log "==================== Setup Complete ===================="
else
    error "Database load failed"
fi
