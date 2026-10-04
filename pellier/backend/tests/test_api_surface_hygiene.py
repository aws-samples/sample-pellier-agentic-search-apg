"""Public API contracts must match the supported Pellier workshop surface."""

from __future__ import annotations

RETIRED_DEMO_PATHS = {
    "/api/dev/chaos",
    "/api/storefront/briefing",
    "/api/storefront/pulse",
    "/api/tools/restock",
    "/api/autocomplete",
    "/api/queries/recent",
    "/api/queries/clear",
    "/api/context/stats",
    "/api/context/clear",
    "/api/context/prompts",
    "/api/performance/compare",
    "/api/performance/runtime",
    "/api/performance/quantization",
    "/api/performance/categories",
    "/api/performance/iterative-scan",
    "/api/performance/quantization-benchmark",
    "/api/traces/status",
    "/api/traces/waterfall",
    "/api/traces/info",
    "/api/guardrails/check",
    "/api/guardrails/decisions",
    "/api/agentcore/policy/list",
    "/api/agentcore/memory/ltm",
    "/api/agentcore/policy/decisions",
    "/api/agentcore/memories",
    "/api/agentcore/gateway/tools",
    "/api/agentcore/memories/episodes",
    "/api/agentcore/analytics",
    "/api/observatory/readiness",
    "/api/operator/actions/issue-credit",
    "/api/operator/actions/resolve-return",
}


def _published_paths() -> set[str]:
    """OpenAPI flattens FastAPI's nested included routers into HTTP paths."""
    import app as app_module

    return set(app_module.app.openapi()["paths"])


def test_retired_demo_routes_are_not_shipped() -> None:
    assert _published_paths().isdisjoint(RETIRED_DEMO_PATHS)


def test_supported_status_routes_remain_for_bootstrap_health_checks() -> None:
    assert {
        "/api/storefront/catalog-stats",
        "/api/performance/stats",
        "/api/agentcore/gateway/status",
        "/api/agentcore/memory/status",
        "/api/agentcore/runtime/status",
    } <= _published_paths()
