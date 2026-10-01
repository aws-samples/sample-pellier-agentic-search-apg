"""Guard the live-data contract for the participant-facing surfaces.

The storefront and Observatory may display an explicit unavailable/empty
state, but they must never replace a failed Aurora/API read with browser
fixtures or locally fabricated persona data.
"""

from __future__ import annotations

import asyncio
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "pellier" / "frontend" / "src"
BACKEND = ROOT / "pellier" / "backend"


def test_observatory_data_hook_is_api_only() -> None:
    body = (FRONTEND / "observatory" / "hooks" / "useObservatoryData.ts").read_text()

    assert "const apiEndpoints" in body
    assert "fixtureImporters" not in body
    assert "allowFixtureFallback" not in body


def test_agent_registry_reports_each_specialists_balanced_model() -> None:
    """The topology must expose the factory's real default, not a legacy alias."""
    from config import settings
    from routes.observatory import list_agents

    agents = asyncio.run(list_agents())
    models = {agent["name"]: agent["model"] for agent in agents}

    assert models == {
        "Search Agent": settings.BEDROCK_OPUS_MODEL,
        "Personalization Agent": settings.BEDROCK_OPUS_MODEL,
        "Pricing Agent": settings.BEDROCK_REPORTING_MODEL,
        "Inventory Agent": settings.BEDROCK_REPORTING_MODEL,
        "Customer Service Agent": settings.BEDROCK_OPUS_MODEL,
    }


def test_persona_runtime_has_no_file_or_process_memory_fallback() -> None:
    body = (BACKEND / "app.py").read_text()

    assert "personas-config.json" not in body
    assert "/api/observatory/personas/reload" not in body
    assert "_session_persona" not in body
    assert "pellier.persona_profiles" in body
    assert "pellier.shopper_sessions" in body


def test_persona_membership_comes_from_the_customer_record() -> None:
    """Profile presentation is seeded; membership is a current customer fact."""
    source = (BACKEND / "app.py").read_text()
    persona_query = source[
        source.index("async def _persona_rows") : source.index("def _persona_payload")
    ]

    assert "JOIN pellier.customers c" in persona_query
    assert "c.membership" in persona_query
    assert "pp.membership," not in persona_query


def test_live_surface_migration_provisions_profiles_sessions_and_scenarios() -> None:
    body = (ROOT / "scripts" / "migrations" / "029_live_surface_data.sql").read_text()

    for relation in (
        "pellier.persona_profiles",
        "pellier.shopper_sessions",
        "pellier.workshop_scenarios",
    ):
        assert relation in body
    assert "regexp_replace(\"imgUrl\", '\\.png$', '.webp')" in body
    assert "journey_role" in body
    assert "journey_stage" in body
    for stage in ("establish", "exercise", "prove"):
        assert f"'{stage}'" in body
    assert "'required'" in body
    assert "'explore'" in body


def test_historical_theo_seed_retains_its_recorded_return_conversation() -> None:
    seed = (ROOT / "scripts" / "migrations" / "029_live_surface_data.sql").read_text()
    repair = (
        ROOT / "scripts" / "migrations" / "040_resequence_theo_governed_turn.sql"
    ).read_text()
    bootstrap = (ROOT / "scripts" / "bootstrap-labs.sh").read_text()
    reset = (ROOT / "scripts" / "reset-governed-workshop.sh").read_text()

    required_turn = (
        "('theo', 3, 'My Wabi-Sabi Bowl arrived chipped. Please help me return it.', "
        "'required', 'prove', '37')"
    )
    optional_turn = (
        "('theo', 4, 'Without asking me to repeat the ritual or material, "
        "which pairing should I choose and why?', 'explore', NULL, '34')"
    )
    assert required_turn in seed
    assert optional_turn in seed
    assert "WHERE persona_id = 'theo'" in repair
    assert "AND ordinal = 2" in repair
    assert "AND ordinal = 3" in repair
    assert "040_resequence_theo_governed_turn.sql" in bootstrap
    assert "041_align_theo_pairing_preview.sql" in bootstrap
    assert "040_resequence_theo_governed_turn.sql" in reset
    assert "041_align_theo_pairing_preview.sql" in reset


def test_historical_anna_seed_retains_its_recorded_retrieval_previews() -> None:
    seed = (ROOT / "scripts" / "migrations" / "029_live_surface_data.sql").read_text()
    repair = (
        ROOT / "scripts" / "migrations" / "042_align_anna_guided_previews.sql"
    ).read_text()
    bootstrap = (ROOT / "scripts" / "bootstrap-labs.sh").read_text()
    reset = (ROOT / "scripts" / "reset-governed-workshop.sh").read_text()

    retrieval_turn = (
        "('anna', 2, 'Keep it under $100 and in stock. Show me the strongest two options.', "
        "'required', 'exercise', '28')"
    )
    proof_turn = (
        "('anna', 3, 'Which one should I choose? Compare the two options using their current prices and availability.', "
        "'required', 'prove', NULL)"
    )
    assert retrieval_turn in seed
    assert proof_turn in seed
    assert "WHERE persona_id = 'anna'" in repair
    assert "AND ordinal = 2" in repair
    assert "AND ordinal = 3" in repair
    assert "Build checkpoint · inventory proof" in (
        FRONTEND / "observatory" / "surfaces" / "observe" / "ObservatoryCuratedTurns.tsx"
    ).read_text()
    assert "042_align_anna_guided_previews.sql" in bootstrap
    assert "042_align_anna_guided_previews.sql" in reset


def test_storefront_persona_edits_are_durable_aurora_merchandising() -> None:
    migration = (
        ROOT / "scripts" / "migrations" / "030_storefront_editorial_order.sql"
    ).read_text()
    expansion = (
        ROOT / "scripts" / "migrations" / "035_expand_persona_discovery_grids.sql"
    ).read_text()
    products_route = (BACKEND / "routes" / "products.py").read_text()

    assert "storefront_rank" in migration
    for ranked_product in (
        "('marco', '20', 10)",
        "('anna', '30', 10)",
        "('theo', '40', 10)",
    ):
        assert ranked_product in migration
        assert ranked_product in expansion
    assert "count(*) <> 10" in expansion
    assert "fresh_count <> 9" in expansion
    assert "storefront_rank IS NOT NULL" in products_route
    assert "ORDER BY {order}" in products_route


def test_unsigned_edit_restores_the_reference_runner_merchandising() -> None:
    """The forward migration restores Cloudform without hiding the tote."""
    initial_edit = (
        ROOT / "scripts" / "migrations" / "030_storefront_editorial_order.sql"
    ).read_text()
    refinement = (
        ROOT / "scripts" / "migrations" / "031_refine_fresh_storefront_edit.sql"
    ).read_text()
    restoration = (
        ROOT / "scripts" / "migrations" / "032_restore_fresh_runner_edit.sql"
    ).read_text()
    scenarios = (ROOT / "scripts" / "migrations" / "029_live_surface_data.sql").read_text()
    curations = (FRONTEND / "data" / "personaCurations.ts").read_text()

    assert "('fresh', '10', 9)" in initial_edit
    assert "('fresh', '9', 9)" not in initial_edit
    assert 'WHEN "productId" = \'10\' THEN 9' in refinement
    assert 'WHEN "productId" = \'9\' THEN 9' in restoration
    assert 'WHEN "productId" = \'10\' THEN NULL' in restoration
    assert (
        "'A considered carry-all for a long weekend.', 'explore', NULL, '10'"
        in scenarios
    )
    assert "A considered carry-all for a long weekend." in curations


def test_inventory_contract_covers_all_sixty_curated_products() -> None:
    warehouse = (
        ROOT / "scripts" / "migrations" / "006_warehouse_inventory.sql"
    ).read_text()
    convergence = (
        ROOT / "scripts" / "migrations" / "033_extend_curated_inventory.sql"
    ).read_text()

    assert 'pc."productId"::int BETWEEN 1 AND 60' in warehouse
    assert "IF nrows <> 180 OR invalid_products <> 0 THEN" in warehouse
    assert 'pc."productId"::int BETWEEN 1 AND 60' in convergence
    assert "inventory_rows <> 180" in convergence


def test_persona_selector_uses_editorial_personalities() -> None:
    seed = (ROOT / "scripts" / "migrations" / "029_live_surface_data.sql").read_text()
    refinement = (
        ROOT / "scripts" / "migrations" / "034_refine_persona_personalities.sql"
    ).read_text()

    for personality in (
        "Travel, utility, leather, linen",
        "Gifting, ceremony, silk, glass",
        "Slow living, craft, stoneware, natural materials",
    ):
        assert personality in seed
        assert personality in refinement


def test_persona_hero_descriptions_match_the_approved_scenes() -> None:
    seed = (ROOT / "scripts" / "migrations" / "029_live_surface_data.sql").read_text()
    refinement = (
        ROOT / "scripts" / "migrations" / "036_refresh_persona_hero_alt_text.sql"
    ).read_text()

    for description in (
        "Leather weekender with folded linen and brass travel details in warm daylight",
        "Ribbon-wrapped gift beside an amber candle, ceramic bud vase, and blank card",
        "Charcoal stoneware bowl beside natural linen, a beeswax candle, and olive branches",
    ):
        assert description in seed
        assert description in refinement


def test_persona_heroes_use_fixed_approved_images() -> None:
    seed = (ROOT / "scripts" / "migrations" / "029_live_surface_data.sql").read_text()
    refinement = (
        ROOT / "scripts" / "migrations" / "037_serve_persona_hero_masters.sql"
    ).read_text()
    hero = (FRONTEND / "components" / "PellierHero.tsx").read_text()

    for image in (
        "/products/hero-marco.png",
        "/products/hero-anna.png",
        "/products/hero-theo.png",
    ):
        assert image in seed
        assert image in refinement
    assert 'data-testid="persona-hero-image"' in hero
    assert "/products/landing-hero-weekender.webp" in hero
    assert "src={asset(hero.image)}" in hero
    assert "/api/observatory/personas" not in hero


def test_voice_transcription_is_not_shipped_when_no_voice_control_exists() -> None:
    app = (BACKEND / "app.py").read_text()
    chat = (FRONTEND / "components" / "ChatDrawer.tsx").read_text()
    hero = (FRONTEND / "components" / "PellierHero.tsx").read_text()

    assert "transcribe_router" not in app
    assert "useVoiceSearch" not in chat
    assert "useVoiceSearch" not in hero
    assert not (BACKEND / "routes" / "transcribe.py").exists()
    assert not (FRONTEND / "hooks" / "useVoiceSearch.ts").exists()


def test_observatory_never_substitutes_browser_or_hardcoded_data() -> None:
    """A failed live read is visible; it is never simulated in the browser."""
    # Personas are listed by the Storefront's chooser and concierge, both from the
    # API. The Observatory Settings page that also listed them is retired, and must
    # stay retired rather than return with a local fallback list.
    assert not (FRONTEND / "observatory" / "surfaces" / "Settings.tsx").exists()
    persona_lists = [
        (FRONTEND / "components" / name).read_text()
        for name in ("PersonaModal.tsx", "PersonaConcierge.tsx")
    ]
    tool_discovery = (
        FRONTEND / "observatory" / "hooks" / "useToolDiscovery.ts"
    ).read_text()
    skills = (
        FRONTEND / "observatory" / "surfaces" / "understand" / "Skills.tsx"
    ).read_text()
    session_chat = (
        FRONTEND / "observatory" / "surfaces" / "observe" / "ChatTab.tsx"
    ).read_text()

    for persona_list in persona_lists:
        assert "FALLBACK_PERSONAS" not in persona_list
        assert "apiFetch('/api/observatory/personas')" in persona_list
    assert "discoverToolsLocally" not in tool_discovery
    assert "routeSkillsOffline" not in skills
    assert "SHOWCASE_PRODUCTS" not in session_chat
    assert "searchCatalog" not in session_chat
    assert "ComposerBar" not in session_chat
    assert "PERSONA_STRIP_META" not in session_chat
