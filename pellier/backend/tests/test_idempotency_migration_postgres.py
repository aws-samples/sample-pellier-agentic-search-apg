"""Reapply migration 023 against real quantity and evidence guards."""

from pathlib import Path

import pytest

from tests.test_forensic_dataset_postgres import sql  # noqa: F401


MIGRATIONS = Path(__file__).resolve().parents[3] / "scripts" / "migrations"


def _between(filename: str, start: str, end: str) -> str:
    text = (MIGRATIONS / filename).read_text()
    return text[text.index(start):text.index(end)]


@pytest.mark.parametrize("orders", ["none", "unreturned", "fully_returned"])
def test_success_probe_owns_its_fixture_and_preserves_business_rows(sql, orders):
    sql('''DROP SCHEMA pellier CASCADE;
        CREATE SCHEMA pellier;
        CREATE TABLE pellier.product_catalog (
            "productId" text PRIMARY KEY, name text, quantity integer,
            updated_at timestamptz DEFAULT now());
        INSERT INTO pellier.product_catalog VALUES ('31', 'Existing robe', 10);
    ''')
    sql(_between(
        "002_workshop_telemetry.sql",
        "CREATE TABLE IF NOT EXISTS pellier.customers",
        "CREATE TABLE IF NOT EXISTS pellier.approvals",
    ))
    sql(_between(
        "005_theo_returns.sql",
        "CREATE TABLE IF NOT EXISTS pellier.returns",
        "CREATE INDEX IF NOT EXISTS returns_customer_idx",
    ))
    sql((MIGRATIONS / "011_governed_write_integrity.sql").read_text())
    sql(_between(
        "013_inventory_ledger.sql",
        "ALTER TABLE pellier.returns",
        "-- Inventory ledger: the single source of truth",
    ))
    sql(_between(
        "047_evidence_immutability.sql",
        "CREATE OR REPLACE FUNCTION pellier.write_operations_fill_once()",
        "REVOKE UPDATE ON pellier.write_operations",
    ))
    sql('''INSERT INTO pellier.customers (id, name)
        VALUES ('CUST-JESSICA', 'Existing customer');
        INSERT INTO pellier.write_operations
            (idempotency_key, operation, request_hash, result, completed_at)
        VALUES ('existing-proof', 'initiate_return', 'existing-hash',
                '{"status":"success"}', now());
    ''')
    if orders != "none":
        sql('''INSERT INTO pellier.orders (customer_id, product_id, quantity)
            VALUES ('CUST-JESSICA', '31', 1);''')
    if orders == "fully_returned":
        sql('''INSERT INTO pellier.returns (customer_id, product_id, reason)
            VALUES ('CUST-JESSICA', '31', 'changed_mind');''')

    def snapshot():
        return tuple(
            sql(f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)),"
                f" '[]'::jsonb) FROM pellier.{table} t").stdout
            for table in ("customers", "orders", "returns", "write_operations",
                          "product_catalog")
        )

    before = snapshot()
    for _ in range(2):
        result = sql((MIGRATIONS / "023_idempotency_claims_release_on_failure.sql").read_text())
        assert "migration 023: verified" in result.stderr
        assert "skipping success probe" not in result.stderr
        assert snapshot() == before
