"""
Search request and response models
"""

from typing import List, Literal, Optional, Dict
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .product import ProductWithScore


class SearchRequest(BaseModel):
    """Search request model for Lab 1 semantic search"""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Search query text"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results to return"
    )
    min_similarity: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Minimum similarity score threshold (0-1)"
    )
    search_mode: str = Field(
        default="vector",
        description="Search mode: 'vector', 'hybrid', or 'keyword'"
    )


class SearchResult(BaseModel):
    """Individual search result"""
    
    product: ProductWithScore
    explanation: Optional[str] = None
    rrf_score: Optional[float] = None
    vector_rank: Optional[int] = None
    fulltext_rank: Optional[int] = None


class SearchResponse(BaseModel):
    """Legacy search response model used by /api/search (snake_case shape)."""
    
    query: str
    results: List[SearchResult]
    total_results: int
    search_time_ms: float
    search_type: str = "semantic"


class RecommendationRequest(BaseModel):
    """Recommendation request model for Lab 2"""

    productId: int
    limit: int = 5
    exclude_same_product: bool = True


class AgentResponse(BaseModel):
    """Response from multi-agent system (Lab 2)"""
    
    agent_name: str
    response: str
    data: Optional[dict] = None
    execution_time_ms: float
    tools_used: List[str] = []


class HealthResponse(BaseModel):
    """Health check response"""
    
    status: str
    database: str
    bedrock: str
    custom_tools: str = "not_available"
    version: str


class ChatMessage(BaseModel):
    """Chat message"""
    role: str
    content: str


class ChatRequest(BaseModel):
    """Chat request"""
    message: str
    conversation_history: List[ChatMessage] = []
    session_id: Optional[str] = None
    workshop_mode: Optional[str] = Field(default=None, description="Workshop progression mode: 'legacy', 'search', 'agentic', 'production'")
    guardrails_enabled: bool = Field(default=False, description="Enable content moderation guardrails")
    customer_id: Optional[str] = Field(default=None, description="Persona customer id (e.g. 'CUST-MARCO'). None = anonymous.")
    pattern: Optional[str] = Field(
        default=None,
        description=(
            "Agent orchestration pattern for this turn. "
            "'dispatcher' — Storefront production path; direct specialist invocation. "
            "'agents_as_tools' — Atelier Pattern I; Haiku orchestrator + @tool specialists. "
            "'graph' — Atelier Pattern II (commit 2); Strands GraphBuilder with conditional edges. "
            "None defaults to 'agents_as_tools' for backwards compatibility."
        ),
    )


class ChatResponse(BaseModel):
    """Chat response"""
    response: str
    products: List[Dict] = []
    suggestions: List[str] = []
    tool_calls: List[Dict] = []
    agent_execution: Optional[Dict] = None
    model: str = ""
    success: bool = True
    token_count: Optional[int] = None
    estimated_cost_usd: Optional[float] = None


# === STOREFRONT MODELS (Task 1.3 / Design Data Models) ===
#
# Mirrors the TypeScript storefront types added in Task 1.2
# (frontend/src/services/types.ts). The legacy `SearchResponse` above keeps
# the snake_case shape used by the existing /api/search endpoint; the
# storefront personalization endpoints described in design.md use
# `StorefrontSearchResponse` with a camelCase wire format.


# Tag literal types - four groups from storefront.md preferences modal.
VibeTag = Literal[
    "minimal", "bold", "serene", "adventurous", "creative", "classic"
]
ColorTag = Literal["warm", "neutral", "earth", "soft", "moody"]
OccasionTag = Literal[
    "everyday", "travel", "evening", "outdoor", "slow", "work"
]
CategoryTag = Literal[
    "linen", "footwear", "outerwear", "accessories", "home", "dresses"
]


ReasoningStyle = Literal["picked", "matched", "pricing", "context"]


class ReasoningChip(BaseModel):
    """Reasoning chip attached to a storefront product card."""

    style: ReasoningStyle
    text: str
    urgent_clause: Optional[str] = None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


StorefrontCategory = Literal[
    "Linen", "Dresses", "Accessories", "Outerwear", "Footwear",
    "Home", "Tops", "Bottoms", "Bags",
]
StorefrontBadge = Literal["EDITORS_PICK", "BESTSELLER", "JUST_IN"]


class StorefrontProduct(BaseModel):
    """Editorial product shape consumed by the storefront home page."""

    id: int
    brand: str
    name: str
    color: str
    price: float
    rating: float
    review_count: int
    category: StorefrontCategory
    image_url: str
    badge: Optional[StorefrontBadge] = None
    tags: List[str] = Field(default_factory=list)
    reasoning: Optional[ReasoningChip] = None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class StorefrontSearchResponse(BaseModel):
    """Personalized search response wire shape (camelCase on the wire).

    Matches the TypeScript `StorefrontSearchResponse` added in Task 1.2 and
    the design.md Data Models section. `model_dump(by_alias=True)` emits
    camelCase keys (`queryEmbeddingMs`, `searchMs`, `totalMs`), while
    `model_validate({...})` accepts both snake_case and camelCase input
    (`populate_by_name=True`).
    """

    products: List[StorefrontProduct] = Field(default_factory=list)
    query_embedding_ms: int
    search_ms: int
    total_ms: int

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
