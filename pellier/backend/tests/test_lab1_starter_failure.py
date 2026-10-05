"""Lab 1's contract: the starters fail the way the guide's Spot step shows, the solutions do not.

Task 1A. The starter's fusion expression counts a missing rank as rank zero, so
a product found by only one search scores too high: the worksheet prints
"differs" for exactly those products and fails. The solution matches every
recorded score.

Task 1B. The starter's fallback rebuilds the plan from the shopper's words and
drops her limits: Anna's request, forced onto the fallback, returns a candle and
the receipt records a search that kept none of her three limits.
``scripts/lab1_compare.py`` says so. The solution keeps them.

Both run on the real schema and the real search pipeline
(``store_tools.search_products``); only the embedding and the reranker are
stand-ins. The query vector is the Sunday Morning Candle's own embedding, so
the vector search ranks candles first and a fallback that forgot "no candles"
cannot hide it.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import psycopg
import pytest
from psycopg.rows import dict_row

from services import search_plan, store_tools
from tests import lab_variants
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab1_compare = importlib.import_module("lab1_compare")

QUERY = "A housewarming gift under $100, in stock, no candles; something for slow mornings."
EXTRACTED = {
    "required_categories": [], "categories": ["Home"],
    "tags": ["gift", "slow"], "price_max_usd": 100, "in_stock_only": True,
    "exclusions": ["candle"], "unsupported_exclusions": [],
    "soft_signal": "a housewarming gift for slow mornings", "lifted": [],
}
CANDLE_ID = "80"


@pytest.fixture(scope="module")
def conn(fresh_db: Any) -> Any:  # noqa: F811 - the imported fixture
    connection = psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                                 dbname="postgres", autocommit=True, row_factory=dict_row)
    try:
        yield connection
    finally:
        connection.close()


def _run(conn: Any):
    def run(sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [dict(row) for row in cur.fetchall()] if cur.description else []
    return run


def _candle_embedding(conn: Any) -> List[float]:
    with conn.cursor() as cur:
        cur.execute('SELECT embedding::text AS e FROM pellier.product_catalog '
                    'WHERE "productId" = %s', (CANDLE_ID,))
        return json.loads(cur.fetchone()["e"])


def _anna_search(conn: Any, monkeypatch: pytest.MonkeyPatch, variant: str) -> Dict[str, Any]:
    """Anna's request through the real pipeline, with the variant's fallback in place."""
    monkeypatch.setattr(search_plan.SearchPlan, "_with_relaxations",
                        lab_variants.plan_fallback(variant))
    vector = _candle_embedding(conn)
    return store_tools.search_products(
        _run(conn), query=QUERY, extracted=dict(EXTRACTED), limit=5,
        embed=lambda _text: vector,
        rerank=lambda **kw: [{"index": i, "relevance_score": 1 - i / 100}
                             for i in range(len(kw["documents"]))],
        receipt={"turn_id": f"turn-lab1-{variant}", "session_id": f"persona-anna-{variant}",
                 "rail": "in-process", "embedding_model": "stand-in", "rerank_model": "stand-in"},
    )


def _psql_file(cluster: Any, path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-h", str(cluster.socket), "-U", "postgres",
         "-d", "postgres", "-P", "pager=off", "-f", str(path)],
        capture_output=True, text=True, timeout=60,
    )


# ---------------------------------------------------------------------------
# Task 1B: the fallback
# ---------------------------------------------------------------------------


def test_the_starter_fallback_returns_a_candle_and_drops_annas_limits(conn, monkeypatch) -> None:
    payload = _anna_search(conn, monkeypatch, lab_variants.STARTER)
    returned = [product["productId"] for product in payload["products"]]
    assert payload["search_plan"]["relaxations"][0]["step"] == "drop_tags", payload
    assert CANDLE_ID in returned, returned
    assert payload["search_plan"]["hard_constraints"]["price_max_usd"] is None
    assert payload["search_plan"]["exclusions"] == []

    finding, rows = lab1_compare.evaluate(conn)
    assert finding.state == "CONTRADICTED", finding
    assert "a candle" in finding.observed
    assert "dropped under $100, in stock, no candles" in finding.observed
    assert any(row[-1] != "ok" for row in rows)


def test_the_solution_fallback_keeps_annas_limits(conn, monkeypatch) -> None:
    payload = _anna_search(conn, monkeypatch, lab_variants.SOLUTION)
    returned = [product["productId"] for product in payload["products"]]
    assert payload["search_plan"]["relaxations"][0]["step"] == "drop_tags", payload
    assert returned and CANDLE_ID not in returned
    assert payload["search_plan"]["hard_constraints"]["price_max_usd"] == 100
    assert payload["search_plan"]["exclusions"] == ["candle"]

    finding, rows = lab1_compare.evaluate(conn)
    assert finding.state == "PROVED", finding
    assert rows and all(row[-1] == "ok" for row in rows)


@pytest.mark.parametrize("variant", [lab_variants.STARTER, lab_variants.SOLUTION])
def test_the_plan_contract_separates_the_starter_from_the_solution(monkeypatch, variant) -> None:
    """The local plan contract the retired lab1_plan_contract_check.py ran, per variant."""
    monkeypatch.setattr(search_plan.SearchPlan, "_with_relaxations",
                        lab_variants.plan_fallback(variant))
    original = search_plan.build_plan(QUERY, dict(EXTRACTED))
    before = original.to_dict()
    first, fallback = original.relaxation_ladder()
    assert original.to_dict() == before, "the ladder changed the validated request"
    assert first.soft == original.soft and not first.relaxations
    assert fallback.soft.tags == () and fallback.soft.soft_signal == original.soft.soft_signal
    assert [r.step for r in fallback.relaxations] == ["drop_tags"]
    keeps = (fallback.hard == original.hard
             and fallback.exclusions == original.exclusions
             and fallback.compile_predicates(include_soft=False)
             == original.compile_predicates(include_soft=False))
    assert keeps is (variant == lab_variants.SOLUTION)
    strict = search_plan.SearchPlan(intent="strict", hard=original.hard, soft=original.soft,
                                    exclusions=original.exclusions, relaxation_policy="strict")
    assert len(strict.relaxation_ladder()) == 1


# ---------------------------------------------------------------------------
# Task 1A: the fusion expression
# ---------------------------------------------------------------------------


def _single_list_products(conn: Any) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) AS n
              FROM (SELECT * FROM pellier.retrieval_receipts
                     WHERE session_id LIKE 'persona-anna-%' AND rrf_scores <> '{}'
                     ORDER BY receipt_id DESC LIMIT 1) r
             CROSS JOIN LATERAL jsonb_object_keys(r.rrf_scores) AS k(id)
             WHERE NOT (r.vector_ranks ? k.id AND r.lexical_ranks ? k.id)""")
        return int(cur.fetchone()["n"])


def test_the_starter_expression_misses_every_one_list_product(
    fresh_db, conn, monkeypatch,  # noqa: F811
) -> None:
    _anna_search(conn, monkeypatch, lab_variants.STARTER)
    one_list = _single_list_products(conn)
    assert one_list > 0, "the receipt must hold a product found by one search only"

    done = _psql_file(fresh_db, lab_variants.LAB1_RRF[lab_variants.STARTER])
    assert done.returncode != 0
    assert "Lab 1A check failed" in done.stdout
    assert done.stdout.count("| differs") == one_list, done.stdout
    assert "Expected  every recomputed score equals the score receipt" in done.stdout
    assert "persona-anna-starter" in done.stdout


def test_the_solution_expression_matches_every_recorded_score(
    fresh_db, conn, monkeypatch,  # noqa: F811
) -> None:
    _anna_search(conn, monkeypatch, lab_variants.SOLUTION)
    done = _psql_file(fresh_db, lab_variants.LAB1_RRF[lab_variants.SOLUTION])
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Lab 1A check passed" in done.stdout
    assert "| differs" not in done.stdout


def test_the_worksheet_says_what_to_do_without_a_receipt(fresh_db) -> None:  # noqa: F811
    with psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                         dbname="postgres", autocommit=True) as other:
        other.execute("CREATE DATABASE lab1_empty")
    try:
        empty = subprocess.run(
            [str(fresh_db.bin / "psql"), "-X", "-h", str(fresh_db.socket), "-U", "postgres",
             "-d", "lab1_empty", "-c", "CREATE SCHEMA pellier; CREATE TABLE "
             "pellier.retrieval_receipts (receipt_id bigint, session_id text, query_preview "
             "text, vector_ranks jsonb, lexical_ranks jsonb, rrf_scores jsonb)"],
            capture_output=True, text=True, timeout=60)
        assert empty.returncode == 0, empty.stderr
        done = subprocess.run(
            [str(fresh_db.bin / "psql"), "-X", "-h", str(fresh_db.socket), "-U", "postgres",
             "-d", "lab1_empty", "-f", str(lab_variants.LAB1_RRF[lab_variants.SOLUTION])],
            capture_output=True, text=True, timeout=60)
    finally:
        with psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                             dbname="postgres", autocommit=True) as other:
            other.execute("DROP DATABASE lab1_empty")
    assert done.returncode != 0
    assert "choose Anna on the home page" in done.stdout
