"""Theo's required ticket request is written in three places; they must agree.

Migration 056 seeds it for the live request rails, the frontend names it as a
required prompt, and the Lab 3 proof card's fallback replays it through the
AgentCore CLI. A wording change in one place would leave a participant running
a request the other two do not recognise.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MIGRATION = REPO / "scripts/migrations/056_align_required_lab_requests.sql"
JOURNEYS = REPO / "pellier/frontend/src/data/workshopJourneys.ts"
OBSERVATORY = REPO / "pellier/backend/routes/observatory.py"


def _seeded_ticket_request() -> str:
    match = re.search(
        r"SET prompt = '([^']+)',\s*journey_stage = 'exercise'",
        MIGRATION.read_text(encoding="utf-8"),
    )
    assert match, "migration 056 no longer seeds Theo's required ticket request"
    return match.group(1)


def test_frontend_required_prompt_matches_the_seeded_request() -> None:
    source = JOURNEYS.read_text(encoding="utf-8")
    block = re.search(r"WORKSHOP_REQUIRED_PROMPTS[^=]*=\s*\{(.*?)\n\}", source, re.S)
    assert block, "WORKSHOP_REQUIRED_PROMPTS not found"
    theo = re.search(r"theo:\s*\[(.*?)\n\s*\],", block.group(1), re.S)
    assert theo, "Theo has no required prompts"
    assert f"'{_seeded_ticket_request()}'" in theo.group(1)


def test_proof_card_fallback_replays_the_seeded_request() -> None:
    source = OBSERVATORY.read_text(encoding="utf-8")
    assert f'--prompt \\"{_seeded_ticket_request()}\\"' in source
