"""
Pydantic models for Pellier Backend
"""
import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


# Email format regex — RFC 5322 lite. We don't use Pydantic's ``EmailStr``
# because it pulls in the ``email-validator`` package transitively and
# that's a runtime-install liability for workshop attendees. The upstream
# (Cognito JWT verification) already validates email format before a
# ``VerifiedUser`` is ever constructed, so this check is defense-in-depth
# against hand-built model instances in tests and internal callers.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

from .product import Product, ProductWithScore, ProductSearchResult, ProductFilters
from .search import (
    CategoryTag,
    ColorTag,
    OccasionTag,
    ReasoningChip,
    ReasoningStyle,
    SearchRequest,
    SearchResponse,
    SearchResult,
    StorefrontBadge,
    StorefrontCategory,
    StorefrontProduct,
    StorefrontSearchResponse,
    VibeTag,
)


# === STOREFRONT MODELS (Task 1.3 / Design Data Models) ===
#
# `Preferences` and `VerifiedUser` mirror the TypeScript types added in
# Task 1.2 (frontend/src/services/types.ts). Both emit camelCase keys on
# the wire and accept either casing on input.


class Preferences(BaseModel):
    """User preferences captured by the onboarding modal.

    Mirrors the TypeScript `Preferences` shape: four multi-select tag groups
    keyed by the four `*Tag` literal types re-exported from `models.search`.
    """

    vibe: List[VibeTag] = Field(default_factory=list)
    colors: List[ColorTag] = Field(default_factory=list)
    occasions: List[OccasionTag] = Field(default_factory=list)
    categories: List[CategoryTag] = Field(default_factory=list)

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class VerifiedUser(BaseModel):
    """Verified Cognito user returned by `CognitoAuthService.validate_jwt`.

    Field names use snake_case in Python and camelCase on the wire to match
    the frontend `User` type. `given_name` serializes as `givenName`.
    """

    user_id: str
    email: str
    given_name: str
    # Raw Cognito access token (the original bearer string), kept server-side
    # only so it can be passed through to the AgentCore Gateway for
    # identity-preserving MCP tool calls. ``exclude=True`` keeps it out of all
    # API responses — it must never be serialized back to the frontend.
    access_token: Optional[str] = Field(default=None, exclude=True)

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    @field_validator("email")
    @classmethod
    def _email_format(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("email is not a well-formed address")
        return v


__all__ = [
    # Legacy models
    "Product",
    "ProductWithScore",
    "ProductSearchResult",
    "ProductFilters",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    # Storefront tag literal types
    "VibeTag",
    "ColorTag",
    "OccasionTag",
    "CategoryTag",
    # Storefront reasoning and product models
    "ReasoningStyle",
    "ReasoningChip",
    "StorefrontCategory",
    "StorefrontBadge",
    "StorefrontProduct",
    "StorefrontSearchResponse",
    # Storefront user + preferences
    "Preferences",
    "VerifiedUser",
]
