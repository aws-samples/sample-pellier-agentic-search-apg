"""
Configuration management for Blaize Bazaar Backend

Uses Pydantic Settings for environment variable validation and type safety.
All configuration is loaded from environment variables or .env file.
"""

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
    AWS_REGION: str = "us-west-2"
    AWS_DEFAULT_REGION: Optional[str] = None
    
    # ========================================
    # Bedrock Model Configuration
    # ========================================
    # Embedding model for semantic search (Cohere Embed v4)
    BEDROCK_EMBEDDING_MODEL: str = "us.cohere.embed-v4:0"

    # Rerank model for hybrid search (Cohere Rerank v3.5)
    BEDROCK_RERANK_MODEL: str = "cohere.rerank-v3-5:0"

    # --- Agent model config ---
    #
    # Per-agent model selection is an architectural decision, not a knob.
    # Read `lab-content/shared/model-mix-sidebar.en.md` for the reasoning:
    #
    #   Sonnet 4.6  — editorial specialists (Style Advisor, Curator,
    #                 Experience Guide). Needs voice + personality.
    #   Haiku 4.5   — reporting specialists (Value Analyst, Stock Keeper)
    #                 and routing (Orchestrator, SkillRouter). Needs
    #                 speed + determinism.
    #   Opus 4.7    — stretch-lab model. Workshop participants can
    #                 temporarily swap Style Advisor to Opus in the
    #                 Module 3 optional exercise to compare quality /
    #                 cost / latency tradeoffs.
    #
    # Model IDs follow Bedrock's cross-region inference profile naming.
    # Sonnet + Opus use bare alias IDs (no date stamp); Haiku 4.5 still
    # uses the date-stamped form because it's how the profile is exposed.
    BEDROCK_SONNET_MODEL: str = "global.anthropic.claude-sonnet-4-6"
    BEDROCK_HAIKU_MODEL: str = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    BEDROCK_OPUS_MODEL: str = "global.anthropic.claude-opus-4-7"

    # Legacy alias — kept for tests + scripts that still reference it.
    # New code should use BEDROCK_SONNET_MODEL / BEDROCK_HAIKU_MODEL /
    # BEDROCK_OPUS_MODEL directly so the per-agent choice is readable.
    BEDROCK_CHAT_MODEL: str = "global.anthropic.claude-opus-4-7"
    
    # ========================================
    # Application Configuration
    # ========================================
    # API settings
    API_VERSION: str = "1.0.0"
    API_TITLE: str = "Blaize Bazaar Workshop API"
    API_DESCRIPTION: str = "Semantic Search API powered by Amazon Aurora PostgreSQL and Bedrock"
    
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
    
    # ========================================
    # Search Configuration
    # ========================================
    # Default number of search results
    DEFAULT_SEARCH_LIMIT: int = 20
    MAX_SEARCH_LIMIT: int = 100
    
    # Vector search parameters
    VECTOR_SIMILARITY_THRESHOLD: float = 0.0  # Minimum similarity score
    
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
    # Bedrock Guardrails (Lab 3)
    # ========================================
    BEDROCK_GUARDRAIL_ID: Optional[str] = None
    BEDROCK_GUARDRAIL_VERSION: str = "DRAFT"

    # ========================================
    # AgentCore Configuration (Lab 4)
    # ========================================
    # 4a — Identity (Cognito)
    #
    # Historical name was COGNITO_USER_POOL_ID (Lab 4 "wire it live" demo).
    # The storefront spec (Req 4.1, 4.2, Challenge 9.1) standardises on
    # COGNITO_POOL_ID. Both are accepted; `cognito_pool_id_resolved` picks
    # whichever is set so existing .env files keep working.
    COGNITO_USER_POOL_ID: Optional[str] = None
    COGNITO_POOL_ID: Optional[str] = None
    COGNITO_REGION: Optional[str] = None  # defaults to AWS_REGION if unset
    COGNITO_CLIENT_ID: Optional[str] = None
    COGNITO_CLIENT_SECRET: Optional[str] = None
    COGNITO_DOMAIN: Optional[str] = None  # e.g. "blaize-bazaar.auth.us-west-2.amazoncognito.com"

    # Storefront origin + OAuth callback (Req 3.1.1, 3.1.2, 7.2.3)
    APP_BASE_URL: Optional[str] = None  # e.g. "http://localhost:5173"
    OAUTH_REDIRECT_URI: Optional[str] = None  # e.g. "http://localhost:8000/api/auth/callback"

    # 4b — Memory
    AGENTCORE_MEMORY_ID: Optional[str] = None

    # 4c — Gateway (MCP)
    AGENTCORE_GATEWAY_URL: Optional[str] = None
    AGENTCORE_GATEWAY_API_KEY: str = "workshop"

    # 4d — Observability
    CLOUDWATCH_LOG_GROUP: str = "/blaize-bazaar/agents"
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None

    # 4e — Runtime
    AGENTCORE_RUNTIME_ENDPOINT: Optional[str] = None

    # Challenge 5 feature flag. When False (default) the `/api/agent/chat`
    # endpoint runs the in-process Strands orchestrator from Challenge 4.
    # When True it forwards every request through
    # `services.agentcore_runtime.run_agent_on_runtime` so participants
    # can migrate from local execution to managed runtime by flipping
    # this single env var in `backend/.env`.
    USE_AGENTCORE_RUNTIME: bool = False

    # ========================================
    # Development & Debugging
    # ========================================
    DEBUG: bool = False
    DEVELOPMENT_MODE: bool = True

    # Show SQL queries in logs
    SHOW_SQL: bool = False
    
    # Model configuration
    model_config = SettingsConfigDict(
        env_file=".env",
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
        if self.DATABASE_URL:
            return self.DATABASE_URL
        
        from urllib.parse import quote_plus
        return (
            f"postgresql://{self.DB_USER}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
    
    @property
    def aws_region_resolved(self) -> str:
        """
        Get AWS region, preferring AWS_REGION over AWS_DEFAULT_REGION.
        
        Returns:
            str: AWS region name
        """
        return self.AWS_REGION or self.AWS_DEFAULT_REGION or "us-west-2"

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
    if not settings.AWS_REGION:
        raise ValueError("AWS_REGION is required")
    
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
    print("Blaize Bazaar Workshop - Configuration Summary")
    print("="*70)
    print(f"Database: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    print(f"AWS Region: {settings.aws_region_resolved}")
    print(f"Embedding Model: {settings.BEDROCK_EMBEDDING_MODEL}")
    print(f"Chat Model: {settings.BEDROCK_CHAT_MODEL}")
    print(f"API Version: {settings.API_VERSION}")
    print(f"Debug Mode: {settings.DEBUG}")
    print(f"Development Mode: {settings.DEVELOPMENT_MODE}")
    print("="*70)