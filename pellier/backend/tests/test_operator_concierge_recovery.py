"""Running and abandoned Concierge turns, executed on an isolated PostgreSQL.

`test_operator_concierge_sessions.py` models these statements in a fake. This suite
runs them: the lease clock, the gate that holds a new request behind an unanswered
turn, the row lock that makes settling happen once, and a review prepared by the
real ``propose_review`` against migration 020's unique index. The runner tests
drive a turn through the same database and close, time out, or stop it partway.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import psycopg
import pytest
from psycopg.rows import dict_row

from services import operator_concierge
from services import operator_concierge_runner as RUNNER
from services import operator_concierge_sessions as SESSIONS
from services import operator_review as REVIEW

CUSTOMER = "CUST-JESSICA"
CREDIT = {"customer_id": CUSTOMER, "amount_cents": 2500, "reason": "courtesy"}

# The columns these paths read and write, from migrations 002, 007, 020, 021 and 051.
# The pending-review index is migration 020's, verbatim.
_SCHEMA = """
DROP SCHEMA IF EXISTS pellier CASCADE;
CREATE SCHEMA pellier;
CREATE TABLE pellier.customers (id TEXT PRIMARY KEY);
CREATE TABLE pellier.product_catalog (product_id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE pellier.orders (
    id BIGSERIAL PRIMARY KEY, customer_id TEXT, product_id INTEGER,
    placed_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE pellier.conversations (
    session_id VARCHAR PRIMARY KEY, agent_name VARCHAR,
    context JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);
CREATE TABLE pellier.messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR NOT NULL REFERENCES pellier.conversations(session_id)
        ON DELETE CASCADE,
    role VARCHAR NOT NULL, content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);
CREATE TABLE pellier.approvals (
    id BIGSERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES pellier.customers(id) ON DELETE CASCADE,
    tool TEXT NOT NULL, args JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(), decided_at TIMESTAMPTZ,
    source_turn_id TEXT, order_id BIGINT REFERENCES pellier.orders(id),
    issue TEXT, recommendation JSONB, action_hash TEXT, decided_by TEXT,
    execution_turn_id TEXT, requested_by_sub TEXT, requester_kind TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS approvals_open_per_action_idx
    ON pellier.approvals (customer_id, tool, action_hash)
    WHERE status = 'pending';
INSERT INTO pellier.customers VALUES ('CUST-JESSICA');
INSERT INTO pellier.product_catalog VALUES (7, 'Linen throw');
INSERT INTO pellier.orders (customer_id, product_id) VALUES ('CUST-JESSICA', 7);
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
        pytest.skip("PostgreSQL server binaries are required for the recovery proof")
    temporary = tempfile.TemporaryDirectory(prefix="pellier-recovery-", dir="/tmp")
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
        yield f"host={socket} user=proof dbname=postgres"
    finally:
        run(str(binaries / "pg_ctl"), "-D", str(data), "-m", "immediate", "-w", "stop")
        temporary.cleanup()


class PgDb:
    """The two accessors these paths use, with the pool's commit-on-exit semantics."""

    def __init__(self, conninfo: str) -> None:
        self.conninfo = conninfo

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[Any]:
        async with await psycopg.AsyncConnection.connect(
            self.conninfo, row_factory=dict_row
        ) as conn:
            yield conn

    async def fetch_one(self, query: str, *params: Any) -> Optional[Dict[str, Any]]:
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return await cur.fetchone()

    async def rows(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return list(await cur.fetchall())


@pytest.fixture
def pg(cluster: str) -> PgDb:
    with psycopg.connect(cluster, autocommit=True) as conn:
        conn.execute(_SCHEMA)
    return PgDb(cluster)


@pytest.fixture(autouse=True)
def _no_runs_leak() -> Any:
    yield
    assert not RUNNER._RUNS, "a turn run outlived its test"


async def _session(pg: PgDb) -> str:
    created = await SESSIONS.create_session(pg, customer_id=CUSTOMER, operator_sub="op-1")
    return created["sessionId"]


async def _ask(pg: PgDb, sid: str, message: str = "Prepare a return", key: str = "") -> str:
    turn = await SESSIONS.append_operator_turn(
        pg, session_id=sid, customer_id=CUSTOMER, operator_sub="op-1",
        message=message, transport_key=key,
    )
    return turn["turnId"]


async def _messages(pg: PgDb, sid: str) -> List[Dict[str, Any]]:
    return await pg.rows(
        "SELECT id, role, content, metadata FROM pellier.messages"
        " WHERE session_id = %s ORDER BY id", sid,
    )


async def _lease(pg: PgDb, sid: str) -> Optional[Dict[str, Any]]:
    row = await pg.fetch_one(
        "SELECT metadata->'active_turn' AS lease FROM pellier.conversations"
        " WHERE session_id = %s", sid,
    )
    return (row or {}).get("lease")


async def _expire(pg: PgDb, sid: str) -> None:
    async with pg.get_connection() as conn:
        await conn.execute(
            "UPDATE pellier.conversations SET metadata = jsonb_set(metadata,"
            " '{active_turn,lease_until}', to_jsonb(extract(epoch FROM now())::float8 - 1))"
            " WHERE session_id = %s", (sid,),
        )


async def _history(pg: PgDb, sid: str) -> Dict[str, Any]:
    return await RUNNER.load_settled_history(pg, session_id=sid, customer_id=CUSTOMER)


async def _propose(pg: PgDb, turn_id: str) -> Optional[int]:
    return await REVIEW.propose_review(
        pg, action="give_store_credit", args=CREDIT, source_turn_id=turn_id,
        issue="Linen throw", requested_by_sub="op-1",
        requester_kind=REVIEW.REQUESTER_OPERATOR,
    )


# ---------------------------------------------------------------------------
# The gate, the lease, and settling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_open_turn_per_session_and_its_lease(pg: PgDb) -> None:
    sid = await _session(pg)
    turn_id = await _ask(pg, sid, key="tk-1")
    lease = await _lease(pg, sid)
    assert lease["turn_id"] == turn_id and lease["owner"] == SESSIONS.WORKER_ID

    with pytest.raises(SESSIONS.OpenTurnError) as blocked:
        await _ask(pg, sid, "Something else")
    assert blocked.value.turn_id == turn_id
    with pytest.raises(SESSIONS.OpenTurnError):
        await _ask(pg, sid, key="tk-1")
    assert len(await _messages(pg, sid)) == 1

    await SESSIONS.append_assistant_artifact(
        pg, session_id=sid, customer_id=CUSTOMER, turn_id=turn_id,
        summary="Done.", artifact={},
    )
    assert await _lease(pg, sid) is None
    replay = await SESSIONS.append_operator_turn(
        pg, session_id=sid, customer_id=CUSTOMER, operator_sub="op-1",
        message="Prepare a return", transport_key="tk-1",
    )
    assert replay["replayed"] is True and replay["turnId"] == turn_id


@pytest.mark.asyncio
async def test_after_a_restart_the_turn_waits_for_its_lease_then_settles(
    pg: PgDb, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SESSIONS, "WORKER_ID", "worker-before-restart")
    sid = await _session(pg)
    turn_id = await _ask(pg, sid)
    request_before = await _messages(pg, sid)
    monkeypatch.setattr(SESSIONS, "WORKER_ID", "worker-after-restart")

    still = await _history(pg, sid)
    assert still["openTurn"]["state"] == SESSIONS.OPEN_TURN_RUNNING
    assert len(still["messages"]) == 1, "a leased turn was settled"

    await _expire(pg, sid)
    settled = await _history(pg, sid)
    assert settled["openTurn"] is None
    request, answer = settled["messages"]
    assert answer["turnId"] == turn_id and answer["role"] == "assistant"
    assert answer["turnState"] == SESSIONS.TURN_INTERRUPTED
    assert answer["artifact"]["interruption"]["cause"] == SESSIONS.CAUSE_STOPPED
    assert (await _messages(pg, sid))[:1] == request_before, "the request was rewritten"
    assert request["turnState"] == SESSIONS.TURN_INCOMPLETE
    assert await _lease(pg, sid) is None


@pytest.mark.asyncio
async def test_an_interrupted_turn_shows_its_review_and_a_retry_reuses_it(
    pg: PgDb, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SESSIONS, "WORKER_ID", "worker-that-stopped")
    sid = await _session(pg)
    first_turn = await _ask(pg, sid, "Prepare a return for the linen throw, damaged")
    review_id = await _propose(pg, first_turn)
    assert review_id is not None
    monkeypatch.setattr(SESSIONS, "WORKER_ID", "worker-now")
    await _expire(pg, sid)

    history = await _history(pg, sid)
    answer = history["messages"][-1]
    assert answer["turnState"] == SESSIONS.TURN_INTERRUPTED
    assert f"review #{review_id}, awaiting a decision" in answer["content"]
    (action,) = answer["artifact"]["proposedActions"]
    assert action["reviewId"] == review_id
    assert action["reviewSourceTurnId"] == first_turn
    assert action["tool"] == "give_store_credit"
    assert action["state"] == "review_required"
    assert action["material"] == CREDIT
    assert action["actionHash"] == REVIEW.action_fingerprint("give_store_credit", CREDIT)

    retry_turn = await _ask(pg, sid, "Prepare a return for the linen throw, damaged")
    assert await _propose(pg, retry_turn) == review_id
    reviews = await pg.rows("SELECT id, status, source_turn_id FROM pellier.approvals")
    assert reviews == [{"id": review_id, "status": "pending", "source_turn_id": first_turn}]


@pytest.mark.asyncio
async def test_readers_settling_together_append_one_answer(pg: PgDb) -> None:
    sid = await _session(pg)
    turn_id = await _ask(pg, sid)
    # A turn from before leases existed has no owner at all.
    async with pg.get_connection() as conn:
        await conn.execute(
            "UPDATE pellier.conversations SET metadata = metadata - 'active_turn'"
            " WHERE session_id = %s", (sid,),
        )
    outcomes = await asyncio.gather(*[
        SESSIONS.settle_abandoned_turns(pg, session_id=sid, customer_id=CUSTOMER)
        for _ in range(4)
    ])
    assert sorted(len(o) for o in outcomes) == [0, 0, 0, 1]
    answers = [m for m in await _messages(pg, sid) if m["role"] == "assistant"]
    assert [a["metadata"]["turn_id"] for a in answers] == [turn_id]


@pytest.mark.asyncio
async def test_lease_renewal_moves_the_expiry_forward(pg: PgDb) -> None:
    sid = await _session(pg)
    await _ask(pg, sid)
    before = (await _lease(pg, sid))["lease_until"]
    await asyncio.sleep(0.05)
    await SESSIONS.renew_lease(pg, session_id=sid)
    assert (await _lease(pg, sid))["lease_until"] > before


# ---------------------------------------------------------------------------
# The runner: turns that outlive their reader, or stop partway
# ---------------------------------------------------------------------------

def _scripted_turn(
    pg: PgDb, script: Any,
) -> Any:
    """A stand-in for `stream_turn` that saves the request, then follows `script`."""
    async def stream_turn(db: Any, **turn: str) -> AsyncIterator[Any]:
        saved = await SESSIONS.append_operator_turn(
            db, session_id=turn["session_id"], customer_id=turn["customer_id"],
            operator_sub=turn["operator_sub"], message=turn["request"],
            transport_key=turn["transport_key"],
        )
        yield "step", {"kind": "request", "status": "complete"}
        async for event in script(db, turn, saved["turnId"]):
            yield event
    return stream_turn


def _start(pg: PgDb, sid: str, key: str = "tk-1") -> RUNNER.TurnRun:
    return RUNNER.start(
        pg, customer_id=CUSTOMER, session_id=sid, operator_sub="op-1",
        request="Prepare a return for the linen throw, damaged", transport_key=key,
    )


@pytest.mark.asyncio
async def test_closing_the_stream_does_not_stop_the_turn(
    pg: PgDb, monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = asyncio.Event()

    async def script(db: Any, turn: Dict[str, str], turn_id: str) -> AsyncIterator[Any]:
        await release.wait()
        await SESSIONS.append_assistant_artifact(
            db, session_id=turn["session_id"], customer_id=CUSTOMER, turn_id=turn_id,
            summary="The throw arrived damaged.", artifact={"proposedActions": []},
        )
        yield "answer", {"summary": "The throw arrived damaged."}
        yield "complete", {"status": "complete", "turnId": turn_id}

    monkeypatch.setattr(operator_concierge, "stream_turn", _scripted_turn(pg, script))
    monkeypatch.setattr(RUNNER, "HEARTBEAT_SECONDS", 0.05)
    sid = await _session(pg)
    run = _start(pg, sid)

    reader = run.follow()
    assert (await asyncio.wait_for(reader.__anext__(), 5))[1]["kind"] == "request"
    await reader.aclose()  # the browser tab closes
    leased = (await _lease(pg, sid))["lease_until"]
    await asyncio.sleep(0.2)
    assert (await _lease(pg, sid))["lease_until"] > leased, "the lease was not renewed"
    assert (await _history(pg, sid))["openTurn"]["state"] == SESSIONS.OPEN_TURN_RUNNING

    # A reload follows the same turn from its first event.
    async def reload() -> List[str]:
        return [kind async for kind, _ in _released(run, release)]

    follower = await asyncio.wait_for(reload(), 10)
    assert follower == ["step", "answer", "complete"]
    assert run.task is not None and run.task.done()
    history = await _history(pg, sid)
    assert history["openTurn"] is None
    assert history["messages"][-1]["turnState"] == SESSIONS.TURN_COMPLETE
    assert await _lease(pg, sid) is None
    assert not RUNNER.running_here(sid, "")


async def _released(run: RUNNER.TurnRun, release: asyncio.Event) -> AsyncIterator[Any]:
    started = False
    async for event in run.follow():
        if not started:
            started = True
            release.set()
        yield event


@pytest.mark.asyncio
async def test_inflight_retry_preserves_the_client_binding(pg, monkeypatch) -> None:
    release = asyncio.Event()

    async def script(db, turn, turn_id):
        await release.wait()
        await SESSIONS.append_assistant_artifact(
            db, session_id=turn["session_id"], customer_id=CUSTOMER, turn_id=turn_id,
            summary="Done.", artifact={},
        )
        yield "complete", {"turnId": turn_id}

    monkeypatch.setattr(operator_concierge, "stream_turn", _scripted_turn(pg, script))
    sid = await _session(pg)
    run = _start(pg, sid)
    try:
        assert _start(pg, sid) is run
        with pytest.raises(SESSIONS.SessionError) as rejected:
            RUNNER.start(
                pg, customer_id="CUST-ANNA", session_id=sid, operator_sub="op-1",
                request="Prepare a return", transport_key="tk-1",
            )
        assert (rejected.value.code, rejected.value.status_code) == (
            "session_client_mismatch", 403,
        )
    finally:
        release.set()
        await _drain(run)


@pytest.mark.asyncio
async def test_a_turn_that_raises_is_settled_with_the_review_it_prepared(
    pg: PgDb, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def script(db: Any, turn: Dict[str, str], turn_id: str) -> AsyncIterator[Any]:
        await _propose(db, turn_id)
        raise RuntimeError("synthesis connection reset")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(operator_concierge, "stream_turn", _scripted_turn(pg, script))
    sid = await _session(pg)
    events = await _drain(_start(pg, sid))
    assert events[-1] == ("error", {"detail": "operator_unavailable"})

    answer = (await _history(pg, sid))["messages"][-1]
    assert answer["turnState"] == SESSIONS.TURN_INTERRUPTED
    assert answer["content"].startswith("This request hit an error")
    assert [a["reviewId"] for a in answer["artifact"]["proposedActions"]] == [
        r["id"] for r in await pg.rows("SELECT id FROM pellier.approvals")
    ]


@pytest.mark.asyncio
async def test_a_turn_past_its_deadline_is_settled(
    pg: PgDb, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def script(db: Any, turn: Dict[str, str], turn_id: str) -> AsyncIterator[Any]:
        await asyncio.sleep(30)
        yield "complete", {}

    monkeypatch.setattr(operator_concierge, "stream_turn", _scripted_turn(pg, script))
    monkeypatch.setattr(RUNNER, "TURN_DEADLINE_SECONDS", 0.3)
    sid = await _session(pg)
    events = await _drain(_start(pg, sid))
    assert events[-1] == ("error", {"detail": "turn_deadline_exceeded"})
    answer = (await _history(pg, sid))["messages"][-1]
    assert answer["artifact"]["interruption"]["cause"] == SESSIONS.CAUSE_DEADLINE


@pytest.mark.asyncio
async def test_a_stopping_worker_records_the_interruption(
    pg: PgDb, monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = asyncio.Event()

    async def script(db: Any, turn: Dict[str, str], turn_id: str) -> AsyncIterator[Any]:
        saved.set()
        await asyncio.sleep(30)
        yield "complete", {}

    monkeypatch.setattr(operator_concierge, "stream_turn", _scripted_turn(pg, script))
    sid = await _session(pg)
    run = _start(pg, sid)
    await asyncio.wait_for(saved.wait(), 5)
    assert run.task is not None
    run.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run.task
    answer = (await _history(pg, sid))["messages"][-1]
    assert answer["turnState"] == SESSIONS.TURN_INTERRUPTED
    assert answer["artifact"]["interruption"]["cause"] == SESSIONS.CAUSE_STOPPED


@pytest.mark.asyncio
async def test_the_same_request_follows_the_running_turn_and_another_waits(
    pg: PgDb, monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = asyncio.Event()

    async def script(db: Any, turn: Dict[str, str], turn_id: str) -> AsyncIterator[Any]:
        await release.wait()
        await SESSIONS.append_assistant_artifact(
            db, session_id=turn["session_id"], customer_id=CUSTOMER, turn_id=turn_id,
            summary="Done.", artifact={},
        )
        yield "complete", {"status": "complete"}

    monkeypatch.setattr(operator_concierge, "stream_turn", _scripted_turn(pg, script))
    sid = await _session(pg)
    run = _start(pg, sid, key="tk-1")
    assert _start(pg, sid, key="tk-1") is run
    with pytest.raises(SESSIONS.SessionError) as waiting:
        _start(pg, sid, key="tk-2")
    assert waiting.value.code == "turn_in_progress" and waiting.value.status_code == 409
    release.set()
    assert (await asyncio.wait_for(RUNNER.result(run), 10)) == {"status": "complete"}
    users = [m for m in await _messages(pg, sid) if m["role"] == "user"]
    assert len(users) == 1


@pytest.mark.asyncio
async def test_a_new_request_settles_the_abandoned_turn_before_it_starts(
    pg: PgDb, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def script(db: Any, turn: Dict[str, str], turn_id: str) -> AsyncIterator[Any]:
        await SESSIONS.append_assistant_artifact(
            db, session_id=turn["session_id"], customer_id=CUSTOMER, turn_id=turn_id,
            summary="Answered.", artifact={},
        )
        yield "complete", {"status": "complete", "turnId": turn_id}

    monkeypatch.setattr(operator_concierge, "stream_turn", _scripted_turn(pg, script))
    sid = await _session(pg)
    stuck = await _ask(pg, sid, "An earlier request")  # its task is gone

    final = await asyncio.wait_for(RUNNER.result(_start(pg, sid, key="tk-new")), 10)
    rows = await _messages(pg, sid)
    assert [(m["role"], m["metadata"]["turn_id"], m["metadata"]["turn_state"]) for m in rows] == [
        ("user", stuck, SESSIONS.TURN_INCOMPLETE),
        ("assistant", stuck, SESSIONS.TURN_INTERRUPTED),
        ("user", final["turnId"], SESSIONS.TURN_INCOMPLETE),
        ("assistant", final["turnId"], SESSIONS.TURN_COMPLETE),
    ]


@pytest.mark.asyncio
async def test_a_replayed_key_after_abandonment_returns_the_settled_answer(
    pg: PgDb,
) -> None:
    """The real `stream_turn`: its replay path runs no model and no evidence load."""
    sid = await _session(pg)
    stuck = await _ask(pg, sid, "Prepare a return", key="tk-lost")

    events = await _drain(RUNNER.start(
        pg, customer_id=CUSTOMER, session_id=sid, operator_sub="op-1",
        request="Prepare a return", transport_key="tk-lost",
    ))
    kinds = [kind for kind, _ in events]
    assert kinds == ["step", "answer", "complete"]
    complete = events[-1][1]
    assert complete["replayed"] is True and complete["turnId"] == stuck
    assert complete["status"] == SESSIONS.TURN_INTERRUPTED
    assert len([m for m in await _messages(pg, sid) if m["role"] == "user"]) == 1


async def _drain(run: RUNNER.TurnRun) -> List[Any]:
    async def collect() -> List[Any]:
        return [event async for event in run.follow()]

    events = await asyncio.wait_for(collect(), 10)
    if run.task is not None:
        await asyncio.gather(run.task, return_exceptions=True)
    return events


def test_the_isolated_schema_matches_the_migrations() -> None:
    """The pending-review index here is migration 020's, so the reuse proof holds."""
    migrations = Path(REVIEW.__file__).resolve().parents[3] / "scripts" / "migrations"
    index = (
        "CREATE UNIQUE INDEX IF NOT EXISTS approvals_open_per_action_idx\n"
        "    ON pellier.approvals (customer_id, tool, action_hash)\n"
        "    WHERE status = 'pending';"
    )
    assert index in (migrations / "020_operator_review.sql").read_text()
    assert index in _SCHEMA
    chat = (migrations / "007_chat_session_tables.sql").read_text()
    assert "id           SERIAL PRIMARY KEY" in chat and "metadata     JSONB" in chat
