"""Requirement revisions persist per session on real PostgreSQL."""
import asyncio

import pytest

from services.shopping_requirements import load_latest, resolve_for_turn
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)


class _Db:
    """The two calls the store makes, on a real psycopg connection."""

    def __init__(self, cluster) -> None:
        import psycopg
        from psycopg.rows import dict_row

        self._conn = psycopg.connect(
            host=str(cluster.socket), user="postgres", dbname="postgres",
            autocommit=True, row_factory=dict_row,
        )

    async def fetch_one(self, sql, *params):
        return self._conn.execute(sql, params).fetchone()

    async def execute_query(self, sql, *params):
        self._conn.execute(sql, params)


def _extractor(updates):
    return lambda message, _current: updates[message]


UPDATES = {
    "under $100, no candles": {
        "change": "update", "price_max_usd": 100, "add_exclusions": ["candle"],
        "quotes": {"price_max_usd": "under $100", "add_exclusions": "no candles"},
    },
    "show me more": {"change": "keep"},
    "no leather": {
        "change": "update", "add_exclusions": ["leather"],
        "quotes": {"add_exclusions": "no leather"},
    },
}


def _turn(db, session, message, turn):
    return asyncio.run(resolve_for_turn(
        db, session_id=session, message=message, turn_id=turn,
        extract_update=_extractor(UPDATES),
    ))


@pytest.fixture
def db(fresh_db):
    return _Db(fresh_db)


def test_show_me_more_reads_the_stored_requirements(db):
    _turn(db, "anna-1", "under $100, no candles", "t1")
    later = _turn(db, "anna-1", "show me more", "t2")
    assert (later.revision, later.price_max_usd, later.exclusions) == (2, 100.0, ("candle",))
    stored = asyncio.run(load_latest(db, "anna-1"))
    assert (stored.revision, stored.turn_id, stored.exclusions) == (2, "t2", ("candle",))


def test_two_sessions_never_share_requirements(db):
    _turn(db, "shopper-a", "under $100, no candles", "a1")
    _turn(db, "shopper-b", "no leather", "b1")
    a = asyncio.run(load_latest(db, "shopper-a"))
    b = asyncio.run(load_latest(db, "shopper-b"))
    assert (a.exclusions, a.price_max_usd) == (("candle",), 100.0)
    assert (b.exclusions, b.price_max_usd) == (("leather",), None)


def test_a_turn_without_a_session_is_not_stored(db):
    first = _turn(db, None, "under $100, no candles", "x1")
    again = _turn(db, None, "show me more", "x2")
    assert first.exclusions == ("candle",)
    assert again.exclusions == () and again.revision == 1
