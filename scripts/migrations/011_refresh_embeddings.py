#!/usr/bin/env python3
"""Migration 011: Refresh stale embeddings in pellier.product_catalog.

The 40 product rows in Aurora were embedded BEFORE the brand rename
(old name → Pellier). The descriptions and brand fields have since been
rewritten in place, but the embedding column still encodes the old
sub-brand semantics. Symptom: the Curator faithfully reads
brand="Pellier Editions" from the row but its prose generation pulls
the old brand name from the retrieval-context vibe.

This script re-embeds every row using the CURRENT description, name,
brand, color, and category fields, then UPDATEs the embedding column
in place.

Idempotent: safe to re-run. Each row's embedding is overwritten with
a fresh embedding generated from the row's current text fields.

Usage
-----
    # Run from the project root.
    python3 scripts/migrations/011_refresh_embeddings.py
    python3 scripts/migrations/011_refresh_embeddings.py --dry-run
    python3 scripts/migrations/011_refresh_embeddings.py --limit 5

Environment
-----------
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD  (in the project's .env)
    AWS_REGION  (defaults to us-west-2)
    AWS credentials with bedrock:InvokeModel access.

Cost
----
    40 rows × ~50 tokens each × $0.0001/1K tokens ≈ $0.0002. Effectively free.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import boto3
import psycopg

logger = logging.getLogger("refresh_embeddings")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
EMBED_MODEL = "cohere.embed-english-v4:0"
EMBED_DIM = 1024


def load_env() -> dict:
    """Read .env into os.environ for DB credentials. No external dep."""
    env = {}
    if ENV_FILE.exists():
        with ENV_FILE.open() as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in env.items():
        os.environ.setdefault(k, v)
    return env


def build_doc_text(row: dict) -> str:
    """The text we send to Cohere for embedding. Mirrors the original
    seed_boutique_catalog.py format so distances stay comparable across
    refreshes."""
    parts = [
        row.get("name") or "",
        row.get("brand") or "",
        row.get("color") or "",
        row.get("category") or "",
        row.get("description") or "",
    ]
    tags = row.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    if tags:
        parts.append(" ".join(str(t) for t in tags))
    return " ".join(p for p in parts if p)


def embed_one(client, text: str) -> list[float]:
    """Single Cohere v4 embed call.

    Cohere v4 response shape: {"embeddings": {"float": [[...1024 floats...]]}}.
    Earlier Cohere models returned the flat {"embeddings": [[...]]} shape;
    don't confuse the two.
    """
    body = {
        "texts": [text],
        "input_type": "search_document",
        "embedding_types": ["float"],
        "output_dimension": EMBED_DIM,
    }
    response = client.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(response["body"].read())
    embeddings_data = payload.get("embeddings", {}) or {}
    float_embeddings = embeddings_data.get("float", []) if isinstance(embeddings_data, dict) else embeddings_data
    if not float_embeddings:
        raise RuntimeError(f"empty embeddings in Cohere response: {payload}")
    embedding = float_embeddings[0]
    if len(embedding) != EMBED_DIM:
        raise RuntimeError(f"unexpected embedding length from Cohere: {len(embedding)} (expected {EMBED_DIM})")
    return embedding


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview, no writes.")
    parser.add_argument("--limit", type=int, default=0, help="Process only N rows (debug).")
    args = parser.parse_args()

    load_env()

    region = os.environ.get("AWS_REGION", "us-west-2")
    db_host = os.environ.get("DB_HOST")
    if not db_host:
        logger.error("DB_HOST not set; cannot connect to Aurora")
        return 2

    bedrock = boto3.client("bedrock-runtime", region_name=region)

    conn_str = (
        f"host={db_host} port={os.environ.get('DB_PORT', 5432)} "
        f"dbname={os.environ.get('DB_NAME', 'postgres')} "
        f"user={os.environ.get('DB_USER', 'postgres')} "
        f"password={os.environ['DB_PASSWORD']}"
    )

    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "productId", name, brand, color, category, description, tags
                  FROM pellier.product_catalog
                 ORDER BY "productId"
                """
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        logger.info("Loaded %d rows from pellier.product_catalog", len(rows))
        if args.limit:
            rows = rows[: args.limit]
            logger.info("Limited to %d rows for debug", len(rows))

        updated = 0
        for row in rows:
            doc = build_doc_text(row)
            if args.dry_run:
                logger.info("DRY RUN | productId=%s | text='%s...'", row["productId"], doc[:80])
                continue
            try:
                emb = embed_one(bedrock, doc)
            except Exception as e:
                logger.error("embed failed for productId=%s: %s", row["productId"], e)
                continue
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pellier.product_catalog
                       SET embedding = %s::vector,
                           updated_at = now()
                     WHERE "productId" = %s
                    """,
                    (json.dumps(emb), row["productId"]),
                )
            updated += 1
            if updated % 5 == 0:
                logger.info("  refreshed %d/%d rows", updated, len(rows))
                conn.commit()

        if not args.dry_run:
            conn.commit()
        logger.info("Done. Refreshed %d rows.", updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
