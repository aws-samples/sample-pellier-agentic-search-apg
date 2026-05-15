"""
Chat Service with Product Card Support

Uses Strands SDK for multi-agent orchestration with direct asyncpg database access.
Context Manager tracks tokens and manages conversation state.
"""

import json
import logging
import os
from typing import List, Dict, Any, Optional
import re


def _safe_float(val, default=0.0):
    """Safely convert a value to float, stripping currency symbols."""
    try:
        return float(str(val).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0):
    """Safely convert a value to int, stripping currency symbols."""
    try:
        return int(float(str(val).replace("$", "").replace(",", "").strip()))
    except (ValueError, TypeError):
        return default


GUARDRAILS_SUFFIX = """

GUARDRAILS (ACTIVE):
- Do NOT recommend products related to weapons, alcohol, or tobacco
- Do NOT provide medical, legal, or financial advice
- Flag inappropriate requests politely
- Keep all responses family-friendly"""

SINGLE_AGENT_PROMPT = """You are Pellier AI, the shopping assistant for Pellier.

TOOL SELECTION:
- whats_trending → When user asks about trending, popular, or best-selling items. Pass category if they mention one (e.g. "trending in electronics" → category="Electronics").
- find_pieces → Descriptive or intent-based product queries (e.g. "gift for a cook", "noise-canceling headphones under $200")
- price_intelligence → Pricing statistics and category comparisons

Call exactly one tool per query. Extract price limits and pass as max_price.
The search tool handles category mapping automatically — pass the user's words directly.

RESPONSE STYLE:
Write 1-2 short sentences as a conversational intro. Products render as visual cards
automatically — do not list them in text. Never use markdown tables, numbered lists,
headers, or emojis. Never claim products are unavailable or inventory is being refreshed.
Never ask follow-up questions. If zero results, say "I couldn't find exact matches —
try a different search term."."""


# ---------------------------------------------------------------------------
# Deterministic intent classification — replaces LLM-based routing
# ---------------------------------------------------------------------------
PRICING_KEYWORDS = {"deal", "deals", "cheap", "cheapest", "price", "pricing",
                    "discount", "affordable", "budget", "value", "cost", "save",
                    "best price", "on sale", "bargain", "compare price"}
INVENTORY_KEYWORDS = {"restock", "inventory", "stock", "out of stock",
                      "low stock", "available", "availability", "in stock",
                      "running low", "sold out", "back in stock",
                      "warehouse", "at the brooklyn", "at the austin",
                      "at the portland", "on the floor"}
SUPPORT_KEYWORDS = {"return", "refund", "policy", "troubleshoot",
                    "issue", "problem", "warranty", "broken", "defective",
                    "chipped", "damaged", "arrived", "what now"}
# "help" used to live in SUPPORT_KEYWORDS but it's too generic — Anna's
# canonical T3 ("help me pair a candle with something else") is a
# recommendation request, not post-purchase support. Same logic for
# "support" alone (which was redundant with "policy"/"warranty"/etc.).
# Real support queries always carry one of the unambiguous tokens
# above (return/refund/warranty/chipped/damaged/etc.).
SEARCH_KEYWORDS = {"search for", "looking for", "where can I", "compare", "browse",
                   "what do you have", "do you have", "show me", "find me"}

# Past-purchase / history queries — these reference the shopper's own
# order history and must route to the recommendation specialist with the
# persona's LTM preamble, NEVER to support (which has no order-history
# tool). Matched case-insensitively against the full query.
PAST_PURCHASE_PATTERN = re.compile(
    r'\b('
    r'what (did|have) i (buy|bought|purchase|purchased|order|ordered)|'
    r'what i (bought|purchased|ordered)|'
    r'(my|last) (purchase|purchases|order|orders|time)|'
    r'last time i (bought|purchased|ordered)|'
    r'previous (purchase|order|orders)|'
    r'order history|purchase history|buy again|reorder'
    r')\b',
    re.IGNORECASE,
)

# Product-seeking phrases that override pricing keywords. "Find me a
# linen shirt under $150" is a search with a price filter, not a
# pricing analysis request.
PRODUCT_SEEKING_PATTERNS = re.compile(
    r'\b(find|show|get|give|suggest|recommend|looking for|want|need|buy)\b.*'
    r'\b(shirt|dress|shoe|bag|jacket|pants|top|linen|cotton|silk|leather|'
    r'cashmere|wool|sandal|sneaker|boot|tote|candle|throw|towel|hat|cuff|'
    r'earring|scarf|vest|cardigan|blazer|trench|anorak)\b',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Triage fast-path — short-circuits greetings/meta/thanks before the
# orchestrator is created. Cuts the "empty response" failure mode to
# zero for the demo queries that used to route into
# recommendation and come back blank. Deterministic by
# design so workshop demos never depend on an LLM roll for small-talk.
# ---------------------------------------------------------------------------

# Order matters: we check startswith for greeting/thanks to tolerate
# trailing punctuation ("hi!", "hi there"), and a normalized-word set
# for meta queries.
_GREETING_PREFIXES = (
    "hi", "hello", "hey", "howdy", "yo",
    "good morning", "good afternoon", "good evening",
)
_THANKS_PREFIXES = ("thanks", "thank you", "thx", "ty", "appreciate")
_META_PHRASES = (
    "what can you do", "what do you do", "who are you", "what are you",
    "how do you work", "what are your capabilities",
    "how can you help", "what can i ask",
)
# "help" on its own is meta — but "help me X" is a real request. Match
# it as a whole-query word, not as a substring (which mis-classified
# Anna's "help me pair a candle with something else" turn).
_META_EXACT_WORDS = ("help",)


def classify_triage(query: str) -> Optional[str]:
    """Return a triage bucket for trivial queries, or None to fall through.

    Buckets:
      ``greeting`` — "hi", "hello", etc.
      ``meta``     — capability/meta questions.
      ``thanks``   — user is closing the conversation politely.

    Kept deterministic (no LLM) so the demo path never rolls empty on
    the greeting that opens a stage demo.
    """
    if not query:
        return None
    q = query.strip().lower()
    # Strip trailing punctuation so "hi!" and "hi." both match.
    q = re.sub(r'[!?.,;:]+$', '', q).strip()
    if not q:
        return None

    # Length cap: treat queries over 60 chars as real questions even if
    # they START with "hi" (e.g. "hi, can you find me a linen shirt...").
    if len(q) > 60:
        return None

    for prefix in _GREETING_PREFIXES:
        if q == prefix or q.startswith(prefix + " ") or q.startswith(prefix + ","):
            return "greeting"
    for prefix in _THANKS_PREFIXES:
        if q == prefix or q.startswith(prefix + " ") or q.startswith(prefix + ","):
            return "thanks"
    for phrase in _META_PHRASES:
        if q == phrase or phrase in q:
            return "meta"
    # Exact-word meta triggers — only fire when the query IS the word
    # (after stripping punctuation), never as a substring. Prevents
    # "help me pair X with Y" from being classified as a meta question.
    for word in _META_EXACT_WORDS:
        if q == word:
            return "meta"
    return None


# Canned responses per triage bucket. Kept short + on-brand so the
# demo still feels boutique, not transactional. Multiple variants so
# repeat demos don't sound identical.
_TRIAGE_REPLIES = {
    "greeting": (
        "Hi! I'm Pellier — your concierge for the boutique. "
        "Tell me what you're after: a piece, a vibe, a price range, or a gift."
    ),
    "meta": (
        "I can help you browse the catalog, compare pieces, check what's in stock, "
        "or surface what's trending right now. Ask me anything — "
        '"something for long summer walks" is a good way in.'
    ),
    "thanks": (
        "Anytime. Come back when you're ready for the next piece."
    ),
}


async def _append_boutique_stm_turn(
    session_id: Optional[str],
    user_message: str,
    assistant_message: str,
    user: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist a Boutique dispatcher turn to AgentCore Memory (STM).

    Keeps ``GET /api/agent/session/{id}`` aligned with Marco pills on
    ``/api/chat/stream`` so the Builder's STM lab sees continuity without
    routing the storefront through ``/api/agent/chat``.
    """
    if not session_id:
        return
    try:
        from config import settings as _settings

        if not _settings.AGENTCORE_MEMORY_ID:
            return
        from services.agentcore_memory import AgentCoreMemory

        sub = user.get("sub") if user and isinstance(user, dict) else None
        namespace = (
            f"user:{sub}:session:{session_id}"
            if sub
            else f"anon:{session_id}"
        )
        memory = AgentCoreMemory()
        await memory.append_session_turn(
            namespace, {"role": "user", "content": user_message}
        )
        await memory.append_session_turn(
            namespace, {"role": "assistant", "content": assistant_message}
        )
    except Exception as exc:
        logger.debug("STM append skipped: %s", exc)


def classify_intent(query: str) -> str:
    """Deterministic intent classification via keyword matching.
    Returns 'pricing', 'inventory', 'customer_support', 'search', or 'recommendation'."""
    q = query.lower()
    words = set(re.findall(r'\w+', q))

    # Past-purchase queries route to recommendation so the specialist can
    # ground in the persona's order history via the LTM preamble. Takes
    # priority over everything else — these are personal-profile
    # questions, not shopping queries in the usual sense.
    if PAST_PURCHASE_PATTERN.search(query):
        return "recommendation"

    # If the query seeks a specific product, route to search even if
    # price keywords are present. "find me a linen shirt under $150"
    # is search, not pricing.
    is_product_seeking = bool(PRODUCT_SEEKING_PATTERNS.search(query))

    # Multi-word phrases first (higher specificity)
    if not is_product_seeking:
        for phrase in PRICING_KEYWORDS:
            if ' ' in phrase and phrase in q:
                return "pricing"
    for phrase in INVENTORY_KEYWORDS:
        if ' ' in phrase and phrase in q:
            return "inventory"

    # Single-word matches — pricing only if not product-seeking
    if not is_product_seeking and words & {w for w in PRICING_KEYWORDS if ' ' not in w}:
        return "pricing"
    if words & {w for w in INVENTORY_KEYWORDS if ' ' not in w}:
        return "inventory"

    # Support keywords (single-word only)
    if words & SUPPORT_KEYWORDS:
        return "customer_support"

    # Product-seeking queries → search
    if is_product_seeking:
        return "search"

    # Search keywords (multi-word phrase matching)
    for phrase in SEARCH_KEYWORDS:
        if ' ' in phrase and phrase in q:
            return "search"
    if words & {w for w in SEARCH_KEYWORDS if ' ' not in w}:
        return "search"

    return "recommendation"


# ---------------------------------------------------------------------------
# Product extraction — single source of truth, replaces LLM JSON generation
# ---------------------------------------------------------------------------
class ProductExtractor:
    """Extract products from tool results programmatically.
    The LLM never generates product JSON — this class handles it."""

    @staticmethod
    def extract(tool_result_str: str) -> list:
        """Parse tool result JSON and return normalized product dicts."""
        try:
            data = json.loads(tool_result_str)
        except (json.JSONDecodeError, TypeError):
            return []

        products = []
        if isinstance(data, dict) and "products" in data:
            products = data["products"]
        elif isinstance(data, list):
            products = data

        return [ProductExtractor._normalize(p) for p in products if isinstance(p, dict)]

    @staticmethod
    def _normalize(p: dict) -> dict:
        """Normalize field names from various tool output formats.

        Tool results today come from the boutique catalog (``name``,
        ``category``, ``imgUrl``); legacy keys (``product_description``,
        ``category_name``, ``product_url``) are retained as fallbacks so
        older unit fixtures and any cached agent output still resolve.
        """
        return {
            "productId": p.get("productId") or p.get("product_id", ""),
            "name": (p.get("name") or p.get("product_description", ""))[:80],
            "brand": p.get("brand", ""),
            "color": p.get("color", ""),
            "price": _safe_float(p.get("price", 0)),
            "rating": _safe_float(p.get("rating") or p.get("stars", 0)),
            "reviews": _safe_int(p.get("reviews", 0)),
            "category": p.get("category") or p.get("category_name", ""),
            "imgUrl": p.get("imgUrl") or p.get("img_url", ""),
            "badge": p.get("badge"),
            "tags": list(p.get("tags") or []),
        }


def _repair_json(raw: str) -> str:
    """Best-effort repair of common LLM JSON quirks."""
    # Remove trailing commas before ] or }
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    # Add missing commas between }{ or }"
    raw = re.sub(r'(\})\s*(\{)', r'\1,\2', raw)
    raw = re.sub(r'(\})\s*"', r'\1,"', raw)
    # Fix single quotes to double quotes (only around keys/values)
    raw = re.sub(r"(?<=[\[{,:])\s*'([^']*?)'\s*(?=[,\]}:])", r'"\1"', raw)
    # Remove control chars that break JSON
    raw = re.sub(r'[\x00-\x1f]+', ' ', raw)
    return raw

import boto3

# Configure logging levels
logging.getLogger("strands").setLevel(logging.INFO)
logging.getLogger("strands.tools.registry").setLevel(logging.INFO)
logging.getLogger("strands.event_loop").setLevel(logging.INFO)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
    level=logging.INFO
)

logger = logging.getLogger(__name__)


def _safe_register_hooks(session_manager, agent) -> None:
    """Register session manager hooks on an agent, handling the API
    mismatch between ``bedrock-agentcore`` (calls ``add_callback``)
    and ``strands-agents`` 1.36+ (uses ``add_hook``).

    Falls back gracefully — STM still works via the ``session_manager``
    property even if hook registration fails; the hooks are an
    optimization for batch flushing, not a hard requirement.
    """
    try:
        session_manager.register_hooks(agent)
    except AttributeError as exc:
        # bedrock-agentcore calls registry.add_callback() but Strands
        # 1.36+ renamed it to add_hook(). The session_manager property
        # is sufficient for basic STM — hooks are for batch flush.
        logger.debug(
            "session_manager.register_hooks failed (API mismatch): %s — "
            "STM still works via session_manager property",
            exc,
        )
    except Exception as exc:
        logger.warning("session_manager.register_hooks failed: %s", exc)


class EnhancedChatService:
    """Enhanced chat service with product card support"""
    
    def __init__(self, db_service=None):
        """Initialize with Strands SDK for multi-agent orchestration"""
        from config import settings
        
        self.model_id = settings.BEDROCK_CHAT_MODEL
        self.region = settings.AWS_REGION
        self.bedrock = boto3.client('bedrock-runtime', region_name=self.region)
        self.session_storage_dir = "/tmp/pellier-sessions"
        self.db_service = db_service
        self._agent_stats: Dict[str, Any] = {
            "query_count": 0,
            "products_found": 0,
            "agent_calls_by_type": {},
            "total_response_time_ms": 0,
            "avg_response_time_ms": 0,
        }

        # Check Strands availability
        try:
            from strands import Agent
            self.Agent = Agent
            self.strands_available = True
            logger.info("✅ ChatService initialized with Strands SDK")
            
        except ImportError as e:
            self.strands_available = False
            logger.error(f"❌ Strands SDK not available: {e}")
            logger.error("Install with: pip install strands-agents strands-agents-tools")
    

    
    def _track_query(self, products_count: int = 0, duration_ms: int = 0, agent_type: str = "general"):
        """Update per-session agent stats after a query."""
        self._agent_stats["query_count"] += 1
        self._agent_stats["products_found"] += products_count
        self._agent_stats["agent_calls_by_type"][agent_type] = self._agent_stats["agent_calls_by_type"].get(agent_type, 0) + 1
        self._agent_stats["total_response_time_ms"] += duration_ms
        qc = self._agent_stats["query_count"]
        self._agent_stats["avg_response_time_ms"] = round(self._agent_stats["total_response_time_ms"] / qc) if qc else 0

    def get_agent_stats(self) -> Dict[str, Any]:
        """Return current session agent stats."""
        return dict(self._agent_stats)

    async def chat(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        session_id: Optional[str] = None,
        workshop_mode: Optional[str] = None,
        guardrails_enabled: bool = False,
        user: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enhanced chat that returns structured product data

        Routes based on workshop_mode:
        - 'legacy'/'search': Chat disabled
        - 'agentic'/None: Full multi-agent orchestrator (Module 2)
        - 'production': Full orchestrator + AgentCore services (Module 3)
        """
        try:
            # Workshop mode routing
            if workshop_mode in ("legacy", "search"):
                return {
                    "response": "Chat is not available in this workshop mode. Progress to Module 2 to unlock agentic AI.",
                    "products": [],
                    "suggestions": [],
                    "tool_calls": [],
                    "success": True,
                    "context_tracking": False,
                    "orchestrator_enabled": False,
                    "model": self.model_id
                }

            logger.info(f"💬 Enhanced chat processing: '{message[:60]}...' (mode={workshop_mode or 'agentic'}, user={user.get('email') if user else 'anonymous'})")

            # Require Strands
            if not self.strands_available:
                raise RuntimeError(
                    "Strands SDK not available. Install with: "
                    "pip install strands-agents strands-agents-tools"
                )

            return await self._strands_enhanced_chat(message, conversation_history, session_id, guardrails_enabled, user=user)
            
        except Exception as e:
            logger.error(f"❌ Chat failed: {e}", exc_info=True)
            return self._error_response(str(e))
    
    async def _strands_enhanced_chat(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        session_id: Optional[str] = None,
        guardrails_enabled: bool = False,
        user: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Enhanced chat using Strands Orchestrator with specialized agents"""
        logger.info(f"🤖 Processing query with Strands Orchestrator")
        
        # Get context manager for token tracking
        from services.context_manager import get_context_manager
        context_manager = get_context_manager()
        
        # Track user message
        context_manager.add_message("user", message)
        
        try:
            # Import orchestrator
            from agents.orchestrator import create_orchestrator, create_guarded_orchestrator

            # Create session manager if session_id provided
            session_manager = None
            if session_id:
                # === WIRE IT LIVE (Lab 4b) ===
                # Use AgentCore Memory for managed session persistence
                if user and settings.AGENTCORE_MEMORY_ID:
                    from services.agentcore_memory import create_agentcore_session_manager
                    session_manager = create_agentcore_session_manager(
                        session_id=session_id,
                        user_id=user.get("sub", "anonymous"),
                    )
                    if session_manager:
                        logger.info(f"🧠 AgentCore Memory session created for user={user.get('email')}")
                # === END WIRE IT LIVE ===

                # No fallback — AgentCore Memory is the only session manager.
                # If AGENTCORE_MEMORY_ID is not set, the agent runs without session memory.
                if not session_manager:
                    logger.info(f"ℹ️ No session manager — agent runs stateless (set AGENTCORE_MEMORY_ID to enable)")

            # Create orchestrator — use guarded variant when guardrails enabled (Lab 3)
            logger.info(f"🎯 Creating agent orchestrator (guardrails={'ON' if guardrails_enabled else 'OFF'})...")
            if guardrails_enabled:
                orchestrator = create_guarded_orchestrator()
            else:
                orchestrator = create_orchestrator()

            # Graceful fallback if orchestrator not implemented yet (Module 3b TODO)
            if orchestrator is None:
                return self._error_response(
                    "🔧 The AI agent orchestrator isn't wired up yet. "
                    "Complete Module 3b to enable the chat assistant."
                )

            # Add OpenTelemetry trace attributes
            orchestrator.trace_attributes = {
                "session.id": session_id or "anonymous",
                "session.user": user.get("email", "anonymous") if user else "anonymous",
                "user.query": message[:100],
                "workshop": "pellier",
                "service": "pellier"
            }
            
            logger.info(f"🔍 Orchestrator created with OTEL tracing")
            
            # Add session manager if provided
            if session_manager:
                orchestrator.session_manager = session_manager
                _safe_register_hooks(session_manager, orchestrator)
            
            # Build conversation context
            conversation_context = ""
            if conversation_history:
                recent_history = conversation_history[-16:]
                for msg in recent_history:
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    if len(content) > 300:
                        content = content[:300] + "..."
                    conversation_context += f"{role.upper()}: {content}\n\n"
            
            # Prepare message for orchestrator
            full_message = message
            if conversation_context:
                full_message = f"""CONVERSATION HISTORY:
{conversation_context}
---
CURRENT REQUEST: {message}"""

            # Deterministic intent classification. The previous
            # ``[ROUTING DIRECTIVE: call the X tool]`` prefix injection
            # was deleted in the three-pattern refactor — see
            # ``chat_stream()`` for context.
            intent = classify_intent(message)
            intent_hint = {
                "pricing": "pricing",
                "inventory": "inventory",
                "customer_support": "support",
                "search": "search",
                "recommendation": "recommendation",
            }[intent]
            logger.info(f"🎯 Intent: {intent} → {intent_hint}")
            
            # Invoke orchestrator with timing
            import time
            start_time = time.time()
            
            logger.info(f"🔄 Invoking orchestrator with query: {message[:100]}...")
            import asyncio
            response = await asyncio.to_thread(orchestrator, full_message)
            # Strands AgentResult.__str__() extracts text from the last
            # message's content blocks. When the orchestrator's final cycle
            # is a tool_use (specialist returned but orchestrator didn't
            # generate a follow-up text), str() is empty. Fall back to
            # extracting text from tool_result content blocks.
            response_text = str(response).strip()
            if not response_text:
                try:
                    content = response.message.get("content", [])
                    for block in content:
                        if isinstance(block, dict) and "toolResult" in block:
                            tr = block["toolResult"].get("content", [])
                            for item in tr:
                                if isinstance(item, dict) and "text" in item:
                                    response_text = item["text"]
                                    break
                        if response_text:
                            break
                except Exception:
                    pass
            
            # Track assistant response in context manager
            context_manager.add_message("assistant", response_text)
            
            logger.info(f"✅ Orchestrator completed with agent chain")
            logger.info(f"📝 Final response length: {len(response_text)} chars")
            
            # Extract agent execution from OpenTelemetry traces. When
            # OTEL isn't wired correctly the payload carries
            # otel_enabled=False + reason; the frontend renders a banner
            # instead of synthesizing fake spans (see Bug 3 audit note).
            from services.otel_trace_extractor import extract_agent_execution_from_otel

            agent_execution = extract_agent_execution_from_otel()

            if agent_execution.get("otel_enabled") and agent_execution.get("trace_id"):
                logger.info(f"✨ OpenTelemetry trace_id: {agent_execution['trace_id']}")
            elif not agent_execution.get("otel_enabled"):
                logger.error(
                    f"📊 OTEL telemetry unavailable — reason: "
                    f"{agent_execution.get('reason', 'unknown')}"
                )
            
            # Extract structured data from response
            parsed = await self._parse_agent_response(response_text, message, conversation_history)
            
            result = {
                "response": parsed["text"],
                "products": parsed["products"],
                "suggestions": parsed["suggestions"],
                "success": True,
                "context_tracking": True,
                "orchestrator_enabled": True,
                "agent_execution": agent_execution,
                "model": self.model_id
            }
            
            logger.info(f"📦 Agent execution: {len(agent_execution['agent_steps'])} steps, {len(agent_execution['tool_calls'])} tool calls | OTEL: {agent_execution.get('otel_enabled', False)}")
            logger.info(f"✅ Response generated ({agent_execution['total_duration_ms']}ms)")
            return result
            
        except Exception as e:
            logger.error(f"❌ Orchestrator execution failed: {e}", exc_info=True)
            raise RuntimeError(f"Agent execution failed: {str(e)}")
    
    async def _single_agent_stream(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        session_id: Optional[str] = None,
        guardrails_enabled: bool = False
    ):
        """Streaming single-agent mode for Lab 2."""
        import asyncio
        import time

        from services.context_manager import get_context_manager
        context_manager = get_context_manager()
        context_manager.add_message("user", message)

        try:
            from strands import Agent
            from strands.models.bedrock import BedrockModel
            from services.agent_tools import (
                find_pieces,
                whats_trending,
                price_intelligence,
            )

            single_prompt = SINGLE_AGENT_PROMPT
            if guardrails_enabled:
                single_prompt += GUARDRAILS_SUFFIX

            agent = Agent(
                model=BedrockModel(model_id=self.model_id, max_tokens=8192, temperature=0.0),
                system_prompt=single_prompt,
                tools=[find_pieces, whats_trending, price_intelligence]
            )

            # Build conversation context
            conversation_context = ""
            if conversation_history:
                for msg in conversation_history[-16:]:
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')[:300]
                    conversation_context += f"{role.upper()}: {content}\n\n"

            full_message = message
            if conversation_context:
                full_message = f"CONVERSATION HISTORY:\n{conversation_context}\n---\nCURRENT REQUEST: {message}"

            yield {"type": "start", "content": "Initializing single agent..."}
            yield {"type": "agent_step", "agent": "SearchAssistant", "action": "Analyzing query", "status": "in_progress"}

            # Queue-based streaming bridge
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def streaming_callback(**kwargs):
                if "data" in kwargs:
                    try:
                        asyncio.run_coroutine_threadsafe(queue.put({"_text": kwargs["data"]}), loop).result(timeout=10)
                    except Exception:
                        pass

            agent.callback_handler = streaming_callback

            # Hook tool events
            try:
                from strands.hooks.events import BeforeToolCallEvent, AfterToolCallEvent

                def on_before_tool(event: BeforeToolCallEvent):
                    tool_name = ""
                    if hasattr(event, 'tool_use') and isinstance(event.tool_use, dict):
                        tool_name = event.tool_use.get("name", "")
                    if tool_name:
                        try:
                            asyncio.run_coroutine_threadsafe(queue.put({"_tool_start": tool_name}), loop).result(timeout=5)
                        except Exception:
                            pass

                def on_after_tool(event: AfterToolCallEvent):
                    tool_name = ""
                    if hasattr(event, 'tool_use') and isinstance(event.tool_use, dict):
                        tool_name = event.tool_use.get("name", "")
                    # Extract the actual tool result text from the Strands SDK result structure
                    result_str = ""
                    if hasattr(event, 'result') and event.result:
                        raw = event.result
                        # Strands SDK wraps results as: {'content': [{'text': '...'}], 'status': '...'}
                        if isinstance(raw, dict) and 'content' in raw:
                            for block in raw.get('content', []):
                                if isinstance(block, dict) and 'text' in block:
                                    result_str = block['text']
                                    break
                        if not result_str:
                            result_str = str(raw)
                    try:
                        asyncio.run_coroutine_threadsafe(queue.put({"_tool_done": tool_name, "_result": result_str}), loop).result(timeout=10)
                    except Exception:
                        pass

                agent.add_hook(on_before_tool)
                agent.add_hook(on_after_tool)
            except (ImportError, AttributeError):
                pass

            start_time = time.time()
            agent_result = [None]
            agent_error = [None]

            async def run_agent():
                try:
                    agent_result[0] = await asyncio.to_thread(agent, full_message)
                except Exception as e:
                    agent_error[0] = e
                finally:
                    await queue.put({"_done": True})

            task = asyncio.create_task(run_agent())
            products_sent = []
            products_buffered = []  # Hold products until text streams first
            price_limit = self._extract_price_limit(message)

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=120)
                except asyncio.TimeoutError:
                    yield {"type": "error", "error": "Agent execution timed out"}
                    break

                if "_done" in event:
                    break

                if "_tool_start" in event:
                    yield {"type": "agent_step", "agent": "SearchAssistant", "action": "Searching", "status": "in_progress"}
                    yield {"type": "tool_call", "tool": event["_tool_start"], "status": "executing"}

                elif "_text" in event:
                    # Stream text tokens to the client in real time
                    yield {"type": "content_delta", "delta": event["_text"]}

                elif "_tool_done" in event:
                    result_str = event.get("_result", "")
                    if result_str:
                        raw_products = ProductExtractor.extract(result_str)
                        logger.info(f"📦 Extracted {len(raw_products)} raw products from tool result")
                        if raw_products:
                            formatted = await self._format_products(raw_products)
                            # Enforce price limit from user query as safety net
                            if price_limit:
                                formatted = [p for p in formatted if p.get("price", 0) <= price_limit]
                            sent_ids = {p.get("id") or p.get("productId") for p in products_buffered}
                            sent_names = {p.get("name") or p.get("product_description") for p in products_buffered}
                            new_products = [
                                p for p in formatted
                                if (p.get("id") or p.get("productId")) not in sent_ids
                                and (p.get("name") or p.get("product_description")) not in sent_names
                            ]
                            products_buffered.extend(new_products)

                    yield {"type": "agent_step", "agent": "SearchAssistant", "action": "Done", "status": "completed"}
                    # Clear pre-tool thinking text so post-tool response doesn't concatenate
                    yield {"type": "content_reset"}

            await task

            if agent_error[0]:
                yield {"type": "error", "error": str(agent_error[0])}
                return

            response_text = str(agent_result[0]) if agent_result[0] else ""
            context_manager.add_message("assistant", response_text)
            parsed = await self._parse_agent_response(response_text, message, conversation_history, has_tool_products=bool(products_buffered))

            # Send text FIRST
            if parsed["text"]:
                yield {"type": "content", "content": parsed["text"]}

            # Then send buffered products
            if products_buffered:
                for i, product in enumerate(products_buffered):
                    yield {"type": "product", "product": product, "index": i, "total": len(products_buffered)}
                products_sent = products_buffered
            elif parsed["products"]:
                for i, product in enumerate(parsed["products"]):
                    yield {"type": "product", "product": product, "index": i, "total": len(parsed["products"])}
                products_sent = parsed["products"]

            duration_ms = int((time.time() - start_time) * 1000)
            token_count, estimated_cost, cost_breakdown = self._estimate_cost(response_text)
            self._track_query(products_count=len(products_sent), duration_ms=duration_ms, agent_type="SearchAssistant")
            yield {
                "type": "complete",
                "response": {
                    "response": parsed["text"],
                    "products": products_sent,
                    "suggestions": parsed["suggestions"],
                    "success": True,
                    "context_tracking": True,
                    "orchestrator_enabled": False,
                    "agent_execution": {
                        "agent_steps": [{"agent": "SearchAssistant", "action": "Processing", "status": "completed", "timestamp": start_time, "duration_ms": duration_ms}],
                        "tool_calls": [], "reasoning_steps": [],
                        "total_duration_ms": duration_ms, "success_rate": 1.0
                    },
                    "model": self.model_id,
                    "token_count": token_count,
                    "estimated_cost_usd": estimated_cost,
                    "cost_breakdown": cost_breakdown
                }
            }

        except Exception as e:
            logger.error(f"❌ Single-agent stream failed: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}

    async def _single_agent_chat(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        session_id: Optional[str] = None,
        guardrails_enabled: bool = False
    ) -> Dict[str, Any]:
        """Single-agent mode for Lab 2 — basic tools, no orchestrator routing."""
        import asyncio
        import time

        logger.info(f"🔧 Single-agent mode: '{message[:60]}...'")

        from services.context_manager import get_context_manager
        context_manager = get_context_manager()
        context_manager.add_message("user", message)

        try:
            from strands import Agent
            from strands.models.bedrock import BedrockModel
            from services.agent_tools import (
                find_pieces,
                whats_trending,
                price_intelligence,
            )

            single_prompt = SINGLE_AGENT_PROMPT
            if guardrails_enabled:
                single_prompt += GUARDRAILS_SUFFIX

            agent = Agent(
                model=BedrockModel(
                    model_id=self.model_id,
                    max_tokens=8192,
                    temperature=0.0
                ),
                system_prompt=single_prompt,
                tools=[find_pieces, whats_trending, price_intelligence]
            )

            # Build conversation context
            conversation_context = ""
            if conversation_history:
                for msg in conversation_history[-16:]:
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')[:300]
                    conversation_context += f"{role.upper()}: {content}\n\n"

            full_message = message
            if conversation_context:
                full_message = f"CONVERSATION HISTORY:\n{conversation_context}\n---\nCURRENT REQUEST: {message}"

            start_time = time.time()
            response = await asyncio.to_thread(agent, full_message)
            duration_ms = int((time.time() - start_time) * 1000)

            response_text = str(response) if response else ""
            context_manager.add_message("assistant", response_text)

            parsed = await self._parse_agent_response(response_text, message, conversation_history)

            return {
                "response": parsed["text"],
                "products": parsed["products"],
                "suggestions": parsed["suggestions"],
                "success": True,
                "context_tracking": True,
                "orchestrator_enabled": False,
                "agent_execution": {
                    "agent_steps": [{"agent": "SearchAssistant", "action": "Processing", "status": "completed", "timestamp": start_time, "duration_ms": duration_ms}],
                    "tool_calls": [],
                    "reasoning_steps": [],
                    "total_duration_ms": duration_ms,
                    "success_rate": 1.0
                },
                "model": self.model_id
            }

        except Exception as e:
            logger.error(f"❌ Single-agent chat failed: {e}", exc_info=True)
            raise RuntimeError(f"Single-agent execution failed: {str(e)}")

    async def _parse_agent_response(self, response_text: str, query: str = "", conversation_history: Optional[List[Dict[str, str]]] = None, has_tool_products: bool = False) -> Dict[str, Any]:
        """
        Parse agent response to extract:
        - Text response
        - Product data (from JSON blocks or database query results)
        - Contextual suggestions based on query type
        """
        result = {
            "text": "",
            "products": [],
            "suggestions": []
        }

        # Aggressive JSON extraction - try multiple patterns
        json_patterns = [
            r'```json\s*(\[[\s\S]*?\])\s*```',
            r'```\s*(\[[\s\S]*?\])\s*```',
            r'(\[\s*\{[^\[]*"productId"[^\]]*\])',
            r'(\[\s*\{[^\[]*"product_description"[^\]]*\])'
        ]

        products_data = None
        for pattern in json_patterns:
            json_matches = re.findall(pattern, response_text, re.DOTALL)
            if json_matches:
                raw = json_matches[0]
                logger.info(f"🔍 Found JSON match with pattern {pattern[:50]}...")
                for attempt, text in enumerate([raw, _repair_json(raw)]):
                    try:
                        products_data = json.loads(text)
                        result["products"] = await self._format_products(products_data)
                        # Enforce price limit from user query
                        plimit = self._extract_price_limit(query)
                        if plimit:
                            result["products"] = [p for p in result["products"] if p.get("price", 0) <= plimit]
                        if attempt == 1:
                            logger.info("🔧 JSON repaired successfully")
                        logger.info(f"📦 Extracted {len(result['products'])} products from JSON")
                        break
                    except json.JSONDecodeError as e:
                        if attempt == 1:
                            logger.warning(f"⚠️ Failed to parse JSON even after repair: {e}")
                if products_data:
                    break

        # Extract intro text before "Products:" section
        intro_match = re.search(r'^(.*?)(?=Products:|```json|$)', response_text, re.DOTALL | re.IGNORECASE)
        if intro_match and not result["text"]:
            intro_text = intro_match.group(1).strip()
            if intro_text and len(intro_text) > 10:
                result["text"] = intro_text

        if result["products"]:
            if not result["text"]:
                result["text"] = "Here are some great options for you!"
            logger.info(f"🛍️ Products extracted: {len(result['products'])} products")

        if not products_data:
            logger.debug("No JSON product data in response (pricing/inventory queries may not return products)")

        # Extract suggestions
        suggestions_section = re.search(r'Suggestions?:\s*\n(.*?)(?:\n\n|$)', response_text, re.DOTALL | re.IGNORECASE)
        if suggestions_section:
            suggestions_text = suggestions_section.group(1)
            suggestion_lines = re.findall(r'^-\s*"([^"]+)"', suggestions_text, re.MULTILINE)
            result["suggestions"] = suggestion_lines[:3]

        if not result["suggestions"]:
            result["suggestions"] = self._generate_contextual_suggestions(query, conversation_history)

        # Determine if we have products (either from JSON extraction or tool hooks)
        have_products = bool(result["products"]) or has_tool_products

        # Clean text — strip everything the frontend renders separately
        clean_text = response_text
        # Remove JSON code blocks
        for pattern in json_patterns:
            clean_text = re.sub(pattern, '', clean_text, flags=re.DOTALL)
        clean_text = re.sub(r'```[\s\S]*?```', '', clean_text)
        # Remove Suggestions section
        clean_text = re.sub(r'Suggestions?:.*$', '', clean_text, flags=re.DOTALL | re.IGNORECASE)
        # Remove "Products:" label
        clean_text = re.sub(r'^Products?:\s*$', '', clean_text, flags=re.MULTILINE | re.IGNORECASE)
        # Remove markdown tables
        clean_text = re.sub(r'^\|.*$', '', clean_text, flags=re.MULTILINE)
        # Remove horizontal rules
        clean_text = re.sub(r'^[-*_]{3,}\s*$', '', clean_text, flags=re.MULTILINE)
        # Remove markdown headers
        clean_text = re.sub(r'^#{1,4}\s+.*$', '', clean_text, flags=re.MULTILINE)
        # Remove numbered list lines (1. **Product** — $xx) — only when product cards exist
        if have_products:
            clean_text = re.sub(r'^\d+\.\s+\*\*.*$', '', clean_text, flags=re.MULTILINE)

        # Remove plain-text product listings ONLY when we have product cards to show instead.
        # When there are no product cards (e.g. inventory queries), the text IS the response.
        if have_products:
            # Lines containing price patterns like $xx.xx or $xxx.xx
            clean_text = re.sub(r'^.*\$\d+[\d,.]*\s*.*$', '', clean_text, flags=re.MULTILINE)
            # Lines with star ratings (⭐, ★, or "x.x stars")
            clean_text = re.sub(r'^.*[⭐★].*$', '', clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r'^.*\d+\.\d+\s*stars?.*$', '', clean_text, flags=re.MULTILINE | re.IGNORECASE)
            # Lines with "View Product" or product links
            clean_text = re.sub(r'^.*\[View Product\].*$', '', clean_text, flags=re.MULTILINE | re.IGNORECASE)
            clean_text = re.sub(r'^.*🔗.*$', '', clean_text, flags=re.MULTILINE)
            # Lines with "reviews)" pattern
            clean_text = re.sub(r'^.*\d+[\d,]*\s*reviews?\).*$', '', clean_text, flags=re.MULTILINE | re.IGNORECASE)
            # Lines that are just product names with em dash or bullet formatting
            clean_text = re.sub(r'^[-•]\s+\*\*.*$', '', clean_text, flags=re.MULTILINE)

        # Collapse blank lines
        clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)
        clean_text = clean_text.strip()

        # If we have products (from JSON or tool hooks), keep only brief intro
        if have_products and clean_text:
            sentences = re.split(r'(?<=[.!?])\s+', clean_text)
            intro = ' '.join(sentences[:2]).strip()
            if intro:
                clean_text = intro

        result["text"] = clean_text if clean_text else ("Here are some great options!" if have_products else response_text)

        return result
    
    async def _format_products(self, products_data: List[Dict]) -> List[Dict]:
        """Format products for frontend display."""
        formatted = []

        for product in products_data:
            product_id = product.get("productId") or product.get("product_id")

            raw_price = str(product.get("price", "0")).replace("$", "").replace(",", "").strip()
            try:
                price = float(raw_price)
            except (ValueError, TypeError):
                price = 0.0

            name = product.get("name") or product.get("product_description", "")
            name = name.split(" — ")[0].split(" - ")[0][:80]

            formatted.append({
                "id": product_id,
                "name": name,
                "brand": product.get("brand", ""),
                "color": product.get("color", ""),
                "price": price,
                "rating": _safe_float(product.get("rating") or product.get("stars", 0)),
                "reviews": _safe_int(product.get("reviews", 0)),
                "category": product.get("category") or product.get("category_name", ""),
                "image": (
                    product.get("imgUrl")
                    or product.get("image_url")
                    or product.get("image")
                    or product.get("imgurl")
                    or ""
                ),
                "badge": product.get("badge"),
                "tags": list(product.get("tags") or []),
                "originalPrice": None,
                "discountPercent": 0,
            })

        # Backfill images from database — LLM sometimes drops image URLs.
        if formatted and self.db_service:
            try:
                names = [p.get("name", "")[:60] for p in formatted if p.get("name")]
                if names:
                    placeholders = " OR ".join(["name ILIKE %s"] * len(names))
                    params = [f"%{n[:30]}%" for n in names]
                    rows = await self.db_service.fetch_all(
                        f'SELECT "productId", name, "imgUrl" FROM pellier.product_catalog WHERE {placeholders}',
                        *params,
                    )
                    img_lookup: Dict[str, str] = {}
                    for r in rows:
                        row_name = (r.get("name") or "")[:30].lower()
                        url = r.get("imgUrl") or ""
                        if row_name and url:
                            img_lookup[row_name] = url

                    for p in formatted:
                        name_key = (p.get("name") or "")[:30].lower()
                        if name_key in img_lookup:
                            p["image"] = img_lookup[name_key]
            except Exception as e:
                logger.error(f"🖼️ BACKFILL FAILED: {e}", exc_info=True)

        return formatted
    
    def _generate_contextual_suggestions(self, query: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> List[str]:
        """Generate action-oriented follow-up suggestions that feel agentic."""
        query_lower = query.lower()

        # Extract price context from query
        import re
        price_match = re.search(r'\$(\d+)', query)
        query_price = int(price_match.group(1)) if price_match else None

        # Category-specific action-oriented follow-ups
        if any(w in query_lower for w in ['watch', 'rolex', 'timepiece']):
            suggestions = ["Find me a cheaper alternative", "Compare the top 3 watches", "Which one has the best reviews?"]
        elif any(w in query_lower for w in ['laptop', 'macbook', 'notebook', 'computer']):
            suggestions = ["Which is best for programming?", "Find me one under $800", "Compare MacBook vs Windows options"]
        elif any(w in query_lower for w in ['phone', 'smartphone', 'iphone', 'samsung']):
            suggestions = ["Which has the best camera?", "Find me the best value pick", "Compare iPhone vs Samsung"]
        elif any(w in query_lower for w in ['shoe', 'sneaker', 'nike', 'jordan', 'running']):
            suggestions = ["Find the most cushioned pair", "Show me options under $100", "Which brand has the best ratings?"]
        elif any(w in query_lower for w in ['fragrance', 'perfume', 'cologne']):
            suggestions = ["What's the best everyday scent?", "Find me a gift set under $80", "Show me the highest rated"]
        elif any(w in query_lower for w in ['furniture', 'sofa', 'bed', 'table', 'chair']):
            suggestions = ["What's the best rated piece?", "Find something under $200", "Show me the most popular"]
        elif any(w in query_lower for w in ['kitchen', 'cook', 'pan', 'knife', 'spatula']):
            suggestions = ["Build me a starter kit under $50", "What's the must-have item?", "Show me the best rated"]
        elif any(w in query_lower for w in ['sunglasses', 'glasses', 'shades']):
            suggestions = ["Find me polarized options", "What's trending in shades?", "Show me premium frames"]
        elif any(w in query_lower for w in ['bag', 'handbag', 'backpack', 'purse']):
            suggestions = ["Find me a leather option", "What's the best everyday bag?", "Show me something under $80"]
        elif any(w in query_lower for w in ['sports', 'football', 'basketball', 'yoga']):
            suggestions = ["Build me a workout kit", "What's the best rated gear?", "Find equipment under $30"]
        elif any(w in query_lower for w in ['beauty', 'makeup', 'mascara', 'lipstick']):
            suggestions = ["Build me a beauty starter kit", "What's the top rated product?", "Find me gifts under $40"]
        elif any(w in query_lower for w in ['skin care', 'lotion', 'moisturizer']):
            suggestions = ["What's the best for daily use?", "Find a skincare set under $50", "Show me the highest rated"]
        elif any(w in query_lower for w in ['deal', 'cheap', 'budget', 'affordable']):
            suggestions = ["Find the best value in electronics", "Show me hidden gems under $25", "What's on sale right now?"]
        elif any(w in query_lower for w in ['trending', 'popular', 'best seller']):
            suggestions = ["Why is this one trending?", "Find me something similar but cheaper", "What else is popular today?"]
        elif any(w in query_lower for w in ['recommend', 'suggest', 'gift']):
            suggestions = ["Gifts under $50 for anyone", "What would you pick for a tech lover?", "Show me bestsellers"]
        else:
            suggestions = [
                "Find me the best deal in this category",
                "What would you recommend instead?",
                "Show me what's trending right now"
            ]

        # If there was a price in the query, swap one suggestion for a price-adjacent action
        if query_price and query_price > 50:
            suggestions[1] = f"Find cheaper alternatives under ${query_price // 2}"

        return suggestions[:3]
    
    @staticmethod
    def _estimate_cost(text: str) -> tuple:
        """Estimate token count and cost. Returns (token_count, cost_usd, breakdown)."""
        from services.embeddings import get_cache_stats
        token_count = int(len(text.split()) * 1.3)
        llm_cost = round(token_count * 0.000003, 6)
        embedding_cost = get_cache_stats().get("total_embedding_cost_usd", 0.0)
        total_cost = round(llm_cost + embedding_cost, 6)
        breakdown = {"llm_cost": llm_cost, "embedding_cost": embedding_cost}
        return token_count, total_cost, breakdown

    def _error_response(self, error: str) -> Dict[str, Any]:
        """Error response with clear diagnostic information"""

        # Provide helpful diagnostic info
        diagnostics = []

        if not self.strands_available:
            diagnostics.append("❌ Strands SDK not installed")
            diagnostics.append("   Run: pip install strands-agents strands-agents-tools")

        error_msg = "Configuration Error:\n\n" + "\n".join(diagnostics) if diagnostics else str(error)

        return {
            "response": error_msg,
            "products": [],
            "suggestions": [],
            "success": False,
            "error": str(error),
            "diagnostics": diagnostics
        }

    @staticmethod
    def _extract_price_limit(message: str) -> float | None:
        """Extract a price ceiling from user message (e.g. 'under $50' → 50.0)."""
        import re
        patterns = [
            r'under\s+\$?\s*(\d+(?:\.\d+)?)',
            r'below\s+\$?\s*(\d+(?:\.\d+)?)',
            r'less\s+than\s+\$?\s*(\d+(?:\.\d+)?)',
            r'up\s+to\s+\$?\s*(\d+(?:\.\d+)?)',
            r'max(?:imum)?\s+\$?\s*(\d+(?:\.\d+)?)',
            r'\$\s*(\d+(?:\.\d+)?)\s+(?:or\s+)?(?:less|max|budget|limit)',
        ]
        for pat in patterns:
            m = re.search(pat, message, re.IGNORECASE)
            if m:
                return float(m.group(1))
        return None

    @staticmethod
    def _tool_to_agent_name(tool_name: str) -> str:
        """Map tool function names to user-facing agent names."""
        return {
            'recommendation': 'Curator',
            'pricing': 'Value Analyst',
            'inventory': 'Stock Keeper',
            'support': 'Experience Guide',
            'search': 'Style Advisor',
            'find_pieces': 'Style Advisor',
        }.get(tool_name, 'Style Advisor')

    async def chat_stream(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        session_id: Optional[str] = None,
        workshop_mode: Optional[str] = None,
        guardrails_enabled: bool = False,
        user: Optional[Dict[str, Any]] = None,
        pattern: Optional[str] = None,
    ):
        """
        Async generator yielding SSE events with real-time agent streaming.

        Uses asyncio.Queue to bridge the synchronous agent thread with the
        async SSE generator. Hooks capture tool results so products are
        sent the moment a tool completes, not after the full chain finishes.

        The ``pattern`` parameter selects the orchestration model:
          - ``'dispatcher'`` — Storefront production path. Deterministic
            classifier picks one specialist; that specialist runs
            directly via its factory. One LLM call per turn. Voice
            preserved (no paraphrase cycle).
          - ``'agents_as_tools'`` — Atelier Pattern I. Haiku orchestrator
            + five ``@tool`` specialists. Two LLM calls per turn.
          - ``'graph'`` — Atelier Pattern II. Real Strands
            ``GraphBuilder`` DAG: Haiku router node + 5 specialist
            nodes; conditional edges route the turn to exactly one
            specialist. Exposed through ``GraphAgentAdapter`` so the
            downstream streaming/hook pipeline treats it identically
            to a single Agent.
          - ``None`` → ``'agents_as_tools'`` for backwards compatibility.
        """
        import asyncio
        import time

        # Pattern defaults to agents_as_tools for backwards compat.
        pattern = (pattern or "agents_as_tools").lower()
        if pattern not in ("dispatcher", "agents_as_tools", "graph"):
            logger.warning(
                "Unknown pattern %r; falling back to agents_as_tools", pattern
            )
            pattern = "agents_as_tools"

        # Resolve the effective customer_id for this turn. Personas
        # stash their customer_id in user["customer_id"] from the
        # /api/chat/stream endpoint. If no persona is active this is
        # None and LTM reads are skipped.
        customer_id: Optional[str] = None
        if user and isinstance(user, dict):
            cid = user.get("customer_id")
            if cid and isinstance(cid, str) and cid != "anonymous":
                customer_id = cid

        # Per-turn runtime timing (seeds Atelier Runtime page live strip)
        # and DB query log (seeds Atelier State Management live strip).
        # Markers are recorded inline via time.perf_counter(); the db log
        # is propagated through a ContextVar so tool invocations hit the
        # same buffer even when they run via asyncio.to_thread.
        from services.database import db_query_log_var
        turn_start = time.perf_counter()
        timing: Dict[str, float] = {
            "fastpath": 0.0,
            "intent": 0.0,
            "skill_router": 0.0,
            "orchestrator": 0.0,
            "specialist": 0.0,
            "tools": 0.0,
            "stream": 0.0,
        }
        ttft_mark: List[float] = []  # first streamed token timestamp
        db_queries_for_turn: list = []
        db_token = db_query_log_var.set(db_queries_for_turn)

        # Workshop mode: chat disabled for legacy/search
        if workshop_mode in ("legacy", "search"):
            yield {"type": "content", "content": "Chat is not available in this workshop mode. Progress to Module 2 to unlock agentic AI."}
            yield {"type": "complete", "response": {"response": "Chat is not available in this workshop mode.", "products": [], "suggestions": [], "success": True}}
            return

        # Triage fast-path — deterministic short-circuit for greetings,
        # meta, and thanks. The orchestrator never fires, which means:
        #  (a) no Bedrock call, no rate-limit exposure, no empty-LLM
        #      failure mode — "hi" on stage is guaranteed to reply.
        #  (b) the telemetry tab still gets a panel event so attendees
        #      can see the classification decision explicitly.
        fastpath_t0 = time.perf_counter()
        triage_bucket = classify_triage(message)
        timing["fastpath"] = (time.perf_counter() - fastpath_t0) * 1000
        if triage_bucket:
            logger.info(f"🎯 Triage | {triage_bucket} | msg={message[:60]!r}")
            reply = _TRIAGE_REPLIES[triage_bucket]
            yield {"type": "start", "content": "Routing your message..."}
            yield {
                "type": "agent_step",
                "agent": "Triage",
                "action": f"Classified as {triage_bucket} — skipping specialists",
                "status": "completed",
            }
            yield {"type": "content", "content": reply}
            context_manager_for_triage = None
            try:
                from services.context_manager import get_context_manager
                context_manager_for_triage = get_context_manager()
                context_manager_for_triage.add_message("user", message)
                context_manager_for_triage.add_message("assistant", reply)
            except Exception:
                pass
            yield {
                "type": "complete",
                "response": {
                    "response": reply,
                    "products": [],
                    "suggestions": [
                        "something for long summer walks",
                        "what's low on stock right now",
                        "pieces that travel well",
                    ],
                    "success": True,
                    "triage": triage_bucket,
                    "orchestrator_enabled": False,
                    "agent_execution": {
                        "agent_steps": [
                            {"agent": "Triage", "action": f"Classified as {triage_bucket}",
                             "status": "completed", "timestamp": 0, "duration_ms": 0},
                        ],
                        "tool_calls": [],
                        "reasoning_steps": [],
                        "waterfall": [],
                        "spans": [],
                        "totalMs": 0,
                        "specialistRoute": f"triage:{triage_bucket}",
                        "total_duration_ms": 0,
                        "success_rate": 1.0,
                        "otel_enabled": False,
                        "reason": "triage fast-path — orchestrator skipped",
                    },
                    "token_count": 0,
                    "estimated_cost_usd": 0.0,
                },
            }
            return

        if not self.strands_available:
            yield {"type": "error", "error": "Strands SDK not available"}
            return

        # --- Setup (mirrors _strands_enhanced_chat) ---
        from services.context_manager import get_context_manager
        context_manager = get_context_manager()
        context_manager.add_message("user", message)

        from agents.orchestrator import create_orchestrator, create_guarded_orchestrator

        session_manager = None
        if session_id:
            # === WIRE IT LIVE (Lab 4b) ===
            from config import settings
            if user and settings.AGENTCORE_MEMORY_ID:
                try:
                    from services.agentcore_memory import create_agentcore_session_manager
                    # Prefer persona customer_id over Cognito sub so memory
                    # is scoped to the persona's identity for the demo.
                    memory_user_id = (
                        customer_id
                        or user.get("sub", "anonymous")
                    )
                    session_manager = create_agentcore_session_manager(
                        session_id=session_id,
                        user_id=memory_user_id,
                    )
                    if session_manager:
                        logger.info(f"🧠 AgentCore Memory (stream) for user={memory_user_id}")
                except Exception as e:
                    logger.warning(f"AgentCore Memory setup failed: {e}")
            # === END WIRE IT LIVE ===

            if not session_manager:
                logger.info("ℹ️ No session manager for streaming — agent runs stateless")

        # Agent construction — Pattern I (Agents-as-Tools) builds the
        # orchestrator here. Pattern III (Dispatcher) defers construction
        # until after persona + skill ContextVars are set below, so the
        # specialist factory picks them up at build time.
        #
        # Gateway preference: when ``settings.AGENTCORE_GATEWAY_URL`` is
        # set, we use the MCP-discovered tool path instead of importing
        # @tool symbols directly. This is the production shape — tools
        # live in the Gateway, the orchestrator pulls them at runtime.
        # When the Gateway URL is unset (local dev, Workshop Studio
        # before Module 3c lands), we fall back to the in-process
        # orchestrator silently. Guardrails flag is respected on the
        # fallback path; gateway path honors guardrails via its own
        # prompt extensions (future work).
        orchestrator = None
        gateway_used = False
        if pattern == "agents_as_tools":
            from config import settings as _settings
            if getattr(_settings, "AGENTCORE_GATEWAY_URL", None):
                try:
                    from services.agentcore_gateway import create_gateway_orchestrator
                    orchestrator = create_gateway_orchestrator()
                    if orchestrator is not None:
                        gateway_used = True
                        logger.info("🛰️ Gateway orchestrator | tools via MCP discovery")
                except Exception as exc:
                    logger.warning("Gateway orchestrator failed; falling back to in-proc: %s", exc)
                    orchestrator = None

            if orchestrator is None:
                if guardrails_enabled:
                    orchestrator = create_guarded_orchestrator()
                else:
                    orchestrator = create_orchestrator()

            # Graceful fallback if orchestrator not implemented yet (Module 3b TODO)
            if orchestrator is None:
                yield {
                    "type": "error",
                    "error": "🔧 The AI agent orchestrator isn't wired up yet. "
                             "Complete Module 3b to enable the chat assistant."
                }
                return
        # For dispatcher/graph, ``orchestrator`` is bound later once
        # ContextVars are live. We reuse the ``orchestrator`` name so the
        # existing streaming/hook pipeline treats specialist or graph
        # invocations identically — every code path downstream expects
        # something with ``callback_handler``, ``add_hook``,
        # ``trace_attributes``, and a callable signature. For graph,
        # the GraphAdapter satisfies that interface while running a
        # real Strands ``Graph`` internally.

        # Trace attributes are applied once ``orchestrator`` is bound.
        # For ``agents_as_tools`` that's here; for ``dispatcher`` that's
        # after the specialist factory call below.
        trace_attributes = {
            "session.id": session_id or "anonymous",
            "session.user": user.get("email", "anonymous") if user else "anonymous",
            "user.query": message[:100],
            "workshop": "pellier",
            "service": "pellier",
            "pattern": pattern,
        }

        if orchestrator is not None:
            orchestrator.trace_attributes = trace_attributes
            if session_manager:
                orchestrator.session_manager = session_manager
                _safe_register_hooks(session_manager, orchestrator)

        # Build conversation context
        conversation_context = ""
        if conversation_history:
            for msg in conversation_history[-16:]:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if len(content) > 300:
                    content = content[:300] + "..."
                conversation_context += f"{role.upper()}: {content}\n\n"

        full_message = message
        if conversation_context:
            full_message = (
                f"CONVERSATION HISTORY:\n{conversation_context}\n---\n"
                f"CURRENT REQUEST: {message}"
            )

        # --- Persona LTM preamble -----------------------------------------
        # When a persona is active (customer_id is set), read their LTM
        # facts + order history from Aurora and prepend them to the
        # orchestrator message so specialists ground their reply in the
        # persona's actual history. Skipped for anonymous sessions —
        # they get the editorial fallback.
        persona_preamble = ""
        persona_orders_for_cards: list = []  # hydrated product rows for past-order cards
        if customer_id and self.db_service:
            try:
                facts_rows = await self.db_service.fetch_all(
                    "SELECT summary_text, ts_offset_days "
                    "FROM customer_episodic_seed "
                    "WHERE customer_id = %s "
                    "ORDER BY ts_offset_days DESC LIMIT 8",
                    customer_id,
                )
                orders_rows = await self.db_service.fetch_all(
                    'SELECT pc."productId", pc.name, pc.brand, pc.color, '
                    'pc.price, pc.category, pc."imgUrl", pc.rating, pc.reviews, '
                    'o.placed_at '
                    'FROM orders o '
                    'JOIN pellier.product_catalog pc ON o.product_id = pc."productId" '
                    "WHERE o.customer_id = %s "
                    "ORDER BY o.placed_at DESC LIMIT 10",
                    customer_id,
                )
                customer_row = await self.db_service.fetch_one(
                    "SELECT name FROM customers WHERE id = %s",
                    customer_id,
                )
                name = customer_row["name"] if customer_row else "the shopper"
                if facts_rows or orders_rows:
                    lines = [f"PERSONA CONTEXT — {name} ({customer_id})"]
                    if facts_rows:
                        lines.append("Known about them (LTM):")
                        for f in facts_rows:
                            lines.append(f"  - {f['summary_text']}")
                    if orders_rows:
                        lines.append("Past orders:")
                        for o in orders_rows:
                            lines.append(
                                f"  - {o['name']} (${o['price']:.0f}, {o['category']})"
                            )
                    lines.append(
                        "Use this to tailor the reply — reference past purchases, "
                        "respect preferences, avoid asking for info you already know."
                    )
                    persona_preamble = "\n".join(lines) + "\n---\n"

                # Hydrate order rows into the shape ProductArtifactCard
                # expects. Kept as a dict list so the existing product
                # emission path (yield {"type": "product", ...}) can
                # consume them unchanged when retrospective queries hit.
                for o in (orders_rows or []):
                    persona_orders_for_cards.append({
                        "productId": o.get("productId"),
                        "id": o.get("productId"),
                        "name": o.get("name") or "",
                        "brand": o.get("brand") or "",
                        "color": o.get("color") or "",
                        "price": float(o.get("price") or 0),
                        "category": o.get("category") or "",
                        "imgUrl": o.get("imgUrl") or "",
                        "rating": float(o.get("rating") or 0),
                        "reviews": int(o.get("reviews") or 0),
                        "badge": "From your orders",
                        "tags": [],
                    })

                logger.info(
                    f"👤 Persona LTM | {customer_id} | "
                    f"facts={len(facts_rows)} orders={len(orders_rows)}"
                )
            except Exception as e:
                logger.warning(f"Persona LTM read failed for {customer_id}: {e}")

        if persona_preamble:
            full_message = persona_preamble + full_message

        # Deterministic intent classification.
        #
        # Its output has two consumers:
        #   1. Pattern III (Dispatcher) uses ``intent_hint`` to pick
        #      which specialist factory to build.
        #   2. Telemetry (``📨 chat_stream`` log, Atelier panels) uses
        #      the classification for the routing annotation.
        #
        # The previous ``[ROUTING DIRECTIVE: call the X tool]`` prefix
        # injection was deleted in the three-pattern refactor. It
        # existed to override Haiku's routing in Pattern I when the
        # Haiku orchestrator drifted from the classifier's verdict —
        # a workaround for the "Agents-as-Tools paraphrases" failure
        # mode. Pattern I now runs with the unmodified user message;
        # Pattern III skips Haiku entirely and dispatches by the
        # classifier directly.
        intent_t0 = time.perf_counter()
        intent = classify_intent(message)
        intent_hint = {
            "pricing": "pricing",
            "inventory": "inventory",
            "customer_support": "support",
            "search": "search",
            "recommendation": "recommendation",
        }[intent]
        timing["intent"] = (time.perf_counter() - intent_t0) * 1000
        logger.info(f"🎯 Intent: {intent} → {intent_hint}")

        # --- Skill router ---------------------------------------------------
        # One LLM call to Haiku 4.5 decides which skills to inject into the
        # reasoning specialists' system prompts for this turn. Runs after
        # intent classification so the triage fast-path (greetings, meta,
        # thanks) short-circuits before reaching here.
        #
        # The ``skill_routing`` SSE event must fire BEFORE any text tokens
        # so the boutique UI can render the attribution line above the
        # reply. Storefront reads ``loaded_skills``; Atelier renders the
        # full decision in its live activation log.
        skill_decision = None
        skill_t0 = time.perf_counter()
        try:
            from skills import SkillRouter, get_registry
            router = SkillRouter(get_registry())
            skill_decision = router.route(message)
            logger.info(
                "🪡 Skills | loaded=%s | elapsed=%dms",
                skill_decision.loaded_skills or "none",
                skill_decision.elapsed_ms,
            )
        except Exception as exc:
            logger.warning("Skill router unavailable: %s", exc)
        timing["skill_router"] = (time.perf_counter() - skill_t0) * 1000

        # Emit the routing event immediately — before any text — so the
        # boutique attribution line is mounted above the streamed reply.
        if skill_decision is not None:
            yield {
                "type": "skill_routing",
                "routing": skill_decision.model_dump(),
            }

        # --- Queue-based streaming bridge ---
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        # Callback handler: forward text tokens from the agent thread.
        def streaming_callback(**kwargs):
            if "data" in kwargs:
                try:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"_text": kwargs["data"]}), loop
                    ).result(timeout=10)
                except Exception:
                    pass

        # Hook factories — produce the two BeforeToolCall / AfterToolCall
        # callbacks that push tool lifecycle events onto the queue.
        # Extracted into a helper so the dispatcher path can attach the
        # same hooks to its specialist agent without duplicating code.
        def _attach_streaming_and_hooks(agent) -> None:
            """Attach the shared streaming callback + tool lifecycle
            hooks to any Strands Agent. Same SSE surface regardless of
            pattern."""
            agent.callback_handler = streaming_callback
            try:
                from strands.hooks.events import BeforeToolCallEvent, AfterToolCallEvent

                def on_before_tool(event: BeforeToolCallEvent):
                    tool_name = ""
                    if hasattr(event, 'tool_use') and isinstance(event.tool_use, dict):
                        tool_name = event.tool_use.get("name", "")
                    if tool_name:
                        try:
                            asyncio.run_coroutine_threadsafe(
                                queue.put({"_tool_start": tool_name}), loop
                            ).result(timeout=5)
                        except Exception:
                            pass

                def on_after_tool(event: AfterToolCallEvent):
                    tool_name = ""
                    if hasattr(event, 'tool_use') and isinstance(event.tool_use, dict):
                        tool_name = event.tool_use.get("name", "")
                    # Extract the actual tool result text from the Strands SDK result structure
                    result_str = ""
                    if hasattr(event, 'result') and event.result is not None:
                        raw = event.result
                        if isinstance(raw, dict) and 'content' in raw:
                            for block in raw.get('content', []):
                                if isinstance(block, dict) and 'text' in block:
                                    result_str = block['text']
                                    break
                        if not result_str:
                            result_str = str(raw)
                    try:
                        asyncio.run_coroutine_threadsafe(
                            queue.put({"_tool_done": tool_name, "_result": result_str}), loop
                        ).result(timeout=10)
                    except Exception:
                        pass

                agent.add_hook(on_before_tool)
                agent.add_hook(on_after_tool)
            except (ImportError, AttributeError) as e:
                logger.warning(f"Strands hooks not available, falling back: {e}")

            # Cedar policy enforcement — registered alongside the
            # telemetry hooks so the policy's ``cancel_tool`` write
            # fires before Strands actually invokes the tool. The
            # enforcement hook consults PolicyService; DENY decisions
            # short-circuit the call with a synthetic tool result
            # explaining the violation, which the agent paraphrases
            # to the user.
            #
            # Agent.add_hook() takes an individual callback; we register
            # the provider through the lower-level registry so the
            # provider's ``register_hooks`` runs once and sets up all
            # its callbacks in one shot. GraphAdapter forwards
            # ``add_hook`` per-specialist, so this still propagates to
            # every specialist when pattern=="graph".
            try:
                from services.policy_hook import PolicyEnforcementHook
                policy_provider = PolicyEnforcementHook(session_id=session_id)
                hooks_registry = getattr(agent, "hooks", None)
                if hooks_registry is not None and hasattr(hooks_registry, "add_hook"):
                    hooks_registry.add_hook(policy_provider)
                else:
                    # GraphAdapter / non-Strands shim: fall through to
                    # the callback-style registration so the policy
                    # still fires. PolicyEnforcementHook._on_before_tool
                    # is the exact callback Strands would register via
                    # ``register_hooks``.
                    agent.add_hook(policy_provider._on_before_tool)
            except Exception as exc:
                logger.warning("PolicyEnforcementHook attach failed: %s", exc)

        # For Pattern I (``agents_as_tools``) the orchestrator is
        # already constructed at this point; attach the streaming and
        # hooks to it now. Pattern III attaches after the specialist is
        # built below (once persona + skill ContextVars are live).
        if orchestrator is not None:
            _attach_streaming_and_hooks(orchestrator)

        # --- Yield initial SSE events ---
        yield {"type": "start", "content": "Initializing agent..."}
        yield {
            "type": "agent_step",
            "agent": "Orchestrator",
            "action": "Analyzing query",
            "status": "in_progress"
        }

        # --- Per-turn telemetry bookkeeping ---
        # tool_starts stashes wall-clock start of each active tool so the
        # AfterToolCall log line can report latency without relying on the
        # Strands SDK's own cycle timers (which aren't always exposed).
        tool_starts: Dict[str, float] = {}
        tool_trace: List[Dict[str, Any]] = []

        # --- Run orchestrator in background thread ---
        start_time = time.time()
        orchestrator_t0 = time.perf_counter()
        logger.info(
            f"📨 chat_stream | intent={intent} → {intent_hint} "
            f"| session={session_id or 'anon'} | msg={message[:80]!r}"
        )
        orchestrator_result = [None]
        orchestrator_error = [None]

        # Set the ContextVar with the loaded skills before invoking the
        # orchestrator. asyncio.to_thread (Python 3.9+) propagates context
        # into the worker thread via copy_context(), so specialist agent
        # factories reading via get_loaded_skills() will see these values.
        # The token is reset via a finally block on the orchestrator wait
        # (not here) so a mid-stream error can't leak skills to the next
        # request.
        skill_token = None
        if skill_decision is not None and skill_decision.loaded_skills:
            try:
                from skills import set_loaded_skills, get_registry
                loaded_objs = [
                    get_registry().get(name)
                    for name in skill_decision.loaded_skills
                ]
                loaded_objs = [s for s in loaded_objs if s is not None]
                if loaded_objs:
                    skill_token = set_loaded_skills(loaded_objs)
            except Exception as exc:
                logger.warning("Skill ContextVar set failed: %s", exc)

        def _reset_skill_token() -> None:
            """Idempotent reset — safe to call on any exit path."""
            nonlocal skill_token
            if skill_token is not None:
                try:
                    from skills import loaded_skills_var
                    loaded_skills_var.reset(skill_token)
                except Exception as exc:
                    logger.warning("Skill ContextVar reset failed: %s", exc)
                skill_token = None

        # --- Persona preamble ContextVar ------------------------------
        # Mirrors the skill-loading pattern above. The orchestrator
        # (Haiku, dispatcher) paraphrases the user message when routing
        # to a specialist, which frequently strips the PERSONA CONTEXT
        # block from the ``query`` arg. Stashing the preamble in a
        # ContextVar lets the specialist read it directly when building
        # its system prompt, so the shopper's history is always visible
        # even when Haiku's routing forwards only the short phrase.
        persona_token = None
        if persona_preamble:
            try:
                from services.persona_context import set_persona_preamble
                persona_token = set_persona_preamble(persona_preamble)
            except Exception as exc:
                logger.warning("Persona ContextVar set failed: %s", exc)

        def _reset_persona_token() -> None:
            """Idempotent reset — safe to call on any exit path."""
            nonlocal persona_token
            if persona_token is not None:
                try:
                    from services.persona_context import persona_preamble_var
                    persona_preamble_var.reset(persona_token)
                except Exception as exc:
                    logger.warning("Persona ContextVar reset failed: %s", exc)
                persona_token = None

        # Pattern II (Graph) builds the GraphAdapter here, AFTER the
        # persona + skill ContextVars are live so the specialist
        # factories inside the adapter pick them up at construction
        # time. The adapter looks like an ``Agent`` to the pipeline:
        # callable, exposes ``callback_handler`` / ``add_hook`` /
        # ``trace_attributes`` / ``session_manager``. A real
        # Strands ``Graph`` with a Haiku router + 5 specialist nodes
        # runs under the hood.
        if pattern == "graph":
            try:
                from agents.graph_pattern import build_graph_orchestrator
                orchestrator = build_graph_orchestrator()
                orchestrator.trace_attributes = trace_attributes
                if session_manager:
                    orchestrator.session_manager = session_manager
                    # GraphAdapter forwards session_manager to its
                    # specialists via __setattr__; the wrapper call
                    # below registers hooks on each specialist.
                    for specialist in orchestrator._specialists.values():
                        _safe_register_hooks(session_manager, specialist)
                _attach_streaming_and_hooks(orchestrator)
                logger.info("🔀 Graph | router + 5 specialists via GraphBuilder")
            except Exception as exc:
                logger.exception("Graph pattern failed to build; falling back to dispatcher: %s", exc)
                pattern = "dispatcher"  # fall through to dispatcher branch

        # Pattern III (Dispatcher) builds the specialist here — AFTER
        # the persona + skill ContextVars are live, so the factory
        # picks them up at construction time. The specialist replaces
        # the orchestrator for the downstream streaming pipeline;
        # everything after this point treats ``orchestrator`` as a
        # plain Strands Agent regardless of pattern.
        if pattern == "dispatcher":
            from agents.style_advisor import build_search_agent
            from agents.curator import build_recommendation_agent
            from agents.value_analyst import build_pricing_agent
            from agents import stock_keeper as inventory_agent_module
            from agents import experience_guide as support_agent_module

            # --- Workshop stub detection ---
            #
            # When participants haven't yet wired Stock Keeper (or
            # Experience Guide, in the Workshop format), the Dispatcher
            # intercepts and returns a voice-matched non-answer INSTEAD
            # of invoking the stub agent. This is the graceful gap
            # Marco's Turn 4 lands in during the opening demo; wiring
            # the agent flips the flag and the same turn returns real
            # warehouse data.
            #
            # We yield the non-answer as streaming SSE events so the
            # frontend renders it identically to a normal assistant
            # response (no error UI, no exception).
            _STUB_FALLBACK_MESSAGES = {
                "inventory": (
                    "I can help with style and recommendations, but I don't have "
                    "real-time stock visibility for individual warehouses yet. "
                    "I can tell you the product is in the catalog and marked "
                    "in-stock system-wide — but which warehouse holds it, and "
                    "how many are on the floor, sits outside what I can answer "
                    "right now."
                ),
                "support": (
                    "I can help with style and recommendations, but return "
                    "handling and post-purchase support sits outside what I "
                    "can answer right now. When the Experience Guide is wired "
                    "it will own returns, care instructions, and warranty flow "
                    "end-to-end."
                ),
            }

            _stub_flag = None
            if intent_hint == "inventory":
                _stub_flag = getattr(
                    inventory_agent_module, "_INVENTORY_AGENT_STUBBED", False
                )
            elif intent_hint == "support":
                _stub_flag = getattr(
                    support_agent_module, "_SUPPORT_AGENT_STUBBED", False
                )

            if _stub_flag:
                fallback_text = _STUB_FALLBACK_MESSAGES[intent_hint]
                logger.info(
                    "🎯 Dispatcher | specialist=%s is STUBBED — returning "
                    "voice-matched non-answer (workshop build pending)",
                    intent_hint,
                )
                # Stream the non-answer as if a normal agent produced it.
                # The frontend's streaming handler (services/chat.ts) treats
                # `content` as the canonical text-update event — using
                # `text` here silently drops the message and the user sees
                # the hardcoded "Response completed" default.
                yield {"type": "content", "content": fallback_text}
                yield {
                    "type": "meta",
                    "meta": {
                        "agent": None,
                        "model": None,
                        "note": f"{intent_hint}-intent matched; agent is the workshop build",
                        "fallthrough": True,
                    },
                }
                # Emit a `complete` event so the frontend populates
                # `finalResponse.response` and `agent_execution` instead
                # of falling back to the hardcoded default. `agent_execution`
                # mirrors the shape live agents produce so the Atelier
                # Sessions Brief tab and the inline pill in the chat
                # surface the fall-through honestly (no agent, no model).
                yield {
                    "type": "complete",
                    "response": {
                        "response": fallback_text,
                        "products": [],
                        "suggestions": [],
                        "agent_execution": {
                            "agent": None,
                            "model": None,
                            "fallthrough": True,
                            "intent": intent_hint,
                            "note": (
                                f"{intent_hint}-intent matched; "
                                "agent is the workshop build"
                            ),
                        },
                        "success": True,
                    },
                }
                return

            from agents.stock_keeper import build_inventory_agent
            from agents.experience_guide import build_support_agent

            _DISPATCHER_FACTORIES = {
                "search": build_search_agent,
                "recommendation": build_recommendation_agent,
                "pricing": build_pricing_agent,
                "inventory": build_inventory_agent,
                "support": build_support_agent,
            }
            # intent_hint is one of {pricing, inventory, support,
            # search, recommendation} — guaranteed to be in the map.
            factory = _DISPATCHER_FACTORIES[intent_hint]
            orchestrator = factory()
            orchestrator.trace_attributes = trace_attributes
            if session_manager:
                orchestrator.session_manager = session_manager
                _safe_register_hooks(session_manager, orchestrator)
            _attach_streaming_and_hooks(orchestrator)
            logger.info(f"🎯 Dispatcher | specialist={intent_hint}")

        async def run_orchestrator():
            try:
                orchestrator_result[0] = await asyncio.to_thread(orchestrator, full_message)
            except Exception as e:
                orchestrator_error[0] = e
            finally:
                await queue.put({"_done": True})

        task = asyncio.create_task(run_orchestrator())

        # --- Process events from queue in real-time ---
        products_sent = []
        products_buffered = []  # Hold products until text streams first
        current_tool = None
        price_limit = self._extract_price_limit(message)
        # Drop the products buffer when a write tool succeeded — the
        # customer just filed a return / restocked a shelf and any
        # products that came back from upstream resolution tools (e.g.
        # find_pieces called by Experience Guide to map a product name
        # to an integer id) are plumbing, not recommendations the user
        # wants rendered as cards.
        write_tool_succeeded = False

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=120)
            except asyncio.TimeoutError:
                yield {"type": "error", "error": "Agent execution timed out"}
                break

            if "_done" in event:
                break

            # Tool started (from BeforeToolCallEvent hook)
            if "_tool_start" in event:
                tool_name = event["_tool_start"]
                tool_starts[tool_name] = time.time()
                logger.info(f"🔧 tool_start | {tool_name}")
                if tool_name != current_tool:
                    current_tool = tool_name
                    agent_name = self._tool_to_agent_name(tool_name)
                    yield {
                        "type": "agent_step",
                        "agent": agent_name,
                        "action": "Searching",
                        "status": "in_progress"
                    }
                    yield {"type": "tool_call", "tool": tool_name, "status": "executing"}

            # Tool completed (from AfterToolCallEvent hook) — buffer products for later
            elif "_tool_done" in event:
                tool_name = event.get("_tool_done", "")
                result_str = event.get("_result", "")
                result_count = 0
                # Detect successful write tools so we can suppress the
                # products buffer at emit time. process_return returns
                # status=success with return_id; restock_shelf returns
                # status=success with new_quantity.
                if result_str and tool_name in {"process_return", "restock_shelf"}:
                    try:
                        _data = json.loads(result_str)
                        if (
                            isinstance(_data, dict)
                            and _data.get("status") == "success"
                            and ("return_id" in _data or "new_quantity" in _data)
                        ):
                            write_tool_succeeded = True
                    except (json.JSONDecodeError, TypeError):
                        pass
                if result_str:
                    raw_products = ProductExtractor.extract(result_str)
                    if raw_products:
                        result_count = len(raw_products)
                        formatted = await self._format_products(raw_products)
                        # Enforce price limit from user query as safety net
                        if price_limit:
                            formatted = [p for p in formatted if p.get("price", 0) <= price_limit]
                        # Deduplicate: skip products already buffered (by id or name)
                        sent_ids = {p.get("id") or p.get("productId") for p in products_buffered}
                        sent_names = {p.get("name") or p.get("product_description") for p in products_buffered}
                        new_products = [
                            p for p in formatted
                            if (p.get("id") or p.get("productId")) not in sent_ids
                            and (p.get("name") or p.get("product_description")) not in sent_names
                        ]
                        products_buffered.extend(new_products)
                    # NOTE: the three-pattern refactor deleted the
                    # ``last_specialist_text`` capture here — it used
                    # to snapshot specialist prose so the empty-
                    # response recovery ladder (workaround #3) could
                    # recover it when Haiku's final cycle came back
                    # blank. Dispatcher has no paraphrase cycle;
                    # Agents-as-Tools still runs but no longer needs
                    # the promotion path because the orchestrator's
                    # Haiku output is the user-facing reply, period.

                tool_ms = int(
                    (time.time() - tool_starts.pop(tool_name, time.time())) * 1000
                )
                tool_trace.append(
                    {"tool": tool_name, "ms": tool_ms, "results": result_count}
                )
                logger.info(
                    f"✅ tool_done  | {tool_name:<30} | {tool_ms:>5}ms | results={result_count}"
                )

                agent_name = self._tool_to_agent_name(tool_name)
                yield {
                    "type": "agent_step",
                    "agent": agent_name,
                    "action": "Done",
                    "status": "completed"
                }
                # Reset streamed content — tells the frontend to clear
                # the bubble so the agent's final text response starts
                # fresh. Emitted for BOTH patterns.
                #
                # An earlier fix (a9338b0) skipped this for the
                # dispatcher on the theory that specialists stream
                # once continuously. That's wrong for any specialist
                # that hits a tool — Bedrock's event loop runs two
                # cycles (pre-tool reasoning, post-tool summary) and
                # both fire the callback. Without the reset, the
                # post-tool prose concatenates onto the pre-tool
                # tokens and the bubble shows duplicated phrases
                # with sub-word overlaps at the boundary. The reset
                # clears the pre-tool leakage so only the final
                # summary shows.
                yield {"type": "content_reset"}

            elif "_text" in event:
                # Stream text tokens to the client in real time
                if not ttft_mark:
                    ttft_mark.append(time.perf_counter())
                yield {"type": "content_delta", "delta": event["_text"]}

        # --- Await orchestrator completion ---
        try:
            await task
        finally:
            # Reset ContextVars as soon as the orchestrator is done —
            # specialists can no longer run, so nothing else needs the
            # loaded skills or persona preamble from here on. Safe on
            # exception paths too.
            _reset_skill_token()
            _reset_persona_token()

        if orchestrator_error[0]:
            yield {"type": "error", "error": str(orchestrator_error[0])}
            return

        # --- Inject past-order product cards for retrospective queries ---
        #
        # Disabled in the three-pattern refactor. The blunt "top 3 by
        # placed_at" injection often showed cards that didn't match the
        # specialist's prose (the specialist highlights specific orders
        # from the LTM preamble; the injection grabbed the most recent
        # regardless). The specialist can call find_pieces if it
        # wants to surface product cards; for retrospective queries
        # answered from the preamble, the prose is the answer.
        #
        # Kept as a comment block so the pattern is recoverable if a
        # future iteration wants smarter card injection (e.g., extract
        # product names from the specialist's prose and match them
        # against persona_orders_for_cards).

        # --- Parse and send final response ---
        response_text = str(orchestrator_result[0]) if orchestrator_result[0] else ""
        context_manager.add_message("assistant", response_text)

        parsed = await self._parse_agent_response(response_text, message, conversation_history, has_tool_products=bool(products_buffered))

        # Minimal empty-response fallback. The aggressive recovery
        # ladder (specialist-over-orchestrator promotion and the
        # pre/post content_reset buffer walk) was deleted in the
        # three-pattern refactor — it existed to compensate for Haiku's
        # paraphrase in Pattern I, but the Dispatcher has no paraphrase
        # cycle and the Graph mode routes deterministically. A single
        # generic line covers the pathological case where Bedrock
        # itself returns nothing at all.
        if not parsed["text"] and not products_buffered and not parsed["products"]:
            parsed["text"] = (
                "I couldn't land on a clear answer — try rephrasing or narrowing the ask."
            )
            logger.warning(
                "chat_stream empty response | pattern=%s tools=%d",
                pattern, len(tool_trace),
            )

        # Send clean text content FIRST (before product cards).
        #
        # In the dispatcher path, the specialist's prose was already
        # streamed to the client via content_delta events. The
        # ``content`` event here would overwrite it with whatever
        # ``_parse_agent_response`` extracted from ``str(AgentResult)``
        # — which is often a generic fallback ("Here are some great
        # options!") because the parser strips JSON blocks and the
        # remaining text is short. Skip the ``content`` event when
        # deltas already streamed; the frontend's ``content_delta``
        # handler already built the reply in the bubble.
        #
        # For Pattern I (agents_as_tools), the content event is still
        # useful because the orchestrator's final cycle may produce a
        # different summary than what was streamed during the
        # specialist's tool invocation.
        has_streamed_deltas = bool(ttft_mark)
        if parsed["text"] and not has_streamed_deltas:
            yield {"type": "content", "content": parsed["text"]}

        # Suppress all product cards when the turn included a successful
        # write tool (process_return, restock_shelf). Any products that
        # came back from upstream resolution tools (find_pieces called
        # to map "Wabi-Sabi Bowl" → product_id=31) are plumbing, not
        # recommendations the customer wants alongside their return
        # confirmation. Keep parsed["text"] / streaming intact.
        if write_tool_succeeded:
            products_buffered = []
            parsed["products"] = []
            logger.info("🔇 Products suppressed — successful write tool in turn")

        # Now send buffered products (collected from tool hooks during execution)
        if products_buffered:
            for i, product in enumerate(products_buffered):
                yield {
                    "type": "product",
                    "product": product,
                    "index": i,
                    "total": len(products_buffered)
                }
            products_sent = products_buffered
        elif parsed["products"]:
            # Fallback: send products extracted from response text
            for i, product in enumerate(parsed["products"]):
                yield {
                    "type": "product",
                    "product": product,
                    "index": i,
                    "total": len(parsed["products"])
                }
            products_sent = parsed["products"]
        elif persona_orders_for_cards:
            # Retrospective path: the specialist answered from the LTM
            # preamble without calling find_pieces, so no tool
            # products were buffered. Surface up to 3 past-order cards
            # whose product names appear literally in the specialist's
            # prose — evidence for "your Italian Linen Camp Shirt"
            # references.
            #
            # This replaces the blunt "top 3 by placed_at" injection
            # the refactor deleted. Name matching is tight: a product
            # only surfaces if its full name OR its head (name before
            # any " — " separator) literally appears in the prose, so
            # no card shows up that the specialist didn't name.
            #
            # Products flow into the same render path as forward-
            # looking tool results — full ProductArtifactCard on the
            # frontend — so retrospective and forward turns look the
            # same to the shopper.
            prose = (parsed["text"] or response_text or "").lower()
            matched: list = []
            seen_ids: set = set()
            for order in persona_orders_for_cards:
                name = (order.get("name") or "").strip()
                if not name:
                    continue
                head = name.split(" — ")[0].strip()
                key = name.lower()
                head_key = head.lower()
                if key in prose or (head_key and head_key in prose):
                    pid = order.get("productId") or order.get("id")
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    matched.append(order)
                if len(matched) >= 3:
                    break
            if matched:
                for i, product in enumerate(matched):
                    yield {
                        "type": "product",
                        "product": product,
                        "index": i,
                        "total": len(matched),
                    }
                products_sent = matched

        # OTEL extraction. On failure the payload carries otel_enabled=False
        # + reason so the frontend banner fires (Bug 3); we do NOT
        # synthesize agent_steps.
        try:
            from services.otel_trace_extractor import extract_agent_execution_from_otel
            agent_execution = extract_agent_execution_from_otel()
        except Exception as e:
            logger.error(f"OTEL extraction raised: {e}")
            agent_execution = {
                "agent_steps": [], "tool_calls": [], "reasoning_steps": [],
                "waterfall": [], "spans": [], "totalMs": 0,
                "specialistRoute": "",
                "total_duration_ms": int((time.time() - start_time) * 1000),
                "success_rate": 0,
                "otel_enabled": False,
                "reason": f"OTEL extraction raised: {e}",
            }

        # Cost estimation
        token_count, estimated_cost, cost_breakdown = self._estimate_cost(response_text)
        total_ms = int((time.time() - start_time) * 1000)
        self._track_query(products_count=len(products_sent), duration_ms=total_ms, agent_type="Orchestrator")

        # --- Finalize per-layer timing ------------------------------------
        # Sum tool wall-clock from the tool_trace we've been collecting
        # through BeforeToolCall / AfterToolCall hooks. Orchestrator time
        # is the wall-clock from orchestrator_t0 to turn end minus the
        # streaming tail; specialist time is embedded in orchestrator_ms
        # (Strands doesn't expose it cleanly — document in notes).
        tools_ms = sum(t.get("ms", 0) for t in tool_trace)
        turn_total_ms = int((time.perf_counter() - turn_start) * 1000)
        orchestrator_ms = int((time.perf_counter() - orchestrator_t0) * 1000)
        # Stream = time from first-token to turn end. TTFT = first-token
        # relative to turn start.
        if ttft_mark:
            ttft_ms = int((ttft_mark[0] - turn_start) * 1000)
            stream_ms = int((time.perf_counter() - ttft_mark[0]) * 1000)
        else:
            ttft_ms = turn_total_ms
            stream_ms = 0
        timing["orchestrator"] = max(0, orchestrator_ms - tools_ms - stream_ms)
        timing["specialist"] = 0  # Strands hides this — kept for shape parity
        timing["tools"] = tools_ms
        timing["stream"] = stream_ms

        # Record this turn's latency breakdown into the process-local
        # perf log so /api/performance/runtime can serve live p50/p95
        # aggregates to the Atelier Performance tab. Any failure is
        # swallowed — measurement must never break a turn.
        try:
            from services.performance_log import record_turn
            record_turn(
                session_id=session_id,
                layers=timing,
                ttft_ms=ttft_ms,
                total_ms=turn_total_ms,
                tool_trace=tool_trace,
                pattern=pattern,
            )
        except Exception as _exc:
            logger.debug("performance_log.record_turn failed: %s", _exc)

        # Emit timing + db query events BEFORE the complete event so the
        # Atelier runtime and state-management pages pick them up via
        # their useAgentChat localStorage bridge.
        yield {
            "type": "runtime_timing",
            "timing": {
                "layers": {k: round(v, 1) for k, v in timing.items()},
                "ttft_ms": ttft_ms,
                "total_ms": turn_total_ms,
                "timestamp": int(time.time() * 1000),
            },
        }
        yield {
            "type": "db_queries",
            "queries": list(db_queries_for_turn),
        }
        # Reset the ContextVar so a subsequent request on the same Task
        # doesn't inherit this buffer. The token is set above with
        # db_query_log_var.set(...).
        try:
            db_query_log_var.reset(db_token)
        except Exception:
            pass

        # End-of-turn telemetry: total latency, product count, tool waterfall.
        # Compact one-liner so the workshop terminal stays legible without
        # tail -f tricks.
        tool_summary = " → ".join(
            f"{t['tool']}({t['ms']}ms,{t['results']})" for t in tool_trace
        ) or "no-tools"
        logger.info(
            f"📤 chat_stream done | {total_ms}ms | products={len(products_sent)} "
            f"| tokens={token_count} | {tool_summary}"
        )

        # AgentCore STM — mirror this turn for session continuity labs.
        if session_id and parsed.get("text"):
            await _append_boutique_stm_turn(
                session_id, message, parsed["text"], user=user
            )

        # Complete event with full response payload
        try:
            yield {
                "type": "complete",
                "response": {
                    "response": parsed["text"],
                    "products": products_sent,
                    "suggestions": parsed["suggestions"],
                    "success": True,
                    "context_tracking": True,
                    "orchestrator_enabled": True,
                    "agent_execution": agent_execution,
                    "model": self.model_id,
                    "token_count": token_count,
                    "estimated_cost_usd": estimated_cost,
                    "cost_breakdown": cost_breakdown
                }
            }
        except Exception as e:
            logger.error(f"Failed to serialize complete event: {e}")
            yield {
                "type": "complete",
                "response": {
                    "response": parsed["text"],
                    "products": products_sent,
                    "suggestions": parsed["suggestions"],
                    "success": True
                }
            }


# Alias for backward compatibility
ChatService = EnhancedChatService