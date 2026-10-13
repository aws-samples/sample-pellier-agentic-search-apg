"""The 50,000-product results file is the run the guide quotes; it must match its script.

``scripts/bench/longtail_50k.py`` builds Anna's queries from the finished Lab 1 code. If that
code changes, the SQL the results file records no longer matches, and the numbers it holds
are no longer measurements of the current search.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BENCH = REPO / "scripts" / "bench"
spec = importlib.util.spec_from_file_location("longtail_50k", BENCH / "longtail_50k.py")
longtail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(longtail)
RESULTS = json.loads((BENCH / "longtail_50k_results.json").read_text(encoding="utf-8"))


def _words(sql: str) -> str:
    return " ".join(sql.split())


def test_the_recorded_hybrid_sql_is_what_the_script_builds() -> None:
    queries, _words_query = longtail.anna_sql()
    for name, sql in queries.items():
        assert _words(sql) == _words(RESULTS["hybrid_sql"][name]), name


def test_each_selective_filter_row_records_the_statements_it_ran() -> None:
    for price, row in RESULTS["lab_check"]["variants"].items():
        assert row["sql"] == longtail.variant_sql(f"{price} AND NOT tags ? 'candle'"), price


def test_the_rows_the_faq_quotes() -> None:
    eight, five = (RESULTS["lab_check"]["variants"][p] for p in ("price <= 8", "price <= 5"))
    assert (eight["matching"], eight["off_rows"], eight["strict_rows"]) == (905, 0, 20)
    assert eight["strict_equals_exact"] is True
    assert (five["matching"], five["strict_rows"], five["strict_equals_exact"]) == (67, 20, False)
    assert RESULTS["versions"]["pgvector"] == "0.8.1"
    assert RESULTS["versions"]["version"].startswith("PostgreSQL 18.3")


def test_the_exact_scan_orders_by_an_expression_no_index_serves() -> None:
    assert longtail.lab_query("true", exact=True).endswith("+ 0 LIMIT 20")
    assert "+ 0" not in longtail.lab_query("true")
