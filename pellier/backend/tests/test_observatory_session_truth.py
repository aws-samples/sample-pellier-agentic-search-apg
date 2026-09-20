"""Truth contracts for durable Observatory session summaries."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

from routes import observatory


class _ReplayStubDB:
    """Answers the three reads ``get_session`` makes, keyed by query shape.

    ``claimed`` decides whether ``governed_turn_receipts`` holds a turn taken
    by an identified principal, which is the only fact the anonymous branch
    consults.
    """

    def __init__(self, claimed: bool) -> None:
        self.claimed = claimed

    async def fetch_all(self, query: str, *params: Any) -> list[dict]:
        if 'AS "openingQuery"' in query:
            return [
                {
                    "id": "sess-1",
                    "personaId": "marco",
                    "openingQuery": "linen for Goa",
                    "elapsedMs": 1200,
                    "agentCount": 1,
                    "routingPattern": "Storefront Dispatcher",
                    "timestamp": datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc),
                    "status": "complete",
                }
            ]
        return []

    async def fetch_one(self, query: str, *params: Any) -> Optional[dict]:
        if "COALESCE(principal_sub, '') <> ''" in query:
            return {"claimed": 1} if self.claimed else None
        return None


def _replay_as_anonymous(*, claimed: bool) -> Optional[HTTPException]:
    """Call ``get_session`` with no user and return the refusal, if any."""
    import app

    original = getattr(app, "db_service", None)
    app.db_service = _ReplayStubDB(claimed)
    try:
        asyncio.run(observatory.get_session("sess-1", user=None))
    except HTTPException as exc:
        return exc
    finally:
        app.db_service = original
    return None



def test_opening_query_uses_the_first_audit_row_not_lexical_maximum() -> None:
    """A receipt must not call the alphabetically largest trace the opening turn."""
    source = (
        Path(__file__).resolve().parents[1] / "routes" / "observatory.py"
    ).read_text()

    # Both list and detail use the same chronologically deterministic subquery.
    assert source.count("ORDER BY first_audit.created_at ASC, first_audit.audit_id ASC") == 2
    assert 'max(COALESCE(\n                    NULLIF(ta.args->>\'query\'' not in source


def test_authenticated_session_replay_rejects_mixed_principals() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "routes" / "observatory.py"
    ).read_text()

    # Another identified principal makes the session foreign. An anonymous
    # turn does not: a shopper who signed in mid-session must not be locked
    # out of their own replay by the turn they took before signing in.
    assert "foreign_turn.principal_sub IS NOT NULL" in source
    assert "AND foreign_turn.principal_sub <> %s" in source
    assert "foreign_turn.principal_sub IS DISTINCT FROM %s" not in source
    assert "raise_on_error=True" in source


def test_anonymous_session_replay_refuses_a_claimed_session() -> None:
    """A signed-out reader must not open a named shopper's replay.

    The signed-in branch already refused a session that any other principal
    had touched. The signed-out branch had no check at all, so the stricter
    rule applied only to callers who had proved who they were: an anonymous
    request for a guessed session id returned the shopper's own words, every
    tool argument, and the ledger.
    """
    refused = _replay_as_anonymous(claimed=True)
    assert refused.status_code == 404
    # The same 404 the authenticated branch raises, so a probe cannot tell
    # "not yours" from "does not exist".
    assert refused.detail == observatory.OBSERVATORY_COPY[
        "SESSION_EVIDENCE_NOT_FOUND"
    ]


def test_anonymous_session_replay_still_opens_an_unclaimed_session() -> None:
    """The storefront runs signed out, and the Observatory must stay usable.

    A session no identified principal has taken a turn in is anonymous in
    fact, not merely in the absence of a token, so it stays readable.
    """
    assert _replay_as_anonymous(claimed=False) is None
