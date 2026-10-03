"""
Standalone router exerciser.

Usage:

    # Run all canonical Phase-2 test cases and print a summary
    .venv/bin/python -m skills.router_test

    # Route a single message
    .venv/bin/python -m skills.router_test "a linen piece for slow Sundays"

The tool reads skills from the default /skills/ directory, constructs
a ``SkillRouter``, and prints the ``RouterDecision`` in a readable
format — what loaded, what was considered with reasons, elapsed ms.

Test cases are grounded in the curated Pellier catalog.
Each case pairs a query against the skill(s) we expect to load, with
a short rationale the router should agree with.
"""
from __future__ import annotations

import sys

from .loader import load_registry


# Catalog-grounded canonical test cases. Each tuple is
# ``(query, expected_skills_set, rationale)`` where rationale is a
# human note about why this case demonstrates the skill contract.
#
# Actual runtime skills:
#   - the-packing-list: travel packing, warm-weather capsules, repeat wear
#   - the-gift-table: gift intent, milestones, housewarming, budgets
#   - the-makers-shelf: ceramics, textiles, slow-craft home goods
#   - the-care-card: returns, damage, repair, care, post-purchase handling
#   - the-proof-counter: proof, memory, audit receipts, trace inspection
# Negative cases:
#   - inventory / pricing / policy / spec-sheet factual queries
TEST_CASES: list[tuple[str, set[str], str]] = [
    # --- Single-skill positives --------------------------------------------
    (
        "what should I pack for 10 days in Lisbon with only a carry-on?",
        {"the-packing-list"},
        "Travel packing ask — packable, repeat-wear pieces belong to The Packing List.",
    ),
    (
        "housewarming gift under $80",
        {"the-gift-table"},
        "Gift intent + housewarming + budget — The Gift Table should frame the occasion.",
    ),
    (
        "hand-thrown ceramic pieces for a morning coffee ritual",
        {"the-makers-shelf"},
        "Ceramics + ritual language — The Maker's Shelf should lead with material/process.",
    ),
    (
        "the bowl arrived damaged, what now?",
        {"the-care-card"},
        "Damaged-item post-purchase handling belongs to The Care Card.",
    ),
    (
        "how do you know this fits my taste?",
        {"the-proof-counter"},
        "Proof / memory explanation should load The Proof Counter.",
    ),

    # --- Multi-skill positives ----------------------------------------------
    (
        "housewarming gift for a friend who loves handmade ceramics, around $200",
        {"the-gift-table", "the-makers-shelf"},
        "Housewarming gift plus handmade ceramics should load gift framing and craft knowledge.",
    ),
    (
        "a gift for my partner's anniversary that packs well for a weekend trip",
        {"the-gift-table", "the-packing-list"},
        "Gift milestone plus travel/packing constraints should load both relevant overlays.",
    ),
    (
        "packable linen outfit for warm evenings in Lisbon",
        {"the-packing-list"},
        "Travel + packable + warm-weather capsule language belongs to The Packing List.",
    ),

    # --- Negatives: transactional / factual --------------------------------
    (
        "is the Italian Linen Camp Shirt in stock?",
        set(),
        "Inventory question against a real Editor's Pick ($128). Neither skill "
        "applies — spec-sheet lookups stay with the base tool path.",
    ),
    (
        "how do I return an order?",
        {"the-care-card"},
        "Return-policy handling should load The Care Card.",
    ),
    (
        "what's the Linen Duvet Cover made of?",
        set(),
        "Factual spec-sheet query against a real Home product ($248 Flax). "
        "Material lookup alone should stay with the base agent/tool result.",
    ),
    (
        "what's the cheapest bag you have?",
        set(),
        "Pricing / filter query — no description needed, no gift signal. "
        "Answer: Leather Pouch or Canvas Market Tote at $88.",
    ),
]


def _print_decision(message: str, decision, expected: set[str], rationale: str = "") -> bool:
    """Pretty-print one routing decision. Return True if it matches ``expected``."""
    got = set(decision.loaded_skills)
    match = got == expected

    status = "✓" if match else "✗"
    print(f"\n{status} {message!r}")
    if rationale:
        print(f"  why:       {rationale}")
    print(f"  elapsed:   {decision.elapsed_ms}ms")
    print(f"  loaded:    {sorted(decision.loaded_skills) or '(none)'}")
    if expected != got:
        print(f"  expected:  {sorted(expected) or '(none)'}")

    if decision.considered:
        print("  considered:")
        for item in decision.considered:
            print(f"    - {item['name']}: {item['reason']}")

    if not match and decision.raw_response:
        print("  raw:")
        for line in decision.raw_response.splitlines()[:6]:
            print(f"    {line}")

    return match


def _run_suite() -> int:
    """Run the canonical catalog-grounded test cases. Returns failure count."""
    from .router import SkillRouter

    registry = load_registry()
    if len(registry) == 0:
        print("No skills loaded — nothing to test.")
        return 1

    print(f"Loaded {len(registry)} skills: {[s.name for s in registry.get_all()]}")

    router = SkillRouter(registry)

    print("\n" + "=" * 72)
    print(f"Routing {len(TEST_CASES)} catalog-grounded test cases")
    print("=" * 72)

    fails = 0
    total_ms = 0
    for message, expected, rationale in TEST_CASES:
        decision = router.route(message)
        total_ms += decision.elapsed_ms
        ok = _print_decision(message, decision, expected, rationale)
        if not ok:
            fails += 1

    print("\n" + "=" * 72)
    passed = len(TEST_CASES) - fails
    print(
        f"Result: {passed}/{len(TEST_CASES)} passed · total {total_ms}ms · "
        f"avg {total_ms // max(1, len(TEST_CASES))}ms/call"
    )
    print("=" * 72)
    return fails


def _run_single(message: str) -> int:
    """Route a single ad-hoc message."""
    from .router import SkillRouter

    registry = load_registry()
    router = SkillRouter(registry)
    decision = router.route(message)

    print(f"\nRouting: {message!r}")
    print(f"elapsed:    {decision.elapsed_ms}ms")
    print(f"loaded:     {decision.loaded_skills or '(none)'}")
    if decision.considered:
        print("considered:")
        for item in decision.considered:
            print(f"  - {item['name']}: {item['reason']}")
    if decision.raw_response:
        print("\nraw response:")
        print(decision.raw_response)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(_run_single(" ".join(sys.argv[1:])))
    sys.exit(1 if _run_suite() > 0 else 0)
