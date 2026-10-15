"""Catalog filters must treat shopper text as literal LIKE input, on both rails."""

from __future__ import annotations

from typing import Any

from services import store_tools


class _CaptureRun:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, sql: str, params: Any = ()) -> list[dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        return []


def test_prepare_like_pattern_escapes_every_postgres_metacharacter() -> None:
    assert store_tools.prepare_like_pattern(r"50%_\\") == r"%50\%\_\\\\%"


def test_every_like_filter_binds_the_escaped_pattern_with_an_escape_clause() -> None:
    run = _CaptureRun()
    literal = "50%_"

    store_tools.browse_department(run, department=literal)
    browse_sql, browse_params = run.calls[-1]

    assert browse_params[0] == r"%50\%\_%"
    assert "ESCAPE chr(92)" in browse_sql
    assert "\\" not in browse_sql


def test_check_stock_hands_the_shopper_text_to_the_function_unescaped() -> None:
    """pellier.check_stock escapes each word itself; a pattern here would be escaped twice.

    tests/test_lab2_check_stock_postgres.py proves a %, _ or \\ matches only itself.
    """
    run = _CaptureRun()
    store_tools.check_stock(run, product_query="50%_")
    stock_sql, stock_params = run.calls[-1]
    assert stock_sql == "SELECT * FROM pellier.check_stock(%s)"
    assert stock_params == ("50%_",)
