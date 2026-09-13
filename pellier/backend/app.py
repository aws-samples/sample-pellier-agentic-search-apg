"""
Pellier - Main FastAPI Application
FastAPI app for the Pellier workshop backend.
"""

import asyncio
import os
import re
import time
import logging
import json
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from models.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    HealthResponse,
    ChatRequest,
    ChatResponse,
    PerfCompareRequest,
    PerfIterativeScanRequest,
    PerfQuantizationRequest,
)
from models.product import ProductWithScore
from services.database import DatabaseService
from services.session_ownership import session_actor_id
from services.auth import get_current_user
from services.cognito_auth import require_user
from services.embeddings import EmbeddingService
from services.chat import ChatService
from datetime import datetime
from services.sql_query_logger import init_query_logger, get_query_logger, QueryLog
from services.index_performance import get_index_performance_service
from services.vector_search import VectorSearch
from services.cache import init_cache, get_cache
from routes import (
    agent_router,
    agent_trace_router,
    auth_router,
    products_router,
    search_router,
    pellier_router,
    user_router,
    workshop_router,
)
from routes.transcribe import router as transcribe_router

# Configure logging for Strands SDK
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

# Filter out malicious bot requests from logs
class SecurityScanFilter(logging.Filter):
    """Filter out automated security scanner requests"""
    MALICIOUS_PATTERNS = [
        'phpunit', '.env', 'eval-stdin', 'wp-admin', 'wp-login',
        '.git', 'config.php', 'shell', 'cmd', 'exec'
    ]
    
    def filter(self, record):
        message = record.getMessage().lower()
        return not any(pattern in message for pattern in self.MALICIOUS_PATTERNS)

# Apply filter to uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(SecurityScanFilter())

# Configure the root strands logger
logging.getLogger("strands").setLevel(logging.INFO)

# Configure app logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# Global service instances
db_service: DatabaseService = None
embedding_service: EmbeddingService = None
chat_service: ChatService = None
query_logger = None
index_performance_service = None


def _log_agent_and_tool_inventory() -> None:
    """Log the live specialist roster and tool catalogue at boot.

    Mirrors the ``✅ Loaded N skills...`` line emitted by ``skills.loader``
    so the operator can confirm at a glance:

      * which specialists the Dispatcher (Pattern III) and Orchestrator
        (Pattern I) can route to, and
      * which @tool functions those specialists are allowed to call.

    Runs once per process at lifespan startup. The lists are short and
    lookup-only, so importing the modules here is cheap.
    """
    # Specialists. Each file exports a build_<role>_agent() factory; the
    # public role is the @tool wrapper name the orchestrator sees.
    specialists = [
        ("style_advisor", "search"),
        ("curator", "recommendation"),
        ("value_analyst", "pricing"),
        ("stock_keeper", "inventory"),
        ("experience_guide", "support"),
    ]
    specialist_summary = ", ".join(f"{role}→{name}" for name, role in specialists)
    logger.info(
        "✅ Loaded %d specialist agents: %s",
        len(specialists),
        specialist_summary,
    )

    # Tools. Walk services.agent_tools and collect every Strands @tool
    # so the count stays honest if a tool is added or removed.
    try:
        import services.agent_tools as agent_tools

        tool_names = sorted(
            name
            for name in dir(agent_tools)
            if getattr(agent_tools, name).__class__.__name__ == "DecoratedFunctionTool"
        )
        logger.info(
            "✅ Loaded %d agent tools: %s",
            len(tool_names),
            ", ".join(tool_names),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not enumerate agent tools: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app
    Handles startup and shutdown events
    """
    # Startup
    logger.info("Starting Pellier API...")
    
    global db_service, embedding_service, chat_service, query_logger, index_performance_service

    if settings.PELLIER_SMOKE_MODE:
        logger.info(
            "PELLIER_SMOKE_MODE enabled — skipping Aurora, Bedrock, "
            "Strands, and AgentCore service initialization"
        )
        yield
        logger.info("Shutting down Pellier API smoke process...")
        logger.info("👋 Goodbye!")
        return
    
    try:
        # Initialize Strands OpenTelemetry tracing
        try:
            from strands.telemetry import StrandsTelemetry
            import sys
            
            strands_telemetry = StrandsTelemetry()
            
            # Custom formatter for cleaner trace output
            def format_trace(span):
                attrs = span.attributes or {}
                name = span.name
                duration_ms = (span.end_time - span.start_time) / 1_000_000  # ns to ms
                
                # Extract key metrics
                agent_name = attrs.get('gen_ai.agent.name', '')
                total_tokens = attrs.get('gen_ai.usage.total_tokens', 0)
                prompt_tokens = attrs.get('gen_ai.usage.prompt_tokens', 0)
                completion_tokens = attrs.get('gen_ai.usage.completion_tokens', 0)
                
                # Format based on span type
                if 'invoke_agent' in name:
                    return f"✨ Agent: {agent_name} | {duration_ms:.0f}ms | Tokens: {total_tokens} ({prompt_tokens} in + {completion_tokens} out)\n"
                elif 'chat' in name and total_tokens > 0:
                    return f"  🤖 LLM Call | {duration_ms:.0f}ms | Tokens: {total_tokens}\n"
                elif 'execute_event_loop_cycle' in name:
                    cycle_id = attrs.get('event_loop.cycle_id', '')[:8]
                    return f"  🔄 Cycle {cycle_id} | {duration_ms:.0f}ms\n"
                else:
                    return f"  • {name} | {duration_ms:.0f}ms\n"
            
            strands_telemetry.setup_console_exporter(
                out=sys.stdout,
                formatter=format_trace
            )

            logger.info("✅ Strands OpenTelemetry tracing enabled (compact format)")

            # Export traces to CloudWatch X-Ray via OTLP (requires OTEL_EXPORTER_OTLP_ENDPOINT)
            try:
                import os
                if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
                    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", settings.OTEL_EXPORTER_OTLP_ENDPOINT)
                    os.environ.setdefault("OTEL_SERVICE_NAME", "pellier")
                    os.environ.setdefault("OTEL_RESOURCE_ATTRIBUTES", "service.namespace=pellier,deployment.environment=workshop")
                    strands_telemetry.setup_otlp_exporter()
                    logger.info("✅ OTLP exporter enabled — traces → CloudWatch X-Ray")
                else:
                    logger.info("ℹ️  OTLP exporter skipped (set OTEL_EXPORTER_OTLP_ENDPOINT to enable)")
            except Exception as e:
                logger.warning(f"⚠️ OTLP exporter not available: {e}")

            # Attach in-memory span capture for trace extraction
            try:
                from services.otel_trace_extractor import init_span_capture
                init_span_capture()
            except Exception as e:
                logger.warning(f"⚠️ Failed to init span capture: {e}")

        except ImportError:
            logger.warning("⚠️ Strands OpenTelemetry not available - install with: pip install 'strands-agents[otel]'")
        except Exception as e:
            logger.warning(f"⚠️ Failed to setup OpenTelemetry: {e}")
        
        # Initialize core services
        db_service = DatabaseService()
        await db_service.connect()
        logger.info("✅ Database service initialized")
        
        embedding_service = EmbeddingService()
        logger.info("✅ Embedding service initialized (Cohere Embed v4)")

        # Initialize Valkey cache (graceful fallback to in-memory)
        cache_svc = init_cache(
            valkey_url=settings.VALKEY_URL,
            default_ttl=settings.CACHE_TTL,
        )
        logger.info(f"✅ Cache service initialized (mode={cache_svc.mode})")
        
        chat_service = ChatService(db_service=db_service)
        logger.info("✅ Chat service initialized")

        # Initialize SQL query logger
        query_logger = init_query_logger(max_logs=100)
        logger.info("✅ SQL query logger initialized")

        # Initialize index performance service
        conn_string = f"host={settings.DB_HOST} port={settings.DB_PORT} dbname={settings.DB_NAME} user={settings.DB_USER} password={settings.DB_PASSWORD}"
        index_performance_service = get_index_performance_service(conn_string)
        logger.info("✅ Index performance service initialized")

        # Set chat service logger to INFO
        logging.getLogger('services.chat').setLevel(logging.INFO)

        # Initialize agent tools. The concierge uses pure pgvector
        # semantic search (``VectorSearch.vector_search``); the hybrid
        # + rerank pipeline was removed when the concierge switched
        # to the baseline retrieval teaching surface.
        from services.agent_tools import set_db_service, set_main_loop
        set_db_service(db_service)
        # Capture the running lifespan loop (get_running_loop is the correct,
        # non-deprecated call here — we are inside the async startup hook).
        set_main_loop(asyncio.get_running_loop())
        logger.info("✅ Agent tools initialized with pgvector semantic search")

        # Wire the tool_audit writer the same way. Theo's anchor
        # capability persists every mutation to Aurora's pellier.tool_audit
        # table; the writer is fire-and-forget but needs the same
        # DB pool + main event loop reference to bridge sync→async.
        from services import tool_audit_writer
        tool_audit_writer.set_db_service(db_service)
        tool_audit_writer.set_main_loop(asyncio.get_running_loop())
        logger.info("✅ tool_audit writer initialized for ALLOW-path mutation logging")

        # Load the skill registry once at boot. Per-request cost is zero —
        # skills are served from memory. See backend/skills/ for the
        # registry, models, and (Phase 2) the one-call router.
        from skills import load_registry
        load_registry()

        # Inventory the specialists + tools so the operator can confirm at
        # a glance what the process can actually route to. Keeps parity
        # with the skills loader's "✅ Loaded N skills..." line.
        _log_agent_and_tool_inventory()

        logger.info("🚀 Pellier API is ready!")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Pellier API...")
    
    if db_service:
        await db_service.disconnect()
    
    logger.info("👋 Goodbye!")


# Create FastAPI app
app = FastAPI(
    title="Pellier API",
    description="Agentic AI search with Aurora and Bedrock AgentCore",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Storefront auth routes (Task 3.3) — Cognito sign-in loop + session
# cookie management. Mounted at /api/auth/* by the router's own prefix.
app.include_router(auth_router)

# Storefront user routes (Task 3.4) — preference persistence via
# AgentCore Memory. Mounted at /api/user/* by the router's own prefix.
app.include_router(user_router)

# Storefront agent routes (Task 3.5) — SSE chat stream + session
# history. Mounted at /api/agent/* by the router's own prefix. JWT is
# validated exactly once at stream start; mid-stream token expiry does
# not abort the response (Design Error Handling row + Sequence #2).
app.include_router(agent_router)

# Storefront product + inventory routes (Task 3.6) — editorial and
# personalized product listings, single-product lookup, and the live
# inventory signal for the status strip. The routers are AUTHORITATIVE
# for /api/products, /api/products/{id}, /api/inventory, and /api/search —
# the legacy @app.get/@app.post handlers for those paths were removed and
# should NOT be re-added here, not even for "safety." Add new endpoints to
# routes/products.py and routes/search.py instead.
app.include_router(products_router)
app.include_router(search_router)

# Workshop telemetry surface — returns flat
# {session_id, events: list[dict]} payloads for the panel renderer.
# Intentionally separate from /api/agent/chat so the Pellier SSE
# stream isn't reshaped for the workshop's replay needs.
app.include_router(workshop_router)

# Pellier Labs Observatory read-only API endpoints — sessions, agents, tools,
# routing, memory, performance, evaluations, observatory dashboard.
# Additive to workshop_router (same /api/agent-trace/ prefix, no path conflicts).
app.include_router(agent_trace_router)

# Pellier ambient chrome — briefing (concierge empty state) + pulse
# (4 live metrics above the hero). Both endpoints are contract-typed
# via Pydantic and degrade gracefully; they are never allowed to 5xx
# the homepage.
app.include_router(pellier_router)
app.include_router(transcribe_router)


# Dependency injection
async def get_db_service() -> DatabaseService:
    """Get database service instance"""
    if not db_service:
        raise HTTPException(
            status_code=503, 
            detail="Database unavailable - check network connectivity to Aurora cluster"
        )
    return db_service


async def get_embedding_service() -> EmbeddingService:
    """Get embedding service instance"""
    if not embedding_service:
        raise HTTPException(status_code=503, detail="Embedding service not initialized")
    return embedding_service


# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

# Root + SPA serving ------------------------------------------------------
# The workshop runs in "production build" mode: FastAPI owns port 8000
# and serves the built React SPA from ``../frontend/dist``. No separate
# Vite dev server on attendee laptops — kills the "npm run dev on
# Windows" failure modes (port 5173 conflicts, file watcher limits,
# node_modules install issues behind corporate proxies).
#
# Resolution order for ``FRONTEND_DIST``:
#   1. If ``FRONTEND_DIST_PATH`` env var is set, use that.
#   2. Otherwise look for ``../frontend/dist`` relative to backend/.
#   3. If neither exists (pure API mode / tests), fall back to the
#      JSON status blob from the root handler.
#
# ``SPA_MOUNT_PATH`` controls the URL prefix the SPA is served from.
# Default ``/`` matches the historical behavior — nginx in this repo
# rewrites ``/app/`` → ``/`` before forwarding (see
# scripts/bootstrap-environment.sh:173-182), so root mount works behind
# both ``/ports/8000/*`` and ``/app/*`` proxies. Set to ``/app`` if a
# downstream proxy ever forwards the prefix verbatim instead of
# stripping it.
FRONTEND_DIST = Path(
    os.environ.get("FRONTEND_DIST_PATH")
    or (Path(__file__).resolve().parent.parent / "frontend" / "dist")
).resolve()

SPA_MOUNT_PATH = (os.environ.get("SPA_MOUNT_PATH", "/").rstrip("/") or "/")
SPA_STATIC_FILES = {
    path.relative_to(FRONTEND_DIST).as_posix(): path
    for path in FRONTEND_DIST.rglob("*")
    if path.is_file() and path.name != "index.html"
}


async def _serve_spa_root():
    """Serve the SPA's ``index.html`` if built, else return API status."""
    index_html = FRONTEND_DIST / "index.html"
    if index_html.is_file():
        return FileResponse(
            index_html,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return JSONResponse(
        {
            "message": "Pellier API",
            "version": "1.0.0",
            "note": (
                "Frontend bundle not found at "
                f"{FRONTEND_DIST}. Run `npm run build` in pellier/frontend/ "
                "to produce the SPA, or set FRONTEND_DIST_PATH."
            ),
        }
    )


# Mount path semantics:
#   - SPA_MOUNT_PATH = "/"   → serve SPA at ``/`` (legacy default).
#   - SPA_MOUNT_PATH = "/app" → serve SPA at ``/app/`` and 307-redirect
#     bare ``/app`` to ``/app/``. Trailing slash matters because the
#     bundle uses relative asset URLs ("assets/foo.js"); without the
#     slash, the browser resolves them against ``/`` and 404s.
if SPA_MOUNT_PATH == "/":
    app.add_api_route(
        "/",
        _serve_spa_root,
        methods=["GET"],
        include_in_schema=False,
    )
else:
    _slash_target = SPA_MOUNT_PATH + "/"

    async def _spa_redirect_to_slash():
        return RedirectResponse(url=_slash_target, status_code=307)

    app.add_api_route(
        SPA_MOUNT_PATH,
        _spa_redirect_to_slash,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        _slash_target,
        _serve_spa_root,
        methods=["GET"],
        include_in_schema=False,
    )


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint
    Returns status of all services
    """
    if settings.PELLIER_SMOKE_MODE:
        return HealthResponse(
            status="healthy",
            database="smoke",
            bedrock="smoke",
            custom_tools="available",
            version="1.0.0",
        )

    if not db_service:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable - check network connectivity to Aurora cluster",
        )

    health_status = {
        "status": "healthy",
        "database": "unknown",
        "bedrock": "unknown",
        "custom_tools": "available",
        "version": "1.0.0",
    }

    # Check database connection
    try:
        await db_service.execute_query("SELECT 1")
        health_status["database"] = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["database"] = "disconnected"
        health_status["status"] = "degraded"

    # Check Bedrock access
    try:
        embedding_service.generate_embedding("test")
        health_status["bedrock"] = "accessible"
    except Exception as e:
        logger.error(f"Bedrock health check failed: {e}")
        health_status["bedrock"] = "inaccessible"
        health_status["status"] = "degraded"

    return HealthResponse(**health_status)


# ============================================================================
# LAB 1: SEMANTIC SEARCH ENDPOINTS
# ============================================================================
#
# POST /api/search is authoritative on routes/search.py (StorefrontSearchResponse
# wire shape). The legacy semantic_search handler that used to live here has
# been removed — don't re-add it; the router owns that path.


# NOTE: the old ``POST /api/search/image`` multi-modal endpoint and its
# ``ImageSearchService`` backing have been removed — no frontend caller
# was left after the storefront scope trimmed down to text-in search.
# If image search returns, restore via a fresh ``routes/search.py``
# handler using Bedrock Claude vision + pgvector; don't bring back the
# global service singleton.

_LIKE_METACHARACTERS = re.compile(r"([\\%_])")


def _prepare_like_pattern(term: str) -> str:
    """Neutralize shopper text for use inside an ILIKE pattern.

    Escapes the LIKE metacharacters (``\\``, ``%``, ``_``) so the input
    matches literally, then adds the surrounding wildcards. The value is
    still sent to PostgreSQL as a bound parameter — escaping here only
    stops a stray ``%`` or ``_`` from acting as a wildcard.
    """
    escaped = _LIKE_METACHARACTERS.sub(r"\\\1", term)
    return f"%{escaped}%"


@app.get("/api/products/category/{category_query}")
async def explore_collection(
    category_query: str,
    limit: int = Query(default=5, ge=1, le=50),
    db: DatabaseService = Depends(get_db_service),
):
    """Fast category browsing without embeddings"""
    try:
        logger.info(f"📂 Category browse: '{category_query}' (limit={limit})")
        
        query = """
            SELECT
                "productId",
                name,
                brand,
                color,
                description,
                "imgUrl" as imgurl,
                rating,
                reviews,
                price,
                category,
                badge,
                tags,
                1.0 as similarity_score
            FROM pellier.product_catalog
            WHERE (category ILIKE %s OR name ILIKE %s OR description ILIKE %s)
              AND "imgUrl" IS NOT NULL
              AND NOT (tags ? 'archive')
            ORDER BY rating DESC, reviews::int DESC
            LIMIT %s
        """

        pattern = _prepare_like_pattern(category_query)
        results = await db.fetch_all(query, pattern, pattern, pattern, limit)
        logger.info(f"📦 Found {len(results)} products in category")
        
        return {
            "results": [
                {
                    "product": dict(row),
                    "similarity_score": 1.0
                }
                for row in results
            ],
            "total_results": len(results),
            "search_type": "category"
        }
    except Exception as e:
        logger.error(f"❌ Category browse failed: {e}")
        raise HTTPException(status_code=500, detail="internal_error")



# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


@app.get("/api/tools")
async def list_custom_tools():
    """List all custom business logic tools available"""
    return [
        {"name": "find_pieces", "description": "Search for products by natural language query with optional filters"},
        {"name": "whats_trending", "description": "Get trending products by reviews and ratings"},
        {"name": "explore_collection", "description": "Browse products filtered by category, rating, and price"},
        {"name": "floor_check", "description": "Check stock levels and inventory alerts"},
        {"name": "price_intelligence", "description": "Price analytics by category"},
        {"name": "restock_shelf", "description": "Update product stock quantities"},
        {"name": "side_by_side", "description": "Side-by-side product comparison"},
        {"name": "running_low", "description": "Find products running low on inventory"},
    ]


@app.get("/api/tools/trending")
async def get_trending(
    limit: int = Query(default=5, ge=1, le=50),
    category: str = Query(default=None),
    db: DatabaseService = Depends(get_db_service)
):
    """Get trending products using business logic"""
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(db)
        return await logic.whats_trending(limit, category)
    except Exception as e:
        logger.error(f"Failed to get trending products: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


@app.get("/api/tools/inventory-health")
async def floor_check_endpoint(
    db: DatabaseService = Depends(get_db_service)
):
    """Get inventory health using business logic"""
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(db)
        return await logic.floor_check()
    except Exception as e:
        logger.error(f"Failed to get inventory health: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


@app.get("/api/tools/price-stats")
async def get_price_stats(
    category: str = Query(default=None),
    db: DatabaseService = Depends(get_db_service)
):
    """Get price statistics using business logic"""
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(db)
        return await logic.price_intelligence(category)
    except Exception as e:
        logger.error(f"Failed to get price statistics: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


def _assert_claimable_customer_id(customer_id: str) -> str:
    """HTTP adapter over :func:`services.persona_identity.assert_claimable_customer_id`.

    Args:
        customer_id: The customer id asserted by the caller.

    Returns:
        The same id, unchanged, when the claim is allowed.

    Raises:
        HTTPException: 403 when the id is not a seeded persona, or 503 when
            persona configuration is unreadable and the claim cannot be
            checked at all.
    """
    from services.persona_identity import (
        CustomerIdNotClaimable,
        PersonasUnavailable,
        assert_claimable_customer_id,
    )

    try:
        return assert_claimable_customer_id(customer_id)
    except PersonasUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="personas_unavailable"
        ) from exc
    except CustomerIdNotClaimable as exc:
        raise HTTPException(
            status_code=403, detail="customer_id_not_claimable"
        ) from exc


@app.post("/api/tools/restock")
async def restock_shelf_endpoint(
    request: dict,
    user=Depends(get_current_user),
    db: DatabaseService = Depends(get_db_service)
):
    """Restock a product using business logic. Auth-gated like every other
    write path so the inventory mutation carries a caller identity."""
    product_id = request.get("product_id")
    quantity = request.get("quantity")
    if product_id is None or quantity is None:
        raise HTTPException(
            status_code=422,
            detail="product_id and quantity are required",
        )
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(db)
        return await logic.restock_shelf(
            product_id=product_id,
            quantity=quantity,
        )
    except Exception as e:
        logger.error(f"Failed to restock product: {e}")
        raise HTTPException(status_code=500, detail="restock_failed")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    """
    Chat endpoint with Aurora AI using Strands SDK and Custom Tools
    """
    if not chat_service:
        raise HTTPException(status_code=503, detail="Chat service not initialized")

    try:
        # Convert conversation history to dict format
        history = [{"role": msg.role, "content": msg.content} for msg in request.conversation_history]

        # Get chat response with session persistence
        response = await chat_service.chat(
            message=request.message,
            conversation_history=history,
            session_id=request.session_id,
            workshop_mode=request.workshop_mode,
            guardrails_enabled=request.guardrails_enabled,
            user=user
        )
        
        return ChatResponse(**response)
        
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail="chat_failed")


@app.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    user=Depends(get_current_user),
    session_token: Optional[str] = Header(
        default=None,
        alias="X-Pellier-Session-Token",
    ),
):
    """
    Streaming chat endpoint with real-time agent events via SSE.

    Uses chat_service.chat_stream() which runs the orchestrator in a background
    thread and yields events (tool calls, products, text) the moment they happen
    via an asyncio.Queue bridge, instead of waiting for the full chain to finish.
    """
    from fastapi.responses import StreamingResponse

    # Validate the asserted identity first: before smoke mode, before the
    # service check, and before the SSE response begins. Raising from inside
    # the generator would abort a stream that had already returned 200
    # instead of rejecting the request, and an impersonation attempt is
    # invalid whether or not the chat service happens to be up.
    claimed_customer_id = (
        _assert_claimable_customer_id(request.customer_id)
        if request.customer_id
        else None
    )

    if settings.PELLIER_SMOKE_MODE:
        async def smoke_event_generator():
            content = (
                "I'm Pellier. For ten days in Goa, I would start with the "
                "Italian Linen Camp Shirt, Linen Drawstring Trousers, Linen "
                "Overshirt, and a cotton-linen tee, then rotate the lighter "
                "layers around dinners, travel days, and the beach."
            )
            if request.message.strip().lower() in {"hi", "hello", "hey"}:
                content = (
                    "I'm your Pellier concierge. I can help you "
                    "search linen, compare pieces, and keep the edit grounded."
                )

            routing = {
                "type": "skill_routing",
                "routing": {
                    "loaded_skills": ["the-packing-list"],
                    "considered": [
                        {
                            "name": "the-packing-list",
                            "reason": "Smoke-mode wardrobe query routing.",
                        }
                    ],
                    "elapsed_ms": 1,
                    "user_message": request.message,
                },
            }
            complete = {
                "type": "complete",
                "response": {
                    "response": content,
                    "products": [],
                    "suggestions": [
                        "Compare the linen layers",
                        "Show lighter travel pieces",
                        "Build a 10-day packing list",
                    ],
                    "agent_execution": {
                        "agent_steps": [],
                        "tool_calls": [],
                        "reasoning_steps": [],
                        "total_duration_ms": 1,
                        "success_rate": 1.0,
                    },
                    "token_count": 0,
                    "estimated_cost_usd": 0,
                },
            }

            yield f"data: {json.dumps(routing, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'content_delta', 'delta': content}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps(complete, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            smoke_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    if not chat_service:
        raise HTTPException(status_code=503, detail="Chat service not initialized")

    if request.session_id:
        try:
            session_actor_id(user, session_token)
        except ValueError as exc:
            raise HTTPException(
                status_code=401,
                detail="session_ownership_required",
            ) from exc

    async def event_generator():
        try:
            history = [{"role": msg.role, "content": msg.content} for msg in request.conversation_history]
            # Merge persona customer_id into the user dict so the agent
            # context and LTM reads scope to the right customer. The
            # persona's customer_id takes precedence over the Cognito
            # sub when both are present (workshop affordance) — but only
            # for a seeded demo persona. See _assert_claimable_customer_id.
            effective_user = dict(user) if user else {}
            if claimed_customer_id:
                effective_user["customer_id"] = claimed_customer_id

            from services.agentcore_identity import AgentCoreIdentityService
            from services.agentcore_memory import AgentCoreMemory

            memory_namespace = AgentCoreIdentityService.build_namespace(
                user.get("sub") if user else None,
                request.session_id or "",
            )
            memory = AgentCoreMemory(
                strict=bool(settings.AGENTCORE_MEMORY_ID),
            )
            memory_receipt = {
                "source": "agentcore-memory",
                "loaded_messages": 0,
                "persisted": False,
            }
            if request.session_id:
                try:
                    durable_history = (
                        await memory.get_session_history(memory_namespace)
                    )[-16:]
                    if durable_history:
                        history = durable_history
                    memory_receipt["loaded_messages"] = len(durable_history)
                except Exception as exc:
                    logger.warning(
                        "AgentCore session history read failed for %s: %s",
                        request.session_id,
                        exc.__class__.__name__,
                    )

            streamed_content = ""

            # Per-turn guardrail INPUT check — records a decision in
            # services/guardrails_log so Pellier Labs Grounding page's
            # Guardrails lane shows live audit rows. Only runs when
            # the user enabled guardrails in their request; otherwise
            # the log captures no entry (accurate — nothing happened).
            # Failures are swallowed: guardrail eval is observational,
            # not a hard turn gate in this demo surface.
            guardrail_event = None
            if request.guardrails_enabled:
                try:
                    import time as _time
                    from services.guardrails import GuardrailsService
                    from services.guardrails_log import record_guardrail
                    _g = GuardrailsService()
                    _t0 = _time.perf_counter()
                    _res = _g.check_input(request.message)
                    _latency = int((_time.perf_counter() - _t0) * 1000)
                    record_guardrail(
                        session_id=request.session_id,
                        source="INPUT",
                        action=_res.get("action", "NONE"),
                        allowed=_res.get("allowed", True),
                        violations=_res.get("violations", []),
                        latency_ms=_latency,
                        text_preview=request.message,
                        mode=_res.get("mode"),
                    )
                    guardrail_event = {
                        "type": "guardrail_decision",
                        "guardrail": {
                            "allowed": bool(_res.get("allowed", True)),
                            "action": str(_res.get("action", "NONE")),
                            "violations": len(_res.get("violations", [])),
                            "mode": str(_res.get("mode") or "configured"),
                            "enforced": False,
                        },
                    }
                except Exception as _exc:
                    logger.debug("Input guardrail observational check failed: %s", _exc)
                    guardrail_event = {
                        "type": "guardrail_decision",
                        "guardrail": {
                            "allowed": True,
                            "action": "ERROR",
                            "violations": 0,
                            "mode": "error",
                            "enforced": False,
                        },
                    }

            if guardrail_event is not None:
                yield f"data: {json.dumps(guardrail_event, ensure_ascii=False)}\n\n"

            async for event in chat_service.chat_stream(
                message=request.message,
                conversation_history=history,
                session_id=request.session_id,
                workshop_mode=request.workshop_mode,
                guardrails_enabled=request.guardrails_enabled,
                user=effective_user or None,
                pattern=request.pattern,
                response_mode=request.response_mode,
                memory_managed_by_caller=True,
            ):
                event_type = event.get("type")
                if event_type == "content_reset":
                    streamed_content = ""
                elif event_type == "content_delta":
                    streamed_content += str(event.get("delta") or "")
                elif event_type == "content":
                    streamed_content = str(event.get("content") or "")
                elif event_type == "complete":
                    response_payload = event.setdefault("response", {})
                    assistant_message = (
                        streamed_content.strip()
                        or str(response_payload.get("response") or "").strip()
                    )
                    if request.session_id and assistant_message:
                        try:
                            await memory.append_session_turns(
                                memory_namespace,
                                [
                                    {
                                        "role": "user",
                                        "content": request.message,
                                    },
                                    {
                                        "role": "assistant",
                                        "content": assistant_message,
                                    },
                                ],
                            )
                            memory_receipt["persisted"] = True
                        except Exception as exc:
                            logger.warning(
                                "AgentCore session history append failed for %s: %s",
                                request.session_id,
                                exc.__class__.__name__,
                            )
                    response_payload["memory"] = memory_receipt
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            logger.error(f"Streaming chat failed: {e}")
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "error": "The live agent response failed.",
                        "code": "chat_failed",
                    }
                )
                + "\n\n"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/chat/session/{session_id}")
async def get_pellier_chat_session(
    session_id: str,
    user=Depends(get_current_user),
    session_token: Optional[str] = Header(
        default=None,
        alias="X-Pellier-Session-Token",
    ),
):
    """Return AgentCore Memory turns written by ``/api/chat/stream``."""
    try:
        session_actor_id(user, session_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="session_ownership_required",
        ) from exc
    from services.agentcore_identity import AgentCoreIdentityService
    from services.agentcore_memory import AgentCoreMemory, ManagedMemoryError

    namespace = AgentCoreIdentityService.build_namespace(
        user.get("sub") if user else None,
        session_id,
    )
    try:
        turns = await AgentCoreMemory(
            strict=bool(settings.AGENTCORE_MEMORY_ID),
        ).get_session_history(namespace)
    except ManagedMemoryError as exc:
        raise HTTPException(
            status_code=503,
            detail=exc.code,
        ) from exc
    return {
        "session_id": session_id,
        "source": "agentcore-memory",
        "turns": turns,
    }


@app.get("/api/autocomplete")
async def autocomplete(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=5, ge=1, le=10),
    db: DatabaseService = Depends(get_db_service)
):
    """Product search autocomplete"""
    try:
        query = """
            SELECT name, category
            FROM pellier.product_catalog
            WHERE name ILIKE %s
              AND NOT (tags ? 'archive')
            ORDER BY reviews DESC
            LIMIT %s
        """
        results = await db.fetch_all(query, _prepare_like_pattern(q), limit)
        return {"suggestions": [{
            "text": r["name"][:60],
            "category": r["category"]
        } for r in results]}
    except Exception as e:
        logger.error(f"❌ Autocomplete failed: {e}")
        return {"suggestions": []}


# NOTE: the old ``POST /api/agents/query`` legacy endpoint (which
# dispatched to individual specialist agents by ``agent_type``) has
# been removed. No frontend caller remained — the orchestrator path
# is ``POST /api/agent/chat`` (see routes/agent.py) which the
# concierge already uses.


# ============================================================================
# SQL QUERY INSPECTOR ENDPOINTS
# ============================================================================

@app.get("/api/queries/recent")
async def get_recent_queries(limit: int = Query(default=10, ge=1, le=50)):
    """
    Get recent SQL queries with performance metrics
    
    Returns query logs for the SQL Inspector UI
    """
    try:
        query_logger_instance = get_query_logger()
        queries = query_logger_instance.get_recent_queries(limit=limit)
        stats = query_logger_instance.get_summary_stats()
        
        return {
            "queries": queries,
            "stats": stats,
            "total": len(queries)
        }
    except Exception as e:
        logger.error(f"Failed to get recent queries: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


@app.post("/api/queries/clear")
async def clear_query_logs():
    """Clear all query logs"""
    try:
        query_logger_instance = get_query_logger()
        query_logger_instance.clear_logs()
        return {"status": "success", "message": "Query logs cleared"}
    except Exception as e:
        logger.error(f"Failed to clear logs: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


# ============================================================================
# INDEX PERFORMANCE ENDPOINTS
# ============================================================================

@app.post("/api/performance/compare")
async def compare_index_performance(
    request: PerfCompareRequest,
    embeddings: EmbeddingService = Depends(get_embedding_service)
):
    """
    Compare HNSW index performance vs sequential scan

    Request body is validated by PerfCompareRequest: ef_search reaches a
    Postgres SET statement that cannot bind parameters, so it must be a
    bounded int before it is interpolated.
    """
    try:
        query = request.query
        ef_search = request.ef_search
        limit = request.limit

        logger.info(f"🔬 Index performance comparison: '{query}' (ef_search={ef_search})")
        
        # Generate embedding
        embedding = embeddings.generate_embedding(query)
        
        # Run comparison
        results = await index_performance_service.compare_index_performance(
            query=query,
            embedding=embedding,
            ef_search=ef_search,
            limit=limit
        )
        
        logger.info(f"✅ Comparison complete: HNSW={results['hnsw']['execution_time_ms']}ms, Sequential={results['sequential']['execution_time_ms']}ms")
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Performance comparison failed: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


@app.get("/api/performance/runtime")
async def performance_runtime(include_recent: bool = False):
    """Return rolling aggregates of chat turn latency breakdowns.

    Feeds Pellier Labs Performance tab — layer p50/p95 replace the
    hardcoded 3779ms/4ms numbers, cold-start histogram replaces the
    stub bars, tool p50 fuels the per-tool legend. Empty buffer is
    reported honestly so the UI can show a placeholder instead of
    faking data.
    """
    try:
        from services.performance_log import get_aggregates, get_recent_turns
        agg = get_aggregates()
        if include_recent:
            agg = {**agg, "recent": get_recent_turns(limit=30)}
        return agg
    except Exception as e:
        logger.warning(f"Performance runtime stats failed: {e}")
        return {
            "turn_count": 0,
            "empty": True,
            "error": "runtime_metrics_unavailable",
        }


@app.get("/api/performance/stats")
async def get_index_stats():
    """Get pgvector index statistics"""
    try:
        stats = await index_performance_service.get_index_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get index stats: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


# ============================================================================
# CONTEXT MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/api/context/stats")
async def get_context_stats(session_id: Optional[str] = Query(default=None)):
    """
    Get context statistics for monitoring
    
    Returns comprehensive metrics for token usage, efficiency, and costs.
    Demonstrates context-window management for the configured Bedrock model.
    
    Args:
        session_id: Optional session ID for session-specific stats
    """
    try:
        from services.context_manager import get_context_manager
        
        context_manager = get_context_manager()
        stats = context_manager.get_context_stats()
        
        logger.info(f"📊 Context stats requested: {stats['current_tokens']:,} tokens, {stats['efficiency_score']:.1f}% efficiency")
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get context stats: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


@app.post("/api/context/clear")
async def clear_context(session_id: str = Query(...)):
    """
    Clear context for a session
    
    Useful for starting fresh conversations or freeing memory.
    System prompts are preserved.
    
    Args:
        session_id: Session ID to clear context for
    """
    try:
        from services.context_manager import get_context_manager
        
        context_manager = get_context_manager()
        context_manager.clear_context()
        
        logger.info(f"🗑️ Context cleared for session: {session_id}")
        
        return {
            "status": "success",
            "message": f"Context cleared for session {session_id}",
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"Failed to clear context: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


@app.get("/api/context/prompts")
async def list_prompts():
    """
    List all available prompt templates with versions and performance metrics
    
    Demonstrates enterprise-grade prompt engineering patterns:
    - Versioned prompts for A/B testing
    - Performance tracking per prompt
    - Agent-specific prompt templates
    """
    try:
        from services.context_manager import PromptRegistry
        
        prompts = PromptRegistry.list_available_prompts()
        
        logger.info(f"📋 Listed {len(prompts)} prompt templates")
        
        return {
            "prompts": prompts,
            "total": len(prompts)
        }
        
    except Exception as e:
        logger.error(f"Failed to list prompts: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


# ============================================================================
# QUANTIZATION COMPARISON ENDPOINT
# ============================================================================

@app.get("/api/performance/quantization")
async def get_quantization_comparison():
    """Compare full-precision vs quantized (SQ/BQ) index sizes"""
    if not index_performance_service:
        raise HTTPException(status_code=503, detail="Index performance service not initialized")
    return await index_performance_service.get_quantization_comparison()


@app.get("/api/performance/categories")
async def get_filter_categories():
    """Get distinct categories for iterative scan demo dropdown"""
    if not index_performance_service:
        raise HTTPException(status_code=503, detail="Index performance service not initialized")
    categories = await index_performance_service.get_distinct_categories()
    return {"categories": categories}


@app.post("/api/performance/iterative-scan")
async def compare_iterative_scan(request: PerfIterativeScanRequest):
    """Compare filtered HNSW with and without iterative scan (pgvector 0.8.0+)"""
    if not index_performance_service:
        raise HTTPException(status_code=503, detail="Index performance service not initialized")
    embedding = embedding_service.generate_embedding(request.query)
    return await index_performance_service.compare_filtered_search(
        query=request.query, embedding=embedding,
        category_filter=request.category, ef_search=request.ef_search,
        limit=request.limit,
    )


@app.post("/api/performance/quantization-benchmark")
async def quantization_benchmark(request: PerfQuantizationRequest):
    """Benchmark float32 vs halfvec vs binary quantization with live queries"""
    if not index_performance_service:
        raise HTTPException(status_code=503, detail="Index performance service not initialized")
    embedding = embedding_service.generate_embedding(request.query)
    return await index_performance_service.compare_quantization_benchmark(
        query=request.query, embedding=embedding, limit=request.limit,
    )


# ============================================================================
# PERSONALIZED SEARCH ENDPOINT
# ============================================================================

@app.post("/api/personalization/search")
async def personalized_search(
    request: Request,
    db: DatabaseService = Depends(get_db_service),
):
    """Search with preference-based re-ranking"""
    from services.business_logic import BusinessLogic
    logic = BusinessLogic(db)
    body = await request.json()
    query = body.get("query", "")
    preferences = body.get("preferences", {})
    limit = body.get("limit", 5)
    return await logic.personalized_search(query, preferences, limit)


# ============================================================================
# WORKSHOP MODULE STATUS ENDPOINT
# ============================================================================

@app.get("/api/agent-trace/skills")
async def list_skills():
    """
    List all skills in the registry for Pellier Labs surfaces.

    Returns a bare JSON array, matching the sibling list endpoints
    (``/api/agent-trace/agents``, ``/api/agent-trace/tools/list``) and the
    ``skills.json`` fixture shape. ``useAgentTraceData`` stores the response
    verbatim, so a bare array keeps ``data ?? []`` an array even if a
    surface is ever switched from fixture mode to ``source: 'api'`` for the
    ``skills`` key — a wrapper object would break the downstream ``.map``.

    Each item carries name, description, version, display_name,
    token_estimate, and the full markdown body so the "Open SKILL.md →"
    link can render it inline without a second request. (Curated UI-only
    fields — persona, loadedBy, signals, status — live in the fixture; the
    registry does not own them.)
    """
    from skills import get_registry
    registry = get_registry()
    return [
        {
            "name": s.name,
            "display_name": s.display_name_resolved,
            "description": s.description,
            "version": s.version,
            "token_estimate": s.token_estimate,
            "body": s.body,
            "path": s.path,
        }
        for s in registry.get_all()
    ]


@app.get("/api/agent-trace/search-strategies/compare")
async def compare_search_strategies(query: str):
    """Run the same query through four retrieval strategies, return
    one observed duration per strategy + top-5 product names + (when present) the
    structured filters Sonnet extracted.

    Surfaces Anna's anchor-capability comparison live to the
    Pellier Labs Performance page so workshop participants can see the
    delta between vector-only / hybrid / hybrid+rerank / agentic
    against the real catalog rather than reading a static fixture.

    Strategies:
      1. **vector only** — pgvector cosine over product_catalog.
         Marco's foundation path.
      2. **hybrid (RRF)** — vector + Postgres FTS in parallel, RRF-merged.
         No reranker pass. Kept as a teaching foil — pure lexical
         loses on conversational queries with this corpus.
      3. **hybrid + rerank** — same as #2 plus Cohere Rerank v3.5.
      4. **agentic (Sonnet → filter → vector → rerank)** — Anna's
         shipped path. Sonnet 4.6 extracts {categories, tags,
         price_max, in_stock, soft_signal}; pgvector cosine
         runs over the filtered candidate set with
         ``hnsw.iterative_scan = 'relaxed_order'`` so filtered recall
         doesn't silently collapse; Cohere Rerank reorders the pool
         using the soft_signal phrase (not the raw query) so
         structured constraints don't pollute the rerank score.

    Returns:
      {
        "query": str,
        "strategies": [
          {"strategy", "observedMs", "modeledCostPerThousandUsd",
           "products": [{name, productId}],
           "extractedFilters": {...}  // strategy 4 only
          }
        ]
      }

    This endpoint runs each strategy once. Its durations are observations,
    not percentile statistics. Cost values are modeled incremental request
    costs, not values read from a bill.
    """
    import asyncio
    import time
    from services.embeddings import EmbeddingService
    from services.vector_search import VectorSearch
    from services.hybrid_search import HybridSearch
    from services.rerank import get_rerank_service
    from services.structured_extract import get_structured_extractor

    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="query parameter required")
    q = query.strip()

    embed = EmbeddingService()
    shared_embed_started = time.perf_counter()
    query_embedding = embed.embed_query(q)
    shared_embedding_ms = int(
        (time.perf_counter() - shared_embed_started) * 1000
    )

    if db_service is None:
        raise HTTPException(
            status_code=503,
            detail="DB not initialized — wait for backend startup to complete",
        )
    db = db_service

    # Strategy 1: pure pgvector cosine. Marco's path.
    t0 = time.perf_counter()
    vec = VectorSearch(db)
    vec_rows = await vec.vector_search(
        query_embedding,
        5,
        ef_search=settings.VECTOR_EF_SEARCH_DEFAULT,
    )
    vec_ms = int((time.perf_counter() - t0) * 1000)
    vec_products = [
        {"name": r.get("name", ""), "productId": r.get("product_id")}
        for r in vec_rows[:5]
    ]

    # Strategy 2: hybrid (RRF), no rerank.
    t0 = time.perf_counter()
    hybrid = HybridSearch(db)
    hybrid_rows = await hybrid.search(
        query=q,
        query_embedding=query_embedding,
        top_n=5,
    )
    hybrid_ms = int((time.perf_counter() - t0) * 1000)
    hybrid_products = [
        {"name": r.get("name", ""), "productId": r.get("product_id")}
        for r in hybrid_rows[:5]
    ]

    # Strategy 3: hybrid + rerank.
    t0 = time.perf_counter()
    rerank_pool = await hybrid.search(
        query=q,
        query_embedding=query_embedding,
        top_n=settings.HYBRID_TOP_N,
    )
    documents = [
        f"{r.get('name','')} — {(r.get('description','') or '')[:200]} ({r.get('category','')})"
        for r in rerank_pool
    ]
    rerank_service = get_rerank_service()
    rerank_outcome = rerank_service.rerank_with_status(
        query=q, documents=documents, top_n=5,
    )
    rerank_results = rerank_outcome.results
    rerank_ms = int((time.perf_counter() - t0) * 1000)
    if rerank_results:
        rerank_products = [
            {
                "name": rerank_pool[r["index"]].get("name", ""),
                "productId": rerank_pool[r["index"]].get("product_id"),
            }
            for r in rerank_results
        ]
    else:
        # Bedrock did not reorder this pool. These are RRF rows. The
        # strategy still reports itself as degraded below so the row is
        # never read — or priced — as a reranked result.
        rerank_products = [
            {"name": r.get("name", ""), "productId": r.get("product_id")}
            for r in rerank_pool[:5]
        ]

    # Strategy 4: agentic — Sonnet-extracted filters → filtered vector
    # → rerank with soft_signal. The boto3 calls are synchronous, so
    # they run on a worker thread to keep the event loop responsive.
    t0 = time.perf_counter()
    extractor = get_structured_extractor()
    extracted = await asyncio.to_thread(extractor.extract, q)
    soft_signal = extracted.get("soft_signal") or q
    # Re-embed only when the soft_signal differs from the raw query —
    # a wasted embed on identical text would just inflate the cost
    # number without changing the ranking.
    if soft_signal != q:
        soft_embedding = embed.embed_query(soft_signal)
    else:
        soft_embedding = query_embedding

    # Try the strictest filter set first; if Sonnet over-constrained the
    # query, peel back the *soft* filters in priority order — tags, then
    # categories — until the pool is large enough to rerank against.
    # Soft filters are model-inferred hints, so relaxing one costs
    # nothing but breadth.
    #
    # Price and availability are NOT in that ladder. A shopper who asks
    # for "under $100, in stock" has stated a hard predicate: returning a
    # $240 backordered item would be a wrong answer, not a broader one.
    # The same rule carries to tenancy, entitlement, and eligibility
    # filters in other domains. When the strictest rung still leaves a
    # thin pool, the thin pool IS the answer, and the response says so.
    AGENTIC_MIN_POOL = 5
    cat = extracted.get("categories") or None
    tag = extracted.get("tags") or None
    pmax = extracted.get("price_max_usd")
    in_stock = bool(extracted.get("in_stock_only"))
    filter_attempts: List[tuple[str, Dict[str, Any]]] = [
        ("strict", dict(categories=cat, tags=tag, price_max_usd=pmax, in_stock_only=in_stock)),
        ("drop_tags", dict(categories=cat, tags=None, price_max_usd=pmax, in_stock_only=in_stock)),
        ("drop_cats", dict(categories=None, tags=None, price_max_usd=pmax, in_stock_only=in_stock)),
    ]
    agentic_pool: List[Dict[str, Any]] = []
    filter_used = "strict"
    for label, kw in filter_attempts:
        agentic_pool = await vec.vector_search_filtered(
            embedding=soft_embedding,
            limit=settings.HYBRID_TOP_N,
            ef_search=settings.VECTOR_EF_SEARCH_DEFAULT,
            **kw,
        )
        filter_used = label
        if len(agentic_pool) >= AGENTIC_MIN_POOL:
            break
    agentic_docs = [
        f"{r.get('name','')} — {(r.get('description','') or '')[:200]} ({r.get('category','')})"
        for r in agentic_pool
    ]
    agentic_outcome = rerank_service.rerank_with_status(
        query=soft_signal, documents=agentic_docs, top_n=5,
    )
    agentic_rerank = agentic_outcome.results
    agentic_ms = int((time.perf_counter() - t0) * 1000)
    if agentic_rerank:
        agentic_products = [
            {
                "name": agentic_pool[r["index"]].get("name", ""),
                "productId": agentic_pool[r["index"]].get("product_id"),
            }
            for r in agentic_rerank
        ]
    else:
        agentic_products = [
            {"name": r.get("name", ""), "productId": r.get("product_id")}
            for r in agentic_pool[:5]
        ]

    # Transparent workshop cost model. These are explicit comparison inputs,
    # not metering output: update the rates and review date together after
    # checking the linked Bedrock pricing page for the event region.
    pricing_reviewed_on = "2026-08-16"
    embedding_tokens_per_query = 32
    embedding_usd_per_million_tokens = 0.12
    rerank_usd_per_thousand_queries = 2.0
    sonnet_input_tokens = 600
    sonnet_output_tokens = 100
    sonnet_input_usd_per_million_tokens = 3.0
    sonnet_output_usd_per_million_tokens = 15.0

    embedding_cost_per_thousand = round(
        (
            embedding_tokens_per_query
            * embedding_usd_per_million_tokens
            * 1_000
        )
        / 1_000_000,
        4,
    )
    sonnet_cost_per_thousand = round(
        (
            sonnet_input_tokens * sonnet_input_usd_per_million_tokens
            + sonnet_output_tokens * sonnet_output_usd_per_million_tokens
        )
        / 1_000,
        4,
    )
    soft_signal_embedding_applied = soft_signal != q

    # A strategy is only charged for the stages it actually ran. When
    # Bedrock rerank fails, the row falls back to fusion order — charging
    # it for a rerank call would make the workshop's "is the rerank spend
    # worth it?" comparison answer a question the run never asked.
    rerank_executed = rerank_outcome.executed
    agentic_rerank_executed = agentic_outcome.executed
    rerank_charge = rerank_usd_per_thousand_queries if rerank_executed else 0.0
    agentic_rerank_charge = (
        rerank_usd_per_thousand_queries if agentic_rerank_executed else 0.0
    )

    agentic_cost_per_thousand = round(
        embedding_cost_per_thousand
        + (
            embedding_cost_per_thousand
            if soft_signal_embedding_applied
            else 0
        )
        + sonnet_cost_per_thousand
        + agentic_rerank_charge,
        4,
    )

    return {
        "query": q,
        "queryEmbedding": query_embedding,
        "sharedQueryEmbeddingObservedMs": shared_embedding_ms,
        "measurementAssumptions": {
            "latency": (
                "One wall-clock observation per strategy for this request; "
                "not a percentile. Strategies run sequentially after a shared "
                "query embedding."
            ),
            "cost": (
                "Modeled incremental request cost per 1,000 queries using the "
                "costModel inputs below; not a billing measurement and "
                "excluding provisioned Aurora compute. A strategy is charged "
                "only for the stages that ran on this request: when "
                "rerankExecuted is false, the rerank component is excluded."
            ),
            "quality": (
                "Product order is live. Recall requires labeled relevance "
                "judgments and is not calculated by this endpoint. Read "
                "rerankExecuted before comparing rows: a degraded rerank "
                "returns fusion order under productOrderSource, so its "
                "ordering is not evidence about reranking."
            ),
            "constraints": (
                "Model-inferred soft filters (tags, then categories) are "
                "relaxed to widen a thin pool. Price and availability are "
                "hard predicates and are never relaxed, so a small pool is "
                "reported as a small pool rather than filled with rows that "
                "violate the request."
            ),
        },
        "costModel": {
            "currency": "USD",
            "pricingReviewedOn": pricing_reviewed_on,
            "pricingSource": "https://aws.amazon.com/bedrock/pricing/",
            "components": {
                "queryEmbedding": {
                    "modelId": settings.BEDROCK_EMBEDDING_MODEL,
                    "inputTokensPerRequest": embedding_tokens_per_query,
                    "inputUsdPerMillionTokens": (
                        embedding_usd_per_million_tokens
                    ),
                    "modeledCostPerThousandUsd": (
                        embedding_cost_per_thousand
                    ),
                    "formula": (
                        "tokens × USD per 1M tokens × 1,000 requests / 1,000,000"
                    ),
                },
                "rerank": {
                    "modelId": settings.BEDROCK_RERANK_MODEL,
                    "callsPerRequest": 1,
                    "usdPerThousandQueries": (
                        rerank_usd_per_thousand_queries
                    ),
                    "modeledCostPerThousandUsd": (
                        rerank_usd_per_thousand_queries
                    ),
                    "formula": "one rerank call per request",
                },
                "filterExtraction": {
                    "modelId": settings.BEDROCK_REPORTING_MODEL,
                    "inputTokensPerRequest": sonnet_input_tokens,
                    "outputTokensPerRequest": sonnet_output_tokens,
                    "inputUsdPerMillionTokens": (
                        sonnet_input_usd_per_million_tokens
                    ),
                    "outputUsdPerMillionTokens": (
                        sonnet_output_usd_per_million_tokens
                    ),
                    "modeledCostPerThousandUsd": (
                        sonnet_cost_per_thousand
                    ),
                    "formula": (
                        "(input tokens × input rate + output tokens × output "
                        "rate) × 1,000 requests / 1,000,000"
                    ),
                },
            },
            "additionalSoftSignalEmbeddingApplied": (
                soft_signal_embedding_applied
            ),
        },
        "strategies": [
            {
                "strategy": "vector only",
                "observedMs": vec_ms,
                "modeledCostPerThousandUsd": embedding_cost_per_thousand,
                "costComponents": ["queryEmbedding"],
                "products": vec_products,
            },
            {
                "strategy": "hybrid (RRF)",
                "observedMs": hybrid_ms,
                "modeledCostPerThousandUsd": embedding_cost_per_thousand,
                "costComponents": ["queryEmbedding"],
                "products": hybrid_products,
            },
            {
                "strategy": "hybrid + rerank",
                "observedMs": rerank_ms,
                "modeledCostPerThousandUsd": round(
                    embedding_cost_per_thousand + rerank_charge,
                    4,
                ),
                "costComponents": (
                    ["queryEmbedding", "rerank"]
                    if rerank_executed
                    else ["queryEmbedding"]
                ),
                "products": rerank_products,
                "rerankExecuted": rerank_executed,
                "rerankModelId": rerank_outcome.model_id,
                "rerankRequestId": rerank_outcome.request_id,
                "degradedReason": rerank_outcome.degraded_reason,
                "productOrderSource": (
                    "rerank" if rerank_executed else "hybrid RRF (rerank degraded)"
                ),
            },
            {
                "strategy": "agentic (Sonnet → filter → vector → rerank)",
                "observedMs": agentic_ms,
                "modeledCostPerThousandUsd": agentic_cost_per_thousand,
                "costComponents": [
                    "queryEmbedding",
                    *(
                        ["additionalSoftSignalEmbedding"]
                        if soft_signal_embedding_applied
                        else []
                    ),
                    "filterExtraction",
                    *(["rerank"] if agentic_rerank_executed else []),
                ],
                "products": agentic_products,
                "rerankExecuted": agentic_rerank_executed,
                "rerankModelId": agentic_outcome.model_id,
                "rerankRequestId": agentic_outcome.request_id,
                "degradedReason": agentic_outcome.degraded_reason,
                "productOrderSource": (
                    "rerank"
                    if agentic_rerank_executed
                    else "filtered vector (rerank degraded)"
                ),
                "extractedFilters": {
                    "categories": extracted.get("categories", []),
                    "tags": extracted.get("tags", []),
                    "priceMaxUsd": extracted.get("price_max_usd"),
                    "inStockOnly": extracted.get("in_stock_only", False),
                    "softSignal": soft_signal,
                    "filterUsed": filter_used,
                    "hardConstraintsEnforced": True,
                    "relaxedFilters": (
                        {
                            "strict": [],
                            "drop_tags": ["tags"],
                            "drop_cats": ["tags", "categories"],
                        }.get(filter_used, [])
                    ),
                    "poolSize": len(agentic_pool),
                    "poolBelowTarget": len(agentic_pool) < AGENTIC_MIN_POOL,
                },
            },
        ],
    }


@app.get("/api/agent-trace/search/explain")
async def explain_search(query: str):
    """Run one hybrid query and return every *intermediate* stage so the
    Pellier Labs "Search" surface can show the mechanism, not just the outcome.

    This is the mechanism counterpart to ``/search-strategies/compare``
    (which shows the *outcome* — which products win, how fast, at what
    cost). Here the payload walks the pipeline a single query takes:

        EMBED → VECTOR → LEXICAL → FUSION → RERANK

    Every stage carries the real artifact a participant should read:
    the literal branch SQL for VECTOR/LEXICAL (the same string the live
    path executes — see ``hybrid_search._VECTOR_BRANCH_SQL`` /
    ``_FTS_BRANCH_SQL``), the per-branch ranks the FUSION stage merges,
    and the position delta the RERANK stage produces. The reordering
    between FUSION and RERANK *is* the teaching moment, and it is live
    data — nothing here is fabricated.

    The response is shaped as panel-shaped stages
    (``tag``/``title``/``sql``/``columns``/``rows``/``meta``/``tagClass``)
    so the frontend reuses the existing telemetry-panel renderer. Rows
    are pre-stringified.

    On a Bedrock rerank outage the RERANK stage degrades honestly: it
    reports the failure in ``meta`` and shows the RRF order unchanged
    (``rrf_pos == reranked_pos``) rather than inventing scores.
    """
    import time
    from services.embeddings import EmbeddingService
    from services.hybrid_search import HybridSearch
    from services.rerank import get_rerank_service

    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="query parameter required")
    q = query.strip()

    if db_service is None:
        raise HTTPException(
            status_code=503,
            detail="DB not initialized — wait for backend startup to complete",
        )

    # ---- helpers -------------------------------------------------------
    def _label(row: Dict[str, Any]) -> str:
        name = row.get("name", "") or "(unnamed)"
        brand = row.get("brand", "")
        return f"{name} · {brand}" if brand else name

    def _num(v: Any, places: int = 4) -> str:
        try:
            return f"{float(v):.{places}f}"
        except (TypeError, ValueError):
            return "—"

    DISPLAY = 8  # rows shown per branch/fusion table

    # ---- EMBED ---------------------------------------------------------
    embed = EmbeddingService()
    t0 = time.time()
    query_embedding = embed.embed_query(q)
    embed_ms = int((time.time() - t0) * 1000)
    head = ", ".join(_num(x, 4) for x in query_embedding[:4])
    embed_stage = {
        "stage": "embed",
        "tag": "SEARCH · EMBED",
        "title": "Query → 1024-d vector · Cohere Embed v4",
        "sql": "",
        "columns": ["field", "value"],
        "rows": [
            ["model", settings.BEDROCK_EMBEDDING_MODEL],
            ["input_type", "search_query"],
            ["output_dimension", "1024"],
            ["normalized", "L2 (unit length)"],
            ["vector[:4]", f"[{head}, … (1024 dims)]"],
        ],
        "meta": "Asymmetric retrieval: the query is embedded as search_query, "
                "the catalog was embedded as search_document. L2-normalized so "
                "cosine distance is well-behaved.",
        "tagClass": "amber",
        "durationMs": embed_ms,
    }

    # ---- VECTOR + LEXICAL + FUSION (one live hybrid pass) --------------
    hybrid = HybridSearch(db_service)
    t0 = time.time()
    explained = await hybrid.search_explained(query=q, query_embedding=query_embedding)
    hybrid_ms = int((time.time() - t0) * 1000)
    vector_rows = explained["vector_rows"]
    fts_rows = explained["fts_rows"]
    merged = explained["merged"]
    params = explained["params"]

    vector_stage = {
        "stage": "vector",
        "tag": "SEARCH · VECTOR",
        "title": "HNSW cosine · pgvector",
        "sql": explained["vector_sql"].strip(),
        "columns": ["rank", "product", "similarity"],
        "rows": [
            [str(i + 1), _label(r), _num(r.get("similarity"))]
            for i, r in enumerate(vector_rows[:DISPLAY])
        ],
        "meta": f"Top {params['k_vector']} by cosine over the HNSW index "
                f"(<=> operator). similarity = 1 − distance; higher is closer.",
        "tagClass": "cyan",
    }

    lexical_stage = {
        "stage": "lexical",
        "tag": "SEARCH · LEXICAL",
        "title": "Full-text · ts_rank_cd",
        "sql": explained["fts_sql"].strip(),
        "columns": ["rank", "product", "ts_rank_cd"],
        "rows": [
            [str(i + 1), _label(r), _num(r.get("fts_rank_score"), 5)]
            for i, r in enumerate(fts_rows[:DISPLAY])
        ],
        "meta": "to_tsquery('english', …) with OR-joined stems over the "
                "description_tsv GIN index. ts_rank_cd is cover-density rank "
                "(matched terms close together rank higher). Empty here means "
                "the query had no lexical anchors — vector carries the recall.",
        "tagClass": "cyan",
    }

    fusion_stage = {
        "stage": "fusion",
        "tag": "SEARCH · FUSION",
        "title": f"Reciprocal Rank Fusion (k={params['rrf_k']})",
        "sql": "",
        "columns": ["product", "vec_rank", "fts_rank", "rrf_score"],
        "rows": [
            [
                _label(r),
                str(r.get("vec_rank")) if r.get("vec_rank") is not None else "—",
                str(r.get("fts_rank")) if r.get("fts_rank") is not None else "—",
                _num(r.get("rrf_score"), 5),
            ]
            for r in merged[:DISPLAY]
        ],
        "meta": f"score(d) = Σ 1 / (k + rank) over each branch d appears in, "
                f"k={params['rrf_k']}. A row ranked in BOTH branches outscores "
                f"a row ranked in only one — that consensus is the point. "
                f"'—' means the row never surfaced in that branch.",
        "tagClass": "cyan",
        "durationMs": hybrid_ms,
    }

    # ---- RERANK --------------------------------------------------------
    # Rerank the fused pool. The reordering between FUSION order (rrf_pos)
    # and RERANK order (reranked_pos) is the headline of the whole surface.
    documents = [
        f"{r.get('name','')} — {(r.get('description','') or '')[:200]} ({r.get('category','')})"
        for r in merged
    ]
    rerank_top = min(DISPLAY, len(merged))
    t0 = time.time()
    rerank_results = get_rerank_service().rerank(
        query=q, documents=documents, top_n=rerank_top,
    )
    rerank_ms = int((time.time() - t0) * 1000)

    if rerank_results:
        rerank_rows = []
        for new_pos, res in enumerate(rerank_results, start=1):
            idx = res.get("index")
            if idx is None or idx >= len(merged):
                continue
            prod = merged[idx]
            rrf_pos = idx + 1  # merged is in RRF order
            delta = rrf_pos - new_pos
            arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
            rerank_rows.append([
                _label(prod),
                str(rrf_pos),
                f"{new_pos} {arrow}",
                _num(res.get("relevance_score"), 4),
            ])
        rerank_meta = (
            "Cohere Rerank v3.5 reads the query + each candidate and assigns a "
            "relevance score in [0,1] used to order this pool. ▲/▼ shows how "
            "far a product moved from its RRF position — that movement is "
            "what the rerank spend buys you. Reranking reorders the candidate "
            "pool; it cannot recover a product retrieval never returned."
        )
    else:
        # Honest degrade — no fabricated scores; show RRF order unchanged.
        rerank_rows = [
            [_label(r), str(i + 1), f"{i + 1} —", "n/a"]
            for i, r in enumerate(merged[:rerank_top])
        ]
        rerank_meta = (
            "Rerank unavailable (Bedrock error) — falling back to RRF order, "
            "positions unchanged. This is the documented degrade path: a rerank "
            "outage drops Anna to plain hybrid, it does not take search down."
        )

    rerank_stage = {
        "stage": "rerank",
        "tag": "SEARCH · RERANK",
        "title": "Cohere Rerank v3.5",
        "sql": "",
        "columns": ["product", "rrf_pos", "reranked_pos", "relevance_score"],
        "rows": rerank_rows,
        "meta": rerank_meta,
        "tagClass": "amber",
        "durationMs": rerank_ms,
    }

    return {
        "query": q,
        "params": params,
        "stages": [
            embed_stage,
            vector_stage,
            lexical_stage,
            fusion_stage,
            rerank_stage,
        ],
    }


@app.get("/api/agent-trace/catalog")
async def agent_trace_catalog():
    """
    Tool catalog + agent grants for Pellier Labs Architecture pages.

    Powers three surfaces:
      - MCP page's tool card grid (Fired / Idle state + p50 latency)
      - Tool Registry bipartite graph (agent → tool edges with styles)
      - Tool Registry detail rows (grants per tool)

    The catalog is hardcoded here because Pellier's tools are declared
    in Python at import time — there isn't a runtime tool-metadata
    table. If we ever add a real tool table (like the ``tools`` table
    migration 001 seeds for the Week 2 teaching panel), swap this to
    read from it.

    ``recent_calls`` and ``last_12_turns`` would come from a real
    telemetry store. For now we report 0 / 0 — the live strip on each
    page surfaces the current turn's activity via SSE, which is what
    matters for a live demo.
    """
    # Agent definitions — matches imports in backend/agents/*.py
    agents = [
        {"name": "orchestrator", "model": "Sonnet", "role": "SONNET · ROUTES"},
        {"name": "search", "model": "Opus", "role": "OPUS · 3 GRANTS"},
        {"name": "recommendation", "model": "Opus", "role": "OPUS · 4 GRANTS"},
        {"name": "pricing", "model": "Sonnet", "role": "SONNET · 3 GRANTS"},
        {"name": "support", "model": "Opus", "role": "OPUS · 2 GRANTS"},
        {"name": "inventory", "model": "Sonnet", "role": "SONNET · 3 GRANTS"},
    ]

    # Tool catalog — headline + description + typical p50.
    # p50 values are approximate defaults; the live strip surfaces
    # actual per-call latencies via the existing tool-call SSE.
    tools = [
        {
            "name": "find_pieces",
            "version": "v2.1",
            "headline": "Semantic search across the catalog.",
            "description": "Natural-language query against pgvector; returns top-k matched products.",
            "p50_ms": 280,
        },
        {
            "name": "whats_trending",
            "version": "v1.3",
            "headline": "Current bestsellers and just-ins.",
            "description": "Returns products tagged BESTSELLER / JUST_IN / EDITORS_PICK from the catalog.",
            "p50_ms": 120,
        },
        {
            "name": "explore_collection",
            "version": "v1.2",
            "headline": "Browse by named category.",
            "description": "Filter-by-category read for shoppers who know what shelf they want.",
            "p50_ms": 80,
        },
        {
            "name": "side_by_side",
            "version": "v1.0",
            "headline": "Side-by-side product comparison.",
            "description": "Takes two product IDs, returns attributes arranged for comparison.",
            "p50_ms": 180,
        },
        {
            "name": "price_intelligence",
            "version": "v1.1",
            "headline": "Price trends, deals, and budget fit.",
            "description": "Analyzes pricing across a category or a specific product family.",
            "p50_ms": 220,
        },
        {
            "name": "floor_check",
            "version": "v1.0",
            "headline": "Stock levels at a glance.",
            "description": "Inventory summary by category with low-stock flags.",
            "p50_ms": 95,
        },
        {
            "name": "running_low",
            "version": "v1.0",
            "headline": "What's running low right now.",
            "description": "Reads products below the restock threshold, ordered by urgency.",
            "p50_ms": 110,
        },
        {
            "name": "restock_shelf",
            "version": "v1.0",
            "headline": "Place a restock signal.",
            "description": "Writes a restock request. Gated — requires explicit user confirmation.",
            "p50_ms": 145,
            "gated": True,
        },
        {
            "name": "returns_and_care",
            "version": "v1.0",
            "headline": "Return windows by category.",
            "description": "Policy lookup used by customer support for returns / refunds questions.",
            "p50_ms": 45,
        },
    ]

    # Agent → tool grants, derived from imports in backend/agents/*.py.
    # Style: 'solid' = everyday access, 'dashed' = read-only/rare,
    # 'gated' = requires user confirmation (espresso-dashed in the UI).
    grants = [
        # search agent imports
        {"agent": "search", "tool": "find_pieces", "style": "solid"},
        {"agent": "search", "tool": "explore_collection", "style": "solid"},
        {"agent": "search", "tool": "side_by_side", "style": "solid"},
        # recommendation agent imports
        {"agent": "recommendation", "tool": "find_pieces", "style": "solid"},
        {"agent": "recommendation", "tool": "whats_trending", "style": "solid"},
        {"agent": "recommendation", "tool": "side_by_side", "style": "solid"},
        {"agent": "recommendation", "tool": "explore_collection", "style": "solid"},
        # pricing agent imports
        {"agent": "pricing", "tool": "price_intelligence", "style": "solid"},
        {"agent": "pricing", "tool": "explore_collection", "style": "solid"},
        {"agent": "pricing", "tool": "find_pieces", "style": "dashed"},
        # inventory agent imports
        {"agent": "inventory", "tool": "floor_check", "style": "solid"},
        {"agent": "inventory", "tool": "running_low", "style": "solid"},
        {"agent": "inventory", "tool": "restock_shelf", "style": "gated"},
        # support agent imports
        {"agent": "support", "tool": "returns_and_care", "style": "solid"},
        {"agent": "support", "tool": "find_pieces", "style": "dashed"},
    ]

    return {
        "agents": agents,
        "tools": tools,
        "grants": grants,
    }


# ---------------------------------------------------------------------------
# Persona endpoints — workshop affordance for switching curated identities.
# Reads from docs/personas-config.json; no database table for persona defs.
# ---------------------------------------------------------------------------

from services.persona_identity import PERSONAS_CONFIG_PATH as _PERSONAS_CONFIG_PATH
from services.persona_identity import load_personas as _load_personas
from services.persona_identity import reset_cache as _reset_personas_cache


@app.get("/api/agent-trace/personas/reload")
async def reload_personas():
    """Dev helper — force re-read of personas-config.json."""
    _reset_personas_cache()
    return {"reloaded": True, "count": len(_load_personas())}


# In-memory session → persona mapping. Lightweight — no DB table.
# Keyed by session_id; value is the persona id string.
_session_persona: dict[str, str] = {}


@app.get("/api/agent-trace/personas")
async def list_personas():
    """Return the three persona definitions (without internal customer_ids)."""
    personas = _load_personas()
    return [
        {
            "id": p["id"],
            "display_name": p["display_name"],
            "role_tag": p["role_tag"],
            "blurb": p["blurb"],
            "avatar_color": p["avatar_color"],
            "avatar_initial": p["avatar_initial"],
            "stats": p["stats"],
        }
        for p in personas
    ]


from pydantic import BaseModel as _BaseModel


class PersonaSwitchRequest(_BaseModel):
    persona_id: str
    current_session_id: Optional[str] = None


@app.post("/api/persona/switch")
async def switch_persona(req: PersonaSwitchRequest):
    """End the current session and start a new one under the given persona."""
    personas = _load_personas()
    persona = next((p for p in personas if p["id"] == req.persona_id), None)
    if not persona:
        raise HTTPException(status_code=404, detail=f"Unknown persona: {req.persona_id}")

    import uuid
    # AgentCore Memory requires session IDs ≥33 chars. Use the full
    # uuid4 hex (32 chars) plus the prefix to guarantee compliance.
    new_session_id = f"persona-{req.persona_id}-{uuid.uuid4().hex}"

    # Track the mapping so /api/persona/current can resolve it.
    _session_persona[new_session_id] = req.persona_id

    return {
        "session_id": new_session_id,
        "persona": {
            "id": persona["id"],
            "display_name": persona["display_name"],
            "role_tag": persona["role_tag"],
            "avatar_color": persona["avatar_color"],
            "avatar_initial": persona["avatar_initial"],
            "customer_id": persona["customer_id"],
            "stats": persona["stats"],
        },
    }


@app.get("/api/persona/current")
async def get_current_persona(session_id: Optional[str] = Query(default=None)):
    """Return the active persona for a session, or null."""
    if not session_id or session_id not in _session_persona:
        return {"persona": None}
    persona_id = _session_persona[session_id]
    personas = _load_personas()
    persona = next((p for p in personas if p["id"] == persona_id), None)
    if not persona:
        return {"persona": None}
    return {
        "persona": {
            "id": persona["id"],
            "display_name": persona["display_name"],
            "role_tag": persona["role_tag"],
            "avatar_color": persona["avatar_color"],
            "avatar_initial": persona["avatar_initial"],
            "customer_id": persona["customer_id"],
            "stats": persona["stats"],
        },
    }


# NOTE: the legacy /api/agent-trace/status endpoint (multi-module stub detection
# for an older workshop draft) was removed from the current required path.
# Pellier Labs progress strip reads GET /api/agent-trace/build-state instead, which
# tracks only the single floor_check exercise. See
# routes/agent_trace.py::get_build_state.


# ============================================================================
# AGENT STATS ENDPOINT
# ============================================================================

@app.get("/api/agent/stats")
async def get_agent_stats():
    """Get session-level agent activity stats"""
    if not chat_service:
        raise HTTPException(status_code=503, detail="Chat service not initialized")
    return chat_service.get_agent_stats()


# ============================================================================
# CACHE & COST ENDPOINTS
# ============================================================================

@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get cache statistics — Valkey/in-memory + embedding cost data."""
    from services.embeddings import get_cache_stats as get_embedding_stats
    cache = get_cache()
    result = cache.stats() if cache else {"mode": "unavailable"}
    result["embedding"] = get_embedding_stats()
    return result


# ============================================================================
# OPENTELEMETRY TRACING ENDPOINTS
# ============================================================================

@app.get("/api/traces/status")
async def get_tracing_status():
    """
    Get OpenTelemetry tracing status and configuration
    """
    try:
        from opentelemetry import trace
        tracer_provider = trace.get_tracer_provider()
        
        return {
            "enabled": tracer_provider is not None,
            "provider_type": type(tracer_provider).__name__,
            "exporters": ["console"],
            "note": "Traces automatically captured by Strands SDK"
        }
    except Exception as e:
        logger.warning("Tracing status fetch failed: %s", e)
        return {"enabled": False, "error": "tracing_status_unavailable"}


@app.get("/api/traces/waterfall")
async def get_trace_waterfall(
    session_id: str = Query(..., min_length=1, max_length=256),
    user=Depends(require_user),
):
    """Get waterfall timing data from captured OTEL spans.

    Always returns HTTP 200 with a structured payload. When OTEL is not
    wired correctly the payload carries ``otel_enabled: False`` plus a
    ``reason`` string — the frontend renders a banner instead of the
    waterfall. See docs/troubleshooting-otel.md.
    """
    try:
        from services.otel_trace_extractor import get_waterfall_data
        return get_waterfall_data(
            session_id=session_id,
            user_id=user.user_id,
        )
    except Exception:
        logger.exception("get_waterfall_data failed")
        return {
            "spans": [],
            "totalMs": 0,
            "specialistRoute": "",
            "waterfall": [],
            "span_count": 0,
            "otel_enabled": False,
            "reason": (
                "Telemetry unavailable. See docs/troubleshooting-otel.md."
            ),
        }


@app.get("/api/traces/info")
async def get_tracing_info():
    """
    Get OpenTelemetry tracing documentation and setup info
    """
    return {
        "tracing_enabled": True,
        "sdk": "Strands OpenTelemetry",
        "exporters": {
            "console": {"enabled": True, "description": "Development traces to console"},
            "otlp": {"enabled": False, "description": "Export to CloudWatch X-Ray/Jaeger"}
        },
        "captured_data": [
            "Agent invocations and routing",
            "LLM calls with token usage",
            "Tool executions with results",
            "End-to-end latency"
        ],
        "visualization": "docker run -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one:latest"
    }


# ============================================================================
# GUARDRAILS ENDPOINT
# ============================================================================

@app.post("/api/guardrails/check")
async def check_guardrails(request: Request):
    """Demo endpoint to test Bedrock Guardrails on input/output text.

    Also records the decision in ``services/guardrails_log`` so the
    Pellier Labs Grounding page's Guardrails lane can surface a live audit
    trail alongside the Cedar policy decisions.
    """
    import time as _time
    from services.guardrails import GuardrailsService
    from services.guardrails_log import record_guardrail

    body = await request.json()
    text = body.get("text", "")
    source = body.get("source", "INPUT")
    session_id = body.get("session_id", "") or ""

    svc = GuardrailsService()
    t0 = _time.perf_counter()
    if source == "OUTPUT":
        result = svc.check_output(text)
    else:
        result = svc.check_input(text)
    latency_ms = int((_time.perf_counter() - t0) * 1000)

    record_guardrail(
        session_id=session_id or None,
        source=source,
        action=result.get("action", "NONE"),
        allowed=result.get("allowed", True),
        violations=result.get("violations", []),
        latency_ms=latency_ms,
        text_preview=text,
        mode=result.get("mode"),
    )

    pii = svc.detect_pii(text)
    return {
        **result,
        "pii_detection": pii,
        "source": source,
        "configured": svc.is_configured,
        "latency_ms": latency_ms,
    }


@app.get("/api/guardrails/decisions")
async def guardrails_decisions(session_id: str = "", limit: int = 50):
    """Return recent guardrail outcomes for a session.

    Feeds Pellier Labs Grounding page's Guardrails lane. Distinct from
    ``/api/agentcore/policy/decisions`` (Cedar tool-call enforcement);
    these are Bedrock content filter outcomes on the prose side.
    """
    try:
        from services.guardrails_log import get_guardrails
        decisions = get_guardrails(session_id or None, limit=max(1, min(500, int(limit))))
        return {"session_id": session_id or "_anonymous", "decisions": decisions, "count": len(decisions)}
    except Exception as e:
        logger.warning(f"Guardrails decisions fetch failed: {e}")
        return {
            "session_id": session_id,
            "decisions": [],
            "count": 0,
            "error": "guardrail_history_unavailable",
        }


# ============================================================================
# AGENTCORE POLICY ENDPOINTS (Cedar)
# ============================================================================

@app.get("/api/agentcore/policy/list")
async def list_policies():
    """List the Cedar policies attached to the managed AgentCore Policy
    engine (Gateway-enforced, ENFORCE mode).

    Reads the managed engine via boto3 ``bedrock-agentcore-control``
    ``list_policies`` keyed on ``AGENTCORE_POLICY_ENGINE_ID``. The old
    local fake-Cedar ``PolicyService`` was removed — enforcement is now
    entirely at the Gateway, so this is a pure read of the managed
    engine's Cedar statements.
    """
    try:
        from services.managed_policy import list_managed_policies
        result = list_managed_policies()
        return {"policies": result.get("policies", []), "source": result.get("source")}
    except Exception as e:
        logger.warning(f"Failed to list policies: {e}")
        return {"policies": [], "error": "managed_policy_unavailable"}


# NOTE: the former POST /api/agentcore/policy/check route was removed.
# It evaluated actions against the local fake-Cedar engine (also removed).
# The managed AgentCore Policy engine evaluates Cedar at the Gateway at
# tool-call time and exposes no client-side "evaluate this action" API,
# so there is nothing for a runtime check endpoint to call.


@app.get("/api/agentcore/memory/ltm")
async def memory_ltm(customer_id: str = ""):
    """Return LTM facts for a persona, ranked by recency.

    Reads the ``pellier.customer_episodic_seed`` fixture table via
    ``services/episodic_memory.fetch_episodic_seed`` — the same source
    chat.py consults when building the persona preamble. The
    MemoryArchPage uses this to replace its hard-coded STUB_LTM_FACTS
    so attendees see persona-tailored history (Marco's linen notes,
    Anna's gift cues, Theo's slow-craft signals) the moment they pick
    a persona.

    Returns ``{customer_id, facts: [{text, ts_offset_days, relative}]}``.
    Anonymous or unknown customers return an empty facts list — the
    frontend falls back to the stub in that case so the page stays
    populated for fresh visitors.
    """
    if not customer_id or customer_id == "anonymous":
        return {"customer_id": customer_id or "", "facts": [], "source": "anonymous"}
    try:
        from services.episodic_memory import fetch_episodic_seed, _format_relative
        if db_service is None:
            return {"customer_id": customer_id, "facts": [], "source": "db-unavailable"}
        rows = await fetch_episodic_seed(db_service, customer_id, limit=10)
        facts = [
            {
                "text": r["summary_text"],
                "ts_offset_days": r["ts_offset_days"],
                "relative": _format_relative(r["ts_offset_days"]),
            }
            for r in rows
        ]
        return {"customer_id": customer_id, "facts": facts, "source": "aurora"}
    except Exception as e:
        logger.warning(f"Memory LTM fetch failed for {customer_id}: {e}")
        return {
            "customer_id": customer_id,
            "facts": [],
            "source": "error",
            "error": "memory_unavailable",
        }


@app.get("/api/agentcore/memory/status")
async def memory_status():
    """Return whether an ACTIVE AgentCore Memory is backing the SDK path.

    The MemoryArchPage in Pellier Labs reads this to show an honest
    banner — either 'Live: AgentCore Memory (id=...)' or 'Fallback:
    in-process dict; set AGENTCORE_MEMORY_ID to enable LIVE'. An ID and
    importable SDK are not sufficient: the control-plane resource must
    exist and report ACTIVE.
    """
    try:
        from services.agentcore_memory import probe_memory_backend_status

        return await asyncio.to_thread(probe_memory_backend_status)
    except Exception as e:
        logger.warning(f"Memory status fetch failed: {e}")
        return {
            "live": False,
            "source": "in-process-dict",
            "error": "memory_status_unavailable",
        }


@app.get("/api/agentcore/gateway/status")
async def gateway_status():
    """Return the effective Gateway wiring for the current backend.

    Pellier Labs MCP / Tool Registry tabs use this to show whether tools
    are being discovered via MCP (Gateway configured) or loaded via
    direct @tool imports (fallback). The ``source`` field is the
    human-readable label shown next to the tool list.
    """
    try:
        from config import settings
        gateway_url = getattr(settings, "AGENTCORE_GATEWAY_URL", None) or ""
        if gateway_url:
            return {
                "configured": True,
                "source": "mcp-discovery",
                "gateway_url": gateway_url,
                "fallback_reason": None,
            }
        return {
            "configured": False,
            "source": "in-process-imports",
            "gateway_url": "",
            "fallback_reason": "AGENTCORE_GATEWAY_URL env var not set",
        }
    except Exception as e:
        logger.warning(f"Gateway status fetch failed: {e}")
        return {
            "configured": False,
            "source": "in-process-imports",
            "error": "gateway_status_unavailable",
        }


@app.get("/api/agentcore/policy/decisions")
async def policy_decisions(session_id: str = "", limit: int = 50):
    """Return recent managed-rail policy decisions for a session.

    The gate is now the managed AgentCore Policy engine at the Gateway,
    which emits ALLOW/DENY decisions to CloudWatch rather than a
    queryable API. Instead of fabricating a decisions store, we surface
    the ``pellier.tool_audit`` ALLOW rows — those rows ARE the managed
    rail's ALLOW evidence (the experience Lambda writes one per tool the
    Gateway let through). A DENY produces no row because the tool never
    ran. See ``services/managed_policy.recent_decisions``."""
    try:
        from services.managed_policy import recent_decisions
        return await recent_decisions(db_service, session_id or None, limit=limit)
    except Exception as e:
        logger.warning(f"Policy decisions fetch failed: {e}")
        return {
            "session_id": session_id,
            "decisions": [],
            "count": 0,
            "error": "policy_history_unavailable",
        }


# ============================================================================
# AGENTCORE ENDPOINTS
# ============================================================================

@app.get("/api/agentcore/memories")
async def agentcore_memories(user=Depends(get_current_user)):
    """Get stored memories for authenticated user"""
    if not user:
        return {"memories": [], "message": "Sign in to view memories"}
    try:
        from services.agentcore_memory import get_user_memories
        memories = get_user_memories(user["sub"])
        return {"memories": memories, "user": user["email"]}
    except Exception as e:
        logger.warning(f"Failed to fetch memories: {e}")
        return {"memories": [], "error": "managed_memory_unavailable"}


@app.get("/api/agentcore/gateway/tools")
async def agentcore_gateway_tools(user=Depends(get_current_user)):
    """List tools registered in the AgentCore Gateway MCP server.

    JWT passthrough: forwards the caller's Cognito token so the live tool
    list is fetched under their identity. Anonymous callers get [] from a
    JWT-protected Gateway (the "skipped" state), which is intentional.
    """
    try:
        from services.agentcore_gateway import list_gateway_tools
        _token = (user or {}).get("access_token") if isinstance(user, dict) else None
        tools = list_gateway_tools(access_token=_token)
        return {"tools": tools, "gateway_url": settings.AGENTCORE_GATEWAY_URL or "not configured"}
    except Exception as e:
        logger.warning(f"Failed to list gateway tools: {e}")
        return {"tools": [], "error": "managed_gateway_unavailable"}


@app.get("/api/agentcore/runtime/status")
async def agentcore_runtime_status():
    """Get AgentCore Runtime execution status"""
    runtime_endpoint = settings.AGENTCORE_RUNTIME_ENDPOINT
    if runtime_endpoint:
        if runtime_endpoint.startswith("arn:"):
            runtime_id = runtime_endpoint.rsplit("/", 1)[-1]
            return {
                "mode": "agentcore",
                "endpoint": runtime_endpoint,
                "runtime_id": runtime_id,
                "healthy": True,
                "status": "configured",
            }

        # Check health of remote runtime
        try:
            import requests as req
            resp = await asyncio.to_thread(req.get, f"{runtime_endpoint}/health", timeout=3)
            return {
                "mode": "agentcore",
                "endpoint": runtime_endpoint,
                "healthy": resp.status_code == 200,
                "latency_ms": int(resp.elapsed.total_seconds() * 1000),
            }
        except Exception:
            return {
                "mode": "agentcore",
                "endpoint": runtime_endpoint,
                "healthy": False,
            }
    return {
        "mode": "local",
        "endpoint": f"http://localhost:{settings.PORT}",
        "healthy": True,
    }


# ============================================================================
# AGENTCORE GOING FURTHER ENDPOINTS
# ============================================================================

@app.get("/api/agentcore/memories/episodes")
async def get_episodic_memories(query: str, user=Depends(get_current_user)):
    """Search episodic memories for relevant past experiences"""
    if not user:
        return {"episodes": [], "message": "Sign in to search episodic memories"}
    try:
        from services.agentcore_memory import search_episodic_memories
        episodes = search_episodic_memories(user["sub"], query)
        return {"episodes": episodes, "query": query, "user": user["email"]}
    except Exception as e:
        logger.warning(f"Failed to search episodic memories: {e}")
        return {"episodes": [], "error": "episodic_memory_unavailable"}


# NOTE: the former POST /api/agentcore/policy/create route was removed.
# Cedar policy creation is owned by the pinned AgentCore CLI project, not a
# runtime endpoint. The old preview-era natural-language helper is gone.


@app.post("/api/agentcore/analytics")
async def analytics_query(request: Request):
    """Run a data analytics query using Code Interpreter agent"""
    try:
        from services.code_interpreter import create_analytics_agent
        body = await request.json()
        prompt = body.get("prompt", "")
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt is required")
        agent = create_analytics_agent()
        if agent is None:
            return {
                "response": "Code Interpreter is not available. Ensure AGENTCORE_RUNTIME_ENDPOINT is configured and strands-agents-tools is installed.",
                "available": False,
            }
        result = str(agent(prompt))
        return {"response": result, "available": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analytics query failed: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


# ============================================================================
# SPA STATIC MOUNT + CLIENT-ROUTE CATCH-ALL
# ============================================================================
# Mounted LAST so every @app.get/@app.post above wins on path conflict.
# The SPA owns ``/`` and every client-side route (``/workshop``,
# ``/storyboard``, ``/discover``, etc.); ``/api/*`` routes remain
# API-side.
#
# The ``/assets`` mount serves Vite's hashed bundle output with a
# browser-friendly cache header — hashed filenames make long cache
# lifetimes safe. ``/fonts`` serves the self-hosted font files we ship
# from ``public/fonts/`` (no Google Fonts runtime dependency — corporate
# networks that block fonts.gstatic.com don't break the workshop).
#
# The catch-all handler falls back to ``index.html`` for anything that
# doesn't map to an /api/* path or a real file in dist/. React Router
# picks up from there.

if FRONTEND_DIST.is_dir():
    _assets_url = (
        "/assets" if SPA_MOUNT_PATH == "/" else f"{SPA_MOUNT_PATH}/assets"
    )
    _fonts_url = (
        "/fonts" if SPA_MOUNT_PATH == "/" else f"{SPA_MOUNT_PATH}/fonts"
    )
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount(_assets_url, StaticFiles(directory=assets_dir), name="assets")
    fonts_dir = FRONTEND_DIST / "fonts"
    if fonts_dir.is_dir():
        app.mount(_fonts_url, StaticFiles(directory=fonts_dir), name="fonts")

    # Client-route catch-all. Explicitly does NOT match /api/* or /ws/*
    # — those already resolve against the routers above and a 404 from
    # here would mask a real routing bug. We also refuse to serve files
    # that escape dist/ via .. segments.
    #
    # IMPORTANT: do not register any routes after this catch-all — its
    # ``{full_path:path}`` pattern matches everything under SPA_MOUNT_PATH
    # and would shadow them. The dynamic mount path makes ordering
    # invisible from a quick read; if you need a new route under the
    # SPA prefix, add it ABOVE this block.
    _catchall_url = (
        "/{full_path:path}"
        if SPA_MOUNT_PATH == "/"
        else f"{SPA_MOUNT_PATH}/{{full_path:path}}"
    )

    @app.get(_catchall_url, include_in_schema=False)
    async def spa_fallback(full_path: str):
        # When SPA_MOUNT_PATH = "/", /api/foo arrives here as "api/foo"
        # and we must reject it so the real router 404s aren't masked.
        # When SPA_MOUNT_PATH = "/app", /app/api/foo arrives as
        # "api/foo" too — but in that case the real API lives at
        # /api/foo (no /app prefix), so the SPA correctly owns
        # /app/api/* and we let it fall through to index.html.
        if SPA_MOUNT_PATH == "/" and (
            full_path.startswith("api/") or full_path.startswith("ws/")
        ):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = SPA_STATIC_FILES.get(full_path)
        if candidate is not None:
            return FileResponse(candidate)
        # Anything else → SPA entry. React Router handles the rest.
        return FileResponse(
            FRONTEND_DIST / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    logger.info(
        "SPA mounted at %s (FRONTEND_DIST=%s)", SPA_MOUNT_PATH, FRONTEND_DIST
    )
else:
    logger.warning(
        "⚠️  Frontend dist not found at %s — API will run, SPA will 404. "
        "Run `cd pellier/frontend && npm run build` to produce it.",
        FRONTEND_DIST,
    )


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
