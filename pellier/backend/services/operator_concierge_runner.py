"""Concierge turns run apart from the request that started them.

A turn used to run inside the HTTP response that streamed it. Closing the tab, a
proxy timeout, or a reload cancelled that response at whatever it was waiting on,
so the operator's request stayed saved and its answer was never written. The
conversation then showed an ``incomplete`` turn that nothing would ever finish, and
the composer stayed locked behind it.

Now each turn is a task this worker owns. A response only reads the task's events,
so a disconnect stops the reading and never the work, and a reload can follow the
same turn again. While the task runs, a lease on the conversation says so. When it
ends without an answer, or its worker disappears and the lease lapses, the turn is
settled: an ``interrupted`` answer records what the turn left behind, and the
session takes requests again.

    running    this worker has the task, or another worker's lease is unexpired
    abandoned  no task here and no live lease: settled on the next read or request
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple

from services import operator_concierge_sessions as sessions

logger = logging.getLogger(__name__)

# A third of the lease, so two renewals can fail before a reader may settle the turn.
HEARTBEAT_SECONDS = 10
# Longer than any measured turn and shorter than the browser's five-minute stream
# deadline, so a stuck turn is settled here before the browser gives up on it.
TURN_DEADLINE_SECONDS = 240
# How long a stopping worker spends recording that its turn was interrupted.
_SETTLE_ON_STOP_SECONDS = 5

Event = Tuple[str, Dict[str, Any]]


class TurnRun:
    """One turn's work and the events it has produced, for any number of readers."""

    def __init__(self, *, session_id: str, customer_id: str, transport_key: str) -> None:
        self.session_id = session_id
        self.customer_id = customer_id
        self.transport_key = transport_key
        self.events: List[Event] = []
        self.error: Optional[sessions.SessionError] = None
        self.saved = False
        self.done = False
        self.task: Optional[asyncio.Task[None]] = None
        self._readers: Set[asyncio.Queue[Optional[Event]]] = set()

    def publish(self, kind: str, data: Dict[str, Any]) -> None:
        self.events.append((kind, data))
        for queue in self._readers:
            queue.put_nowait((kind, data))

    def close(self) -> None:
        self.done = True
        for queue in self._readers:
            queue.put_nowait(None)

    async def follow(self) -> AsyncIterator[Event]:
        """Every event so far, then each new one until the turn ends.

        A reader that leaves early, such as a closed tab, removes only itself.
        """
        queue: asyncio.Queue[Optional[Event]] = asyncio.Queue()
        for event in self.events:
            queue.put_nowait(event)
        if self.done:
            queue.put_nowait(None)
        else:
            self._readers.add(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
        finally:
            self._readers.discard(queue)


# One run per session. A session holds at most one open turn, so the session names it.
_RUNS: Dict[str, TurnRun] = {}


def running_here(session_id: str, _turn_id: str) -> bool:
    """Whether this worker is running the session's open turn.

    A run that has not saved its request yet counts as well. It is about to answer
    or settle whatever turn it finds, and a reader that waits one more poll for it
    loses nothing.
    """
    run = _RUNS.get(session_id)
    return run is not None and not run.done


def start(
    db: Any,
    *,
    customer_id: str,
    session_id: str,
    operator_sub: str,
    request: str,
    transport_key: str = "",
) -> TurnRun:
    """Start a turn, or return the run already working on this same request.

    A network retry of the request in flight carries the same transport key and
    follows the first attempt. Any other request waits for it.
    """
    current = _RUNS.get(session_id)
    if current is not None and not current.done:
        if customer_id != current.customer_id:
            raise sessions.SessionError("session_client_mismatch", 403)
        if transport_key and transport_key == current.transport_key:
            return current
        raise sessions.SessionError("turn_in_progress", 409)

    run = TurnRun(
        session_id=session_id, customer_id=customer_id, transport_key=transport_key,
    )
    _RUNS[session_id] = run
    run.task = asyncio.create_task(
        _drive(
            run, db,
            customer_id=customer_id,
            session_id=session_id,
            operator_sub=operator_sub,
            request=request,
            transport_key=transport_key,
        ),
        name=f"concierge-turn-{session_id}",
    )
    return run


async def result(run: TurnRun) -> Dict[str, Any]:
    """The turn's final payload, or the error that ended it."""
    final: Dict[str, Any] = {}
    async for kind, data in run.follow():
        if kind == "complete":
            final = data
    if not final and run.error is not None:
        raise run.error
    return final


async def load_settled_history(
    db: Any, *, session_id: str, customer_id: str, limit: int = 40
) -> Dict[str, Any]:
    """The conversation, with any turn whose worker is gone settled first.

    A running turn is reported as running, so the reader can wait for it. Reading is
    what settles an abandoned one, because a restarted worker leaves nothing behind
    that could do it. If settling fails, the history is returned as it stands and
    still says the turn was abandoned.
    """
    history = await sessions.load_history(
        db, session_id=session_id, customer_id=customer_id, limit=limit,
        running_here=running_here,
    )
    open_turn = history.get("openTurn") or {}
    if open_turn.get("state") != sessions.OPEN_TURN_ABANDONED:
        return history
    try:
        await sessions.settle_abandoned_turns(
            db, session_id=session_id, customer_id=customer_id,
            running_here=running_here,
        )
    except sessions.SessionError:
        raise
    except Exception as exc:  # noqa: BLE001 - the unsettled history is still true
        logger.warning("Concierge turn %s could not be settled: %s",
                       open_turn.get("turnId"), exc)
        return history
    return await sessions.load_history(
        db, session_id=session_id, customer_id=customer_id, limit=limit,
        running_here=running_here,
    )


async def _renew(db: Any, session_id: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            await sessions.renew_lease(db, session_id=session_id)
        except Exception as exc:  # noqa: BLE001 - the next renewal may succeed
            logger.warning("Concierge lease renewal failed for %s: %s", session_id, exc)


async def _consume(run: TurnRun, db: Any, turn: Dict[str, str]) -> None:
    from services import operator_concierge

    heartbeat: Optional[asyncio.Task[None]] = None
    try:
        async for kind, data in operator_concierge.stream_turn(db, **turn):
            if not run.saved:
                # The first event follows the saved request and the lease it wrote.
                run.saved = True
                heartbeat = asyncio.create_task(_renew(db, turn["session_id"]))
            run.publish(kind, data)
    finally:
        if heartbeat is not None:
            heartbeat.cancel()


async def _work(run: TurnRun, db: Any, turn: Dict[str, str]) -> None:
    try:
        await _consume(run, db, turn)
    except sessions.OpenTurnError:
        # An earlier turn in this session has no answer. Settle it when no worker
        # owns it, then try once more. Refused again, it is still running elsewhere.
        await sessions.settle_abandoned_turns(
            db, session_id=turn["session_id"], customer_id=turn["customer_id"],
        )
        await _consume(run, db, turn)


async def _settle(db: Any, turn: Dict[str, str], cause: str) -> None:
    try:
        await sessions.settle_abandoned_turns(
            db, session_id=turn["session_id"], customer_id=turn["customer_id"],
            cause=cause,
        )
    except Exception as exc:  # noqa: BLE001 - the lease lapses and a reader settles it
        logger.warning("Concierge turn in %s not settled on %s: %s",
                       turn["session_id"], cause, exc)


async def _drive(run: TurnRun, db: Any, **turn: str) -> None:
    cause = ""
    try:
        await asyncio.wait_for(_work(run, db, turn), TURN_DEADLINE_SECONDS)
    except asyncio.CancelledError:
        # The worker is stopping. Record the interruption if there is still time;
        # otherwise the lease lapses and the next reader settles the turn.
        if run.saved:
            try:
                await asyncio.wait_for(
                    asyncio.shield(_settle(db, turn, sessions.CAUSE_STOPPED)),
                    _SETTLE_ON_STOP_SECONDS,
                )
            except BaseException as exc:  # noqa: BLE001 - stopping regardless
                logger.warning("Concierge turn in %s left for its lease to settle: %r",
                               turn["session_id"], exc)
        _finish(run)
        raise
    except asyncio.TimeoutError:
        run.error = sessions.SessionError("turn_deadline_exceeded", 504)
        cause = sessions.CAUSE_DEADLINE
    except sessions.SessionError as exc:
        run.error = exc
        cause = sessions.CAUSE_ERROR
    except Exception:  # noqa: BLE001 - reported to the reader and settled below
        logger.exception("Concierge turn failed in %s", turn["session_id"])
        run.error = sessions.SessionError("operator_unavailable", 500)
        cause = sessions.CAUSE_ERROR

    # A request refused before it was saved left nothing to settle.
    if cause and run.saved:
        await _settle(db, turn, cause)
    if run.error is not None:
        run.publish("error", {"detail": run.error.code})
    _finish(run)


def _finish(run: TurnRun) -> None:
    if _RUNS.get(run.session_id) is run:
        del _RUNS[run.session_id]
    run.close()
