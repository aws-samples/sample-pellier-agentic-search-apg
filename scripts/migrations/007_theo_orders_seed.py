"""Seed Theo with persona-coherent orders so process_return ownership gates pass.

Theo is the third persona in the workshop and anchors the third Aurora
capability (Aurora as agent system-of-record). His ceramics-return demo
turn relies on three things being true:

  1. Theo exists in the ``customers`` table.
  2. Theo has at least one ``orders`` row for a real product, so the
     ownership SQL JOIN inside BusinessLogic.process_return finds him.
  3. The Wabi-Sabi Bowl is one of his orders — that's the piece he
     "buys" in his persona profile and the piece the chipped-ceramics
     fixture session names.

Marco and Anna got their orders seeded by an earlier migration; Theo
was added later and never got the same treatment. This script closes
that gap. It is idempotent (ON CONFLICT DO NOTHING + NOT EXISTS) so it
can run on every workshop redeploy without producing duplicate rows.

Run:
    python scripts/migrations/007_theo_orders_seed.py

Reads DB connection from .env (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD).
"""
import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv(".env")

dsn = (
    f"host={os.environ['DB_HOST']} "
    f"dbname={os.environ['DB_NAME']} "
    f"user={os.environ['DB_USER']} "
    f"password={os.environ['DB_PASSWORD']}"
)

# Four persona-coherent orders. The placed_at offsets give Theo a
# realistic "slow craft" history — recent Wabi-Sabi Bowl, older
# Brass Incense Holder. Names are matched against the live catalog
# (product_id is INTEGER per scripts/load_catalog.py L398).
SQL = """
-- Idempotent: customer row.
INSERT INTO customers (id, name, preferences_summary)
VALUES (
    'theo',
    'Theo',
    'Home + slow craft. Ceramics, linen throws, stoneware. Finishes what he buys, slowly.'
)
ON CONFLICT (id) DO NOTHING;

-- Idempotent: 4 orders matching Theo's persona profile. Wabi-Sabi
-- Bowl is required for the chipped-ceramics fixture demo turn.
WITH theo_products AS (
    SELECT
        "productId",
        name,
        CASE name
            WHEN 'Wabi-Sabi Bowl'           THEN 8
            WHEN 'Stoneware Pour-Over Set'  THEN 21
            WHEN 'Ceramic Tumblers'         THEN 45
            WHEN 'Brass Incense Holder'     THEN 90
        END AS days_ago
      FROM blaize_bazaar.product_catalog
     WHERE name IN (
         'Wabi-Sabi Bowl',
         'Stoneware Pour-Over Set',
         'Ceramic Tumblers',
         'Brass Incense Holder'
     )
)
INSERT INTO orders (customer_id, product_id, quantity, placed_at)
SELECT 'theo', "productId", 1, now() - (days_ago || ' days')::interval
  FROM theo_products
 WHERE NOT EXISTS (
     SELECT 1
       FROM orders
      WHERE customer_id = 'theo'
        AND product_id  = theo_products."productId"
 );

-- Verify: print Theo's orders so the operator can confirm.
SELECT
    o.customer_id,
    o.product_id,
    p.name,
    o.quantity,
    o.placed_at::date
  FROM orders o
  JOIN blaize_bazaar.product_catalog p ON p."productId" = o.product_id
 WHERE o.customer_id = 'theo'
 ORDER BY o.placed_at DESC;
"""

if __name__ == "__main__":
    r = subprocess.run(["psql", dsn, "-c", SQL])
    sys.exit(r.returncode)
