"""Lab 1A's contract: the starter's vector branch ranks nothing, the solution ranks by meaning.

The starter keeps the vector branch's SELECT, with the plan's limits applied, and
stubs out the ranking, so the search answers from words alone. The participant
writes the cosine-distance order and the similarity. ``scripts/lab1_check.py --task 1A``
judges the live ``vector_branch_sql`` with vectors whose nearest product is known
(each product's own embedding), so these tests swap in each variant and read the
verdict. The worksheet ``workshop/lab-1-words.sql`` is model-free; its rows are
pinned here because the guide quotes them.

All of it runs on the real schema and catalog of a fresh cluster.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Callable, Dict, List

import psycopg
import pytest
from psycopg.rows import dict_row

from services import store_tools
from tests import lab_variants
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab1_vector = importlib.import_module("lab1_vector")
WORKSHEET = REPO / "workshop" / "lab-1-words.sql"
MEANING = REPO / "workshop" / "lab-1-meaning.sql"
LIVE = REPO / "pellier" / "backend" / "services" / "store_tools.py"
LABEL = "Vector branch - order by meaning"
DISTANCE = "embedding <=> (SELECT emb FROM query_embedding)"


@pytest.fixture(scope="module")
def conn(fresh_db: Any) -> Any:  # noqa: F811 - the imported fixture
    connection = psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                                 dbname="postgres", autocommit=True, row_factory=dict_row)
    try:
        yield connection
    finally:
        connection.close()


def _variant(replacements: Dict[str, str]) -> Callable[..., str]:
    """The solution's ``vector_branch_sql`` with one realistic mistake written into it."""
    source = lab_variants.body(lab_variants._VECTOR, lab_variants.SOLUTION)
    for old, new in replacements.items():
        assert old in source, old
        source = source.replace(old, new)
    function = "def vector_branch_sql(extra_clauses=()):\n" + textwrap.indent(
        textwrap.dedent(source), "    ")
    scratch: Dict[str, Any] = {}
    exec(compile(function, "<variant>", "exec"), vars(store_tools), scratch)  # noqa: S102
    return scratch["vector_branch_sql"]


def _verdict(conn: Any, monkeypatch: pytest.MonkeyPatch, branch: Callable[..., str]):
    monkeypatch.setattr(store_tools, "vector_branch_sql", branch)
    return lab1_vector.evaluate(conn)


def test_the_live_region_is_the_starter() -> None:
    live = lab_variants.region(LIVE.read_text(encoding="utf-8"), LABEL)
    assert live == lab_variants.body(lab_variants._VECTOR, lab_variants.STARTER)


def test_the_starter_ranks_nothing(conn, monkeypatch) -> None:
    finding, rows = _verdict(conn, monkeypatch, lab_variants.vector_branch(lab_variants.STARTER))
    assert finding.state == "CONTRADICTED", finding
    assert finding.observed == ("the vector branch returned no rows, so nothing is ranked by "
                                "meaning yet")
    assert [row[3] for row in rows] == [0, 0, 0, 0]


def test_the_solution_ranks_by_meaning(conn, monkeypatch) -> None:
    finding, rows = _verdict(conn, monkeypatch, lab_variants.vector_branch(lab_variants.SOLUTION))
    assert finding.state == "PROVED", finding
    assert [row[1] for row in rows[:3]] == list(lab1_vector.SELF_PROBES)
    assert all(row[4] == "ok" for row in rows)


@pytest.mark.parametrize(("mistake", "replacements", "observed"), [
    ("farthest first", {f"ORDER BY {DISTANCE}": f"ORDER BY {DISTANCE} DESC"},
     "not in order of rising distance"),
    ("distance reported as similarity", {f"1 - ({DISTANCE}) AS similarity":
                                         f"{DISTANCE} AS similarity"},
     "reports similarity"),
    ("Euclidean operator", {"<=>": "<->"}, "reports similarity"),
    ("a fixed LIMIT", {"LIMIT %s": "LIMIT 5"}, "your vector branch raised an error"),
    ("limits ignored", {"{_indent_clauses(extra_clauses)}": "{_indent_clauses(extra_clauses)}"
                        " OR true"},
     "came back under Anna's limits, and it is a candle"),
])
def test_the_check_catches_a_realistic_mistake(conn, monkeypatch, mistake: str,
                                               replacements: Dict[str, str],
                                               observed: str) -> None:
    finding, _rows = _verdict(conn, monkeypatch, _variant(replacements))
    assert finding.state == "CONTRADICTED", (mistake, finding)
    assert observed in finding.observed, (mistake, finding.observed)


def _annas_first_sentence() -> str:
    scenarios = json.loads((REPO / "data" / "scenarios.json").read_text(encoding="utf-8"))
    (first,) = [s["prompt"] for s in scenarios
                if s["persona"] == "anna" and s["journey_stage"] == "establish"]
    return first


def test_the_worksheet_query_is_the_one_the_search_builds_from_the_1a_sentence() -> None:
    worksheet = WORKSHEET.read_text(encoding="utf-8")
    expected = store_tools.or_tsquery(_annas_first_sentence())
    assert f"\\set words '{expected}'" in worksheet


def _worksheet_rows(cluster: Any, worksheet: Path = WORKSHEET, bars: int = 2) -> List[List[str]]:
    done = subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-h", str(cluster.socket), "-U", "postgres",
         "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-P", "pager=off", "-f", str(worksheet)],
        capture_output=True, text=True, timeout=60,
    )
    assert done.returncode == 0, done.stderr
    assert "NOTICE" not in done.stdout + done.stderr
    return [[cell.strip() for cell in line.split("|")]
            for line in done.stdout.splitlines() if line.count("|") >= bars]


def test_the_worksheet_shows_her_words_finding_the_wrong_things(fresh_db) -> None:  # noqa: F811
    rows = {row[1]: row for row in _worksheet_rows(fresh_db) if row[0].isdigit()}
    assert rows["Housewarming Gift Box"][0] == "1"
    assert rows["Housewarming Gift Box"][2] == "gift, housewarming"
    assert rows["Gift Wrapping Kit"][2] == "gift"
    assert not {"Stoneware Mugs, Set of 2", "Stoneware Pour-Over Set", "Ceramic Tumblers"} & rows.keys()
    assert len(rows) == 10


def test_the_meaning_worksheet_shows_distances_without_ranking_them(fresh_db) -> None:  # noqa: F811
    rows = {row[0]: row[1:] for row in _worksheet_rows(fresh_db, MEANING)
            if row[0] != "name"}
    assert set(rows) == {
        "Ceramic Tumblers", "Espresso Cups, Set of 4", "Morning Run Shorts",
        "Neroli Oil", "Quilted Silk Vest", "Stoneware Mugs, Set of 2",
        "Stoneware Pour-Over Set", "Wabi-Sabi Bowl",
    }
    assert list(rows) == sorted(rows)
    assert rows["Stoneware Mugs, Set of 2"] == ["0.0000", "1.0000"]
    distances = [float(distance) for distance, _ in rows.values()]
    assert distances != sorted(distances) and distances != sorted(distances, reverse=True)
    for distance, similarity in rows.values():
        assert abs(float(similarity) - (1 - float(distance))) < 1e-4
    assert float(rows["Ceramic Tumblers"][0]) < float(rows["Morning Run Shorts"][0])
    # Task 1A needs the operator class only; the partial index waits for Go deeper.
    indexes = {row[0]: row[1] for row in _worksheet_rows(fresh_db, MEANING, bars=1)
               if row[0].startswith("product_catalog_")}
    assert list(indexes) == ["product_catalog_embedding_hnsw"]
    assert "vector_cosine_ops" in indexes["product_catalog_embedding_hnsw"]


def test_the_worksheet_ranks_the_fitting_products_outside_the_rerank_pool(fresh_db) -> None:  # noqa: F811
    fitting = {row[0]: row for row in _worksheet_rows(fresh_db)
               if row[0] in {"Stoneware Mugs, Set of 2", "Stoneware Pour-Over Set",
                             "Ceramic Tumblers"}}
    assert len(fitting) == 3
    for name, row in fitting.items():
        assert int(row[1]) > store_tools.DEFAULT_RERANK_POOL_K, (name, row)
        assert row[3] == "slow", (name, row)


SELECTIVE = (["category = ANY(%s)", "price <= %s"], [["Home"], 35.0])


def test_a_selective_storefront_search_stays_off_the_full_graph(conn) -> None:
    """Home under $35 is under 0.2% of the rows: through the full graph, one search in two
    came back short. The photographed-only partial index keeps every list full and close."""
    clauses, params = SELECTIVE
    branch = lab_variants.vector_branch(lab_variants.SOLUTION)(clauses)
    exact = branch.replace(f"ORDER BY {DISTANCE}", f"ORDER BY ({DISTANCE}) + 0")
    assert exact != branch
    probes = [row["e"] for row in conn.execute(
        f'SELECT embedding::text AS e FROM pellier.product_catalog '
        f'WHERE {store_tools.VISIBLE_CATALOG_SQL} ORDER BY "productId"::int LIMIT 25')]
    plan = "\n".join(row["QUERY PLAN"] for row in conn.execute(
        "EXPLAIN (COSTS OFF) " + branch, (probes[0], *params, 20)))
    assert "product_catalog_embedding_hnsw" not in plan
    eligible = conn.execute(
        "SELECT count(*) AS n FROM pellier.product_catalog "
        f"WHERE {store_tools.VISIBLE_CATALOG_SQL} AND " + " AND ".join(clauses),
        params).fetchone()["n"]
    recalls = []
    for probe in probes:
        got = [row["product_id"] for row in conn.execute(branch, (probe, *params, 20))]
        want = [row["product_id"] for row in conn.execute(exact, (probe, *params, 20))]
        assert len(got) == min(20, eligible)
        recalls.append(len(set(got) & set(want)) / len(want))
    assert sum(recalls) / len(recalls) >= 0.9
