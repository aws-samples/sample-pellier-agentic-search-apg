"""Product-envelope regression coverage for streamed specialist results."""

import json

import pytest

from services import inventory_evidence
from services.chat import (
    EnhancedChatService,
    ProductExtractor,
    _is_incomplete_router_preface,
    _mentions_returned_product,
    _new_unique_products,
    _specialist_prose,
)


PRODUCT = {
    "productId": 7,
    "name": "Italian Linen Camp Shirt",
    "brand": "Pellier",
    "price": 228,
    "category": "Shirts",
    "imgUrl": "/products/italian-linen-camp-shirt.png",
}


def test_extracts_direct_tool_product_envelope():
    products = ProductExtractor.extract(json.dumps({"products": [PRODUCT]}))

    assert products == [
        {
            "productId": 7,
            "name": "Italian Linen Camp Shirt",
            "brand": "Pellier",
            "color": "",
            "price": 228.0,
            "rating": 0.0,
            "reviews": 0,
            "category": "Shirts",
            "imgUrl": "/products/italian-linen-camp-shirt.png",
            "badge": None,
            "tags": [],
        }
    ]


def test_extracts_products_forwarded_by_agents_as_tools_specialist():
    result = (
        "The indigo camp shirt is the strongest warm-weather option."
        "\n\n```json\n"
        f"{json.dumps([PRODUCT])}"
        "\n```"
    )

    products = ProductExtractor.extract(result)

    assert [product["productId"] for product in products] == [7]
    assert products[0]["imgUrl"] == "/products/italian-linen-camp-shirt.png"


def test_ignores_non_product_json_markers_and_duplicate_products():
    result = (
        "A grounded result."
        "\n\n```json\n"
        '{"type": "escalation", "reason": "human requested"}'
        "\n```\n"
        "```json\n"
        f"{json.dumps([PRODUCT, PRODUCT, {'status': 'success'}])}"
        "\n```"
    )

    products = ProductExtractor.extract(result)

    assert [product["productId"] for product in products] == [7]


def test_deduplicates_forwarded_batch_against_existing_and_itself():
    existing = [{"id": "7", "name": "Italian Linen Camp Shirt"}]
    candidates = [
        {"id": 7, "name": "Italian Linen Camp Shirt"},
        {"id": "16", "name": "Linen Overshirt"},
        {"id": 16, "name": "Linen Overshirt"},
        {"name": "Cotton-Linen Crew Tee"},
        {"name": "cotton-linen crew tee"},
    ]

    assert _new_unique_products(existing, candidates) == [
        {"id": "16", "name": "Linen Overshirt"},
        {"name": "Cotton-Linen Crew Tee"},
    ]


def test_extracts_specialist_prose_without_forwarded_product_payload():
    result = (
        "Lead with the Italian Linen Camp Shirt at $228."
        "\n\n```json\n"
        f"{json.dumps([PRODUCT])}"
        "\n```"
    )

    assert _specialist_prose(result) == (
        "Lead with the Italian Linen Camp Shirt at $228."
    )


def test_only_short_trailing_colon_copy_is_an_incomplete_router_preface():
    assert _is_incomplete_router_preface(
        "Here's a resort edit built around your linen wardrobe:"
    )
    assert not _is_incomplete_router_preface(
        "Lead with the Italian Linen Camp Shirt, then add the overshirt."
    )
    assert not _is_incomplete_router_preface("")


def test_detects_product_grounding_by_returned_name():
    products = [{"name": "Italian Linen Camp Shirt"}, {"name": ""}]

    assert _mentions_returned_product(
        "Lead with the Italian Linen Camp Shirt.",
        products,
    )
    assert not _mentions_returned_product("Here are some great options!", products)


@pytest.mark.asyncio
async def test_parser_preserves_grounded_editorial_price_sentence():
    service = EnhancedChatService.__new__(EnhancedChatService)
    prose = (
        "The Cotton-Linen Crew Tee at $68 is the closest match for a "
        "linen top under $150."
    )

    parsed = await service._parse_agent_response(
        prose,
        "Find a linen shirt under $150",
        has_tool_products=True,
    )

    assert parsed["text"] == prose


@pytest.mark.asyncio
async def test_parser_preserves_full_specialist_reply_when_cards_exist():
    service = EnhancedChatService.__new__(EnhancedChatService)
    prose = (
        "The Olive Branch Vessel is the strongest anchor for the table. "
        "Pair it with the Ceramic Ring Dish for a smaller echo of the same glaze. "
        "The Wabi-Sabi Bowl you already own belongs in the background, not as the "
        "new recommendation."
    )

    parsed = await service._parse_agent_response(
        prose,
        "Help me build a ceramic table edit",
        has_tool_products=True,
    )

    assert parsed["text"] == prose
    assert "Ceramic Ring Dish" in parsed["text"]
    assert parsed["text"].endswith("new recommendation.")


@pytest.mark.asyncio
async def test_format_products_preserves_quantity_and_owned_status():
    service = EnhancedChatService.__new__(EnhancedChatService)
    service.db_service = None

    products = await service._format_products(
        [
            {
                **PRODUCT,
                "quantity": 4,
                "badge": "From your orders",
            }
        ]
    )

    assert products[0]["quantity"] == 4
    assert products[0]["inStock"] is True
    assert products[0]["ownership"] == "owned"


@pytest.mark.asyncio
async def test_format_products_escapes_like_metacharacters_in_image_backfill():
    """A product name containing a literal LIKE metacharacter (e.g. the very
    real "100% Cotton") must not widen the backfill match: the character has
    to reach Postgres as a literal, not as a wildcard."""

    class _CapturingCatalog:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple]] = []

        async def fetch_all(self, query, *params):
            self.calls.append((query, params))
            return []

    catalog = _CapturingCatalog()
    service = EnhancedChatService.__new__(EnhancedChatService)
    service.db_service = catalog

    await service._format_products(
        [{**PRODUCT, "name": "100% Cotton Shirt_Deluxe"}]
    )

    assert len(catalog.calls) == 1
    _, params = catalog.calls[0]
    assert params == (r"%100\% cotton shirt\_deluxe%",)


@pytest.mark.asyncio
async def test_continuity_cards_rehydrate_catalog_media_without_overwriting_live_stock():
    class Catalog:
        async def fetch_all(self, query, *params):
            assert '"productId" = ANY(%s)' in query
            assert params == (["35", "37"],)
            return [
                {
                    "productId": 35,
                    "brand": "Pellier Home",
                    "color": "Brass",
                    "imgUrl": "/products/brass-incense-holder.png",
                    "rating": 4.8,
                    "reviews": 189,
                    "category": "Home Decor",
                    "badge": None,
                    "tags": ["ritual"],
                },
                {
                    "productId": 37,
                    "brand": "Pellier Home",
                    "color": "Cream",
                    "imgUrl": "/products/wabi-sabi-bowl.png",
                    "rating": 4.9,
                    "reviews": 167,
                    "category": "Home Decor",
                    "badge": "Editor's Pick",
                    "tags": ["stoneware"],
                },
            ]

    service = EnhancedChatService.__new__(EnhancedChatService)
    service.db_service = Catalog()
    products = [
        {
            "id": 35,
            "name": "Brass Incense Holder",
            "price": 45,
            "quantity": 50,
            "inStock": True,
        },
        {
            "id": 37,
            "name": "Wabi-Sabi Bowl",
            "price": 65,
            "quantity": 50,
            "inStock": True,
        },
    ]

    await service._hydrate_catalog_card_metadata(products)

    assert products[0]["image"] == "/products/brass-incense-holder.png"
    assert products[0]["category"] == "Home Decor"
    assert products[0]["rating"] == 4.8
    assert products[0]["quantity"] == 50
    assert products[0]["inStock"] is True
    assert products[1]["image"] == "/products/wabi-sabi-bowl.png"
    assert products[1]["badge"] == "Editor's Pick"


@pytest.mark.asyncio
async def test_product_cards_receive_reconciled_inventory_not_catalog_cache(
    monkeypatch: pytest.MonkeyPatch,
):
    service = EnhancedChatService.__new__(EnhancedChatService)
    service.db_service = object()
    products = [{"id": 7, "quantity": 50, "inStock": True}]

    async def resolve(_db, product_ids):
        assert product_ids == ["7"]
        return {
            "7": inventory_evidence.InventoryEvidence(
                product_id="7",
                status=inventory_evidence.RECONCILED_IN_STOCK,
                available_quantity=14,
            )
        }

    monkeypatch.setattr(inventory_evidence, "resolve_inventory_many", resolve)

    await service._attach_inventory_evidence(products)

    assert products[0]["quantity"] == 14
    assert products[0]["inStock"] is True
    assert products[0]["availability"]["status"] == "reconciled_in_stock"
    assert products[0]["availability"]["availableQuantity"] == 14
