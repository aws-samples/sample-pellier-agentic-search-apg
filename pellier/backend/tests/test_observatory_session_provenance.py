"""The Sessions list separates conversations from direct runs, on real PostgreSQL.

A conversation is a session the chat pipeline recorded: a Storefront session row,
a governed turn receipt, or a tool run inside a chat turn. Probes, proofs and direct
Gateway or Operator calls leave tool rows only. Elapsed time is not the test: a
one-tool conversation spans zero milliseconds, and a per-customer Gateway ledger
spans days.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from routes import observatory
from services.auth import get_current_user

_SCHEMA = """
DROP SCHEMA IF EXISTS pellier CASCADE;
CREATE SCHEMA pellier;
CREATE TABLE pellier.tool_audit (
    audit_id BIGSERIAL PRIMARY KEY, session_id TEXT, tool TEXT, caller TEXT,
    args JSONB, result JSONB, latency_ms INTEGER, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE pellier.governed_turn_receipts (
    turn_id TEXT PRIMARY KEY, session_id TEXT, principal_sub TEXT,
    terminal_status TEXT, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE pellier.governed_receipts (session_id TEXT, principal_id TEXT);
CREATE TABLE pellier.shopper_sessions (session_id TEXT PRIMARY KEY, persona_id TEXT);

-- Marco's Storefront conversation: one tool, so zero elapsed milliseconds, plus
-- a managed read the Gateway recorded under the turn id it was handed.
INSERT INTO pellier.shopper_sessions VALUES ('persona-marco-1', 'marco');
INSERT INTO pellier.governed_turn_receipts VALUES
    ('turn-marco-1', 'persona-marco-1', NULL, 'complete', now());
INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms) VALUES
    ('persona-marco-1', 'check_inventory', 'agent', '{"query": "linen"}', '{"success": true}', 40),
    ('turn-marco-1', 'get_ticket_history', 'gateway', '{"turn_id": "turn-marco-1"}', '{}', 30);

-- An anonymous Storefront chat: no persona session, but a turn receipt.
INSERT INTO pellier.governed_turn_receipts VALUES
    ('turn-anon-1', 'session-anon-1', NULL, 'complete', now());
INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms) VALUES
    ('session-anon-1', 'search_products', 'agent', '{"query": "shirt"}', '{"success": true}', 50),
    ('session-anon-1', 'check_inventory', 'agent', '{"query": "shirt"}', '{"success": true}', 20);

-- A Storefront turn that ended before its receipt was written: its tool still
-- carries the turn id the chat route minted.
INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms) VALUES
    ('session-lost-receipt', 'search_products_hybrid', 'agent',
     '{"query": "bag", "turn_id": "turn-lost-1"}', '{"status": "success"}', 60);

-- A grant probe from the test harness, and the per-customer Gateway ledger that
-- policy and identity proofs write to over days.
INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms) VALUES
    ('grant-probe-1', 'grant_probe', 'test', '{}', '{}', 0);
INSERT INTO pellier.tool_audit
    (session_id, tool, caller, args, result, latency_ms, created_at) VALUES
    ('gateway-CUST-JESSICA', 'initiate_return', 'gateway',
     '{"idempotency_key": "identity-boundary-1"}', '{"success": true}', 90,
     now() - interval '10 days'),
    ('gateway-CUST-JESSICA', 'issue_credit', 'gateway',
     '{"idempotency_key": "boundaries-1"}', '{"success": true}', 80, now());
"""


def _binaries() -> Optional[Path]:
    candidates = [Path("/opt/homebrew/opt/postgresql@18/bin"),
                  Path("/opt/homebrew/opt/postgresql@17/bin"),
                  *sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True)]
    found = shutil.which("initdb")
    if found:
        candidates.insert(0, Path(found).resolve().parent)
    return next((p for p in candidates
                 if all((p / name).is_file() for name in ("postgres", "pg_ctl", "initdb"))),
                None)


@pytest.fixture(scope="module")
def cluster() -> Any:
    binaries = _binaries()
    if binaries is None:
        pytest.skip("PostgreSQL server binaries are required for the provenance proof")
    temporary = tempfile.TemporaryDirectory(prefix="pellier-sessions-", dir="/tmp")
    root = Path(temporary.name)
    socket, data = root / "socket", root / "data"
    socket.mkdir()

    def run(*args: str) -> None:
        subprocess.run(args, capture_output=True, text=True, timeout=60, check=True)

    run(str(binaries / "initdb"), "-D", str(data), "-U", "proof", "-A", "trust",
        "--no-locale", "--encoding=UTF8", "--no-sync")
    run(str(binaries / "pg_ctl"), "-D", str(data), "-l", str(root / "postgres.log"),
        "-o", f"-F -h '' -k {socket}", "-w", "start")
    try:
        conninfo = f"host={socket} user=proof dbname=postgres"
        with psycopg.connect(conninfo, autocommit=True) as conn:
            conn.execute(_SCHEMA)
        yield conninfo
    finally:
        run(str(binaries / "pg_ctl"), "-D", str(data), "-m", "immediate", "-w", "stop")
        temporary.cleanup()


class PgDb:
    """The one accessor the Sessions list uses."""

    def __init__(self, conninfo: str) -> None:
        self.conninfo = conninfo

    async def fetch_all(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        async with await psycopg.AsyncConnection.connect(
            self.conninfo, row_factory=dict_row
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return list(await cur.fetchall())


@pytest.fixture
def client(cluster: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def live_db() -> PgDb:
        return PgDb(cluster)

    monkeypatch.setattr(observatory, "_live_db", live_db)
    app = FastAPI()
    app.include_router(observatory.router)
    app.dependency_overrides[get_current_user] = lambda: None
    return TestClient(app)


def _listed(client: TestClient, query: str = "") -> Dict[str, Dict[str, Any]]:
    response = client.get(f"/api/observatory/sessions{query}")
    assert response.status_code == 200, response.text
    return {row["id"]: row for row in response.json()}


def test_participants_see_conversations_by_default(client: TestClient) -> None:
    listed = _listed(client)
    assert set(listed) == {"persona-marco-1", "session-anon-1", "session-lost-receipt"}
    assert {row["provenance"] for row in listed.values()} == {"conversation"}
    # A one-tool conversation is still a conversation, and the Gateway read keyed
    # by its turn id belongs to it rather than appearing as a session of its own.
    assert listed["persona-marco-1"]["elapsedMs"] >= 0
    assert "turn-marco-1" not in listed


def test_direct_runs_appear_only_when_asked_for_and_say_so(client: TestClient) -> None:
    listed = _listed(client, "?include_direct=true")
    assert set(listed) == {
        "persona-marco-1", "session-anon-1", "session-lost-receipt",
        "grant-probe-1", "gateway-CUST-JESSICA",
    }
    assert listed["grant-probe-1"]["provenance"] == "direct"
    assert listed["gateway-CUST-JESSICA"]["provenance"] == "direct"
    assert listed["persona-marco-1"]["provenance"] == "conversation"
    # A direct run is not credited to a dispatcher it never passed through.
    assert listed["grant-probe-1"]["routingPattern"] == "Direct tool call"
    assert listed["gateway-CUST-JESSICA"]["routingPattern"] == "Managed Gateway"
    assert listed["session-anon-1"]["routingPattern"] == "Storefront Dispatcher"


def test_the_persona_filter_still_applies_alongside_the_option(client: TestClient) -> None:
    assert set(_listed(client, "?persona=marco&include_direct=true")) == {"persona-marco-1"}
