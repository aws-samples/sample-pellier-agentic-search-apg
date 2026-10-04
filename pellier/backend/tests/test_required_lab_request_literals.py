"""Theo's required ticket request is written in two places; they must agree.

Migration 057 seeds it for the live request rails and the home page's
suggestion row, and the frontend names it as a required prompt. A wording
change in one place would leave a participant running a request the other
does not recognise.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MIGRATION = REPO / "scripts/migrations/057_shopper_sign_in_edits.sql"
JOURNEYS = REPO / "pellier/frontend/src/data/workshopJourneys.ts"


def _seeded_ticket_request() -> str:
    match = re.search(
        r"SET prompt = '([^']+)',\s*preview_product_id = '37'",
        MIGRATION.read_text(encoding="utf-8"),
    )
    assert match, "migration 057 no longer seeds Theo's required ticket request"
    return match.group(1)


def test_frontend_required_prompt_matches_the_seeded_request() -> None:
    source = JOURNEYS.read_text(encoding="utf-8")
    block = re.search(r"WORKSHOP_REQUIRED_PROMPTS[^=]*=\s*\{(.*?)\n\}", source, re.S)
    assert block, "WORKSHOP_REQUIRED_PROMPTS not found"
    theo = re.search(r"theo:\s*\[(.*?)\n\s*\],", block.group(1), re.S)
    assert theo, "Theo has no required prompts"
    assert f"'{_seeded_ticket_request()}'" in theo.group(1)
