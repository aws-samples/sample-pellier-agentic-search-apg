"""Product transport across the Pattern I specialist boundary."""

from agents.specialist_hooks import (
    forward_or_append_products,
    reset_product_collector,
    reset_specialist_reply_collector,
    select_products_for_reply,
    set_product_collector,
    set_specialist_reply_collector,
)


PRODUCT = {
    "productId": 7,
    "name": "Italian Linen Camp Shirt",
    "price": 228,
}


def test_bound_collector_keeps_product_json_out_of_router_context():
    collector = []
    token = set_product_collector(collector)
    try:
        result = forward_or_append_products(
            'The indigo camp shirt is the strongest option.\n\n```json\n[]\n```',
            [PRODUCT],
        )
    finally:
        reset_product_collector(token)

    assert result == "The indigo camp shirt is the strongest option."
    assert collector == [PRODUCT]


def test_direct_specialist_call_preserves_fenced_product_fallback():
    result = forward_or_append_products("A grounded result.", [PRODUCT])

    assert result.startswith("A grounded result.\n\n```json\n[")
    assert '"productId": 7' in result
    assert result.endswith("\n```")


def test_bound_reply_collector_preserves_completed_specialist_prose():
    products = []
    replies = []
    product_token = set_product_collector(products)
    reply_token = set_specialist_reply_collector(replies)
    try:
        result = forward_or_append_products(
            "Lead with the Italian Linen Camp Shirt.",
            [PRODUCT],
        )
    finally:
        reset_specialist_reply_collector(reply_token)
        reset_product_collector(product_token)

    assert result == "Lead with the Italian Linen Camp Shirt."
    assert replies == ["Lead with the Italian Linen Camp Shirt."]


def test_reply_selection_does_not_promote_owned_context_to_best_match():
    candidates = [
        {"productId": "36", "name": "Ceramic Tumblers"},
        {"productId": "37", "name": "Wabi-Sabi Bowl"},
        {"productId": "35", "name": "Brass Incense Holder"},
        {"productId": "34", "name": "Terracotta Planter"},
    ]
    selected = select_products_for_reply(
        (
            "Since you already own the Ceramic Tumblers, Wabi-Sabi Bowl, and "
            "Brass Incense Holder, the Terracotta Planter is the new piece "
            "that completes the ritual."
        ),
        candidates,
        owned_products=candidates[:3],
    )

    assert selected == [{"productId": "34", "name": "Terracotta Planter"}]


def test_reply_selection_does_not_card_a_name_inside_a_longer_name():
    hadley = {"productId": "2", "name": "Hadley Linen Shirt"}
    linen = {"productId": "9", "name": "Linen Shirt"}

    selected = select_products_for_reply(
        "I recommend the Hadley Linen Shirt for the trip.", [linen, hadley]
    )

    assert selected == [hadley]


def test_reply_selection_keeps_both_when_each_name_appears_on_its_own():
    hadley = {"productId": "2", "name": "Hadley Linen Shirt"}
    linen = {"productId": "9", "name": "Linen Shirt"}

    selected = select_products_for_reply(
        "Pack the Linen Shirt for the beach and the Hadley Linen Shirt for dinner.",
        [hadley, linen],
    )

    assert selected == [linen, hadley]


def test_reply_selection_requires_whole_words():
    tee = {"productId": "5", "name": "Tee"}
    trousers = {"productId": "6", "name": "Linen Trousers"}

    selected = select_products_for_reply(
        "The Linen Trousers steer the evening look.", [tee, trousers]
    )

    assert selected == [trousers]


def test_reply_selection_lets_same_named_variants_share_a_mention():
    charcoal = {"productId": "36", "name": "Ceramic Tumblers"}
    ivory = {"productId": "38", "name": "Ceramic Tumblers"}

    selected = select_products_for_reply(
        "The Ceramic Tumblers are the gentler price.", [charcoal, ivory]
    )

    assert selected == [charcoal, ivory]
