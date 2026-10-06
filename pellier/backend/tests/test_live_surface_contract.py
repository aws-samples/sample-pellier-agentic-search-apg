"""Guard the data contract for the participant-facing surfaces.

The shopper profiles and their guided prompts are checked-in files under
``data/``, served by ``/api/personas`` and ``/api/scenarios``; the business
facts (orders, stock, tickets) are read from Aurora. The storefront may show
an explicit unavailable state, but never invents persona data.
"""

from __future__ import annotations

import json
import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "pellier" / "frontend" / "src"
BACKEND = ROOT / "pellier" / "backend"


DATA = ROOT / "data"
SCHEMA = ROOT / "scripts" / "migrations" / "001_schema.sql"
SEED = ROOT / "scripts" / "migrations" / "002_seed.sql"


def _personas() -> dict[str, dict]:
    return {p["id"]: p for p in json.loads((DATA / "personas.json").read_text())}


def _prompts() -> list[dict]:
    return json.loads((DATA / "scenarios.json").read_text())


def test_personas_and_prompts_are_checked_in_files_and_orders_come_from_aurora() -> None:
    body = (BACKEND / "app.py").read_text()
    loader = (BACKEND / "services" / "personas.py").read_text()

    assert "personas-config.json" not in body
    assert '"personas.json"' in loader and '"scenarios.json"' in body
    # The order counts on the persona cards are read, not written into the file.
    assert "FROM pellier.orders GROUP BY customer_id" in body
    for profile in _personas().values():
        assert "orders" not in profile and "membership" not in profile


def test_every_shopper_profile_names_its_customer_and_its_edit() -> None:
    personas = _personas()
    assert list(personas) == ["fresh", "marco", "anna", "theo", "jessica"]
    assert personas["fresh"]["customer_id"] is None
    assert {p["customer_id"] for p in personas.values() if p["customer_id"]} == {
        "CUST-MARCO", "CUST-ANNA", "CUST-THEO", "CUST-JESSICA",
    }
    assert {p["id"]: p["edit"] for p in personas.values()} == {
        "fresh": "fresh", "marco": "marco", "anna": "anna", "theo": "theo", "jessica": "house",
    }


def test_the_persona_file_is_the_one_persona_to_customer_map() -> None:
    """The agent tools and the Operator read persona and customer from the file."""
    from services.personas import customer_for_persona, persona_for_customer

    for persona, profile in _personas().items():
        customer = profile["customer_id"]
        assert customer_for_persona(persona) == customer
        if customer:
            assert persona_for_customer(customer) == persona
    assert customer_for_persona("Marco") == "CUST-MARCO"
    assert persona_for_customer("CUST-NOBODY") is None
    for consumer in ("services/agent_tools.py", "routes/operator.py"):
        assert "_PERSONA_CUSTOMER_IDS" not in (BACKEND / consumer).read_text(), consumer


def test_theo_and_jessica_share_a_home_in_the_files_and_in_the_seed() -> None:
    personas = _personas()
    assert personas["theo"]["shares_home_with"] == "jessica"
    assert personas["jessica"]["shares_home_with"] == "theo"
    seed = SEED.read_text()
    shared = "'22 Alder Street, Portland, OR 97214'"
    theo_rows = [line for line in seed.splitlines() if "'CUST-THEO'" in line and shared in line]
    jessica_rows = [line for line in seed.splitlines() if "'CUST-JESSICA'" in line and shared in line]
    assert len(theo_rows) == 4 and len(jessica_rows) == 5


def test_every_shoppers_required_prompts_are_their_lab_prompts() -> None:
    required: dict[str, list[str]] = {}
    for prompt in _prompts():
        if prompt["journey_role"] == "required":
            required.setdefault(prompt["persona"], []).append(prompt["prompt"])
    assert required == {
        "anna": [
            "A housewarming gift for a friend who loves slow mornings. In stock, under $100, "
            "and no candles.",
            "A gift with a watch, under $100, in stock, no candles.",
        ],
        "marco": [
            "Is the Velvet Opera Cape in stock?",
            "How many Hadley Linen Shirts are available at the Brooklyn warehouse, "
            "and what ship window is recorded?",
        ],
        "theo": [
            "Something for a slower morning routine",
            "My Wabi-Sabi Bowl arrived chipped. What is happening with my ticket?",
            "Jessica and I share an address. She sent two things back last week and "
            "hasn't heard anything. Can you check her ticket too?",
        ],
        "jessica": [
            "Please ask a person to look at a store credit for the two items I returned."
        ],
    }
    goa = next(p for p in _prompts() if "Goa" in p["prompt"])
    assert goa["persona"] == "marco" and goa["journey_role"] == "explore"
    assert all(p["journey_role"] in ("required", "explore") for p in _prompts())
    assert {p["journey_stage"] for p in _prompts()} <= {None, "establish", "exercise", "prove"}


def _seed_edits() -> dict[str, list[tuple[str, int]]]:
    """Each edit's ``(product_id, storefront_rank)`` rows, in seed order."""
    seed = SEED.read_text()
    block = seed[seed.index("WITH edit (persona_id, product_id, storefront_rank)"):]
    block = block[:block.index("UPDATE pellier.product_catalog")]
    edits: dict[str, list[tuple[str, int]]] = {}
    for edit, product_id, rank in re.findall(r"\('(\w+)', '(\d+)', (\d+)\)", block):
        edits.setdefault(edit, []).append((product_id, int(rank)))
    return edits


def test_every_edit_has_twelve_unique_existing_pieces() -> None:
    """Twelve fills complete rows at two, three, four or six cards across."""
    edits = _seed_edits()
    catalog = {str(p["id"]): p for p in json.loads((DATA / "pellier_catalog.json").read_text())}

    assert set(edits) == {p["edit"] for p in _personas().values()}
    placed: list[str] = []
    for edit, rows in edits.items():
        ids = [product_id for product_id, _rank in rows]
        assert len(ids) == 12, edit
        assert len(set(ids)) == 12, f"{edit} lists a piece twice"
        assert [rank for _id, rank in rows] == list(range(1, 13)), edit
        assert set(ids) <= set(catalog), f"{edit} lists a piece the catalog lacks"
        placed.extend(ids)
    assert len(placed) == len(set(placed)), "a piece belongs to one edit"
    # Jessica's edit keeps out the robe she sent back.
    assert "42" not in [product_id for product_id, _rank in edits["house"]]
    # Most of an edit is its own moment; the two exceptions are named in the seed.
    borrowed = sorted(
        (edit, product_id)
        for edit, rows in edits.items()
        for product_id, _rank in rows
        if catalog[product_id]["moment"] != edit
    )
    assert borrowed == [("house", "56"), ("house", "59")]


def test_storefront_persona_edits_are_ranked_in_the_seed() -> None:
    seed = SEED.read_text()
    products_route = (BACKEND / "routes" / "products.py").read_text()

    assert "SET persona_id = edit.persona_id" in seed
    assert "Expected five storefront edits of twelve pieces each" in seed
    assert "storefront_rank IS NOT NULL" in products_route
    assert "ORDER BY {order}" in products_route
    carry_all = next(p for p in _prompts() if p["prompt"] == "A considered carry-all for a long weekend.")
    assert carry_all["persona"] == "fresh" and carry_all["preview_product_id"] == "10"


def test_inventory_covers_all_hundred_products_and_matches_the_catalog() -> None:
    seed = SEED.read_text()
    assert "Expected 300 warehouse rows" in seed
    assert "disagree with their warehouse rows" in seed


def test_persona_selector_uses_editorial_personalities() -> None:
    personas = _personas()
    assert personas["marco"]["role_tag"] == "Travel, utility, leather, linen"
    assert personas["anna"]["role_tag"] == "Gifting, ceremony, silk, glass"
    assert personas["theo"]["role_tag"] == "Slow living, craft, stoneware, natural materials"


def test_persona_blurbs_are_plain_sentences() -> None:
    """Anna's blurb is a sentence and never uses "search" as a noun (VOICE.md)."""
    personas = _personas()
    assert personas["anna"]["blurb"] == (
        "Buys for others: partner, mother, friends. Lately she shops for milestones."
    )
    for profile in personas.values():
        assert "search" not in profile["blurb"].lower()
        assert profile["blurb"].endswith(".")


def test_persona_hero_descriptions_match_the_refreshed_scenes() -> None:
    """Copied verbatim from the image refresh report; no maker's hands, no rib tool."""
    personas = _personas()
    assert personas["fresh"]["hero_alt"] == (
        "A leather weekender on an oak bench beside a linen throw, a wooden bowl and a "
        "stoneware vase of olive branches"
    )
    assert personas["marco"]["hero_alt"] == (
        "A cognac leather holdall and a folded linen shirt on a short oak bench against a "
        "plain white wall"
    )
    assert personas["anna"]["hero_alt"] == (
        "A white gift box tied with a blush-pink ribbon, a blank kraft tag and a vase with "
        "one eucalyptus stem on a small oak side table"
    )
    assert personas["theo"]["hero_alt"] == (
        "A charcoal stoneware bowl holding a beeswax taper beside folded linen on a small "
        "oak side table"
    )


def test_persona_heroes_use_fixed_approved_images() -> None:
    """The persona files carry the approved scenes; the home hero carries none.

    The direction A home opens with the statement and the Ask Pellier bar,
    not a photograph, so the hero reads no scene metadata at all. The
    approved images stay for the persona cover inside Ask Pellier.
    """
    personas = _personas()
    hero = (FRONTEND / "components" / "PellierHero.tsx").read_text()
    chat_body = (FRONTEND / "components" / "PellierChatBody.tsx").read_text()

    for persona in ("marco", "anna", "theo"):
        assert personas[persona]["hero_image"] == f"/products/hero-{persona}.png"
    assert 'data-testid="persona-hero-image"' not in hero
    assert "hero_image" not in hero
    assert "persona.hero_image" in chat_body


def test_voice_transcription_is_not_shipped_when_no_voice_control_exists() -> None:
    app = (BACKEND / "app.py").read_text()
    chat = (FRONTEND / "components" / "ChatDrawer.tsx").read_text()
    hero = (FRONTEND / "components" / "PellierHero.tsx").read_text()

    assert "transcribe_router" not in app
    assert "useVoiceSearch" not in chat
    assert "useVoiceSearch" not in hero
    assert not (BACKEND / "routes" / "transcribe.py").exists()
    assert not (FRONTEND / "hooks" / "useVoiceSearch.ts").exists()
