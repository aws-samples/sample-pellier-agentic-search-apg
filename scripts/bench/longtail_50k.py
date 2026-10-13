#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3", "numpy"]
# ///
"""Measure Pellier's retrieval on a 50,000-product catalog in Aurora, through the RDS Data API.

Pellier's own catalog has 100 products, too few for an index to matter. This loads the
100 hero products with their stored Cohere Embed v4 vectors plus a synthetic long tail of
49,900, builds Pellier's indexes, and measures what the guide's Go deeper quotes: index
build times and sizes, the Lab 1 index check (an exact scan against HNSW with iterative
scan off and in strict order), the same query under more selective filters, and Anna's
hybrid query warm and cold. ``scripts/bench/longtail_50k_results.json`` is the run the
guide quotes.

Catalog
    A directory holding ``catalog.jsonl`` (49,900 tail records, ids 101 to 50000),
    ``embeddings.npy`` (float32, shape (50000, 1024), row i is product ids.txt[i]) and
    ``ids.txt``. The tail was written by Claude Haiku 4.5 and embedded with Cohere Embed v4
    (search_document, 1024 dimensions); it is invented marketing copy, not inventory, and
    it is not stored in this repository. The quoted run used the files whose sha256 the
    results file records.

Cluster
    A throwaway Aurora PostgreSQL cluster with the Data API enabled and an empty database
    named by ``--database``; the quoted run used Aurora PostgreSQL 18.3, Serverless v2 at
    8 ACU (minimum = maximum). Delete the cluster afterwards.

Steps, in order:

    uv run scripts/bench/longtail_50k.py setup load build anna versions lab_check \\
        hybrid_warm --cluster-arn ARN --secret-arn ARN --catalog-dir DIR --out FILE
    uv run scripts/bench/longtail_50k.py cold_restart hybrid_cold --cluster-arn ARN ...

Cold means cold storage: ``cold_restart`` stops and starts the cluster. A
``RebootDBInstance`` is not enough on 18.3: Aurora kept every page in its buffer cache
across the reboot, so the first queries after it read nothing from storage. Run
``hybrid_cold`` straight after ``cold_restart``; its fused query runs third, after the two
branches have read their pages, so only the vector and full-text numbers are cold.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import boto3
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "pellier" / "backend"), str(REPO / "scripts")]

ANNA = ("A housewarming gift for a friend who loves slow mornings. In stock, under $100, "
        "and no candles.")
ANNA_LIMITS = {"price_max_usd": 100, "in_stock_only": True, "exclusions": ["candle"]}
ALBUM = "(SELECT embedding FROM pellier.product_catalog WHERE name = 'Linen Photo Album')"
ALBUM_PK = "(SELECT embedding FROM pellier.product_catalog WHERE \"productId\" = '78')"
LAB_FILTER = "price <= 35 AND NOT tags ? 'candle'"
OFF = ("SET LOCAL enable_seqscan = off", "SET LOCAL hnsw.ef_search = 40",
       "SET LOCAL hnsw.iterative_scan = off")
STRICT = ("SET LOCAL enable_seqscan = off", "SET LOCAL hnsw.ef_search = 40",
          "SET LOCAL hnsw.iterative_scan = strict_order")
STRICT_ONLY = ("SET LOCAL hnsw.iterative_scan = strict_order",)
INDEXES = (
    ("GIN (description_tsv)", "CREATE INDEX product_catalog_description_tsv_gin "
                              "ON pellier.product_catalog USING gin (description_tsv)"),
    ("trigram lower(name)", "CREATE INDEX product_catalog_name_trgm "
                            "ON pellier.product_catalog USING gin (lower(name) gin_trgm_ops)"),
    ("trigram lower(category)", "CREATE INDEX product_catalog_category_trgm "
                                "ON pellier.product_catalog USING gin (lower(category) "
                                "gin_trgm_ops)"),
    ("partial btree", "CREATE INDEX product_catalog_storefront_edit ON pellier.product_catalog "
                      "(persona_id, storefront_rank) WHERE storefront_rank IS NOT NULL"),
    ("HNSW", "CREATE INDEX product_catalog_embedding_hnsw ON pellier.product_catalog "
             "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"),
)
INSERT = """INSERT INTO pellier.product_catalog ("productId", name, brand, color, price,
    description, category, tags, materials, rating, reviews, "imgUrl", badge, tier, quantity,
    embedding, persona_id)
SELECT x.id::text, x.name, x.brand, x.color, x.price, x.description, x.department, x.tags,
       x.materials, x.rating, x.reviews, x.img, x.badge, 1, x.quantity, x.embedding::vector,
       x.persona
  FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(id int, name text, brand text, color text,
       price numeric, description text, department text, tags jsonb, materials jsonb,
       rating numeric, reviews int, quantity int, embedding text, img text, badge text,
       persona text)
ON CONFLICT ("productId") DO NOTHING"""


class Bench:
    """One cluster, one results file; each public method is a step."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.data = boto3.client("rds-data", region_name=args.region)
        self.out = Path(args.out)
        self.res: Dict[str, Any] = json.loads(self.out.read_text()) if self.out.exists() else {}

    # -- plumbing ----------------------------------------------------------------

    def save(self) -> None:
        self.out.write_text(json.dumps(self.res, indent=1) + "\n")

    def sql(self, statement: str, params: Optional[list] = None,
            tx: Optional[str] = None) -> List[Dict[str, Any]]:
        kw: Dict[str, Any] = {"resourceArn": self.args.cluster_arn,
                              "secretArn": self.args.secret_arn, "database": self.args.database,
                              "sql": statement, "includeResultMetadata": True}
        if params:
            kw["parameters"] = params
        if tx:
            kw["transactionId"] = tx
        reply = self.data.execute_statement(**kw)
        cols = [c["name"] for c in reply.get("columnMetadata", [])]
        return [{c: (list(v.values())[0] if v else None) for c, v in zip(cols, rec)}
                for rec in reply.get("records", [])]

    def in_tx(self, statements: Sequence[str]) -> List[List[Dict[str, Any]]]:
        """Run statements in one transaction and roll it back, so every SET LOCAL ends."""
        tx = self.data.begin_transaction(resourceArn=self.args.cluster_arn,
                                         secretArn=self.args.secret_arn,
                                         database=self.args.database)["transactionId"]
        try:
            return [self.sql(s, tx=tx) for s in statements]
        finally:
            self.data.rollback_transaction(resourceArn=self.args.cluster_arn,
                                           secretArn=self.args.secret_arn, transactionId=tx)

    def explain(self, query: str, settings: Sequence[str] = (),
                analyze: bool = True) -> Tuple[Optional[float], str]:
        verb = "EXPLAIN (ANALYZE, BUFFERS)" if analyze else "EXPLAIN (COSTS OFF)"
        plan = self.in_tx([*settings, f"{verb} {query}"])[-1]
        text = "\n".join(row["QUERY PLAN"] for row in plan)
        found = re.search(r"Execution Time: ([\d.]+) ms", text)
        return (float(found.group(1)) if found else None), text

    def median_ms(self, query: str, settings: Sequence[str] = ()) -> float:
        return round(statistics.median(self.explain(query, settings)[0] for _ in range(5)), 2)

    def ids(self, query: str, settings: Sequence[str] = ()) -> List[str]:
        return [row["productId"] for row in self.in_tx([*settings, query])[-1]]

    def count(self, where: str) -> int:
        rows = self.sql(f"SELECT count(*) AS n FROM pellier.product_catalog WHERE {where}")
        return int(rows[0]["n"])

    # -- steps -------------------------------------------------------------------

    def setup(self) -> None:
        """Pellier's catalog table and its iterative-scan default, from 001_schema.sql."""
        schema = (REPO / "scripts" / "migrations" / "001_schema.sql").read_text()
        table = schema[schema.index("CREATE TABLE pellier.product_catalog"):
                       schema.index("CREATE INDEX product_catalog_embedding_hnsw")]
        scan = schema[schema.index("DO $iterative_scan$"):
                      schema.index("$iterative_scan$;") + len("$iterative_scan$;")]
        for statement in ("CREATE EXTENSION IF NOT EXISTS vector",
                          "CREATE EXTENSION IF NOT EXISTS pg_trgm", "CREATE SCHEMA pellier",
                          table.strip().rstrip(";"), scan.rstrip(";"), "CREATE SCHEMA lt",
                          "CREATE TABLE lt.q (name text PRIMARY KEY, emb vector(1024))"):
            self.sql(statement)

    def load(self) -> None:
        """The 100 hero products and the 49,900-row tail, with their vectors."""
        import seed_pellier_catalog as seed

        catalog = Path(self.args.catalog_dir)
        vectors = np.load(catalog / "embeddings.npy")
        row_of = {int(pid): i for i, pid in enumerate((catalog / "ids.txt").read_text().split())}

        def vec(pid: int) -> str:
            return "[" + ",".join("%.9g" % x for x in vectors[row_of[pid]]) + "]"

        rows = [{"id": int(p.productId), "name": p.name, "brand": p.brand, "color": p.color,
                 "price": float(p.price), "description": p.description,
                 "department": p.department, "tags": p.tags, "materials": p.materials,
                 "rating": float(p.rating), "reviews": int(p.reviews),
                 "quantity": int(p.quantity), "embedding": vec(int(p.productId)),
                 "img": p.public_image_path, "badge": p.badge or "", "persona": p.persona}
                for p in seed.load_catalog()]
        for line in (catalog / "catalog.jsonl").read_text().splitlines():
            r = json.loads(line)
            rows.append({**{k: r[k] for k in ("id", "name", "brand", "color", "price",
                                               "description", "department", "tags",
                                               "materials", "rating", "reviews", "quantity")},
                         "embedding": vec(r["id"]), "img": "/products/longtail-placeholder.webp",
                         "badge": None, "persona": None})
        chunks = [rows[i:i + 192] for i in range(0, len(rows), 192)]
        started = time.time()
        with ThreadPoolExecutor(6) as pool:
            list(pool.map(self._put, chunks))
        self.res["load"] = {"rows": self.count("true"), "chunks": len(chunks),
                            "seconds": round(time.time() - started, 1)}
        self.save()

    def _put(self, chunk: List[Dict[str, Any]]) -> None:
        for attempt in range(8):
            try:
                self.sql(INSERT, [{"name": "rows", "value": {"stringValue": json.dumps(chunk)}}])
                return
            except Exception:  # noqa: BLE001 - the Data API throttles; retry, then raise
                if attempt == 7:
                    raise
                time.sleep(min(30, 2 ** attempt))

    def build(self) -> None:
        """Pellier's indexes, timed one by one, then their sizes."""
        builds = {}
        for label, statement in INDEXES:
            tx = self.data.begin_transaction(resourceArn=self.args.cluster_arn,
                                             secretArn=self.args.secret_arn,
                                             database=self.args.database)["transactionId"]
            self.sql("SET LOCAL maintenance_work_mem = '1GB'", tx=tx)
            self.sql("SET LOCAL max_parallel_maintenance_workers = 4", tx=tx)
            started = time.time()
            self.sql(statement, tx=tx)
            builds[label] = round(time.time() - started, 2)
            self.data.commit_transaction(resourceArn=self.args.cluster_arn,
                                         secretArn=self.args.secret_arn, transactionId=tx)
        self.sql("ANALYZE pellier.product_catalog")
        self.res["build_seconds"] = builds
        self.res["index_sizes"] = self.sql(
            "SELECT indexrelid::regclass::text AS idx, "
            "pg_size_pretty(pg_relation_size(indexrelid)) AS size FROM pg_index "
            "WHERE indrelid = 'pellier.product_catalog'::regclass ORDER BY 1")
        self.save()

    def anna(self) -> None:
        """Anna's sentence, embedded once with Cohere Embed v4 as a search query."""
        body = {"texts": [ANNA], "input_type": "search_query", "embedding_types": ["float"],
                "output_dimension": 1024}
        reply = boto3.client("bedrock-runtime", region_name=self.args.region).invoke_model(
            modelId="us.cohere.embed-v4:0", contentType="application/json",
            accept="application/json", body=json.dumps(body))
        vector = json.loads(reply["body"].read())["embeddings"]["float"][0]
        self.sql("INSERT INTO lt.q VALUES ('anna', CAST(:v AS vector)) "
                 "ON CONFLICT (name) DO UPDATE SET emb = EXCLUDED.emb",
                 [{"name": "v", "value": {"stringValue": "[" + ",".join(
                     "%.9g" % x for x in vector) + "]"}}])

    def versions(self) -> None:
        self.res["versions"] = self.sql(
            "SELECT version() AS version, (SELECT extversion FROM pg_extension "
            "WHERE extname = 'vector') AS pgvector, current_setting('shared_buffers') "
            "AS shared_buffers, current_setting('hnsw.iterative_scan', true) AS iterative_scan, "
            "current_setting('hnsw.ef_search', true) AS ef_search")[0]
        self.save()

    def lab_check(self) -> None:
        """The Lab 1 index check at this size, then the same query under narrower filters."""
        out: Dict[str, Any] = {"eligible": self.count(LAB_FILTER),
                               "plan_planner": self.explain(lab_query(LAB_FILTER),
                                                            analyze=False)[1]}
        exact = self.ids(lab_query(LAB_FILTER, exact=True))
        strict = self.ids(lab_query(LAB_FILTER), STRICT)
        out.update(rows_off=len(self.ids(lab_query(LAB_FILTER), OFF)), rows_strict=len(strict),
                   strict_equals_exact=strict == exact)
        for label, ref in (("name lookup", ALBUM), ("pk lookup", ALBUM_PK)):
            out[label] = {"exact_ms": self.median_ms(lab_query(LAB_FILTER, ref, exact=True)),
                          "planner_ms": self.median_ms(lab_query(LAB_FILTER, ref)),
                          "off_ms": self.median_ms(lab_query(LAB_FILTER, ref), OFF),
                          "strict_ms": self.median_ms(lab_query(LAB_FILTER, ref), STRICT)}
        out["variants"] = {price: self._variant(price)
                           for price in ("price <= 35", "price <= 8", "price <= 5")}
        self.res["lab_check"] = out
        self.save()

    def _variant(self, price: str) -> Dict[str, Any]:
        where = f"{price} AND NOT tags ? 'candle'"
        plan = self.explain(lab_query(where, ALBUM_PK), analyze=False)[1]
        exact = self.ids(lab_query(where, ALBUM_PK, exact=True))
        strict = self.ids(lab_query(where, ALBUM_PK), STRICT)
        return {"matching": self.count(where),
                "planner": "HNSW" if "hnsw" in plan else "exact (Sort over Seq Scan)",
                "off_rows": len(self.ids(lab_query(where, ALBUM_PK), OFF)),
                "strict_rows": len(strict), "strict_equals_exact": strict == exact,
                "exact_ms": self.median_ms(lab_query(where, ALBUM_PK, exact=True)),
                "strict_ms": self.median_ms(lab_query(where, ALBUM_PK), STRICT),
                "sql": variant_sql(where)}

    def hybrid_warm(self) -> None:
        queries, words = anna_sql()
        self.res["hybrid_sql"] = queries
        self.res["hybrid_warm_ms"] = {k: [self.explain(q, STRICT_ONLY)[0] for _ in range(3)]
                                      for k, q in queries.items()}
        self.res["fts_matches"] = self.count(
            f"description_tsv @@ to_tsquery('english', '{words}')")
        self.save()

    def cold_restart(self) -> None:
        """Stop and start the cluster, so the next queries read from Aurora storage."""
        rds = boto3.client("rds", region_name=self.args.region)
        cluster = self.args.cluster_arn.split(":")[-1]
        started = time.time()
        rds.stop_db_cluster(DBClusterIdentifier=cluster)
        rds.get_waiter("db_cluster_stopped").wait(DBClusterIdentifier=cluster)
        stopped = time.time()
        rds.start_db_cluster(DBClusterIdentifier=cluster)
        rds.get_waiter("db_cluster_available").wait(DBClusterIdentifier=cluster)
        self.res["cold_restart"] = {"stop_seconds": round(stopped - started),
                                    "start_seconds": round(time.time() - stopped),
                                    "postmaster_started": self.sql(
                                        "SELECT pg_postmaster_start_time()::text AS t")[0]["t"]}
        self.save()

    def hybrid_cold(self) -> None:
        queries, _words = anna_sql()
        cold: Dict[str, Any] = {}
        for key in ("vector", "fts", "fused"):
            ms, text = self.explain(queries[key], STRICT_ONLY)
            planning = re.search(r"Planning Time: ([\d.]+) ms", text)
            cold[key] = {"execution_ms": ms,
                         "planning_ms": float(planning.group(1)) if planning else None,
                         "buffers_first": re.findall(r"Buffers: shared [^\n]*", text)[:2]}
        cold["vector_second_ms"] = self.explain(queries["vector"], STRICT_ONLY)[0]
        self.res["hybrid_cold"] = cold
        self.save()


def lab_query(where: str, ref: str = ALBUM, exact: bool = False) -> str:
    """The Lab 1 index check's query; ``+ 0`` makes the order an expression no index serves."""
    order = f"(embedding <=> {ref}) + 0" if exact else f"embedding <=> {ref}"
    return (f'SELECT "productId" FROM pellier.product_catalog WHERE {where} '
            f'ORDER BY {order} LIMIT 20')


def variant_sql(where: str) -> Dict[str, Dict[str, Any]]:
    """The exact statements one selective-filter row ran, each mode in its own transaction."""
    return {"exact": {"settings": [], "query": lab_query(where, ALBUM_PK, exact=True)},
            "off": {"settings": list(OFF), "query": lab_query(where, ALBUM_PK)},
            "strict": {"settings": list(STRICT), "query": lab_query(where, ALBUM_PK)}}


def anna_sql() -> Tuple[Dict[str, str], str]:
    """Anna's two branches as the finished Lab 1 code builds them, and their fusion in SQL."""
    from services import search_plan, store_tools

    plan = search_plan.build_plan(ANNA, ANNA_LIMITS)
    clauses, params = plan.compile_predicates(include_soft=False)
    values = iter(params)
    predicates = []
    for clause in clauses:
        while "%s" in clause:
            value = next(values)
            text = ("ARRAY[" + ",".join(f"'{x}'" for x in value) + "]"
                    if isinstance(value, list) else str(value))
            clause = clause.replace("%s", text, 1)
        predicates.append(clause)
    words = store_tools.or_tsquery(ANNA)
    path = REPO / "solutions" / "the-quiet-search" / "retrieval" / "store_tools_solution.py"
    spec = importlib.util.spec_from_file_location("store_tools_solution", path)
    finished = importlib.util.module_from_spec(spec)
    sys.modules["store_tools_solution"] = finished
    spec.loader.exec_module(finished)
    vector = (finished.vector_branch_sql(predicates)
              .replace("%s::vector", "(SELECT emb FROM lt.q WHERE name = 'anna')", 1)
              .replace("LIMIT %s", "LIMIT 20"))
    fts = (finished.fts_branch_sql(predicates)
           .replace("to_tsquery('english', %s)", f"to_tsquery('english', '{words}')")
           .replace("LIMIT %s", "LIMIT 20"))
    where = " AND ".join(['"imgUrl" IS NOT NULL', *predicates])
    fused = f"""WITH query_embedding AS (SELECT emb FROM lt.q WHERE name = 'anna'),
t AS (SELECT product_id, row_number() OVER () AS r FROM (SELECT "productId" AS product_id
       FROM pellier.product_catalog WHERE {where}
      ORDER BY embedding <=> (SELECT emb FROM query_embedding) LIMIT 20) v),
f AS (SELECT product_id, row_number() OVER () AS r FROM (SELECT "productId" AS product_id
       FROM pellier.product_catalog, to_tsquery('english', '{words}') q
      WHERE {where} AND description_tsv @@ q ORDER BY ts_rank_cd(description_tsv, q) DESC
      LIMIT 20) w)
SELECT coalesce(t.product_id, f.product_id) AS product_id, p.name,
       coalesce(1.0 / (60 + t.r), 0) + coalesce(1.0 / (60 + f.r), 0) AS rrf_score
  FROM t FULL JOIN f ON f.product_id = t.product_id
  JOIN pellier.product_catalog p ON p."productId" = coalesce(t.product_id, f.product_id)
 ORDER BY rrf_score DESC, coalesce(t.product_id, f.product_id) LIMIT 20"""
    return {"vector": vector, "fts": fts, "fused": fused}, words


STEPS = ("setup", "load", "build", "anna", "versions", "lab_check", "hybrid_warm",
         "cold_restart", "hybrid_cold")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("steps", nargs="+", choices=STEPS)
    parser.add_argument("--cluster-arn", required=True)
    parser.add_argument("--secret-arn", required=True)
    parser.add_argument("--catalog-dir", help="catalog.jsonl, embeddings.npy and ids.txt")
    parser.add_argument("--database", default="pellier")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--out", default="longtail_50k_results.json")
    args = parser.parse_args(argv)
    if "load" in args.steps and not args.catalog_dir:
        parser.error("load needs --catalog-dir")
    bench = Bench(args)
    for step in args.steps:
        started = time.time()
        getattr(bench, step)()
        print(f"{step} done in {time.time() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
