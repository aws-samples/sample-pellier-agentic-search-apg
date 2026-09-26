"""Shared deployment and evidence contract for Pellier's managed memory.

This module has no application settings or AWS clients. Provisioning and the
participant experiment use the same strategy names and namespace boundaries.
"""
from __future__ import annotations

from typing import Any


EVENT_EXPIRY_DAYS = 30
STRATEGIES = {
    "preferences": ("USER_PREFERENCE", "PellierUserPreferences", "userPreferenceMemoryStrategy", "/pellier/preferences/{actorId}/"),
    "facts": ("SEMANTIC", "PellierFacts", "semanticMemoryStrategy", "/pellier/facts/{actorId}/"),
    "summary": ("SUMMARIZATION", "PellierSessionSummary", "summaryMemoryStrategy", "/pellier/summaries/{actorId}/{sessionId}/"),
    "episodic": ("EPISODIC", "PellierEpisodes", "episodicMemoryStrategy", "/pellier/episodes/{actorId}/{sessionId}/"),
}
REFLECTION_NAMESPACE = "/pellier/episodes/{actorId}/"


def namespace(kind: str, actor: str, session: str) -> str:
    return STRATEGIES[kind][3].format(actorId=actor, sessionId=session)


def strategy_configurations() -> list[dict[str, Any]]:
    strategies = [
        {"type": kind, "name": name, "namespaceTemplates": [template]}
        for kind, name, _union, template in STRATEGIES.values()
    ]
    strategies[0]["description"] = "Extract durable shopper preferences"
    strategies[-1]["reflectionNamespaceTemplates"] = [REFLECTION_NAMESPACE]
    return strategies


def configuration_errors(memory: dict[str, Any]) -> list[str]:
    """Check the service's actual configuration, including actor isolation."""
    errors = []
    if memory.get("status") != "ACTIVE":
        errors.append("Memory resource is not ACTIVE")
    if memory.get("eventExpiryDuration") != EVENT_EXPIRY_DAYS:
        errors.append("Conversation event expiry must be 30 days")
    for kind, (strategy_type, name, _union, template) in STRATEGIES.items():
        matches = [s for s in memory.get("strategies", []) if s.get("name") == name]
        if len(matches) != 1:
            errors.append(f"{strategy_type}: expected one {name} strategy")
            continue
        strategy = matches[0]
        if strategy.get("type") != strategy_type or strategy.get("status") != "ACTIVE" or not strategy.get("strategyId"):
            errors.append(f"{strategy_type}: strategy type, ACTIVE state and ID must match")
        if (strategy.get("namespaceTemplates") or strategy.get("namespaces")) != [template]:
            errors.append(f"{strategy_type}: namespace must be {template}")
        if kind == "episodic":
            reflection = strategy.get("configuration", {}).get("reflection", {}).get("episodicReflectionConfiguration", {})
            if (reflection.get("namespaceTemplates") or reflection.get("namespaces")) != [REFLECTION_NAMESPACE]:
                errors.append("EPISODIC: reflections must remain in the actor namespace")
    return errors


def record_matches(record: dict[str, Any], strategy_id: str, path: str) -> bool:
    """Accept only identified, nonempty records in the exact requested scope."""
    return bool(
        isinstance(record.get("memoryRecordId"), str) and record["memoryRecordId"]
        and record.get("memoryStrategyId") == strategy_id
        and path in record.get("namespaces", [])
        and isinstance(record.get("content", {}).get("text"), str)
        and record["content"]["text"].strip()
    )
