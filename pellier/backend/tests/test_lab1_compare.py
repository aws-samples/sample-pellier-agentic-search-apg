"""Lab 1B's verdict judges what the shopper asked for against what the answering search kept.

Pure over a receipt and catalog rows, so every edge runs offline here;
``tests/test_lab1_starter_failure.py`` runs it on the real schema against the
starter and the solution.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab1 = importlib.import_module("lab1_compare")

ASKED = {"hard_constraints": {"price_max_usd": 100, "in_stock_only": True, "categories": []},
         "exclusions": ["candle"]}
KEPT = {"price_max_usd": 100, "in_stock_only": True, "categories": []}
FELL_BACK = [{"step": "drop_tags", "dropped": ["slow"]}]


def _receipt(*, requested: Optional[Dict[str, Any]] = ASKED, kept: Optional[Dict] = None,
             exclusions: Optional[List[str]] = None,
             relaxations: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    config = {"requested": requested} if requested is not None else {}
    return {"receipt_id": 7, "session_id": "persona-anna-x", "created_at": "now",
            "query_preview": "gift", "retrieval_config": json.dumps(config),
            "hard_constraints": kept if kept is not None else KEPT,
            "exclusions": ["candle"] if exclusions is None else exclusions,
            "relaxations": FELL_BACK if relaxations is None else relaxations}


def _judge(receipt: Dict[str, Any], broken: Optional[List[str]] = None):
    return lab1._judge(receipt, lab1.requested_limits(receipt), ["22", "28"], broken or [])


def test_kept_limits_after_the_fallback_prove_it() -> None:
    finding = _judge(_receipt())
    assert finding.state == "PROVED"
    assert finding.observed == "all 2 keep under $100, in stock, no candles after the fallback"
    assert "the shopper asked: under $100, in stock, no candles" in finding.evidence


def test_a_dropped_limit_is_named_and_blames_the_fallback() -> None:
    lost = {"price_max_usd": None, "in_stock_only": False, "categories": []}
    finding = _judge(_receipt(kept=lost, exclusions=[]))
    assert finding.state == "CONTRADICTED"
    assert finding.observed.endswith("dropped under $100, in stock, no candles")
    assert "_with_relaxations" in finding.next_step


@pytest.mark.parametrize("requested, observed", [
    ({"hard_constraints": {"price_max_usd": None, "in_stock_only": False, "categories": []},
      "exclusions": []}, "the request stated no limit, so there was nothing to keep"),
    (None, "the receipt does not record what the shopper asked"),
])
def test_a_request_with_nothing_to_keep_asks_for_the_guides_request(requested, observed) -> None:
    """Anna's chip used to state no limit; a fix must not read CONTRADICTED for it."""
    finding = _judge(_receipt(requested=requested, kept={}, exclusions=[]))
    assert finding.state == "NOT YET"
    assert finding.observed == observed
    assert lab1.ANNA_REQUEST in finding.next_step


def test_a_first_pass_answer_is_not_yet_and_does_not_blame_the_fallback() -> None:
    finding = _judge(_receipt(relaxations=[]), ["80 Sunday Morning Candle is excluded candle"])
    assert finding.state == "NOT YET"
    assert finding.observed.startswith("the first search answered, so the fallback never ran")
    assert "_with_relaxations" not in finding.next_step


def test_only_the_limits_asked_for_are_judged() -> None:
    """A request with only an exclusion is not failed for a budget nobody stated."""
    wool = {"hard_constraints": {"price_max_usd": None, "in_stock_only": False,
                                 "categories": []}, "exclusions": ["wool"]}
    limits = lab1.requested_limits(_receipt(requested=wool))
    pricey = {"price": 240, "quantity": 0, "category": "Home", "tags": ["warm"],
              "materials": ["wool"]}
    assert lab1.product_breaks(pricey, limits) == ["excluded wool"]
    finding = _judge(_receipt(requested=wool, kept={}, exclusions=["wool"]))
    assert finding.state == "PROVED", finding


def test_a_department_the_answer_widened_is_dropped() -> None:
    home = {"hard_constraints": {"price_max_usd": None, "in_stock_only": False,
                                 "categories": ["Home"]}, "exclusions": []}
    requested = lab1.requested_limits(_receipt(requested=home))
    assert lab1.dropped(requested, lab1.limits_of({"categories": []}, [])) == ["home only"]
    assert lab1.dropped(requested, lab1.limits_of({"categories": ["Home"]}, [])) == []
    away = {"price": 10, "quantity": 1, "category": "Bath and body", "tags": [], "materials": []}
    assert lab1.product_breaks(away, requested) == ["in Bath and body"]


def test_the_guides_request_is_annas_first_suggestion() -> None:
    prompts = json.loads((REPO / "data" / "scenarios.json").read_text(encoding="utf-8"))
    anna = sorted((p for p in prompts if p["persona"] == "anna"), key=lambda p: p["ordinal"])
    assert anna[0]["prompt"] == lab1.ANNA_REQUEST
    assert anna[0]["journey_role"] == "required"
