-- Run with: uv run scripts/aurora_analytics.py query
-- Two questions, one database. pellier.warehouse_inventory is live Aurora stock. lake.daily_sales
-- and lake.deliveries are foreign tables over Parquet files in Amazon S3: Aurora reads the files
-- where they are, through the aurora_analytics extension, and joins them in the same query.
-- The files are fixed sample data for the 28 days to 22 November 2026. Days count from that
-- day: per_day is units sold a day, sold_out_in is the days the stock lasts at that pace,
-- arrives_in is the days until the next delivery, and days_out is the gap between them.

-- Marco's Hadley Linen Shirt is sold out in Brooklyn. When is it back?
WITH pace AS (
  SELECT warehouse_code, sum(units_sold) / 28.0 AS sold_per_day
  FROM lake.daily_sales
  WHERE product_id = '2'
  GROUP BY warehouse_code
)
SELECT w.warehouse_code AS warehouse,
       w.quantity AS in_stock,
       round(pace.sold_per_day, 1) AS per_day,
       d.arrives_in_days AS arrives_in,
       d.units AS arriving
FROM pellier.warehouse_inventory w
LEFT JOIN pace ON pace.warehouse_code = w.warehouse_code
LEFT JOIN lake.deliveries d ON d.product_id = w.product_id AND d.warehouse_code = w.warehouse_code
WHERE w.product_id = '2'
ORDER BY w.warehouse_code;

-- Across the catalog: which products in stock today sell out before their next delivery?
WITH pace AS (
  SELECT product_id, warehouse_code, sum(units_sold) / 28.0 AS sold_per_day
  FROM lake.daily_sales
  GROUP BY product_id, warehouse_code
)
SELECT p.name,
       w.warehouse_code AS warehouse,
       w.quantity AS in_stock,
       round(pace.sold_per_day, 1) AS per_day,
       floor(w.quantity / NULLIF(pace.sold_per_day, 0))::int AS sold_out_in,
       d.arrives_in_days AS arrives_in,
       d.arrives_in_days - floor(w.quantity / NULLIF(pace.sold_per_day, 0))::int AS days_out
FROM pellier.warehouse_inventory w
JOIN pellier.product_catalog p ON p."productId" = w.product_id
JOIN pace ON pace.product_id = w.product_id AND pace.warehouse_code = w.warehouse_code
JOIN lake.deliveries d ON d.product_id = w.product_id AND d.warehouse_code = w.warehouse_code
WHERE w.quantity > 0
  AND floor(w.quantity / NULLIF(pace.sold_per_day, 0)) < d.arrives_in_days
ORDER BY days_out DESC, p.name, w.warehouse_code;
