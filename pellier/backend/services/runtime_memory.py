"""Read preferences in Runtime using only the verified customer's namespace."""
from __future__ import annotations

import json
import os

from services.conversation_context import remembered_preferences


def load_preferences(customer_id: str) -> list[dict[str, str]]:
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if not memory_id or not customer_id:
        return []
    from bedrock_agentcore.memory import MemorySessionManager

    manager = MemorySessionManager(memory_id=memory_id,
                                   region_name=os.environ.get("AWS_REGION", "us-east-1"))
    namespace = f"/pellier/preferences/{customer_id}/"
    records = manager.list_long_term_memory_records(namespace=namespace, max_results=20)
    preferences = []
    for record in records:
        if "namespaces" in record and namespace not in record["namespaces"]:
            continue
        try:
            content = json.loads((record.get("content") or {}).get("text") or "{}")
        except (ValueError, TypeError):
            continue
        if isinstance(content, dict):
            preferences.append({"record_id": record.get("memoryRecordId"),
                                "preference": content.get("preference")})
    return remembered_preferences(preferences)
