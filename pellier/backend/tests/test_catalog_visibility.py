"""Shopper surfaces must not expose retrieval-evaluation distractors."""

import pytest

from routes.products import _fetch_editorial_catalog
from services.business_logic import BusinessLogic
from services.hybrid_search import _FTS_BRANCH_SQL, _VECTOR_BRANCH_SQL
from services.vector_search import VectorSearch


ARCHIVE_FILTER = "NOT (tags ? 'archive')"


class _Cursor:
    def __init__(self):
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, sql, params=None):
        self.statements.append((sql, params))

    async def fetchall(self):
        return []


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def cursor(self):
        return self._cursor


class _VectorDB:
    def __init__(self):
        self.cursor = _Cursor()

    def get_connection(self):
        return _Connection(self.cursor)


class _BusinessDB:
    def __init__(self):
        self.statements = []

    async def fetch_all(self, sql, *_params):
        self.statements.append(sql)
        return []

    async def fetch_one(self, sql, *_params):
        self.statements.append(sql)
        return {
            "total_products": 0,
            "total_units": 0,
            "running_low_count": 0,
            "out_of_stock_count": 0,
            "avg_quantity": 0,
            "min_price": 0,
            "max_price": 0,
            "avg_price": 0,
            "median_price": 0,
        }


@pytest.mark.asyncio
async def test_vector_and_hybrid_retrieval_exclude_archive_products():
    db = _VectorDB()

    await VectorSearch(db).vector_search([0.0] * 1024, limit=5, ef_search=40)

    catalog_sql = [
        sql for sql, _params in db.cursor.statements if "product_catalog" in sql
    ]
    assert len(catalog_sql) == 1
    assert ARCHIVE_FILTER in catalog_sql[0]
    assert ARCHIVE_FILTER in _VECTOR_BRANCH_SQL
    assert ARCHIVE_FILTER in _FTS_BRANCH_SQL


@pytest.mark.asyncio
async def test_catalog_lists_and_business_tools_exclude_archive_products():
    db = _BusinessDB()
    logic = BusinessLogic(db)

    await _fetch_editorial_catalog(db)
    await _fetch_editorial_catalog(db, category="Apparel")
    await logic.get_trending_products()
    await logic.check_inventory()
    await logic.get_price_analysis()
    await logic.get_price_analysis("Apparel")
    await logic.get_products_by_category("Apparel")
    await logic.get_low_stock()

    catalog_sql = [
        sql for sql in db.statements if "pellier.product_catalog" in sql
    ]
    assert catalog_sql
    assert all(ARCHIVE_FILTER in sql for sql in catalog_sql)


class _EscapeCaptureDB:
    """Records the SQL text and bound params ``_fetch_editorial_catalog`` sends.

    Unlike ``_BusinessDB`` above, a real PostgreSQL ``LIKE``/``ILIKE`` ``ESCAPE``
    clause must be empty or exactly one character
    ("invalid escape string" otherwise) -- a constraint a stub that merely
    records SQL text can't enforce by itself, so the assertions below check
    the clause's shape directly rather than relying on execution succeeding.
    """

    def __init__(self) -> None:
        self.query: str = ""
        self.params: tuple = ()

    async def fetch_all(self, query: str, *params):
        self.query = query
        self.params = params
        return []


@pytest.mark.asyncio
async def test_editorial_catalog_category_filter_uses_a_valid_escape_clause():
    """category ILIKE ... ESCAPE must carry exactly one backslash.

    Regression: the clause once read ``ESCAPE '\\\\'`` (two backslash
    characters between the quotes), which PostgreSQL rejects outright with
    "invalid escape string" on every single ``category``-filtered request --
    live-verified against PostgreSQL 17. A fake DB that only records SQL text
    without executing it never surfaces that failure, so this test checks the
    clause's exact shape instead of trusting a stub's silent success.
    """
    db = _EscapeCaptureDB()

    await _fetch_editorial_catalog(db, category="A%B_C\\D")

    assert "ESCAPE '\\'" in db.query
    assert "ESCAPE '\\\\'" not in db.query
    # The bound pattern must escape the shopper-controlled metacharacters
    # using that same single-character escape, so % and _ stay literal and
    # a literal backslash in the category name doesn't unbalance the clause.
    assert db.params[0] == "%A\\%B\\_C\\\\D%"
