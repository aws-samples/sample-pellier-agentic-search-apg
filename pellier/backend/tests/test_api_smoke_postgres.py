"""The real FastAPI app answers storefront reads against a freshly set-up PostgreSQL.

Unit tests on fakes passed while `GET /api/products` returned HTTP 500 on a real
database: the catalog held department names the storefront response model rejected.
This test runs the whole app, startup included, against the `fresh_db` cluster.

The app runs in a child interpreter. `config.py` builds `Settings` at import time and
many modules bind `settings` and the database service when imported, so pointing an
already-imported app at this cluster would mean reloading most of the backend, and
the reloaded modules would keep the cluster's settings for every later test. A child
process imports everything with the cluster's settings and exits, so nothing leaks.

Bedrock is the one boundary replaced: the child swaps the embedding service for a
fixed vector after startup, and it runs with no AWS credentials, so a stray call to
AWS fails instead of spending money.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from services.structured_extract import KNOWN_CATEGORIES
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

BACKEND = Path(__file__).resolve().parents[1]
PERSONAS = ("fresh", "marco", "anna", "theo")
RESULT_PREFIX = "SMOKE_RESULT "

_DRIVER = r"""
import json
import sys

from fastapi.testclient import TestClient

import app as backend


class OfflineEmbeddings:
    def generate_embedding(self, text, *args, **kwargs):
        return [1.0] + [0.0] * 1023

    def embed_query(self, query):
        return self.generate_embedding(query)


def summarize(response):
    body = response.json() if response.status_code == 200 else None
    if isinstance(body, dict) and "products" in body:
        body = body["products"]
    rows = body if isinstance(body, list) else [body] if isinstance(body, dict) else []
    return {
        "status": response.status_code,
        "count": len(body) if isinstance(body, list) else None,
        "categories": sorted({row["category"] for row in rows if "category" in row}),
        "detail": "" if response.status_code == 200 else response.text[:400],
    }


results = {}
with TestClient(backend.app, raise_server_exceptions=False) as client:
    backend.embedding_service = OfflineEmbeddings()
    for persona in json.loads(sys.argv[1]):
        response = client.get("/api/products", params={"persona": persona})
        results[f"products?persona={persona}"] = summarize(response)
    results["products/2"] = summarize(client.get("/api/products/2"))
    results["health"] = summarize(client.get("/api/health"))
    results["search"] = summarize(
        client.post("/api/search", json={"query": "linen shirt", "limit": 5}))
print("SMOKE_RESULT " + json.dumps(results))
"""


def _child_env(cluster) -> dict[str, str]:
    env = {key: value for key, value in cluster.env().items()
           if not key.startswith(("AWS_", "PG"))}
    env.update({
        "DATABASE_URL": f"postgresql://postgres@/postgres?host={cluster.socket}&port=5432",
        "PELLIER_DISABLE_DOTENV": "1",
        "OTEL_CLOUDWATCH_TRACES_ENABLED": "false",
        "AWS_REGION": "us-east-1",
        "AWS_CONFIG_FILE": os.devnull,
        "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
        "AWS_EC2_METADATA_DISABLED": "true",
    })
    return env


def _run_app(cluster) -> tuple[dict[str, dict], str]:
    done = subprocess.run(
        [sys.executable, "-c", _DRIVER, json.dumps(PERSONAS)],
        cwd=BACKEND, env=_child_env(cluster), capture_output=True, text=True, timeout=300,
    )
    lines = [line for line in done.stdout.splitlines() if line.startswith(RESULT_PREFIX)]
    assert done.returncode == 0 and lines, (
        f"app smoke run failed ({done.returncode}):\n{done.stdout[-3000:]}\n{done.stderr[-6000:]}")
    return json.loads(lines[-1][len(RESULT_PREFIX):]), done.stderr


def _failures(results: dict[str, dict]) -> dict[str, dict]:
    """Every route that did not answer 200, returned no listing, or showed a non-department."""
    failures = {}
    for route, result in results.items():
        empty_listing = route.startswith("products?") and not result["count"]
        foreign = set(result["categories"]) - set(KNOWN_CATEGORIES)
        if result["status"] != 200 or empty_listing or foreign:
            failures[route] = result
    return failures


def test_storefront_reads_succeed_on_a_fresh_database(fresh_db):
    results, server_log = _run_app(fresh_db)
    failures = _failures(results)
    assert failures == {}, f"{json.dumps(failures, indent=2)}\nserver log:\n{server_log[-4000:]}"
    shown = {category for result in results.values() for category in result["categories"]}
    assert len(shown) > 1, results
