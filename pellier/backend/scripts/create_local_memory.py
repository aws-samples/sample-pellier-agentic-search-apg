"""Create (or reuse) an AgentCore Memory resource for local development.

STM only — no LTM strategies. Idempotent: re-running reuses the
existing resource if one named "pellier-local" already exists.

Writes AGENTCORE_MEMORY_ID=<id> to .env (appends if not present,
updates if present).

Usage:
    .venv/bin/python scripts/create_local_memory.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

MEMORY_NAME = "pellier_local"
REGION = "us-east-1"
ENV_FILE = _BACKEND_ROOT / ".env"


def main() -> int:
    from bedrock_agentcore.memory import MemoryControlPlaneClient

    cp = MemoryControlPlaneClient(region_name=REGION)

    # Check for existing resource with the same name
    print(f"Listing existing Memory resources in {REGION}...")
    existing = cp.list_memories()
    match = None
    for m in existing:
        name = m.get("name", "")
        mid = m.get("memoryId", "") or m.get("id", "")
        status = m.get("status", "?")
        print(f"  found: {name or mid} [{status}]")
        # Match by name or by id prefix (list response sometimes omits name)
        if name == MEMORY_NAME or mid.startswith(MEMORY_NAME):
            match = m

    if match:
        memory_id = match.get("memoryId") or match.get("id", "")
        print(f"\n✓ Reusing existing Memory: {MEMORY_NAME} → {memory_id}")
    else:
        print(f"\nCreating new Memory: {MEMORY_NAME} (STM only, no LTM strategies)...")
        result = cp.create_memory(
            name=MEMORY_NAME,
            description="Pellier local dev — STM only (conversation history). LTM lives in Aurora pgvector.",
        )
        memory_id = result.get("memoryId") or result.get("memory_id") or result.get("id")
        if not memory_id:
            print(f"✗ create_memory returned unexpected shape: {result}")
            return 1
        print(f"✓ Created Memory: {MEMORY_NAME} → {memory_id}")

    # Write to .env
    _update_env(memory_id)
    print(f"\n✓ .env updated: AGENTCORE_MEMORY_ID={memory_id}")
    print("  Restart the backend to pick up the change.")
    return 0


def _update_env(memory_id: str) -> None:
    """Append or update AGENTCORE_MEMORY_ID in .env."""
    key = "AGENTCORE_MEMORY_ID"
    if ENV_FILE.exists():
        content = ENV_FILE.read_text()
        if re.search(rf"^{key}=", content, re.MULTILINE):
            # Update existing line
            content = re.sub(
                rf"^{key}=.*$",
                f"{key}={memory_id}",
                content,
                flags=re.MULTILINE,
            )
            ENV_FILE.write_text(content)
            return
    # Append
    with open(ENV_FILE, "a") as f:
        f.write(f"\n# AgentCore Memory (STM) — created by scripts/create_local_memory.py\n")
        f.write(f"{key}={memory_id}\n")


if __name__ == "__main__":
    sys.exit(main())
