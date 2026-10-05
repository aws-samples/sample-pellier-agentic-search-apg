"""Product-envelope regression coverage for streamed specialist results."""

import json

import pytest

from services.chat import (
    EnhancedChatService,
    ProductExtractor,
    _new_unique_products,
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
        "The Tall Stoneware Vase is the strongest anchor for the table. "
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
async def test_inline_rating_cannot_replace_recommendations_with_past_purchase():
    from services.product_envelope import select_products_for_reply

    service = EnhancedChatService.__new__(EnhancedChatService)
    candle = {"productId": "4", "name": "Santal & Fig Candle"}
    recommendations = [
        {"productId": "31", "name": "Stoneware Pour-Over Set"},
        {"productId": "36", "name": "Ceramic Tumblers"},
        {"productId": "1", "name": "Tall Stoneware Vase"},
    ]
    prose = (
        "This sits in the register of the Santal & Fig Candle you've sent before.\n\n"
        "The Stoneware Pour-Over Set at $165 is the clear one to lead with, "
        "an Editors' Pick at 4.9 stars. Add Ceramic Tumblers at $78, or "
        "the Tall Stoneware Vase at $185 for the mantel."
    )
    parsed = await service._parse_agent_response(
        prose, "A housewarming gift for slow morning rituals", has_tool_products=True,
    )
    assert parsed["text"] == prose
    assert select_products_for_reply(
        parsed["text"], [candle, *recommendations], owned_products=[candle],
    ) == recommendations


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [
    "★ 4.9 (134 reviews)", "4.9 stars", "4.9 stars (134 reviews)",
    "4.9 ★ (134)", "★★★★★", "(134 reviews)",
    "\u2b50\ufe0f" * 4 + " 4.5", "★★★★☆ 4.2 (88)", "★★★★½", "- 4.8 stars", "4.5/5",
    "4.6 out of 5", "* 4.9 ★",
])
async def test_parser_removes_standalone_rating_metadata(metadata):
    service = EnhancedChatService.__new__(EnhancedChatService)
    prose = "Lead with the Stoneware Pour-Over Set."
    parsed = await service._parse_agent_response(
        prose + "\n" + metadata, "A housewarming gift", has_tool_products=True,
    )
    assert parsed["text"] == prose


@pytest.mark.asyncio
@pytest.mark.parametrize("detail", ["4.9 stars", "★ 4.9", "134 reviews)", "4.5/5 by 88 shoppers"])
async def test_parser_preserves_ratings_and_review_counts_inside_prose(detail):
    service = EnhancedChatService.__new__(EnhancedChatService)
    prose = f"The Ceramic Tumblers are rated {detail}, with a hand-thrown finish."
    parsed = await service._parse_agent_response(
        prose, "A housewarming gift", has_tool_products=True,
    )
    assert parsed["text"] == prose


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
                    "brand": "Pellier",
                    "color": "Brass",
                    "imgUrl": "/products/brass-incense-holder.png",
                    "rating": 4.8,
                    "reviews": 189,
                    "category": "Home",
                    "badge": None,
                    "tags": ["ritual"],
                },
                {
                    "productId": 37,
                    "brand": "Pellier",
                    "color": "Cream",
                    "imgUrl": "/products/wabi-sabi-bowl.png",
                    "rating": 4.9,
                    "reviews": 167,
                    "category": "Home",
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
    assert products[0]["category"] == "Home"
    assert products[0]["rating"] == 4.8
    assert products[0]["quantity"] == 50
    assert products[0]["inStock"] is True
    assert products[1]["image"] == "/products/wabi-sabi-bowl.png"
    assert products[1]["badge"] == "Editor's Pick"


@pytest.mark.asyncio
async def test_product_cards_receive_warehouse_units_not_catalog_cache():
    """A card's stock is the sum of its warehouse rows, read once for the set."""
    reads = []

    class _Db:
        async def fetch_all(self, sql, *params):
            reads.append((sql, params))
            return [{"product_id": "7", "units": 14}, {"product_id": "8", "units": 0}]

    service = EnhancedChatService.__new__(EnhancedChatService)
    service.db_service = _Db()
    products = [
        {"id": 7, "quantity": 50, "inStock": True},
        {"id": 8, "quantity": 3, "inStock": True},
        {"id": 9, "quantity": 2, "inStock": True},
    ]

    await service._attach_stock(products)

    assert len(reads) == 1 and "pellier.warehouse_inventory" in reads[0][0]
    assert reads[0][1] == (["7", "8", "9"],)
    assert products[0]["quantity"] == 14 and products[0]["inStock"] is True
    assert products[1]["quantity"] == 0 and products[1]["inStock"] is False
    # A card the read did not reach keeps what it had; no availability is invented.
    assert products[2]["quantity"] == 2
    assert "availability" not in products[0]
