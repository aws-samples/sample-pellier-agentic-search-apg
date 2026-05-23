#!/usr/bin/env python3
"""Seed Aurora with persona data from docs/personas-config.json.

Idempotent: uses ON CONFLICT DO UPDATE for customers and DELETE +
re-INSERT for orders and episodic seed rows. Safe to re-run between
workshop sessions.

Usage:
    cd pellier/backend
    .venv/bin/python ../../scripts/seed_personas.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add backend to path so config + services resolve
BACKEND = Path(__file__).resolve().parent.parent / "pellier" / "backend"
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from services.database import DatabaseService  # noqa: E402

CONFIG_PATH = Path(__file__).resolve().parent.parent / "docs" / "personas-config.json"


async def seed() -> None:
    db = DatabaseService()
    await db.connect()

    config = json.loads(CONFIG_PATH.read_text())
    personas = config["personas"]

    customer_ids = [p["customer_id"] for p in personas]
    print(f"Seeding {len(personas)} personas: {customer_ids}")

    try:
        for p in personas:
            cid = p["customer_id"]
            name = p["display_name"]
            prefs = p.get("blurb", "")

            # ---- customers (upsert) ----
            await db.execute_query(
                """
                INSERT INTO pellier.customers (id, name, preferences_summary)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                    SET name = EXCLUDED.name,
                        preferences_summary = EXCLUDED.preferences_summary
                """,
                cid, name, prefs,
            )
            print(f"  ✓ customer {cid} ({name})")

            # ---- orders (delete + re-insert) ----
            await db.execute_query(
                "DELETE FROM pellier.orders WHERE customer_id = %s", cid
            )
            product_ids = p.get("order_product_ids", [])
            inserted = 0
            for i, pid in enumerate(product_ids):
                # Only insert if the product exists in the catalog
                row = await db.fetch_one(
                    'SELECT 1 FROM pellier.product_catalog WHERE "productId" = %s',
                    int(pid),
                )
                if row:
                    interval_days = (len(product_ids) - i) * 8
                    await db.execute_query(
                        "INSERT INTO pellier.orders (customer_id, product_id, quantity, placed_at) "
                        "VALUES (%s, %s, 1, now() - make_interval(days => %s))",
                        cid, int(pid), interval_days,
                    )
                    inserted += 1
                else:
                    print(f"    ⚠ product {pid} not in catalog, skipped")
            print(f"  ✓ {inserted} orders for {cid}")

            # ---- episodic seed (delete + re-insert) ----
            await db.execute_query(
                "DELETE FROM pellier.customer_episodic_seed WHERE customer_id = %s", cid
            )
            facts = p.get("ltm_facts", [])
            for fact in facts:
                await db.execute_query(
                    """
                    INSERT INTO pellier.customer_episodic_seed
                        (customer_id, summary_text, ts_offset_days)
                    VALUES (%s, %s, %s)
                    """,
                    cid, fact["summary_text"], fact["ts_offset_days"],
                )
            print(f"  ✓ {len(facts)} LTM facts for {cid}")

        print(f"\n✅ Persona seed complete. {len(personas)} personas ready.")

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(seed())
