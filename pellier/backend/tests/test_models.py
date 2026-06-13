"""Round-trip tests for the storefront Pydantic models added in Task 1.3.

Validates the Data Models section of `design.md`:
  - `SearchResponse` (storefront shape) serializes camelCase via `by_alias=True`
    and accepts both snake_case and camelCase on input (`populate_by_name=True`).
  - `Preferences` accepts the four tag literal groups and round-trips.
  - `VerifiedUser` serializes `given_name` as `givenName`.
  - The four tag literal types reject unknown values.

Runnable two ways:
  python -m pytest pellier/backend/tests/test_models.py
  pytest pellier/backend/tests/test_models.py

The design "Done when" signal for this task:
    SearchResponse(
        products=[], query_embedding_ms=1, search_ms=2, total_ms=3
    ).model_dump(by_alias=True)
returns camelCase keys. Imported below as `SearchResponse` (aliased from
`StorefrontSearchResponse`) so the exact done-signal expression runs verbatim.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import (
    Preferences,
    ReasoningChip,
    StorefrontProduct,
    StorefrontSearchResponse,
    VerifiedUser,
)

# The task's "Done when" uses the bare name `SearchResponse`. Alias the
# storefront class under that name so the done-signal assertion reads the
# same way it appears in tasks.md.
SearchResponse = StorefrontSearchResponse


# ---------------------------------------------------------------------------
# SearchResponse (storefront) — the "Done when" assertion
# ---------------------------------------------------------------------------


def test_search_response_done_when_signal_emits_camel_case() -> None:
    """Exact assertion from tasks.md Task 1.3 'Done when'."""
    payload = SearchResponse(
        products=[], query_embedding_ms=1, search_ms=2, total_ms=3
    ).model_dump(by_alias=True)

    assert payload == {
        "products": [],
        "queryEmbeddingMs": 1,
        "searchMs": 2,
        "totalMs": 3,
    }


def test_search_response_accepts_snake_case_input() -> None:
    model = SearchResponse.model_validate(
        {
            "products": [],
            "query_embedding_ms": 10,
            "search_ms": 20,
            "total_ms": 30,
        }
    )
    assert model.query_embedding_ms == 10
    assert model.search_ms == 20
    assert model.total_ms == 30


def test_search_response_accepts_camel_case_input() -> None:
    model = SearchResponse.model_validate(
        {
            "products": [],
            "queryEmbeddingMs": 11,
            "searchMs": 22,
            "totalMs": 33,
        }
    )
    assert model.query_embedding_ms == 11
    assert model.search_ms == 22
    assert model.total_ms == 33


def test_search_response_round_trip_with_product() -> None:
    product = StorefrontProduct(
        id=1,
        brand="Pellier Editions",
        name="Italian Linen Camp Shirt",
        color="Sand",
        price=128.0,
        rating=4.8,
        review_count=142,
        category="Linen",
        image_url="https://example.com/linen-camp-shirt.jpg",
        badge="EDITORS_PICK",
        tags=["minimal", "serene", "classic", "warm", "neutral", "linen"],
        reasoning=ReasoningChip(
            style="matched",
            text="Matches your minimal vibe",
        ),
    )
    response = SearchResponse(
        products=[product],
        query_embedding_ms=42,
        search_ms=128,
        total_ms=185,
    )

    camel = response.model_dump(by_alias=True)
    assert camel["queryEmbeddingMs"] == 42
    assert camel["searchMs"] == 128
    assert camel["totalMs"] == 185

    # Nested product also serializes in camelCase.
    assert camel["products"][0]["reviewCount"] == 142
    assert camel["products"][0]["imageUrl"].endswith("linen-camp-shirt.jpg")
    assert camel["products"][0]["reasoning"]["style"] == "matched"

    # Snake-case serialization still works when alias is not requested.
    snake = response.model_dump()
    assert snake["query_embedding_ms"] == 42
    assert snake["products"][0]["review_count"] == 142
    assert snake["products"][0]["image_url"].endswith("linen-camp-shirt.jpg")

    # Accept the camelCase wire payload back into the model.
    reparsed = SearchResponse.model_validate(camel)
    assert reparsed == response


def test_storefront_product_reasoning_urgent_clause_round_trip() -> None:
    chip = ReasoningChip(
        style="pricing",
        text="Last few in your size",
        urgent_clause="Last few",
    )
    camel = chip.model_dump(by_alias=True)
    assert camel == {
        "style": "pricing",
        "text": "Last few in your size",
        "urgentClause": "Last few",
    }
    assert ReasoningChip.model_validate(camel) == chip


# ---------------------------------------------------------------------------
# Preferences - four tag groups with literal types
# ---------------------------------------------------------------------------


def test_preferences_accepts_all_four_groups_snake_case() -> None:
    prefs = Preferences(
        vibe=["minimal", "classic"],
        colors=["warm", "neutral"],
        occasions=["everyday", "slow"],
        categories=["linen", "accessories"],
    )
    assert prefs.vibe == ["minimal", "classic"]
    assert prefs.colors == ["warm", "neutral"]
    assert prefs.occasions == ["everyday", "slow"]
    assert prefs.categories == ["linen", "accessories"]


def test_preferences_round_trip_via_camel_case() -> None:
    original = Preferences(
        vibe=["creative"],
        colors=["earth"],
        occasions=["evening"],
        categories=["dresses"],
    )
    wire = original.model_dump(by_alias=True)
    # All four group keys are single words already, so camelCase == snake_case
    # for Preferences specifically, but the round-trip must still hold.
    assert wire == {
        "vibe": ["creative"],
        "colors": ["earth"],
        "occasions": ["evening"],
        "categories": ["dresses"],
    }
    assert Preferences.model_validate(wire) == original


def test_preferences_defaults_to_empty_lists() -> None:
    prefs = Preferences()
    assert prefs.vibe == []
    assert prefs.colors == []
    assert prefs.occasions == []
    assert prefs.categories == []


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("vibe", "luminous"),
        ("colors", "cerulean"),
        ("occasions", "brunch"),
        ("categories", "watches"),
    ],
)
def test_preferences_rejects_unknown_tag(field: str, bad_value: str) -> None:
    payload = {"vibe": [], "colors": [], "occasions": [], "categories": []}
    payload[field] = [bad_value]
    with pytest.raises(ValidationError) as exc:
        Preferences.model_validate(payload)
    # The failing field name appears somewhere in the error payload so the
    # API layer can surface it in a 422 response (Requirement 3.2.4).
    assert field in str(exc.value)


# ---------------------------------------------------------------------------
# VerifiedUser - cognito JWT claims
# ---------------------------------------------------------------------------


def test_verified_user_given_name_serializes_as_camel() -> None:
    user = VerifiedUser(
        user_id="cognito-sub-123",
        email="shopper@example.com",
        given_name="Avery",
    )

    camel = user.model_dump(by_alias=True)
    assert camel == {
        "userId": "cognito-sub-123",
        "email": "shopper@example.com",
        "givenName": "Avery",
    }
    # And snake_case direct access works too.
    assert user.user_id == "cognito-sub-123"
    assert user.given_name == "Avery"


def test_verified_user_accepts_camel_case_input() -> None:
    user = VerifiedUser.model_validate(
        {
            "userId": "cognito-sub-456",
            "email": "concierge@example.com",
            "givenName": "Rowan",
        }
    )
    assert user.user_id == "cognito-sub-456"
    assert user.given_name == "Rowan"


def test_verified_user_rejects_malformed_email() -> None:
    with pytest.raises(ValidationError):
        VerifiedUser.model_validate(
            {
                "user_id": "x",
                "email": "not-an-email",
                "given_name": "Kai",
            }
        )


def test_verified_user_accepts_empty_email_for_access_tokens() -> None:
    # Cognito ACCESS tokens carry no ``email`` claim (only ID tokens do), so a
    # username-pool access-token caller legitimately has ``email=""``. The
    # validator must accept that - rejecting it silently demotes an
    # authenticated caller to anonymous (the username-pool regression).
    user = VerifiedUser(user_id="cognito-sub-789", email="", given_name="marco")
    assert user.email == ""
    assert user.given_name == "marco"
