#!/usr/bin/env python3
"""Check the participant's plan fallback locally; no AWS or database calls.

This proves plan preservation and compiled predicate continuity, not deployed
retrieval or database enforcement. Retain the live Anna receipt separately.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_plan_module(path: Path):
    spec = importlib.util.spec_from_file_location("pellier_lab2_plan", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check(module) -> dict:
    original = module.SearchPlan(
        intent="A housewarming gift under $100, in stock, no candles; prefer minimalist",
        hard=module.HardConstraints(price_max_usd=100, in_stock_only=True),
        soft=module.SoftPreferences(tags=("minimalist",), soft_signal="housewarming"),
        exclusions=("candles",),
    )
    before = original.to_dict()
    results = []

    def record(name, passed):
        results.append({"check": name, "passed": bool(passed)})

    try:
        attempts = original.relaxation_ladder()
        record("fallback exists", len(attempts) == 2)
        record("original request unchanged", original.to_dict() == before)
        expected_predicates = original.compile_predicates(include_soft=False)
        for i, attempt in enumerate(attempts):
            record(f"attempt {i}: original hard requirements", attempt.hard == original.hard)
            record(f"attempt {i}: original exclusions", attempt.exclusions == original.exclusions)
            record(f"attempt {i}: original SQL eligibility", attempt.compile_predicates(include_soft=False) == expected_predicates)
            record(f"attempt {i}: request and evidence settings", (
                attempt.intent == original.intent and attempt.top_k == original.top_k
                and attempt.retrieval_strategy == original.retrieval_strategy
                and attempt.evidence_required == original.evidence_required
                and attempt.ambiguous == original.ambiguous
                and attempt.relaxation_policy == original.relaxation_policy
            ))
        if len(attempts) == 2:
            first, fallback = attempts
            record("first attempt keeps the preference", first.soft == original.soft and not first.relaxations)
            record("fallback changes only the declared preference", not fallback.soft.tags and fallback.soft.soft_signal == original.soft.soft_signal)
            record("fallback records what changed", len(fallback.relaxations) == 1 and fallback.relaxations[0].step == "drop_tags" and fallback.relaxations[0].dropped == original.soft.tags)
        strict = module.SearchPlan(hard=original.hard, intent="strict", soft=original.soft, exclusions=original.exclusions, relaxation_policy="strict")
        record("strict request has no fallback", len(strict.relaxation_ladder()) == 1)
        no_preference = module.SearchPlan(intent="plain", hard=original.hard, exclusions=original.exclusions)
        record("no preference means no widening", len(no_preference.relaxation_ladder()) == 1)
    except Exception as exc:
        record("fallback completed", False)
        return {"passed": False, "checks": results, "error": str(exc), "scope": "local plan contract; no live services"}
    return {"passed": all(r["passed"] for r in results), "checks": results, "scope": "local plan contract; no live services"}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    report = check(load_plan_module(ROOT / "pellier/backend/services/search_plan.py"))
    for row in report["checks"]:
        print(f"{'PASS' if row['passed'] else 'FAIL'}: {row['check']}")
    if report.get("error"):
        print(report["error"])
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    print("Local plan contract passed" if report["passed"] else "Local plan contract failed")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
