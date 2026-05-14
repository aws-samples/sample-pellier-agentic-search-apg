"""
Pellier - Main FastAPI Application
FastAPI app for the Pellier workshop backend.
"""

import asyncio
import os
import time
import logging
import json
from contextlib import asynccontextmanager
from typing import Optional

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from models.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    HealthResponse,
    ChatRequest,
    ChatResponse,
)
from models.product import ProductWithScore
from services.database import DatabaseService
from services.auth import get_current_user
from services.embeddings import EmbeddingService
from services.chat import ChatService
from datetime import datetime
from services.sql_query_logger import init_query_logger, get_query_logger, QueryLog
from services.index_performance import get_index_performance_service
from services.vector_search import VectorSearch
from services.cache import init_cache, get_cache
from routes import (
    agent_router,
    atelier_observatory_router,
    auth_router,
    products_router,
    search_router,
    boutique_router,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app
    Handles startup and shutdown events
    """
    # Startup
    logger.info("Starting Pellier Boutique API...")
    
    global db_service, embedding_service, chat_service, query_logger, index_performance_service
    
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

            # === WIRE IT LIVE (Lab 4d) ===
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
            # === END WIRE IT LIVE ===

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
        # to the Module 1 teaching surface.
        from services.agent_tools import set_db_service, set_main_loop
        set_db_service(db_service)
        set_main_loop(asyncio.get_event_loop())
        logger.info("✅ Agent tools initialized with pgvector semantic search")

        # Wire the tool_audit writer the same way. Theo's anchor
        # capability persists every mutation to Aurora's tool_audit
        # table; the writer is fire-and-forget but needs the same
        # DB pool + main event loop reference to bridge sync→async.
        from services import tool_audit_writer
        tool_audit_writer.set_db_service(db_service)
        tool_audit_writer.set_main_loop(asyncio.get_event_loop())
        logger.info("✅ tool_audit writer initialized for ALLOW-path mutation logging")

        # Load the skill registry once at boot. Per-request cost is zero —
        # skills are served from memory. See backend/skills/ for the
        # registry, models, and (Phase 2) the one-call router.
        from skills import load_registry
        load_registry()

        logger.info("🚀 Pellier Boutique API is ready!")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Pellier Boutique API...")
    
    if db_service:
        await db_service.disconnect()
    
    logger.info("👋 Goodbye!")


# Create FastAPI app
app = FastAPI(
    title="Pellier Boutique API",
    description="Agentic AI-Powered Search with Amazon Aurora PostgreSQL and pgvector",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In enterprise deployments, specify actual origins
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

# DAT406 /workshop telemetry surface (Week 1) — returns flat
# {session_id, events: list[dict]} payloads for the panel renderer.
# Intentionally separate from /api/agent/chat so the boutique SSE
# stream isn't reshaped for the workshop's replay needs.
app.include_router(workshop_router)

# Atelier Observatory read-only API endpoints — sessions, agents, tools,
# routing, memory, performance, evaluations, observatory dashboard.
# Additive to workshop_router (same /api/atelier/ prefix, no path conflicts).
app.include_router(atelier_observatory_router)

# Boutique ambient chrome — briefing (concierge empty state) + pulse
# (4 live metrics above the hero). Both endpoints are contract-typed
# via Pydantic and degrade gracefully; they are never allowed to 5xx
# the homepage.
app.include_router(boutique_router)
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
# Resolution order for the root ``/`` endpoint:
#   1. If ``FRONTEND_DIST_PATH`` env var is set, use that.
#   2. Otherwise look for ``../frontend/dist`` relative to backend/.
#   3. If neither exists (pure API mode / tests), fall back to the
#      JSON status blob.
FRONTEND_DIST = Path(
    os.environ.get("FRONTEND_DIST_PATH")
    or (Path(__file__).resolve().parent.parent / "frontend" / "dist")
).resolve()


@app.get("/", include_in_schema=False)
async def root():
    """Serve the SPA's ``index.html`` if built, else return API status."""
    index_html = FRONTEND_DIST / "index.html"
    if index_html.is_file():
        return FileResponse(
            index_html,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return JSONResponse(
        {
            "message": "Pellier Boutique API",
            "version": "1.0.0",
            "note": (
                "Frontend bundle not found at "
                f"{FRONTEND_DIST}. Run `npm run build` in pellier/frontend/ "
                "to produce the SPA, or set FRONTEND_DIST_PATH."
            ),
        }
    )


@app.get("/api/health", response_model=HealthResponse)
async def health_check(
    db: DatabaseService = Depends(get_db_service),
):
    """
    Health check endpoint
    Returns status of all services
    """
    health_status = {
        "status": "healthy",
        "database": "unknown",
        "bedrock": "unknown",
        "custom_tools": "available",
        "version": "1.0.0",
    }

    # Check database connection
    try:
        await db.execute_query("SELECT 1")
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
            ORDER BY rating DESC, reviews::int DESC
            LIMIT %s
        """

        results = await db.fetch_all(
            query,
            f"%{category_query}%",
            f"%{category_query}%",
            f"%{category_query}%",
            limit,
        )
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
        raise HTTPException(status_code=500, detail=str(e))



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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/restock")
async def restock_shelf_endpoint(
    request: dict,
    db: DatabaseService = Depends(get_db_service)
):
    """Restock a product using business logic"""
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(db)
        return await logic.restock_shelf(
            product_id=request["product_id"],
            quantity=request["quantity"]
        )
    except Exception as e:
        logger.error(f"Failed to restock product: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, user=Depends(get_current_user)):
    """
    Streaming chat endpoint with real-time agent events via SSE.

    Uses chat_service.chat_stream() which runs the orchestrator in a background
    thread and yields events (tool calls, products, text) the moment they happen
    via an asyncio.Queue bridge, instead of waiting for the full chain to finish.
    """
    from fastapi.responses import StreamingResponse

    if not chat_service:
        raise HTTPException(status_code=503, detail="Chat service not initialized")

    async def event_generator():
        try:
            history = [{"role": msg.role, "content": msg.content} for msg in request.conversation_history]
            # Merge persona customer_id into the user dict so the agent
            # context and LTM reads scope to the right customer. The
            # persona's customer_id takes precedence over the Cognito
            # sub when both are present (workshop affordance).
            effective_user = dict(user) if user else {}
            if request.customer_id:
                effective_user["customer_id"] = request.customer_id

            # Per-turn guardrail INPUT check — records a decision in
            # services/guardrails_log so the Atelier Grounding page's
            # Guardrails lane shows live audit rows. Only runs when
            # the user enabled guardrails in their request; otherwise
            # the log captures no entry (accurate — nothing happened).
            # Failures are swallowed: guardrail eval is observational,
            # not a hard turn gate in this demo surface.
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
                except Exception as _exc:
                    logger.debug("Input guardrail observational check failed: %s", _exc)

            async for event in chat_service.chat_stream(
                message=request.message,
                conversation_history=history,
                session_id=request.session_id,
                workshop_mode=request.workshop_mode,
                guardrails_enabled=request.guardrails_enabled,
                user=effective_user or None,
                pattern=request.pattern,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            logger.error(f"Streaming chat failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


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
            ORDER BY reviews DESC
            LIMIT %s
        """
        results = await db.fetch_all(query, f"%{q}%", limit)
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/queries/clear")
async def clear_query_logs():
    """Clear all query logs"""
    try:
        query_logger_instance = get_query_logger()
        query_logger_instance.clear_logs()
        return {"status": "success", "message": "Query logs cleared"}
    except Exception as e:
        logger.error(f"Failed to clear logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# INDEX PERFORMANCE ENDPOINTS
# ============================================================================

@app.post("/api/performance/compare")
async def compare_index_performance(
    request: dict,
    embeddings: EmbeddingService = Depends(get_embedding_service)
):
    """
    Compare HNSW index performance vs sequential scan
    
    Request body:
        query: Search query text
        ef_search: HNSW ef_search parameter (default: 40)
        limit: Number of results (default: 10)
    """
    try:
        query = request.get("query")
        ef_search = request.get("ef_search", 40)
        limit = request.get("limit", 10)
        
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/performance/runtime")
async def performance_runtime(include_recent: bool = False):
    """Return rolling aggregates of chat turn latency breakdowns.

    Feeds the Atelier Performance tab — layer p50/p95 replace the
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
        return {"turn_count": 0, "empty": True, "error": str(e)}


@app.get("/api/performance/stats")
async def get_index_stats():
    """Get pgvector index statistics"""
    try:
        stats = await index_performance_service.get_index_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get index stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONTEXT MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/api/context/stats")
async def get_context_stats(session_id: Optional[str] = Query(default=None)):
    """
    Get context statistics for monitoring
    
    Returns comprehensive metrics for token usage, efficiency, and costs.
    Demonstrates enterprise-grade context window management for Claude Opus 4.
    
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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
async def compare_iterative_scan(request: Request):
    """Compare filtered HNSW with and without iterative scan (pgvector 0.8.0)"""
    if not index_performance_service:
        raise HTTPException(status_code=503, detail="Index performance service not initialized")
    body = await request.json()
    query = body.get("query", "")
    category = body.get("category", "")
    ef_search = body.get("ef_search", 40)
    limit = body.get("limit", 10)
    if not query or not category:
        raise HTTPException(status_code=400, detail="query and category required")
    embedding = embedding_service.generate_embedding(query)
    return await index_performance_service.compare_filtered_search(
        query=query, embedding=embedding,
        category_filter=category, ef_search=ef_search, limit=limit,
    )


@app.post("/api/performance/quantization-benchmark")
async def quantization_benchmark(request: Request):
    """Benchmark float32 vs halfvec vs binary quantization with live queries"""
    if not index_performance_service:
        raise HTTPException(status_code=503, detail="Index performance service not initialized")
    body = await request.json()
    query = body.get("query", "")
    limit = body.get("limit", 10)
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    embedding = embedding_service.generate_embedding(query)
    return await index_performance_service.compare_quantization_benchmark(
        query=query, embedding=embedding, limit=limit,
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

@app.get("/api/atelier/skills")
async def list_skills():
    """
    List all skills in the registry for the Atelier Architecture tab.

    Returns shape that matches the frontend's expectations — name,
    description, version, display_name, token_estimate, and the full
    markdown body so the "Open SKILL.md →" link can render it inline
    without a second request.
    """
    from skills import get_registry
    registry = get_registry()
    return {
        "skills": [
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
        ],
        "count": len(registry),
    }


@app.get("/api/atelier/search-strategies/compare")
async def compare_search_strategies(query: str):
    """Run the same query through three retrieval strategies, return
    per-strategy timing + top-5 product names.

    Surfaces Anna's anchor-capability comparison live to the
    Atelier Performance page so workshop participants can see the
    delta between vector-only / hybrid / hybrid+rerank against the
    real catalog rather than reading a static fixture.

    Strategies:
      1. **vector only** — pgvector cosine over product_catalog.
         Marco's foundation path.
      2. **hybrid (RRF)** — vector + BM25 in parallel, RRF-merged.
         No reranker pass.
      3. **hybrid + rerank** — same as #2 plus Cohere Rerank v3.5.
         Anna's shipped path.

    Returns:
      {
        "query": str,
        "strategies": [
          {"strategy", "p50Ms", "costPerThousandUsd", "products": [{name, productId}]}
        ]
      }

    Cost numbers are static (workshop-known fixtures: vector + hybrid
    are effectively free per query, rerank adds ~$1 per 1000 queries).
    The latency numbers come from real wall-clock measurement of each
    branch against the live Aurora pool.
    """
    import time
    from services.embeddings import EmbeddingService
    from services.vector_search import VectorSearch
    from services.hybrid_search import HybridSearch
    from services.rerank import get_rerank_service

    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="query parameter required")
    q = query.strip()

    embed = EmbeddingService()
    query_embedding = embed.embed_query(q)

    if db_service is None:
        raise HTTPException(
            status_code=503,
            detail="DB not initialized — wait for backend startup to complete",
        )
    db = db_service

    # Strategy 1: pure pgvector cosine. Marco's path.
    t0 = time.time()
    vec = VectorSearch(db)
    vec_rows = await vec.vector_search(query_embedding, 5, ef_search=40)
    vec_ms = int((time.time() - t0) * 1000)
    vec_products = [
        {"name": r.get("name", ""), "productId": r.get("product_id")}
        for r in vec_rows[:5]
    ]

    # Strategy 2: hybrid (RRF), no rerank. Cap top_n at 5 here so we
    # see the union ranking pre-rerank.
    t0 = time.time()
    hybrid = HybridSearch(db)
    hybrid_rows = await hybrid.search(
        query=q,
        query_embedding=query_embedding,
        top_n=5,
    )
    hybrid_ms = int((time.time() - t0) * 1000)
    hybrid_products = [
        {"name": r.get("name", ""), "productId": r.get("product_id")}
        for r in hybrid_rows[:5]
    ]

    # Strategy 3: hybrid (top 30) + Cohere Rerank to top 5. Anna's path.
    t0 = time.time()
    rerank_pool = await hybrid.search(
        query=q,
        query_embedding=query_embedding,
        top_n=30,
    )
    documents = [
        f"{r.get('name','')} — {(r.get('description','') or '')[:200]} ({r.get('category','')})"
        for r in rerank_pool
    ]
    rerank_service = get_rerank_service()
    rerank_results = rerank_service.rerank(query=q, documents=documents, top_n=5)
    rerank_ms = int((time.time() - t0) * 1000)
    if rerank_results:
        rerank_products = [
            {
                "name": rerank_pool[r["index"]].get("name", ""),
                "productId": rerank_pool[r["index"]].get("product_id"),
            }
            for r in rerank_results
        ]
    else:
        # Bedrock failure — same fallback the find_pieces_hybrid tool uses.
        rerank_products = [
            {"name": r.get("name", ""), "productId": r.get("product_id")}
            for r in rerank_pool[:5]
        ]

    return {
        "query": q,
        "strategies": [
            {
                "strategy": "vector only",
                "p50Ms": vec_ms,
                "costPerThousandUsd": 0.18,  # embedding cost only
                "products": vec_products,
            },
            {
                "strategy": "hybrid (RRF)",
                "p50Ms": hybrid_ms,
                "costPerThousandUsd": 0.18,
                "products": hybrid_products,
            },
            {
                "strategy": "hybrid + rerank",
                "p50Ms": rerank_ms,
                "costPerThousandUsd": 1.18,  # +$1 for Cohere Rerank
                "products": rerank_products,
            },
        ],
    }


@app.get("/api/atelier/catalog")
async def atelier_catalog():
    """
    Tool catalog + agent grants for the Atelier Architecture pages.

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
        {"name": "orchestrator", "model": "Haiku", "role": "ROUTES"},
        {"name": "search", "model": "Opus", "role": "OPUS · 3 GRANTS"},
        {"name": "recommendation", "model": "Opus", "role": "OPUS · 4 GRANTS"},
        {"name": "pricing", "model": "Opus", "role": "OPUS · 3 GRANTS"},
        {"name": "support", "model": "Opus", "role": "OPUS · 2 GRANTS"},
        {"name": "inventory", "model": "Opus", "role": "OPUS · 3 GRANTS"},
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

import pathlib as _pathlib

_PERSONAS_CONFIG_PATH = _pathlib.Path(__file__).resolve().parent / "personas-config.json"
_personas_cache: Optional[list] = None


def _load_personas() -> list:
    """Load persona definitions from docs/personas-config.json. Cached."""
    global _personas_cache
    if _personas_cache is not None:
        return _personas_cache
    try:
        raw = json.loads(_PERSONAS_CONFIG_PATH.read_text())
        _personas_cache = raw.get("personas", [])
    except Exception as e:
        logger.warning(f"Failed to load personas config: {e}")
        _personas_cache = []
    return _personas_cache


@app.get("/api/atelier/personas/reload")
async def reload_personas():
    """Dev helper — force re-read of personas-config.json."""
    global _personas_cache
    _personas_cache = None
    return {"reloaded": True, "count": len(_load_personas())}


# In-memory session → persona mapping. Lightweight — no DB table.
# Keyed by session_id; value is the persona id string.
_session_persona: dict[str, str] = {}


@app.get("/api/atelier/personas")
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


@app.get("/api/atelier/status")
async def get_workshop_status():
    """Detect which workshop modules have been completed by inspecting stub source code."""
    import inspect

    def is_stub(func, sentinel: str) -> bool:
        try:
            return sentinel.lower() in inspect.getsource(func).lower()
        except Exception:
            return True

    # Module 1 — Smart Search
    from services.vector_search import VectorSearch
    from services.business_logic import BusinessLogic
    m1a = is_stub(VectorSearch.vector_search, "# TODO: Your implementation here")
    m1b = is_stub(BusinessLogic.find_pieces, "# TODO: Your implementation here")

    # Module 2 — Agentic AI (tools + agents + orchestrator)
    from services.agent_tools import whats_trending
    from agents.curator import recommendation
    from agents.orchestrator import create_orchestrator
    m2_tools = is_stub(whats_trending, "# TODO: Your implementation here")
    m2_rec = is_stub(recommendation, "# TODO: Your implementation here")
    m2_orch = is_stub(create_orchestrator, "# TODO: Your implementation here")

    # Module 3 — Production Patterns
    from services.agentcore_memory import create_agentcore_session_manager
    from services.agentcore_gateway import create_gateway_orchestrator
    from services.agentcore_policy import PolicyService
    m3_mem = is_stub(create_agentcore_session_manager, "# TODO: Your implementation here")
    m3_gw = is_stub(create_gateway_orchestrator, "# TODO: Your implementation here")
    m3_pol = is_stub(PolicyService._check_policy, "# TODO: Your implementation here")

    return {
        "modules": {
            "module1": {"complete": not m1a and not m1b, "label": "Smart Search",
                        "stubs": {"vector_search": not m1a, "find_pieces": not m1b}},
            "module2": {"complete": not m2_tools and not m2_rec and not m2_orch, "label": "Agentic AI",
                        "stubs": {"whats_trending": not m2_tools, "recommendation_agent": not m2_rec, "orchestrator": not m2_orch}},
            "module3": {"complete": not m3_mem and not m3_gw and not m3_pol, "label": "Production Patterns",
                        "stubs": {"memory": not m3_mem, "gateway": not m3_gw, "policy": not m3_pol}},
        }
    }


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
        return {"enabled": False, "error": str(e)}


@app.get("/api/traces/waterfall")
async def get_trace_waterfall():
    """Get waterfall timing data from captured OTEL spans.

    Always returns HTTP 200 with a structured payload. When OTEL is not
    wired correctly the payload carries ``otel_enabled: False`` plus a
    ``reason`` string — the frontend renders a banner instead of the
    waterfall. See docs/troubleshooting-otel.md.
    """
    try:
        from services.otel_trace_extractor import get_waterfall_data
        return get_waterfall_data()
    except Exception as e:
        logger.error(f"get_waterfall_data raised: {e}")
        return {
            "spans": [],
            "totalMs": 0,
            "specialistRoute": "",
            "waterfall": [],
            "span_count": 0,
            "otel_enabled": False,
            "reason": (
                f"Telemetry unavailable: extractor raised {type(e).__name__}. "
                f"See docs/troubleshooting-otel.md."
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
    Atelier Grounding page's Guardrails lane can surface a live audit
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

    Feeds the Atelier Grounding page's Guardrails lane. Distinct from
    ``/api/agentcore/policy/decisions`` (Cedar tool-call enforcement);
    these are Bedrock content filter outcomes on the prose side.
    """
    try:
        from services.guardrails_log import get_guardrails
        decisions = get_guardrails(session_id or None, limit=max(1, min(500, int(limit))))
        return {"session_id": session_id or "_anonymous", "decisions": decisions, "count": len(decisions)}
    except Exception as e:
        logger.warning(f"Guardrails decisions fetch failed: {e}")
        return {"session_id": session_id, "decisions": [], "count": 0, "error": str(e)}


# ============================================================================
# CHAOS MODE (Error Handling & Resilience Demo)
# ============================================================================

_chaos_mode = False
_chaos_fail_rate = 0.3  # 30% failure rate when chaos mode active

@app.post("/api/dev/chaos")
async def toggle_chaos_mode(request: Request):
    """Toggle chaos mode for resilience testing"""
    global _chaos_mode
    body = await request.json()
    _chaos_mode = body.get("enabled", not _chaos_mode)
    return {"chaos_mode": _chaos_mode, "fail_rate": _chaos_fail_rate}

@app.get("/api/dev/chaos")
async def get_chaos_status():
    """Get current chaos mode status"""
    return {"chaos_mode": _chaos_mode, "fail_rate": _chaos_fail_rate}


# ============================================================================
# GRAPH ORCHESTRATOR ENDPOINT
# ============================================================================

@app.get("/api/agents/graph")
async def get_agent_graph():
    """Get the multi-agent orchestrator graph structure for visualization"""
    try:
        from agents.graph_orchestrator import get_graph_structure
        return get_graph_structure()
    except Exception as e:
        logger.warning(f"Failed to get graph structure: {e}")
        return {"available": False, "graph_builder_available": False, "nodes": [], "edges": [], "description": str(e)}


# ============================================================================
# AGENTCORE POLICY ENDPOINTS (Cedar)
# ============================================================================

@app.get("/api/agentcore/policy/list")
async def list_policies():
    """List all Cedar policies"""
    try:
        from services.agentcore_policy import get_policy_service
        svc = get_policy_service()
        return {"policies": svc.list_policies()}
    except Exception as e:
        logger.warning(f"Failed to list policies: {e}")
        return {"policies": [], "error": str(e)}


@app.post("/api/agentcore/policy/check")
async def check_policy(request: Request):
    """Evaluate an action against Cedar policies"""
    try:
        from services.agentcore_policy import get_policy_service
        body = await request.json()
        action = body.get("action", "")
        parameters = body.get("parameters", {})
        svc = get_policy_service()
        result = svc.evaluate(action, parameters)
        return result
    except Exception as e:
        logger.error(f"Policy check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agentcore/memory/ltm")
async def memory_ltm(customer_id: str = ""):
    """Return LTM facts for a persona, ranked by recency.

    Reads the ``customer_episodic_seed`` fixture table via
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
        return {"customer_id": customer_id, "facts": [], "source": "error", "error": str(e)}


@app.get("/api/agentcore/memory/status")
async def memory_status():
    """Return whether AgentCore Memory is SDK-backed or using the
    in-memory dict fallback.

    The MemoryArchPage in the Atelier reads this to show an honest
    banner — either 'Live: AgentCore Memory (id=...)' or 'Fallback:
    in-process dict; set AGENTCORE_MEMORY_ID to enable LIVE'. Also
    reports whether the bedrock-agentcore SDK is importable, so a
    broken install surfaces distinctly from a missing env var.
    """
    try:
        from config import settings
        memory_id = getattr(settings, "AGENTCORE_MEMORY_ID", None) or ""

        sdk_available = False
        sdk_error: str | None = None
        try:
            import bedrock_agentcore  # type: ignore  # noqa: F401
            sdk_available = True
        except ImportError as exc:
            sdk_error = str(exc)

        if memory_id and sdk_available:
            return {
                "live": True,
                "source": "agentcore-sdk",
                "memory_id": memory_id,
                "sdk_available": True,
                "fallback_reason": None,
            }
        if memory_id and not sdk_available:
            return {
                "live": False,
                "source": "in-process-dict",
                "memory_id": memory_id,
                "sdk_available": False,
                "fallback_reason": f"bedrock-agentcore SDK not importable: {sdk_error}",
            }
        return {
            "live": False,
            "source": "in-process-dict",
            "memory_id": "",
            "sdk_available": sdk_available,
            "fallback_reason": "AGENTCORE_MEMORY_ID env var not set",
        }
    except Exception as e:
        logger.warning(f"Memory status fetch failed: {e}")
        return {"live": False, "source": "in-process-dict", "error": str(e)}


@app.get("/api/agentcore/gateway/status")
async def gateway_status():
    """Return the effective Gateway wiring for the current backend.

    The Atelier MCP / Tool Registry tabs use this to show whether tools
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
        return {"configured": False, "source": "in-process-imports", "error": str(e)}


@app.get("/api/agentcore/policy/decisions")
async def policy_decisions(session_id: str = "", limit: int = 50):
    """Return the recent per-tool enforcement decisions for a session.

    Feeds the Atelier Policy tab so it can show live DENY/ALLOW
    outcomes per turn instead of a static policy list. Bounded by the
    in-memory PolicyEnforcementHook buffer (oldest decisions evicted
    automatically)."""
    try:
        from services.policy_hook import get_decisions
        decisions = get_decisions(session_id or None, limit=max(1, min(500, int(limit))))
        return {"session_id": session_id or "_anonymous", "decisions": decisions, "count": len(decisions)}
    except Exception as e:
        logger.warning(f"Policy decisions fetch failed: {e}")
        return {"session_id": session_id, "decisions": [], "count": 0, "error": str(e)}


# ============================================================================
# AGENTCORE ENDPOINTS (Lab 4)
# ============================================================================

@app.get("/api/agentcore/memories")
async def agentcore_memories(user=Depends(get_current_user)):
    """Get stored memories for authenticated user (Lab 4b)"""
    if not user:
        return {"memories": [], "message": "Sign in to view memories"}
    try:
        from services.agentcore_memory import get_user_memories
        memories = get_user_memories(user["sub"])
        return {"memories": memories, "user": user["email"]}
    except Exception as e:
        logger.warning(f"Failed to fetch memories: {e}")
        return {"memories": [], "error": str(e)}


@app.get("/api/agentcore/gateway/tools")
async def agentcore_gateway_tools():
    """List tools registered in AgentCore Gateway MCP server (Lab 4c)"""
    try:
        from services.agentcore_gateway import list_gateway_tools
        tools = list_gateway_tools()
        return {"tools": tools, "gateway_url": settings.AGENTCORE_GATEWAY_URL or "not configured"}
    except Exception as e:
        logger.warning(f"Failed to list gateway tools: {e}")
        return {"tools": [], "error": str(e)}


@app.get("/api/agentcore/runtime/status")
async def agentcore_runtime_status():
    """Get AgentCore Runtime execution status (Lab 4e)"""
    runtime_endpoint = settings.AGENTCORE_RUNTIME_ENDPOINT
    if runtime_endpoint:
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
        return {"episodes": [], "error": str(e)}


@app.post("/api/agentcore/policy/create")
async def create_nl_policy(request: Request):
    """Create a Cedar policy from natural language description"""
    try:
        from services.agentcore_policy import create_policy_from_natural_language
        body = await request.json()
        result = create_policy_from_natural_language(
            gateway_id=body.get("gateway_id", ""),
            policy_name=body.get("policy_name", ""),
            natural_language_rule=body.get("rule", ""),
        )
        return result
    except Exception as e:
        logger.error(f"NL policy creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    fonts_dir = FRONTEND_DIST / "fonts"
    if fonts_dir.is_dir():
        app.mount("/fonts", StaticFiles(directory=fonts_dir), name="fonts")

    # Client-route catch-all. Explicitly does NOT match /api/* — those
    # already resolve against the routers above and a 404 from here
    # would mask a real routing bug. We also refuse to serve files that
    # escape dist/ via .. segments.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (FRONTEND_DIST / full_path).resolve()
        # Prevent directory traversal — the resolved path must live
        # inside dist/.
        try:
            candidate.relative_to(FRONTEND_DIST)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not Found")
        if candidate.is_file():
            return FileResponse(candidate)
        # Anything else → SPA entry. React Router handles the rest.
        return FileResponse(
            FRONTEND_DIST / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
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