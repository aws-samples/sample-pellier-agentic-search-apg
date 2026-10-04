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


class PerfCompareRequest(BaseModel):
    """Request model for ``POST /api/performance/compare``.

    ``ef_search`` reaches a Postgres ``SET`` statement, which cannot take a
    bound parameter, so the value is interpolated into SQL text. Declaring it as
    a bounded ``int`` here is the first of two gates -- ``index_performance``
    clamps again at the sink. Without this model FastAPI performs no validation
    at all and a string payload flows straight into the statement.
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Search query text"
    )
    ef_search: int = Field(
        default=40,
        ge=1,
        le=1000,
        description="HNSW ef_search parameter (candidate list size)"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results to return"
    )


class PerfIterativeScanRequest(BaseModel):
    """Request model for ``POST /api/performance/iterative-scan``.

    Same ``ef_search`` reasoning as :class:`PerfCompareRequest`; this route also
    requires a category to demonstrate HNSW overfiltering.
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Search query text"
    )
    category: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Category filter used to trigger HNSW overfiltering"
    )
    ef_search: int = Field(
        default=40,
        ge=1,
        le=1000,
        description="HNSW ef_search parameter (candidate list size)"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results to return"
    )


class PerfQuantizationRequest(BaseModel):
    """Request model for ``POST /api/performance/quantization-benchmark``.

    This route takes no ``ef_search``; the model exists so the body is
    validated rather than read off a bare ``dict``.
    """

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
    """Recommendation request model"""

    productId: int
    limit: int = 5
    exclude_same_product: bool = True


class AgentResponse(BaseModel):
    """Response from the multi-agent system"""
    
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


class ChatHistoryProduct(BaseModel):
    """A rendered product card retained as bounded chat context.

    This identifies a prior recommendation; it is not authoritative for a
    live price or inventory answer, which still requires a current tool read.
    """

    id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=300)
    price: float = Field(ge=0)
    category: Optional[str] = Field(default=None, max_length=120)
    availability: Optional[str] = Field(default=None, max_length=80)
    ownership: Optional[Literal["owned"]] = None


class ChatMessage(BaseModel):
    """Chat message. ``role`` is constrained so a client cannot inject an
    arbitrary role label that gets concatenated into the LLM prompt."""
    role: Literal["user", "assistant"]
    content: str
    products: List[ChatHistoryProduct] = Field(default_factory=list, max_length=3)


class ChatRequest(BaseModel):
    """Chat request"""
    message: str
    conversation_history: List[ChatMessage] = []
    session_id: Optional[str] = None
    workshop_mode: Optional[str] = Field(default=None, description="Workshop progression mode: 'legacy', 'search', 'agentic', 'production'")
    guardrails_enabled: bool = Field(default=False, description="Enable content moderation guardrails")
    customer_id: Optional[str] = Field(
        default=None,
        pattern=r"^CUST-[A-Z0-9-]{1,40}$",
        description="Persona customer id (e.g. 'CUST-MARCO'). None = anonymous.",
    )
    skill_mode: str = Field(
        default="fixed",
        pattern=r"^(fixed|on_demand)$",
        description=(
            "How the agent gets its skills: 'fixed' carries them in the prompt; "
            "'on_demand' lists their names and lets the agent open the ones it "
            "needs. A Builder view choice, remembered per browser. The managed "
            "rail always uses 'fixed'."
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


# The eight store departments, stored as-is in pellier.product_catalog.category.
StorefrontCategory = Literal[
    "Clothing", "Shoes", "Bags and travel", "Accessories",
    "Home", "Kitchen and table", "Bath and body", "Stationery and gifts",
]
StorefrontBadge = Literal["EDITORS_PICK", "BESTSELLER", "JUST_IN"]


class WarehouseStock(BaseModel):
    """One warehouse's on-hand count for a product.

    Projected straight from ``pellier.warehouse_inventory`` joined to
    ``pellier.warehouses`` — the same rows ``check_stock`` reports when the
    Stock agent is asked about a single product. Ship windows are the
    warehouse's configured range in days, not a delivery promise.
    """

    warehouse_id: str
    name: str
    city: str
    quantity: int
    ship_window_min: Optional[int] = None
    ship_window_max: Optional[int] = None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


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
    # The card's one stock line. ``quantity`` is ``product_catalog.quantity``
    # as read with the listing (``None`` means the read did not happen, never
    # zero stock); ``warehouses`` is the per-location breakdown, so the card
    # can say "In stock in Austin and Portland" when Brooklyn holds none.
    quantity: Optional[int] = None
    warehouses: List[WarehouseStock] = Field(default_factory=list)

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ProductAvailability(BaseModel):
    """Live Aurora inventory for one product.

    ``on_hand`` is ``product_catalog.quantity``, the catalog's aggregate
    stock cache. ``warehouses`` is the
    per-location breakdown. Both are reported as read rather than
    reconciled, so a divergence between them stays visible instead of
    being silently resolved in the API layer.
    """

    on_hand: int
    warehouses: List[WarehouseStock] = Field(default_factory=list)

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class StorefrontProductDetail(StorefrontProduct):
    """Single-product shape: the card fields plus catalog copy and stock.

    The listing endpoint keeps returning bare ``StorefrontProduct`` so the
    grid payload stays unchanged; only ``GET /api/products/{id}`` pays for
    the extra description column and inventory join.

    ``availability`` is ``None`` when the inventory tables are unreachable.
    A null is an explicit "not read", which the storefront renders as a
    degraded state — it must never be displayed as zero stock.
    """

    description: Optional[str] = None
    availability: Optional[ProductAvailability] = None


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
