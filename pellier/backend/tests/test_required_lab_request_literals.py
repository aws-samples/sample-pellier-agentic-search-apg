"""Theo's required ticket request is written in two places; they must agree.

``data/scenarios.json`` holds it for the home page's suggestion row, and the
frontend names it as a required prompt. A wording change in one place would
leave a participant running a request the other does not recognise.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCENARIOS = REPO / "data/scenarios.json"
JOURNEYS = REPO / "pellier/frontend/src/data/workshopJourneys.ts"


def _seeded_ticket_request() -> str:
    prompts = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    (ticket,) = [p for p in prompts if p["persona"] == "theo" and p["preview_product_id"] == "37"]
    assert ticket["journey_role"] == "required"
    return ticket["prompt"]


def test_frontend_required_prompt_matches_the_seeded_request() -> None:
    source = JOURNEYS.read_text(encoding="utf-8")
    block = re.search(r"WORKSHOP_REQUIRED_PROMPTS[^=]*=\s*\{(.*?)\n\}", source, re.S)
    assert block, "WORKSHOP_REQUIRED_PROMPTS not found"
    theo = re.search(r"theo:\s*\[(.*?)\n\s*\],", block.group(1), re.S)
    assert theo, "Theo has no required prompts"
    assert f"'{_seeded_ticket_request()}'" in theo.group(1)
