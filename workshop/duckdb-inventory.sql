-- Run with: uv run scripts/duckdb_federation.py query
-- PostgreSQL runs the inner SELECT. DuckDB joins its small result to Parquet.
-- A forecast is not current stock and does not establish a shipping date.
WITH stock AS MATERIALIZED (
  SELECT * FROM postgres_query('aurora', $$
    SELECT p.name, w.warehouse_code, w.quantity
    FROM pellier.warehouse_inventory w
    JOIN pellier.product_catalog p ON p."productId" = w.product_id
    WHERE w.product_id = '2'
  $$)
)
SELECT stock.name,
       stock.warehouse_code,
       stock.quantity AS current_stock,
       forecast.incoming_quantity AS forecast_incoming,
       forecast.expected_receipt_date,
       forecast.forecast_as_of
FROM stock
LEFT JOIN read_parquet($restock_file) AS forecast
  ON forecast.product_id = '2'
 AND forecast.warehouse_code = stock.warehouse_code
ORDER BY stock.warehouse_code;
