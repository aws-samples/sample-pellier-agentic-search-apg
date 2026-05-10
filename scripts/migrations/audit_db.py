#!/usr/bin/env python3
"""Quick audit of all workshop tables in the Aurora cluster."""
import json
import boto3
import psycopg

client = boto3.client("secretsmanager", region_name="us-west-2")
resp = client.get_secret_value(
    SecretId="arn:aws:secretsmanager:us-west-2:619763002613:secret:rds!cluster-5100afbd-ab1f-4498-b49f-502a7dcad9d9-Hbpbdd"
)
creds = json.loads(resp["SecretString"])

conn = psycopg.connect(
    host="dat4xx-labs-test.cluster-chygmprofdnr.us-west-2.rds.amazonaws.com",
    port=5432, dbname="postgres",
    user=creds["username"], password=creds["password"],
)
cur = conn.cursor()

print("=== ALL TABLES ===")
cur.execute("""SELECT table_schema || '.' || table_name
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog','information_schema')
ORDER BY 1""")
for r in cur.fetchall():
    print(f"  {r[0]}")

print("\n=== ROW COUNTS ===")
tables = [
    "pellier.product_catalog",
    "pellier.conversations",
    "pellier.messages",
    "pellier.session_metadata",
    "pellier.tool_uses",
    "pellier.return_policies",
    "public.customers",
    "public.orders",
    "public.customer_episodic_seed",
    "public.tools",
]
for t in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t}: {cur.fetchone()[0]}")
    except Exception as e:
        conn.rollback()
        print(f"  {t}: ERROR - {e}")

print("\n=== PRODUCT CATALOG SCHEMA ===")
cur.execute("""SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='pellier' AND table_name='product_catalog'
ORDER BY ordinal_position""")
for r in cur.fetchall():
    print(f"  {r[0]:30s} {r[1]:25s} nullable={r[2]}")

print("\n=== CUSTOMERS SCHEMA ===")
cur.execute("""SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name='customers'
ORDER BY ordinal_position""")
for r in cur.fetchall():
    print(f"  {r[0]:30s} {r[1]:25s} nullable={r[2]}")

print("\n=== ORDERS SCHEMA ===")
cur.execute("""SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name='orders'
ORDER BY ordinal_position""")
for r in cur.fetchall():
    print(f"  {r[0]:30s} {r[1]:25s} nullable={r[2]}")

print("\n=== TOOLS SCHEMA ===")
cur.execute("""SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name='tools'
ORDER BY ordinal_position""")
for r in cur.fetchall():
    print(f"  {r[0]:30s} {r[1]:25s} nullable={r[2]}")

print("\n=== SAMPLE ORDERS (5 most recent) ===")
cur.execute("SELECT customer_id, product_id, quantity, placed_at FROM orders ORDER BY placed_at DESC LIMIT 5")
for r in cur.fetchall():
    print(f"  {r[0]} | pid={r[1]} | qty={r[2]} | {r[3]}")

print("\n=== SAMPLE EPISODES (first 5) ===")
cur.execute("SELECT customer_id, summary_text, ts_offset_days FROM customer_episodic_seed ORDER BY customer_id, ts_offset_days DESC LIMIT 5")
for r in cur.fetchall():
    print(f"  {r[0]} | {r[2]:4d}d | {r[1]}")

print("\n=== RETURN POLICIES ===")
cur.execute("SELECT category_name, return_window_days FROM pellier.return_policies ORDER BY 1")
for r in cur.fetchall():
    print(f"  {r[0]:15s} {r[1]}d")

print("\n=== TOOLS ===")
cur.execute("SELECT name, owner, requires_approval, description_emb IS NOT NULL AS has_emb FROM tools ORDER BY id")
for r in cur.fetchall():
    print(f"  {r[0]:30s} owner={r[1]:20s} approval={r[2]} emb={r[3]}")

print("\n=== INDEXES ===")
cur.execute("""SELECT schemaname, tablename, indexname
FROM pg_indexes WHERE schemaname NOT IN ('pg_catalog')
ORDER BY 1,2,3""")
for r in cur.fetchall():
    print(f"  {r[0]}.{r[1]}: {r[2]}")

print("\n=== EXTENSIONS ===")
cur.execute("SELECT extname, extversion FROM pg_extension ORDER BY 1")
for r in cur.fetchall():
    print(f"  {r[0]} v{r[1]}")

conn.close()
print("\nAudit complete.")
