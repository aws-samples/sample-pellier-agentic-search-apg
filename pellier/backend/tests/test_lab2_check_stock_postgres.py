"""Lab 2B on real PostgreSQL: pellier.check_stock, as shipped and solved.

Both rails call one function. As shipped it totals the stock of whatever matched
without testing that anything did, so the aggregate over no rows returns one row
with a NULL sum, COALESCE makes it 0, and a piece Pellier does not carry reads as 0
in stock. Only the not-carried probe fails on the starter; the several, sold-out and
in-stock answers are supplied and right. The solution tests for the product first.
A failing run rolls back and leaves the live function as shipped; a passing run
commits the participant's function and its stamp.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import psycopg
from psycopg.rows import dict_row

from tests.fresh_cluster import fresh_db, run_reset  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
LIVE = REPO / "workshop" / "lab-2-check-stock.sql"
STARTER = REPO / "workshop" / "starters" / "lab-2-check-stock.sql"
SOLUTION = REPO / "solutions" / "closing-marcos-gap" / "sql" / "lab-2-check-stock-solution.sql"
SCHEMA = REPO / "scripts" / "migrations" / "001_schema.sql"
LABEL = "Stock check - not carried"
DOLLAR = "$check_stock$"


def _run(cluster: Any, path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-h", str(cluster.socket), "-U", "postgres",
         "-d", "postgres", "-P", "pager=off", "-f", str(path)],
        capture_output=True, text=True, timeout=60,
    )


def _probes(stdout: str) -> Dict[str, List[str]]:
    """Each probe block as name -> [expected, observed, source, verdict]."""
    blocks: Dict[str, Dict[str, str]] = {}
    name = None
    for line in stdout.splitlines():
        head = re.match(r"^(matches|differs)  (.+)$", line)
        value = re.match(r"^ {9}(expected|observed|source) +(.*)$", line)
        if head:
            name = head.group(2)
            blocks[name] = {"verdict": head.group(1)}
        elif name and value:
            blocks[name][value.group(1)] = value.group(2)
    return {name: [b.get("expected", ""), b.get("observed", ""), b.get("source", ""),
                   b["verdict"]] for name, b in blocks.items()}


def _body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split(DOLLAR)[1]


def _statement(text: str) -> str:
    start = text.index("CREATE OR REPLACE FUNCTION pellier.check_stock(")
    return text[start:text.index(f"{DOLLAR};", start) + len(DOLLAR) + 1]


def _live(cluster: Any) -> str:
    return cluster.psql(
        "SELECT encode(sha256(convert_to(prosrc, 'UTF8')), 'hex') || ' ' "
        "|| coalesce(obj_description(oid, 'pg_proc'), 'no stamp') "
        "FROM pg_proc WHERE oid = 'pellier.check_stock(text)'::regprocedure")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_live_worksheet_ships_the_starter() -> None:
    assert LIVE.read_text(encoding="utf-8") == STARTER.read_text(encoding="utf-8")


def test_the_schema_installs_the_starter_function_byte_for_byte() -> None:
    assert _statement(SCHEMA.read_text(encoding="utf-8")) == _statement(
        STARTER.read_text(encoding="utf-8"))


def test_the_solution_differs_from_the_starter_only_inside_the_region() -> None:
    def split(path: Path) -> List[str]:
        text = path.read_text(encoding="utf-8")
        assert text.count(f"WORKSHOP - {LABEL}: START ===") == 1
        head, rest = text.split(f"WORKSHOP - {LABEL}: START ===")
        return [head, rest.split(f"WORKSHOP - {LABEL}: END ===")[1]]
    assert split(SOLUTION) == split(STARTER)
    assert SOLUTION.read_text() != STARTER.read_text()


def test_the_starter_returns_a_row_for_a_piece_not_carried(fresh_db) -> None:  # noqa: F811
    assert fresh_db.psql("SELECT count(*), max(total_units), bool_and(product_id IS NULL) "
                         "FROM pellier.check_stock('Velvet Opera Cape')") == "1|0|t"
    assert _live(fresh_db) == f"{_sha(_body(STARTER))} no stamp"


def test_the_lab_check_uses_the_same_photographed_assortment_as_stock(fresh_db) -> None:
    spec = importlib.util.spec_from_file_location("lab2_scope_check", REPO / "scripts/lab2_check.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    with psycopg.connect(host=str(fresh_db.socket), user="postgres", dbname="postgres",
                          row_factory=dict_row) as conn:
        hidden = conn.execute('SELECT name FROM pellier.product_catalog WHERE "productId" = %s',
                              ('37168',)).fetchone()['name']
        assert check.catalog_answer(conn, hidden) == {"matches": [], "stock": []}
        matches = check.catalog_answer(conn, "linen")["matches"]
        assert len(matches) > 1
        assert all(1 <= int(row["product_id"]) <= 1000 for row in matches)
        offered = conn.execute("SELECT product_id FROM pellier.check_stock('linen')").fetchall()
        # The tool offers at most five matches; the check independently finds all.
        assert len(offered) == 5
        assert {row["product_id"] for row in offered} <= {row["product_id"] for row in matches}


def test_the_starter_fails_only_not_carried_and_shows_the_null_sum(fresh_db) -> None:  # noqa: F811
    before = _live(fresh_db)
    done = _run(fresh_db, STARTER)
    assert done.returncode != 0
    probes = _probes(done.stdout)
    assert len(probes) == 4, done.stdout
    cape = probes['not carried: "Velvet Opera Cape"']
    assert cape == ["no row", "1 row: 0 units; no warehouse rows (no product)",
                    "pellier.check_stock('Velvet Opera Cape')", "differs"]
    for name in ('several: "Linen shirt"', 'sold out: "Quilted Silk Vest"',
                 'in stock: "Hadley Linen Shirt"'):
        assert probes[name][-1] == "matches", (name, probes[name])
    assert probes['several: "Linen shirt"'][1].endswith("rows, one per piece, no count")
    assert probes['sold out: "Quilted Silk Vest"'][1].startswith("1 row: 0 units; ")
    # The cause, printed as a row: no warehouse rows, a NULL sum, a 0 after COALESCE.
    assert re.search(r"^\s+0 \|\s+NULL \|\s+0 ?$", done.stdout, re.MULTILINE), done.stdout
    assert "3 of 4 probes match; rolled back, the live function is unchanged" in done.stdout
    assert "Lab 2B function check failed" in done.stdout
    assert _live(fresh_db) == before


def test_the_solution_passes_every_probe_and_commits_the_function(fresh_db) -> None:  # noqa: F811
    done = _run(fresh_db, SOLUTION)
    assert done.returncode == 0, done.stdout + done.stderr
    probes = _probes(done.stdout)
    assert len(probes) == 4 and all(row[-1] == "matches" for row in probes.values()), probes
    assert probes['in stock: "Hadley Linen Shirt"'][1].startswith("1 row: ")
    assert "4 of 4 probes match; committed, your function is live" in done.stdout
    assert "Lab 2B function check passed" in done.stdout
    sha = _sha(_body(SOLUTION))
    assert _live(fresh_db) == f"{sha} Lab 2B function sha256 {sha}"
    assert fresh_db.psql("SELECT count(*) FROM pellier.check_stock('Velvet Opera Cape')") == "0"
    several = fresh_db.psql("SELECT count(*), count(DISTINCT product_id), "
                            "bool_and(total_units IS NULL) FROM pellier.check_stock('Linen shirt')")
    count, distinct, no_counts = several.split("|")
    assert int(count) >= 2 and count == distinct and no_counts == "t"


def test_like_metacharacters_in_the_query_match_only_themselves(fresh_db) -> None:  # noqa: F811
    """%, _ and \\ are the shopper's characters, never wildcards.

    The catalog's "100% Linen Apron" is the one name that holds a metacharacter.
    """
    def names(query: str) -> str:
        return fresh_db.psql("SELECT coalesce(string_agg(name, ', '), '') "
                             "FROM pellier.check_stock($q$" + query + "$q$)")
    assert names("100%") == "100% Linen Apron"
    for query in ("Line%Apron", "Linen_shirt", "_", "\\"):
        assert names(query) == "", query


def test_a_reset_reinstalls_the_function_as_shipped(fresh_db) -> None:  # noqa: F811
    """scripts/setup/database-reset.sh rebuilds the schema, so a committed answer goes."""
    done = _run(fresh_db, SOLUTION)
    assert done.returncode == 0, done.stdout + done.stderr
    assert _live(fresh_db).endswith(f"Lab 2B function sha256 {_sha(_body(SOLUTION))}")
    run_reset(fresh_db)
    assert _live(fresh_db) == f"{_sha(_body(STARTER))} no stamp"
