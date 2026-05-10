#!/usr/bin/env python3
"""seed_tool_registry.py — Populate the ``tools`` table for /workshop card 7.

Loads the 9 canonical tool names from
``pellier/backend/services/agentcore_gateway.py:GATEWAY_TOOL_NAMES``,
pulls each tool's docstring as the description (single source of truth —
the Gateway uses the same docstring for its MCP ``description`` field),
embeds the description via Cohere Embed v4, and UPSERTs into the
``tools`` table created in migration 001.

Idempotent: rerunning replaces descriptions + embeddings in place
(``ON CONFLICT (tool_id) DO UPDATE``). Run after ``seed-database.sh``
and migration 001.

Usage:
    PGPASSWORD="$DB_PASSWORD" python scripts/seed_tool_registry.py

Environment (same as ``scripts/generate-embeddings.py``):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD — Aurora connection
    AWS_REGION — defaults to us-west-2

Exit codes:
    0  — all 9 tools seeded (or already in place with no drift)
    1  — config/DB failure before seeding started
    2  — partial seed (some rows failed — tools table may be inconsistent)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Allow ``from services.agentcore_gateway import GATEWAY_TOOL_NAMES`` to
# resolve when this script is run from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SRC = REPO_ROOT / "pellier" / "backend"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

import boto3  # noqa: E402
import psycopg  # noqa: E402
from pgvector.psycopg import register_vector  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
logger = logging.getLogger("seed_tool_registry")


COHERE_MODEL_ID = "us.cohere.embed-v4:0"
EMBEDDING_DIMENSION = 1024


# Tools that require approval before execution. Mirrors the approvals
# workflow the workshop surfaces via the Cedar policy hook. Kept narrow
# and deliberate — ``restock_shelf`` writes inventory state; the other
# 9 are read-only.
SENSITIVE_TOOLS = {"restock_shelf"}

# Which "specialist" owns each tool. Names match the five
# boutique-branded specialists (Style Advisor, Curator, Value Analyst,
# Stock Keeper, Experience Guide). Used by Card 7 to show provenance
# per tool row in the Atelier.
TOOL_OWNER: Dict[str, str] = {
    # Style Advisor — editorial search + discovery
    "find_pieces":       "style_advisor",
    "explore_collection": "style_advisor",
    "side_by_side":      "style_advisor",
    "style_match":       "style_advisor",
    # Curator — recommendations + trending
    "whats_trending":    "curator",
    # Value Analyst — pricing intelligence
    "price_intelligence": "value_analyst",
    # Stock Keeper — inventory reads + writes
    "floor_check":       "stock_keeper",
    "running_low":       "stock_keeper",
    "restock_shelf":     "stock_keeper",
    # Experience Guide — returns + care
    "returns_and_care":  "experience_guide",
}


def _load_tool_specs() -> List[Dict[str, Any]]:
    """Import the 10 @tool functions and collect (name, description) pairs.

    We import from ``services.agentcore_gateway`` to keep the tool name
    list authoritative — if a tool is added/removed there, rerunning
    this seeder picks it up without code change here.
    """
    from services.agentcore_gateway import GATEWAY_TOOL_NAMES, _unwrap_strands_tool
    import services.agent_tools as agent_tools  # noqa: WPS433

    specs = []
    for tool_name in GATEWAY_TOOL_NAMES:
        strands_tool = getattr(agent_tools, tool_name, None)
        if strands_tool is None:
            raise RuntimeError(
                f"Tool '{tool_name}' listed in GATEWAY_TOOL_NAMES but not "
                f"found in services.agent_tools — seed aborted."
            )
        fn = _unwrap_strands_tool(strands_tool)
        description = (fn.__doc__ or "").strip()
        if not description:
            raise RuntimeError(
                f"Tool '{tool_name}' has no docstring — description is the "
                f"embedding input, so a missing docstring is fatal."
            )
        # Keep only the first paragraph. Docstrings include workshop
        # "SHORT ON TIME?" hints and Args sections; those would bias
        # the embedding toward meta-text rather than tool purpose.
        first_para = description.split("\n\n", 1)[0].strip()
        specs.append(
            {
                "tool_id": tool_name,  # stable, matches Gateway tool name
                "name": tool_name,
                "description": first_para,
                "owner_agent": TOOL_OWNER.get(tool_name, "unknown"),
                "requires_approval": tool_name in SENSITIVE_TOOLS,
            }
        )
    return specs


def _embed(bedrock: Any, text: str) -> List[float]:
    """Cohere Embed v4 via Bedrock — single-text, search_document input type.

    search_document (not search_query) because this is the *indexed*
    side — the agent's runtime query embedding is the search_query side.
    Cohere's asymmetric retrieval doc calls for this split.
    """
    payload = json.dumps(
        {
            "texts": [text],
            "input_type": "search_document",
            "embedding_types": ["float"],
            "output_dimension": EMBEDDING_DIMENSION,
        }
    )
    resp = bedrock.invoke_model(
        modelId=COHERE_MODEL_ID,
        body=payload,
        accept="*/*",
        contentType="application/json",
    )
    body = json.loads(resp["body"].read())
    vectors = body.get("embeddings", {}).get("float", [])
    if not vectors or len(vectors[0]) != EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Cohere returned unexpected shape for tool embedding: "
            f"{len(vectors)} vectors, "
            f"first dim={len(vectors[0]) if vectors else 0}"
        )
    return vectors[0]


UPSERT_SQL = """
    INSERT INTO tools (
        tool_id, name, description, description_emb,
        enabled, owner_agent, requires_approval
    )
    VALUES (%s, %s, %s, %s, true, %s, %s)
    ON CONFLICT (tool_id) DO UPDATE SET
        name              = EXCLUDED.name,
        description       = EXCLUDED.description,
        description_emb   = EXCLUDED.description_emb,
        enabled           = EXCLUDED.enabled,
        owner_agent       = EXCLUDED.owner_agent,
        requires_approval = EXCLUDED.requires_approval
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the tool specs + would-be embeddings (without Bedrock "
        "call) and exit without touching the database.",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION", "us-west-2"),
        help="AWS region for Bedrock (default: $AWS_REGION or us-west-2)",
    )
    args = parser.parse_args()

    try:
        specs = _load_tool_specs()
    except Exception as exc:
        logger.error("Failed to load tool specs: %s", exc)
        return 1

    logger.info("Loaded %d tool specs from agent_tools", len(specs))
    for s in specs:
        logger.info(
            "  %-28s owner=%-9s approval=%s",
            s["tool_id"],
            s["owner_agent"],
            s["requires_approval"],
        )

    if args.dry_run:
        for s in specs:
            logger.info("--- %s ---", s["tool_id"])
            logger.info("%s", s["description"])
        return 0

    conn_params = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "postgres"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }
    logger.info(
        "Connecting to %s:%s/%s as %s",
        conn_params["host"],
        conn_params["port"],
        conn_params["dbname"],
        conn_params["user"],
    )

    try:
        bedrock = boto3.client("bedrock-runtime", region_name=args.region)
    except Exception as exc:
        logger.error("Bedrock client init failed: %s", exc)
        return 1

    successes = 0
    failures = 0
    try:
        with psycopg.connect(**conn_params, autocommit=False) as conn:
            register_vector(conn)
            with conn.cursor() as cur:
                for s in specs:
                    try:
                        emb = _embed(bedrock, s["description"])
                        cur.execute(
                            UPSERT_SQL,
                            (
                                s["tool_id"],
                                s["name"],
                                s["description"],
                                emb,
                                s["owner_agent"],
                                s["requires_approval"],
                            ),
                        )
                        successes += 1
                        logger.info("✓ upsert %s", s["tool_id"])
                    except Exception as exc:
                        failures += 1
                        logger.error("✗ upsert %s: %s", s["tool_id"], exc)
            conn.commit()
    except Exception as exc:
        logger.error("DB connection or transaction failed: %s", exc)
        return 1

    logger.info(
        "Done. %d succeeded, %d failed (total %d).",
        successes,
        failures,
        len(specs),
    )
    if failures > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
