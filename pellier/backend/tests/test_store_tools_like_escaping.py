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
    expected = r"%50\%\_%"

    store_tools.browse_department(run, department=literal)
    browse_sql, browse_params = run.calls[-1]

    store_tools.check_stock(run, product_query=literal)
    stock_sql, stock_params = run.calls[-1]

    assert browse_params[0] == expected
    assert stock_params == (expected,)
    assert all("ESCAPE '\\'" in sql for sql in (browse_sql, stock_sql))
