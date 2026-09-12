"""Health must describe usable dependencies without blocking the API loop."""

import asyncio
import threading
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from services.database import DatabaseService


@pytest.mark.parametrize("database_ok,bedrock_ok", [
    (True, True), (False, True), (True, False), (False, False),
])
def test_health_http_status_matches_dependency_result(
    monkeypatch, database_ok, bedrock_ok,
):
    import app

    db = SimpleNamespace(check_health=AsyncMock(
        side_effect=None if database_ok else RuntimeError("connection unavailable"),
    ))
    loop_thread = threading.get_ident()

    def embedding(_text):
        assert threading.get_ident() != loop_thread
        if not bedrock_ok:
            raise RuntimeError("model unavailable")
        return [0.1]

    monkeypatch.setattr(app, "db_service", db)
    monkeypatch.setattr(app, "embedding_service", SimpleNamespace(
        generate_embedding=embedding,
    ))
    response = Response()
    result = asyncio.run(app.health_check(response))

    assert response.status_code == (200 if database_ok and bedrock_ok else 503)
    assert result.status == ("healthy" if database_ok and bedrock_ok else "degraded")
    assert result.database == ("connected" if database_ok else "disconnected")
    assert result.bedrock == ("accessible" if bedrock_ok else "inaccessible")
    db.check_health.assert_awaited_once()


@pytest.mark.parametrize("connected", [True, False])
def test_database_health_uses_checked_pool_without_business_setup(connected):
    called = []

    @asynccontextmanager
    async def connection(*, timeout):
        called.append(timeout)
        if not connected:
            raise RuntimeError("checkout probe failed")
        # The connection deliberately has no vector or business-query methods.
        yield object()

    db = DatabaseService()
    db._is_connected = True
    db._pool = SimpleNamespace(connection=connection)
    if connected:
        asyncio.run(db.check_health())
    else:
        with pytest.raises(RuntimeError, match="checkout probe failed"):
            asyncio.run(db.check_health())
    assert called == [3]


def test_database_health_rejects_an_uninitialized_pool():
    with pytest.raises(RuntimeError, match="not connected"):
        asyncio.run(DatabaseService().check_health())
