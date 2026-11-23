#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyarrow==22.0.0"]
# ///
"""Build the Go deeper lake files: four weeks of sales and a delivery plan, in Parquet.

Run on a maintainer's laptop, never on a workshop box. The files are committed under
workshop/lake/, and scripts/aurora_analytics.py uploads them unchanged:

    uv run scripts/build_lake_files.py

The data is synthetic and fixed. Every value comes from a SHA-256 of its product, warehouse
and day, so the same catalog always builds the same rows. Sales cover the 1,000 photographed
products (ids 1 to 1000) in the three warehouses for the 28 days to SNAPSHOT_END. The delivery
plan gives each listed product and warehouse its next delivery, counted in days after
SNAPSHOT_END. Marco's Hadley Linen Shirt (product 2) is fixed by hand, because the guide
quotes it.
"""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
LAKE = ROOT / "workshop" / "lake"
CATALOG = ROOT / "data" / "pellier_catalog.json"
SNAPSHOT_END = date(2026, 11, 22)
DAYS = 28
WAREHOUSES = ("BK-01", "ATX-02", "PDX-01")
PHOTOGRAPHED = range(1, 1001)
RATES = (0.0, 0.2, 0.4, 0.7, 1.0, 1.5, 2.2, 3.0)
DELIVERY_SHARE = 0.2
# Marco's shirt: units sold in the 28 days, and its next delivery (days, units) or None.
MARCO = {
    "BK-01": (28, (3, 12)),
    "ATX-02": (42, (9, 25)),
    "PDX-01": (20, None),
}
SALES_SCHEMA = pa.schema([("product_id", pa.string()), ("warehouse_code", pa.string()),
                          ("sale_date", pa.date32()), ("units_sold", pa.int32())])
DELIVERY_SCHEMA = pa.schema([("product_id", pa.string()), ("warehouse_code", pa.string()),
                             ("arrives_in_days", pa.int32()), ("units", pa.int32())])


def unit(*parts: object) -> float:
    """A number in [0, 1) fixed by its parts."""
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def poisson(rate: float, u: float) -> int:
    """The Poisson(rate) value at cumulative probability u."""
    k, term = 0, math.exp(-rate)
    total = term
    while u >= total and k < 50:
        k += 1
        term *= rate / k
        total += term
    return k


def spread(total: int, day: int) -> int:
    """Day's share of total units, spread evenly so the 28 days sum to total exactly."""
    return (day + 1) * total // DAYS - day * total // DAYS


def daily_sales(product_id: int) -> list[tuple[str, str, date, int]]:
    rows = []
    for warehouse in WAREHOUSES:
        rate = RATES[int(unit("rate", product_id, warehouse) * len(RATES))]
        for day in range(DAYS):
            if product_id == 2:
                units = spread(MARCO[warehouse][0], day)
            else:
                units = poisson(rate, unit("day", product_id, warehouse, day))
            if units:
                sale_date = SNAPSHOT_END - timedelta(days=DAYS - 1 - day)
                rows.append((str(product_id), warehouse, sale_date, units))
    return rows


def deliveries(product_id: int) -> list[tuple[str, str, int, int]]:
    rows = []
    for warehouse in WAREHOUSES:
        if product_id == 2:
            planned = MARCO[warehouse][1]
        elif unit("delivery", product_id, warehouse) < DELIVERY_SHARE:
            planned = (2 + int(unit("arrives", product_id, warehouse) * 19),
                       6 + int(unit("units", product_id, warehouse) * 35))
        else:
            planned = None
        if planned:
            rows.append((str(product_id), warehouse, *planned))
    return rows


def table(rows: list[tuple], schema: pa.Schema) -> pa.Table:
    columns = list(zip(*rows)) if rows else [[] for _ in schema]
    return pa.Table.from_arrays([pa.array(column, type=field.type)
                                 for column, field in zip(columns, schema)], schema=schema)


def write(rows: list[tuple], schema: pa.Schema, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table(rows, schema), path, compression="snappy")
    return {"rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> None:
    products = {p["id"] for p in json.loads(CATALOG.read_text()) if p.get("image")}
    if products != set(PHOTOGRAPHED):
        raise SystemExit("the photographed products are no longer ids 1 to 1000; review the lake")
    sales = sorted(row for product in PHOTOGRAPHED for row in daily_sales(product))
    plan = sorted(row for product in PHOTOGRAPHED for row in deliveries(product))
    files = {}
    first = SNAPSHOT_END - timedelta(days=DAYS - 1)
    for week in range(4):
        start, end = first + timedelta(days=7 * week), first + timedelta(days=7 * week + 6)
        rows = [row for row in sales if start <= row[2] <= end]
        files[f"daily_sales/week-{week + 1}.parquet"] = write(
            rows, SALES_SCHEMA, LAKE / "daily_sales" / f"week-{week + 1}.parquet")
    files["deliveries/plan.parquet"] = write(plan, DELIVERY_SCHEMA,
                                             LAKE / "deliveries" / "plan.parquet")
    manifest = {"snapshot_end": SNAPSHOT_END.isoformat(), "days": DAYS,
                "pyarrow": pa.__version__, "files": files}
    (LAKE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(sales)} sales rows, {len(plan)} delivery rows in {LAKE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
