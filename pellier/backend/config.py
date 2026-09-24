"""
Configuration management for Pellier Backend

Uses Pydantic Settings for environment variable validation and type safety.
All configuration is loaded from environment variables or .env file.
"""

import os
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Environment variables can be set in .env file or system environment.
    """
    
    # ========================================
    # Database Configuration
    # ========================================
    DB_HOST: str
    # The dev launcher preserves the remote host when opening an SSM tunnel.
    # Keep the remote hostname for TLS verification while routing through loopback.
    DB_TUNNEL_REMOTE_HOST: Optional[str] = None
    DB_SSLROOTCERT: Optional[str] = None
    DB_PORT: int = 5432
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    
    # Optional: Full database URL (constructed if not provided)
    DATABASE_URL: Optional[str] = None
    
    # Optional: AWS Secrets Manager ARN for database credentials
    DB_SECRET_ARN: Optional[str] = None
    
    # Optional: Aurora cluster ARN for RDS Data API
    DB_CLUSTER_ARN: Optional[str] = None
    
    # ========================================
    # AWS Configuration
    # ========================================
    AWS_REGION: str = "us-east-1"
    AWS_DEFAULT_REGION: Optional[str] = None
    
    # ========================================
    # Bedrock Model Configuration
    # ========================================
    # Embedding model for semantic search.
    # Cohere Embed v4, enabled in AWS Workshop Studio. The us.* cross-region
    # inference profile is a deliberate configuration choice — profiles route
    # requests across US regions for throughput headroom. The bare model ID
    # also serves on-demand invoke_model (live-verified 2026-08-23,
    # us-east-1). We request output_dimension=1024 (services/embeddings.py)
    # so vectors match the pellier.product_catalog vector(1024) column and
    # the committed embeddings cache — no schema change.
    BEDROCK_EMBEDDING_MODEL: str = "us.cohere.embed-v4:0"

    # Rerank model for hybrid search (Cohere Rerank v3.5), configured as a
    # bare model ID. This branch invokes it through the Bedrock Agent Runtime
    # `rerank` API (services/rerank.py) and derives the model ARN from this
    # ID; `main` invokes the same model through `invoke_model`. Both are
    # valid — see the divergence note in services/rerank.py.
    BEDROCK_RERANK_MODEL: str = "cohere.rerank-v3-5:0"

    # --- Agent model config ---
    #
    # Per-agent model selection is an architectural decision, not a knob.
    # See the Workshop Studio repo's content/90-appendix/index.en.md
    # (the model table) for the rationale:
    #
    #   Claude Opus 5   — editorial specialists (Search Agent, Personalization Agent,
    #                  Customer Service Agent). Needs voice + personality.
    #   Claude Sonnet 5 — routing, structured extraction, and reporting
    #                  specialists (Pricing Agent, Inventory Agent).
    #   Claude Haiku 4.5  — the explicit fast-response mode. It never replaces
    #                  the router; it composes the responding specialist only.
    #
    # Model IDs follow Bedrock cross-region inference profile naming.
    # Editorial agents (Search Agent, Personalization Agent, Customer Service Agent) read
    # BEDROCK_OPUS_MODEL. It is intentionally env-OVERRIDABLE: the model-access
    # preflight (scripts/check_model_access.py, run in bootstrap) detects
    # whether Opus 5 is reachable on the account, and if it is NOT, writes
    #   BEDROCK_OPUS_MODEL=global.anthropic.claude-sonnet-5
    # into .env so editorial agents fall back to Sonnet 5 cleanly — no code
    # path change, no per-request retry. BEDROCK_SONNET_MODEL is the canonical
    # fallback target (real Sonnet 5, not an Opus alias).
    #
    # The governed release pins global Opus 5 / Sonnet 5 / Haiku 4.5.
    # Move config, .env.example, preflight, bootstrap and Studio pins together.
    # Recorded Observatory sessions retain their original model provenance;
    # the configured model catalogue and new live sessions use this release.
    BEDROCK_OPUS_MODEL: str = "global.anthropic.claude-opus-5"
    BEDROCK_SONNET_MODEL: str = "global.anthropic.claude-sonnet-5"
    BEDROCK_ROUTER_MODEL: str = "global.anthropic.claude-sonnet-5"
    BEDROCK_REPORTING_MODEL: str = "global.anthropic.claude-sonnet-5"
    BEDROCK_FAST_MODEL: str = "global.anthropic.claude-haiku-4-5-20251001-v1:0"

    # Legacy alias — kept for tests + scripts that still reference it.
    # Prefer the role-specific Opus/Sonnet settings in agent factories.
    BEDROCK_CHAT_MODEL: str = "global.anthropic.claude-opus-5"

    # max_tokens is a safety ceiling, not a target — billing and latency track
    # tokens actually generated, so a higher cap costs nothing unless a reply
    # truly runs that long. Replies stay short because the system prompts ask
    # for 2-4 sentences; these values just guard against a runaway response and
    # must clear the longest expected reply so it never truncates mid-sentence.
    # Editorial: Search, Personalization, Customer Service. Reporting: Inventory, Pricing.
    AGENT_MAX_TOKENS_OPUS: int = 1200
    AGENT_MAX_TOKENS_SONNET: int = 2048      # richer reveals from the reporting pair
    AGENT_MAX_TOKENS_HAIKU: int = 768        # concise, grounded fast-mode replies
    SKILL_ROUTER_MAX_TOKENS_SONNET: int = 640  # five-skill audit JSON
    ROUTER_MAX_TOKENS_SONNET: int = 1200    # tool route plus concise final handoff
    
    # ========================================
    # Application Configuration
    # ========================================
    # API settings
    API_VERSION: str = "1.0.0"
    API_TITLE: str = "Pellier Workshop API"
    API_DESCRIPTION: str = "Semantic Search API powered by Amazon Aurora PostgreSQL and Bedrock"
    # FAIL CLOSED on this branch. `governed` is the flagship lineage here, and a
    # deployment that forgets to set this must not quietly serve governed writes on the
    # in-process rail: that happened, and a shopper executed a return directly with no
    # human review, no Cedar verdict and no tool_audit receipt.
    #
    # `builders` remains the default on the `main` lineage, where the in-process rail is
    # the intended path. Changing it there would be wrong for the same reason it is
    # right here: the default should be whatever the branch actually ships.
    WORKSHOP_FORMAT: str = "governed"
    
    # CORS settings
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True  # Auto-reload in development
    
    # ========================================
    # Database Pool Configuration
    # ========================================
    # Connection pool settings for psycopg
    DB_POOL_MIN_SIZE: int = 5
    DB_POOL_MAX_SIZE: int = 20
    DB_POOL_TIMEOUT: int = 30  # seconds
    DB_CONNECT_TIMEOUT: int = 10  # seconds
    DB_STATEMENT_TIMEOUT_MS: int = 8000
    DB_LOCK_TIMEOUT_MS: int = 1200
    DB_IDLE_IN_TX_TIMEOUT_MS: int = 15000
    DB_WORK_MEM_MB: int = 16
    
    # ========================================
    # Search Configuration
    # ========================================
    # Default number of search results
    DEFAULT_SEARCH_LIMIT: int = 20
    MAX_SEARCH_LIMIT: int = 100
    
    # Vector search parameters
    VECTOR_SIMILARITY_THRESHOLD: float = 0.0  # Minimum similarity score
    VECTOR_EF_SEARCH_DEFAULT: int = 40
    VECTOR_EF_SEARCH_MAX: int = 160
    HYBRID_VECTOR_K: int = 20
    HYBRID_FTS_K: int = 20
    HYBRID_TOP_N: int = 30
    HYBRID_RRF_K: int = 60

    # Typed query planning on the shipped Personalization Agent path.
    #
    # `search_products_hybrid` always builds a `SearchPlan` and always pushes
    # its hard predicates into both retrieval branches before RRF. This
    # flag controls only whether the *model* also proposes constraints via
    # `services.structured_extract` — a second Sonnet call that adds ~1-3 s
    # to every storefront search. Off by default: the Observatory comparison
    # surface runs the extractor unconditionally, which is where the
    # workshop teaches the trade-off. Turning this on does not change any
    # hard-constraint guarantee; it only adds model-inferred constraints
    # on top of the caller's explicit ones.
    SEARCH_PLANNER_EXTRACT_ENABLED: bool = False
    RERANK_MAX_DOCUMENTS: int = 30
    RERANK_CACHE_TTL_SEC: int = 120
    
    # ========================================
    # Performance & Caching
    # ========================================
    # Enable query result caching (future feature)
    ENABLE_CACHE: bool = False
    CACHE_TTL: int = 300  # seconds
    # Valkey / ElastiCache URL (optional — in-memory fallback if not set)
    # Format: redis://host:6379 or redis://:password@host:6379
    VALKEY_URL: Optional[str] = None
    
    # ========================================
    # Logging Configuration
    # ========================================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # ========================================
    # Bedrock Guardrails
    # ========================================
    BEDROCK_GUARDRAIL_ID: Optional[str] = None
    BEDROCK_GUARDRAIL_VERSION: str = "DRAFT"

    # ========================================
    # AgentCore Configuration
    # ========================================
    # 4a — Identity (Cognito)
    #
    # Historical name was COGNITO_USER_POOL_ID.
    # The storefront spec standardises on
    # COGNITO_POOL_ID. Both are accepted; `cognito_pool_id_resolved` picks
    # whichever is set so existing .env files keep working.
    COGNITO_USER_POOL_ID: Optional[str] = None
    COGNITO_POOL_ID: Optional[str] = None
    COGNITO_REGION: Optional[str] = None  # defaults to AWS_REGION if unset
    COGNITO_CLIENT_ID: Optional[str] = None
    COGNITO_CLIENT_SECRET: Optional[str] = None
    COGNITO_DOMAIN: Optional[str] = None  # e.g. "pellier.auth.us-east-1.amazoncognito.com"
    COGNITO_TEST_CREDENTIALS_SECRET_ARN: Optional[str] = None

    # Storefront origin + OAuth callback (Req 3.1.1, 3.1.2, 7.2.3)
    APP_BASE_URL: Optional[str] = None  # e.g. "http://localhost:5173"
    APP_BASE_PATH: str = ""  # e.g. "/ports/8000" behind Workshop Studio
    OAUTH_REDIRECT_URI: Optional[str] = None  # e.g. "http://localhost:8000/api/auth/callback"

    # 4b — Memory
    AGENTCORE_MEMORY_ID: Optional[str] = None

    # 4c — Gateway (MCP)
    AGENTCORE_GATEWAY_URL: Optional[str] = None
    AGENTCORE_GATEWAY_ARN: Optional[str] = None
    AGENTCORE_GATEWAY_API_KEY: str = "workshop"

    # 4c.5 — Managed Policy (Cedar)
    AGENTCORE_POLICY_ENGINE_ID: Optional[str] = None

    # 4d — Observability
    CLOUDWATCH_LOG_GROUP: str = "/pellier/agents"
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None

    # Collectorless span export to the CloudWatch X-Ray OTLP endpoint.
    #
    # Distinct from OTEL_EXPORTER_OTLP_ENDPOINT above, which drives Strands'
    # unsigned OTLP exporter and therefore cannot reach X-Ray: that endpoint
    # authenticates with SigV4 only, so an unsigned POST is rejected. This
    # flag attaches a SigV4-signing exporter instead.
    #
    # On by default because a governed turn without exported spans has no
    # execution evidence outside the process, which is the whole point of
    # the observability spine. It degrades to an explicit "unavailable"
    # state (never a startup failure) when credentials, permissions, or
    # Transaction Search are missing.
    OTEL_CLOUDWATCH_TRACES_ENABLED: bool = True

    # Endpoint override. Left unset the region default is used:
    #   https://xray.<AWS_REGION>.amazonaws.com/v1/traces
    OTEL_CLOUDWATCH_TRACES_ENDPOINT: Optional[str] = None

    # Keep model prompts, completions, and tool results off exported spans.
    #
    # Strands records all of them as span content by default. A turn is
    # reconstructable from turn_id, identity, policy verdict, and execution
    # outcome, so the content is payload in broadly readable telemetry
    # rather than in the access-controlled ledger.
    #
    # Set false to export full content — useful when debugging what a
    # specialist actually saw, and not a posture for real shopper data.
    OTEL_REDACT_MODEL_CONTENT: bool = True

    # 4e — Runtime
    AGENTCORE_RUNTIME_ENDPOINT: Optional[str] = None
    AGENTCORE_OPERATOR_RUNTIME_ENDPOINT: Optional[str] = None

    # Runtime feature flag. When False (default) the `/api/agent/chat`
    # endpoint runs the in-process Strands orchestrator.
    # When True it forwards every request through
    # `services.agentcore_runtime.run_agent_on_runtime` so participants
    # can migrate from local execution to managed runtime by flipping
    # this single env var in `backend/.env`.
    USE_AGENTCORE_RUNTIME: bool = False

    # 4f — Evals (AgentCore batch evaluation)
    #
    # Off by default — golden-set regression in `tests/test_golden_journeys.py`
    # is the day-1 CI gate. Flip this to `true` (and name the CloudWatch log
    # groups the Runtime writes sessions to) to opt into the prod-cutover
    # graduation path: a real `StartBatchEvaluation` call against AgentCore
    # Evaluations.
    #
    # AgentCore batch evaluation scores observed agent sessions read from
    # CloudWatch Logs — the real API has no dataset ARN and no job role
    # parameter. Both list settings below are comma-separated.
    AGENTCORE_EVALS_ENABLED: bool = False

    # Operator Concierge composer. OFF by default, and it must stay off in the
    # shipped workshop configuration until Phase 4 read orchestration exists.
    #
    # When True the composer submits a real turn: the request is durably persisted
    # and rendered as an honest `incomplete` turn. Nothing is fabricated — no
    # assistant reply, no investigation rows, no Aurora/Bedrock attribution. When
    # False the composer renders read-only, because a submit box that visibly
    # accepts a question and can never answer it is worse than no box.
    #
    # This flag gates ONLY whether an unanswered development turn may be submitted.
    # It does not touch capability truth, session authorization, AgentCore state,
    # review behaviour, or business capabilities.
    OPERATOR_CONCIERGE_COMPOSER_ENABLED: bool = False
    AGENTCORE_EVALS_LOG_GROUPS: Optional[str] = None
    AGENTCORE_EVALS_SERVICE_NAMES: Optional[str] = None
    AGENTCORE_EVALS_EVALUATOR_IDS: Optional[str] = None

    # ========================================
    # Development & Debugging
    # ========================================
    DEBUG: bool = False
    DEVELOPMENT_MODE: bool = True

    # Show SQL queries in logs
    SHOW_SQL: bool = False
    
    # Model configuration
    #
    # ``env_file`` is disabled when PELLIER_DISABLE_DOTENV is set, which the
    # test suite does in tests/conftest.py. Without it the suite is not
    # hermetic: pydantic-settings resolves the relative ".env" against the
    # CWD, so running pytest from this directory loads a developer's real
    # pellier/backend/.env. Tests that assert a variable is *absent* then
    # read the developer's live value instead (monkeypatch.delenv removes
    # the env var, but .env still supplies it), so they pass in CI and fail
    # on any box that has been through bootstrap.
    model_config = SettingsConfigDict(
        env_file=None if os.getenv("PELLIER_DISABLE_DOTENV") else ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",  # Allow extra environment variables
    )
    
    # ========================================
    # Computed Properties
    # ========================================
    
    @property
    def database_url(self) -> str:
        """
        Construct PostgreSQL connection URL.
        
        Returns:
            str: Full database connection URL
        """
        from pathlib import Path
        from urllib.parse import quote_plus, urlencode

        if self.DB_TUNNEL_REMOTE_HOST:
            if self.DB_HOST not in ("127.0.0.1", "::1", "localhost"):
                raise ValueError("An SSM database tunnel must use a loopback DB_HOST")
            certificate = Path(self.DB_SSLROOTCERT).expanduser() if self.DB_SSLROOTCERT else (
                Path.home() / ".cache" / "pellier" / "rds-global-bundle.pem"
            )
            if not certificate.is_file():
                raise ValueError("The RDS CA bundle is missing. Start the app with the local Pellier launcher.")
            query = urlencode({
                "hostaddr": "127.0.0.1" if self.DB_HOST == "localhost" else self.DB_HOST,
                "sslmode": "verify-full",
                "sslrootcert": str(certificate),
                "ssl_min_protocol_version": "TLSv1.2",
                "application_name": "pellier-local-secure",
            })
            # host supplies the certificate identity; hostaddr supplies the local
            # socket destination. A DATABASE_URL override cannot bypass this rail.
            return (
                f"postgresql://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
                f"@{self.DB_TUNNEL_REMOTE_HOST}:{self.DB_PORT}/{self.DB_NAME}?{query}"
            )
        if self.DATABASE_URL:
            return self.DATABASE_URL

        return (
            f"postgresql://{self.DB_USER}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
    
    @property
    def aws_region_resolved(self) -> str:
        """
        Get AWS region. Prefer AWS_DEFAULT_REGION when set so the repo's
        local .env can override an ambient shell AWS_REGION from another
        tool/session.
        
        Returns:
            str: AWS region name
        """
        return self.AWS_DEFAULT_REGION or self.AWS_REGION or "us-east-1"

    @property
    def cognito_pool_id_resolved(self) -> Optional[str]:
        """Return the Cognito User Pool id regardless of env var name used.

        The storefront spec standardises on ``COGNITO_POOL_ID`` while older
        demo code used ``COGNITO_USER_POOL_ID``. Prefer the new name when
        both are set.
        """
        return self.COGNITO_POOL_ID or self.COGNITO_USER_POOL_ID

    @property
    def cognito_region_resolved(self) -> str:
        """Return the region the Cognito User Pool lives in.

        Defaults to the application AWS region when ``COGNITO_REGION`` is
        unset — Cognito pools are regional and the workshop provisions the
        pool in the same region as the rest of the stack.
        """
        return self.COGNITO_REGION or self.aws_region_resolved
    
    @property
    def is_production(self) -> bool:
        """
        Check if running in production mode.
        
        Returns:
            bool: True if production mode
        """
        return not self.DEVELOPMENT_MODE and not self.DEBUG
    
    @property
    def cors_origins_list(self) -> list[str]:
        """
        Get CORS origins as list.
        
        Returns:
            list[str]: List of allowed CORS origins
        """
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return self.CORS_ORIGINS


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses LRU cache to ensure settings are loaded only once.
    This is the recommended way to access settings throughout the application.
    
    Returns:
        Settings: Application settings instance
        
    Example:
        ```python
        from config import get_settings
        
        settings = get_settings()
        print(settings.DATABASE_URL)
        ```
    """
    return Settings()


# Convenience export
settings = get_settings()


# ========================================
# Configuration Validation
# ========================================

def validate_config() -> None:
    """
    Validate configuration at startup.
    
    Raises:
        ValueError: If configuration is invalid
    """
    settings = get_settings()
    
    # Validate database configuration
    if not settings.DB_HOST:
        raise ValueError("DB_HOST is required")
    
    if not settings.DB_NAME:
        raise ValueError("DB_NAME is required")
    
    if not settings.DB_USER:
        raise ValueError("DB_USER is required")
    
    if not settings.DB_PASSWORD:
        raise ValueError("DB_PASSWORD is required")
    
    # Validate AWS configuration
    if not settings.aws_region_resolved:
        raise ValueError("AWS region is required")
    
    # Validate pool sizes
    if settings.DB_POOL_MIN_SIZE > settings.DB_POOL_MAX_SIZE:
        raise ValueError("DB_POOL_MIN_SIZE cannot exceed DB_POOL_MAX_SIZE")
    
    # Validate search limits
    if settings.DEFAULT_SEARCH_LIMIT > settings.MAX_SEARCH_LIMIT:
        raise ValueError("DEFAULT_SEARCH_LIMIT cannot exceed MAX_SEARCH_LIMIT")
    
    print("✅ Configuration validated successfully")


if __name__ == "__main__":
    # Test configuration loading
    validate_config()
    
    settings = get_settings()
    print("\n" + "="*70)
    print("Pellier Workshop - Configuration Summary")
    print("="*70)
    print(f"Database: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    print(f"AWS Region: {settings.aws_region_resolved}")
    print(f"Embedding Model: {settings.BEDROCK_EMBEDDING_MODEL}")
    print(f"Chat Model: {settings.BEDROCK_CHAT_MODEL}")
    print(f"Fast Response Model: {settings.BEDROCK_FAST_MODEL}")
    print(f"API Version: {settings.API_VERSION}")
    print(f"Debug Mode: {settings.DEBUG}")
    print(f"Development Mode: {settings.DEVELOPMENT_MODE}")
    print("="*70)
