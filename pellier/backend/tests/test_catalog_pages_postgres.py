"""The home grid's nine pages, on real PostgreSQL after setup.

The home page shows twelve pieces a page and pages through the whole catalog.
Page 1 is the edit, in its storefront order: "This week at Pellier" signed
out, the shopper's edit signed in. The later pages hold every other piece
once, by department, highest rated first, then by name. This runs the real
setup script on a throwaway cluster and reads every page through the route's
own query, for the signed-out edit and each shopper's.
"""
from __future__ import annotations

from typing import Any, Dict, List

import psycopg
import pytest
from fastapi import HTTPException
from psycopg.rows import dict_row

from routes.products import _catalog_page
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

EDITS = ("fresh", "anna", "marco", "theo", "house")
PAGE_SIZE = 12


class _PgDb:
    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self.conn = conn

    async def fetch_all(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
        async with self.conn.cursor() as cur:
            await cur.execute(sql, params)
            return [dict(row) for row in await cur.fetchall()]


async def _read_all(cluster: Any) -> Dict[str, Any]:
    conninfo = {"host": str(cluster.socket), "port": 5432, "user": "postgres",
                "dbname": "postgres", "autocommit": True, "row_factory": dict_row}
    async with await psycopg.AsyncConnection.connect(**conninfo) as conn:
        db = _PgDb(conn)
        catalog = {row["productId"] for row in await db.fetch_all(
            'SELECT "productId" FROM pellier.product_catalog')}
        read: Dict[str, Any] = {"catalog": catalog, "edits": {}}
        for edit in EDITS:
            pages = [await _catalog_page(db, persona_id=edit, page=n, page_size=PAGE_SIZE)
                     for n in range(1, 10)]
            with pytest.raises(HTTPException) as past_the_end:
                await _catalog_page(db, persona_id=edit, page=10, page_size=PAGE_SIZE)
            order = await db.fetch_all(
                'SELECT "productId" FROM pellier.product_catalog '
                "WHERE persona_id = %s AND storefront_rank IS NOT NULL ORDER BY storefront_rank",
                edit)
            read["edits"][edit] = {
                "pages": pages,
                "past_the_end": past_the_end.value.status_code,
                "edit": [str(row["productId"]) for row in order],
            }
    return read


@pytest.mark.asyncio
async def test_every_edit_pages_through_the_whole_catalog_once(fresh_db) -> None:
    read = await _read_all(fresh_db)
    assert len(read["catalog"]) == 100
    for edit, result in read["edits"].items():
        pages = result["pages"]
        assert [page["page"] for page in pages] == list(range(1, 10)), edit
        assert {(page["total"], page["pages"], page["pageSize"]) for page in pages} == {(100, 9, 12)}
        assert [len(page["products"]) for page in pages] == [12] * 8 + [4], edit
        ids = [str(card["id"]) for page in pages for card in page["products"]]
        assert len(ids) == len(set(ids)) == 100, f"{edit}: a piece repeats across pages"
        assert set(ids) == read["catalog"], edit
        assert result["past_the_end"] == 404, edit


@pytest.mark.asyncio
async def test_page_one_is_the_edit_and_the_rest_follow_by_department(fresh_db) -> None:
    read = await _read_all(fresh_db)
    for edit, result in read["edits"].items():
        pages = result["pages"]
        assert len(result["edit"]) == PAGE_SIZE, edit
        assert [str(card["id"]) for card in pages[0]["products"]] == result["edit"], edit
        rest = [card for page in pages[1:] for card in page["products"]]
        assert rest == sorted(rest, key=lambda card: (card["category"], -card["rating"], card["name"])), edit
    # Each shopper's first page is their own edit, so the later pages differ.
    firsts = {edit: tuple(result["edit"]) for edit, result in read["edits"].items()}
    assert len(set(firsts.values())) == len(EDITS)
