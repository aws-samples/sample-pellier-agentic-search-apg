"""The four shoppers the home page signs in, on real PostgreSQL after setup and reset.

Choosing a shopper signs in with their demo account and selects their edit,
and the signed-in suggestion row shows their lab prompts. Migration 057 gives
Jessica her own profile and Home comforts edit, and makes every shopper's
required prompts exactly their lab prompts. This runs the real setup and reset
scripts on a throwaway cluster and reads the rows through the real routes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import psycopg
import pytest
from psycopg.rows import dict_row

import app as app_module
from tests.fresh_cluster import fresh_db, run_reset  # noqa: F401  (fixture import)

FRONTEND_PUBLIC = Path(__file__).resolve().parents[2] / "frontend" / "public"

LAB_PROMPTS = {
    "anna": [
        "A housewarming gift for a friend who loves slow mornings. In stock, under $100, "
        "and no candles.",
        "A gift with a watch, under $100, in stock, no candles.",
    ],
    "marco": [
        "Is the Velvet Opera Cape in stock?",
        "How many Hadley Linen Shirts are available at the Brooklyn warehouse, "
        "and what ship window is recorded?",
    ],
    "theo": [
        "Hand-thrown ceramics for a slower morning routine",
        "My Wabi-Sabi Bowl arrived chipped. What is happening with my ticket?",
        "Jessica and I share an address. She sent two things back last week and "
        "hasn't heard anything. Can you check her ticket too?",
    ],
    "jessica": ["Please ask a person to look at a store credit for the two items I returned."],
}


class _PgDb:
    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self.conn = conn

    async def fetch_all(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
        async with self.conn.cursor() as cur:
            await cur.execute(sql, params)
            return [dict(row) for row in await cur.fetchall()]


async def _read(cluster: Any, monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    conninfo = {"host": str(cluster.socket), "port": 5432, "user": "postgres",
                "dbname": "postgres", "autocommit": True, "row_factory": dict_row}
    async with await psycopg.AsyncConnection.connect(**conninfo) as conn:
        db = _PgDb(conn)

        async def get_db_service() -> _PgDb:
            return db

        monkeypatch.setattr(app_module, "get_db_service", get_db_service)
        personas = await app_module.list_personas()
        required = {}
        for persona in ("anna", "marco", "theo", "jessica"):
            scenarios = (await app_module.list_scenarios(persona=persona))["scenarios"]
            required[persona] = [s["prompt"] for s in scenarios if s["journeyRole"] == "required"]
        house = await db.fetch_all(
            'SELECT "productId" FROM pellier.product_catalog '
            "WHERE persona_id = 'house' AND storefront_rank IS NOT NULL ORDER BY storefront_rank"
        )
    return {"personas": personas, "required": required, "house": [r["productId"] for r in house]}


@pytest.mark.asyncio
async def test_the_four_shoppers_have_an_edit_and_their_lab_prompts(fresh_db, monkeypatch) -> None:
    read = await _read(fresh_db, monkeypatch)
    shoppers = [p for p in read["personas"] if p["id"] != "fresh"]
    assert [p["id"] for p in shoppers] == ["marco", "anna", "theo", "jessica"]
    jessica = shoppers[-1]
    assert jessica["display_name"] == "Jessica"
    assert (FRONTEND_PUBLIC / jessica["hero_image"].lstrip("/")).is_file(), jessica["hero_image"]
    assert read["required"] == LAB_PROMPTS
    assert len(read["house"]) == 12 and read["house"][0] == "46"
    assert "42" not in read["house"], "the robe she sent back is not in her edit"


@pytest.mark.asyncio
async def test_the_reset_keeps_the_same_shoppers_and_prompts(fresh_db, monkeypatch) -> None:
    before = await _read(fresh_db, monkeypatch)
    run_reset(fresh_db)
    after = await _read(fresh_db, monkeypatch)
    assert after["required"] == before["required"] == LAB_PROMPTS
    assert after["house"] == before["house"]
    assert [p["id"] for p in after["personas"]] == [p["id"] for p in before["personas"]]
