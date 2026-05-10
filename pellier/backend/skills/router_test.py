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

Test cases are grounded in the actual 92-product Pellier catalog
(run ``_catalog_inspect.py`` before retiring if the catalog changes).
Each case pairs a query against the skill(s) we expect to load, with
a short rationale the router should agree with.
"""
from __future__ import annotations

import sys

from .loader import load_registry
from .router import SkillRouter


# Catalog-grounded canonical test cases. Each tuple is
# ``(query, expected_skills_set, rationale)`` where rationale is a
# human note about why this case demonstrates the skill contract.
#
# Style-advisor triggers:
#   - recommending / describing a piece in catalog language
# Gift-concierge triggers:
#   - the purchase is for someone else, especially with an occasion
# Negative cases:
#   - inventory / pricing / policy / spec-sheet factual queries
TEST_CASES: list[tuple[str, set[str], str]] = [
    # --- Single-skill positives --------------------------------------------
    (
        "a linen piece for slow Sundays",
        {"style-advisor"},
        "Self-purchase, descriptive brief — matches 'Linen Camp Shirt (Sage)' "
        "or 'Wide-Leg Linen Trousers'; style-advisor shapes voice.",
    ),
    (
        "something to wear for warm evenings out",
        {"style-advisor"},
        "Evening-tag territory — Silk Slip Midi, Sundress in Washed Linen, "
        "Cashmere-Blend Cardigan. Recommendation request, no gift signal.",
    ),
    (
        "what goes with the Cashmere-Blend Cardigan?",
        {"style-advisor"},
        "Styling question against a real product (the cardigan is catalog row "
        "in Outerwear, $158 Forest). 'What goes with' is classic style-advisor.",
    ),

    # --- Two-skill positives (gift + style) --------------------------------
    (
        "gift for my mom's 60th, around $200",
        {"style-advisor", "gift-concierge"},
        "Milestone gift in the $150-$250 band — Silk Slip Midi ($228), "
        "Knit Column Dress ($198), Saddle Bag ($348 stretch). Both skills apply.",
    ),
    (
        "something my partner would love for our anniversary",
        {"style-advisor", "gift-concierge"},
        "Milestone gift with no product named — Silk Scarf ($148), Brass Cuff "
        "($88), or evening dresses. Both voice and gift logic needed.",
    ),
    (
        "housewarming gift under $80",
        {"style-advisor", "gift-concierge"},
        "Casual gift, Home category — Soy Candle ($58), Linen Napkin Set ($68), "
        "Ceramic Vase ($78). Gift-concierge for occasion etiquette; style-advisor "
        "for editorial voice.",
    ),

    # --- Negatives: transactional / factual --------------------------------
    (
        "is the Italian Linen Camp Shirt in stock?",
        set(),
        "Inventory question against a real Editor's Pick ($128). Neither skill "
        "applies — the spec-sheet negative on style-advisor kicks in.",
    ),
    (
        "how do I return an order?",
        set(),
        "Policy query — support agent territory, no skills load.",
    ),
    (
        "what's the Linen Duvet Cover made of?",
        set(),
        "Factual spec-sheet query against a real Home product ($248 Flax). "
        "Style-advisor negative bullet explicitly excludes material questions.",
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
