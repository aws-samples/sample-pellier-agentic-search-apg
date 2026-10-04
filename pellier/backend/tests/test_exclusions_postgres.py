"""A stated exclusion holds against the real seeded catalog, components included."""
import psycopg

from services.search_plan import build_plan
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

ALL = set(range(1, 101))
# Leather handles (10), footbed (15) and trim (95, 96) count, not only leather goods.
LEATHER = {3, 5, 10, 13, 15, 17, 28, 48, 54, 62, 75, 92, 95, 96, 98}
# Merino (20, 50) and the cashmere blends (46, 57) are wool.
WOOL = {20, 45, 46, 50, 51, 53, 57, 59, 63, 84}
CANDLES = {4, 21, 38, 80}


def _eligible(cluster, exclusions):
    clauses, params = build_plan("a gift", {"exclusions": exclusions}).compile_predicates()
    sql = 'SELECT "productId"::int FROM pellier.product_catalog WHERE ' + " AND ".join(clauses)
    with psycopg.connect(host=str(cluster.socket), user="postgres", dbname="postgres") as conn:
        return {row[0] for row in conn.execute(sql, params)}


def test_no_leather_excludes_leather_parts(fresh_db):
    assert _eligible(fresh_db, ["leather"]) == ALL - LEATHER


def test_no_wool_excludes_merino_and_blends(fresh_db):
    assert _eligible(fresh_db, ["wool"]) == ALL - WOOL


def test_no_candles_still_uses_the_merchandising_tag(fresh_db):
    assert _eligible(fresh_db, ["candle"]) == ALL - CANDLES


def test_exclusions_combine(fresh_db):
    assert _eligible(fresh_db, ["leather", "wool", "candle"]) == ALL - LEATHER - WOOL - CANDLES
