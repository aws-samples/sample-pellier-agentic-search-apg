"""Catalog pagination boundaries on the full 50,000-row PostgreSQL seed.

The home page shows twelve pieces a page from the 1,000 photographed products.
Page 1 is the edit, in its storefront order: "This week at Pellier" signed
out, the shopper's edit signed in. The later pages hold every other piece
once, by department, highest rated first, then by name. This runs the real
setup script on a throwaway cluster, independently sorts the full catalog and
checks the first, second, middle, last and out-of-range pages through the route's
own query for each edit.
"""
from __future__ import annotations

from typing import Any, Dict, List
from contextlib import asynccontextmanager
import json
from math import ceil

import psycopg
import pytest
from fastapi import HTTPException
from psycopg.rows import dict_row

from routes.products import (
    _catalog_page, _related_products, _fetch_editorial_catalog,
    _fetch_products_by_ids, get_storefront_product, get_inventory_signal,
)
from services import store_tools
from services.vector_search import VectorSearch
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

EDITS = ("fresh", "anna", "marco", "theo", "house")
PAGE_SIZE = 12


class _PgDb:
    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self.conn = conn

    @asynccontextmanager
    async def get_connection(self):
        yield self.conn

    async def fetch_one(self, sql: str, *params: Any):
        rows = await self.fetch_all(sql, *params)
        return rows[0] if rows else None

    async def fetch_all(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
        async with self.conn.cursor() as cur:
            await cur.execute(sql, params)
            return [dict(row) for row in await cur.fetchall()]


async def _read_all(cluster: Any) -> Dict[str, Any]:
    conninfo = {"host": str(cluster.socket), "port": 5432, "user": "postgres",
                "dbname": "postgres", "autocommit": True, "row_factory": dict_row}
    async with await psycopg.AsyncConnection.connect(**conninfo) as conn:
        db = _PgDb(conn)
        all_rows = await db.fetch_all(
            'SELECT "productId", name, category, rating, "imgUrl" FROM pellier.product_catalog')
        assert len(all_rows) == 50000
        all_rows = [row for row in all_rows if str(row["imgUrl"] or "").strip()]
        catalog = {row["productId"] for row in all_rows}
        page_count = ceil(len(catalog) / PAGE_SIZE)
        sampled = sorted({1, 2, page_count // 2, page_count})
        read: Dict[str, Any] = {"catalog": catalog, "edits": {}}
        for edit in EDITS:
            pages = [await _catalog_page(db, persona_id=edit, page=n, page_size=PAGE_SIZE)
                     for n in sampled]
            with pytest.raises(HTTPException) as past_the_end:
                await _catalog_page(db, persona_id=edit, page=page_count + 1, page_size=PAGE_SIZE)
            order = await db.fetch_all(
                'SELECT "productId" FROM pellier.product_catalog '
                "WHERE persona_id = %s AND storefront_rank IS NOT NULL ORDER BY storefront_rank",
                edit)
            edit_ids = [str(row["productId"]) for row in order]
            remainder = sorted((r for r in all_rows if str(r["productId"]) not in edit_ids),
                               key=lambda r: (r["category"], -r["rating"], r["name"]))
            expected = edit_ids + [str(r["productId"]) for r in remainder]
            read["edits"][edit] = {
                "expected": expected,
                "sampled": sampled,
                "pages": pages,
                "past_the_end": past_the_end.value.status_code,
                "edit": [str(row["productId"]) for row in order],
            }
    return read


@pytest.mark.asyncio
async def test_every_edit_has_correct_boundaries_and_a_complete_order(fresh_db) -> None:
    read = await _read_all(fresh_db)
    assert read["catalog"] == {str(i) for i in range(1, 1001)}
    for edit, result in read["edits"].items():
        expected = result["expected"]
        assert len(expected) == len(set(expected)) == 1000
        assert set(expected) == read["catalog"]
        assert [page["page"] for page in result["pages"]] == result["sampled"]
        for page in result["pages"]:
            assert (page["total"], page["pages"], page["pageSize"]) == (1000, 84, 12)
            start = (page["page"] - 1) * PAGE_SIZE
            assert [str(card["id"]) for card in page["products"]] == expected[start:start + PAGE_SIZE], edit
        assert len(result["pages"][-1]["products"]) == 4
        assert result["past_the_end"] == 404


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


@pytest.mark.asyncio
async def test_related_products_stay_in_the_department_and_bound_stock_reads(fresh_db) -> None:
    async with await psycopg.AsyncConnection.connect(
        host=str(fresh_db.socket), port=5432, user='postgres', dbname='postgres',
        autocommit=True, row_factory=dict_row,
    ) as conn:
        db = _PgDb(conn)
        for pid in (2, 500, 1000):
            subject = await db.fetch_all(
                'SELECT category FROM pellier.product_catalog WHERE "productId" = %s', str(pid))
            cards = await _related_products(db, pid)
            assert len(cards) == 4
            assert len({card.id for card in cards}) == 4
            assert all(card.id != pid and card.category == subject[0]['category'] for card in cards)
            assert all(len(card.warehouses) == 3 for card in cards)
            assert all(card.image_url and 1 <= card.id <= 1000 for card in cards)
        for pid in (1001, 12500, 50000):
            assert await _related_products(db, pid) == []
        assert await _related_products(db, 999999) == []


@pytest.mark.asyncio
async def test_hidden_rows_cannot_be_browsed_fetched_or_counted(fresh_db):
    async with await psycopg.AsyncConnection.connect(
        host=str(fresh_db.socket), user="postgres", dbname="postgres",
        autocommit=True, row_factory=dict_row,
    ) as conn:
        db = _PgDb(conn)
        products = await _fetch_editorial_catalog(db)
        assert {p.id for p in products} == set(range(1, 1001))
        cards = await _fetch_products_by_ids(db, ["1001", "1000", "37168", "1", "50000"])
        assert [p.id for p in cards] == [1000, 1]
        for pid in (1001, 37168, 50000):
            with pytest.raises(HTTPException) as missing:
                await get_storefront_product(pid, db)
            assert missing.value.status_code == 404
        counts = json.loads((await get_inventory_signal(db)).body)["counts"]
        assert sum(counts.values()) == 1000
        # Empty, NULL and whitespace-only paths all fail closed.
        async with conn.transaction(force_rollback=True):
            await conn.execute('UPDATE pellier.product_catalog SET "imgUrl" = NULL WHERE "productId" = \'1\'')
            await conn.execute('UPDATE pellier.product_catalog SET "imgUrl" = \'   \' WHERE "productId" = \'2\'')
            assert await _fetch_products_by_ids(db, ["1", "2"]) == []
            assert (await _catalog_page(db, persona_id=None, page=1, page_size=12))["total"] == 998


@pytest.mark.asyncio
async def test_real_vector_search_filters_before_limit_and_keeps_distance_order(fresh_db):
    async with await psycopg.AsyncConnection.connect(
        host=str(fresh_db.socket), user="postgres", dbname="postgres",
        autocommit=False, row_factory=dict_row,
    ) as conn:
        db = _PgDb(conn)
        search = VectorSearch(db)
        for pid in ("1", "1000", "37168"):
            row = await db.fetch_one(
                'SELECT embedding::text AS vector FROM pellier.product_catalog WHERE "productId" = %s',
                pid,
            )
            embedding = json.loads(row["vector"])
            for rows in (
                await search.vector_search(embedding, limit=30, ef_search=100),
                await search.vector_search_planned(embedding, limit=30, ef_search=100),
            ):
                assert len(rows) == 30
                assert all(1 <= int(r["product_id"]) <= 1000 and r["img_url"] for r in rows)
                scores = [r["similarity"] for r in rows]
                assert scores == sorted(scores, reverse=True)
                if pid != "37168":
                    assert str(rows[0]["product_id"]) == pid
                    assert scores[0] == pytest.approx(1.0, abs=1e-5)
                # Independently recompute every returned distance in PostgreSQL.
                for result in rows:
                    actual = await db.fetch_one(
                        'SELECT 1 - (embedding <=> %s::vector) AS similarity '
                        'FROM pellier.product_catalog WHERE "productId" = %s',
                        row["vector"], str(result["product_id"]),
                    )
                    assert result["similarity"] == pytest.approx(actual["similarity"])


def test_agent_catalog_tools_and_real_full_text_search_exclude_hidden_rows(fresh_db):
    with psycopg.connect(
        host=str(fresh_db.socket), user="postgres", dbname="postgres",
        autocommit=True, row_factory=dict_row,
    ) as conn:
        def run(sql, params):
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

        hidden = run('SELECT name FROM pellier.product_catalog WHERE "productId" = %s', ("37168",))[0]
        result = store_tools.compare_products(run, product_id_1=1, product_id_2=37168)
        assert result["status"] == "not_found"
        result = store_tools.check_stock(run, product_query=hidden["name"])
        assert hidden["name"] not in json.dumps(result.get("product"))
        assert not result.get("candidates")
        for department in ("Home", "Clothing", "Kitchen and table"):
            result = store_tools.browse_department(run, department=department, limit=20)
            assert result["count"] == 20
            assert all(1 <= int(p["productId"]) <= 1000 for p in result["products"])
        # Hidden rows really match these words. They must be excluded in SQL.
        words = store_tools.or_tsquery("cotton")
        matched_hidden = run(
            'SELECT count(*) AS n FROM pellier.product_catalog '
            'WHERE "productId"::integer > 1000 AND description_tsv @@ to_tsquery(\'english\', %s)',
            (words,),
        )
        assert matched_hidden[0]["n"] > 100
        rows = run(store_tools.fts_branch_sql(), (words, 30))
        assert len(rows) == 30
        assert all(1 <= int(r["product_id"]) <= 1000 and r["img_url"] for r in rows)
        scores = [r["fts_rank_score"] for r in rows]
        assert scores == sorted(scores, reverse=True)
