#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3", "pandas", "pyarrow", "psycopg[binary]"]
# ///
"""Measure Pellier's hybrid ranking on the Amazon Shopping Queries (ESCI) dataset.

Pellier's own catalog has no relevance judgments, so it cannot say whether fusion or
rerank helps. ESCI can: every judged query-product pair is labelled Exact, Substitute,
Complement or Irrelevant. This script runs Pellier's retrieval arms over an ESCI sample
and reports NDCG@10, Recall@10, Recall@50 and MRR for each arm.

Dataset
    Shopping Queries Dataset (ESCI), https://github.com/amazon-science/esci-data,
    Apache License 2.0. Cite: Reddy et al., "Shopping Queries Dataset: A Large-Scale
    ESCI Benchmark for Improving Product Search", arXiv:2206.06588.
    Version: repository commit 7916cdf6ab75a462e77f20ab40428a10923998d5 (2024-10-07), whose
    Git LFS objects are:
      shopping_queries_dataset_examples.parquet
        sha256 4a735b693b4a424a6fc67f5be6e4c811495c488bbf66d02a602d308b2744263a
      shopping_queries_dataset_products.parquet
        sha256 25124442d064d64b26f74082d6fa09438d679efc0c183cf28d19064a2b65a265
    Download both files yourself; nothing from the dataset is stored in this repository.
    Subset: product_locale = "us" and small_version = 1; 500 queries sampled with seed 42;
    a 50,000-product corpus of every judged product plus other US products drawn at random
    (seed 42).

What is Pellier's and what is not
    Pellier's code: the OR-of-tokens full-text query (services.store_tools.or_tsquery),
    reciprocal rank fusion with k = 60 (services.store_tools.rrf_merge), HNSW with
    iterative scan in strict order and ef_search = 40, Cohere Embed v4 at 1024 dimensions,
    Cohere Rerank 3.5 through the Bedrock Agent Runtime Rerank API, and the shipped depths
    (20 rows per branch, top 30 fused, rerank of the top 15).
    Not Pellier's: there is no search plan, so the raw query reaches both branches with no
    hard limits; ESCI's columns stand in for the catalog's (title and brand weight A, color
    B, bullet points C, description D); the embedding text is title, brand, bullets and
    description; vectors are rounded to four decimals, as in the published run; a "deep"
    setting (100 rows per branch, rerank pools of 15 and 50) measures Recall@50. Unjudged
    products count as gain 0. The engine is whatever PostgreSQL with pgvector the DSN names;
    the published run (2026-10-12) used PostgreSQL 18.6 with pgvector 0.8.6.

Run from the repository root, against a throwaway database with the vector extension,
with Bedrock access to both Cohere models in the region:

    uv run scripts/bench/esci_relevance.py prepare DATA_DIR WORK_DIR
    uv run scripts/bench/esci_relevance.py embed WORK_DIR --region us-east-1
    uv run scripts/bench/esci_relevance.py load WORK_DIR "host=... dbname=esci"
    uv run scripts/bench/esci_relevance.py retrieve WORK_DIR "host=... dbname=esci"
    uv run scripts/bench/esci_relevance.py rerank WORK_DIR --region us-east-1
    uv run scripts/bench/esci_relevance.py score WORK_DIR
    uv run scripts/bench/esci_relevance.py vector-check WORK_DIR "host=... dbname=esci"

Delete WORK_DIR and the database afterwards: they hold dataset text.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import random
import re
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pellier" / "backend"))
from services.store_tools import or_tsquery, rrf_merge  # noqa: E402

SEED = 42
N_QUERIES = 500
N_PRODUCTS = 50_000
EMBED_MODEL = "us.cohere.embed-v4:0"
EMBED_BATCH = 96
RERANK_MODEL = "cohere.rerank-v3-5:0"
RRF_K = 60
GAIN = {"E": 1.0, "S": 0.1, "C": 0.01, "I": 0.0}
BOOTSTRAP_SEED = 7
BOOTSTRAP_SAMPLES = 2000
TAG = re.compile(r"<[^>]+>")
# Paired comparisons, in the order the published run drew its bootstrap samples.
PAIRS = (("deep: vector", "deep: full-text"), ("deep: RRF k=60", "deep: vector"),
         ("deep: RRF k=60", "deep: full-text"), ("deep: RRF + rerank@15", "deep: RRF k=60"),
         ("deep: RRF + rerank@50", "deep: RRF + rerank@15"),
         ("shipped: RRF + rerank@15", "shipped: RRF top 30"),
         ("deep: RRF + rerank@15", "deep: vector"))

SCHEMA = """
DROP TABLE IF EXISTS product_catalog;
CREATE TABLE product_catalog (
    product_id  text PRIMARY KEY,
    name        text,
    brand       text,
    color       text,
    bullets     text,
    description text,
    embedding   vector(1024),
    description_tsv tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(name, '')), 'A')
     || setweight(to_tsvector('english', coalesce(brand, '')), 'A')
     || setweight(to_tsvector('english', coalesce(color, '')), 'B')
     || setweight(to_tsvector('english', coalesce(bullets, '')), 'C')
     || setweight(to_tsvector('english', coalesce(description, '')), 'D')
    ) STORED
);
"""
FTS_SQL = """
WITH q AS (SELECT to_tsquery('english', %s) AS ts_q)
SELECT product_id FROM product_catalog CROSS JOIN q
WHERE description_tsv @@ q.ts_q
ORDER BY ts_rank_cd(description_tsv, q.ts_q) DESC, product_id
LIMIT %s
"""
VECTOR_SQL = """
WITH query_embedding AS (SELECT %s::vector AS emb)
SELECT product_id FROM product_catalog
ORDER BY embedding <=> (SELECT emb FROM query_embedding), product_id
LIMIT %s
"""


def clean(text: object, limit: int) -> str:
    """Strip HTML and collapse whitespace, then cut to ``limit`` characters."""
    if not isinstance(text, str):
        return ""
    return " ".join(html.unescape(TAG.sub(" ", text)).split())[:limit]


def prepare(data_dir: str, work_dir: str) -> None:
    """Sample the queries, their judgments and the 50,000-product corpus."""
    import pandas as pd

    data, work = Path(data_dir), Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    examples = pd.read_parquet(data / "shopping_queries_dataset_examples.parquet",
                               columns=["query_id", "query", "product_id", "product_locale",
                                        "esci_label", "small_version"])
    examples = examples[(examples.product_locale == "us") & (examples.small_version == 1)]
    query_ids = pd.Series(sorted(examples.query_id.unique()))
    sample = query_ids.sample(N_QUERIES, random_state=SEED).tolist()
    picked = examples[examples.query_id.isin(sample)]
    qrels = picked[["query_id", "product_id", "esci_label"]].drop_duplicates()
    queries = picked[["query_id", "query"]].drop_duplicates("query_id")
    products = pd.read_parquet(data / "shopping_queries_dataset_products.parquet")
    products = products[products.product_locale == "us"].drop_duplicates("product_id")
    judged = products[products.product_id.isin(set(qrels.product_id))]
    rest = products[~products.product_id.isin(set(qrels.product_id))]
    corpus = pd.concat([judged, rest.sample(N_PRODUCTS - len(judged), random_state=SEED)])
    corpus = corpus.reset_index(drop=True)
    for column, source, limit in (("title", "product_title", 300), ("brand", "product_brand", 80),
                                  ("color", "product_color", 60),
                                  ("bullets", "product_bullet_point", 600),
                                  ("desc", "product_description", 600)):
        corpus[column] = corpus[source].map(lambda text, cut=limit: clean(text, cut))
    body = (corpus.bullets + " " + corpus.desc).str.strip()
    corpus["embed_text"] = (corpus.title + ". " + corpus.brand + ". " + body).str.slice(0, 900)
    corpus["rerank_text"] = corpus.apply(
        lambda r: f"{r.title} \u2014 {(r.desc or r.bullets)[:237]} ({r.brand})", axis=1)
    keep = ["product_id", "title", "brand", "color", "bullets", "desc", "embed_text",
            "rerank_text"]
    corpus[keep].to_parquet(work / "corpus.parquet")
    queries.to_parquet(work / "queries.parquet")
    qrels.to_parquet(work / "qrels.parquet")
    print(f"{len(query_ids)} eligible queries, {len(queries)} sampled, {len(qrels)} judgments, "
          f"{len(corpus)} products")


def embed_texts(client, texts: List[str], input_type: str) -> List[List[float]]:
    """Embed in batches of 96 with Cohere Embed v4, rounded to four decimals."""
    vectors: List[List[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        body = json.dumps({"texts": texts[start:start + EMBED_BATCH], "input_type": input_type,
                           "embedding_types": ["float"], "output_dimension": 1024})
        response = client.invoke_model(modelId=EMBED_MODEL, body=body,
                                       contentType="application/json", accept="*/*")
        batch = json.loads(response["body"].read())["embeddings"]["float"]
        vectors.extend([round(x * 10000) / 10000 for x in vector] for vector in batch)
    return vectors


def embed(work_dir: str, region: str) -> None:
    """Embed every product as a document and every query as a query."""
    import boto3
    import pandas as pd

    work = Path(work_dir)
    client = boto3.client("bedrock-runtime", region_name=region)
    corpus = pd.read_parquet(work / "corpus.parquet")
    queries = pd.read_parquet(work / "queries.parquet")
    products = embed_texts(client, corpus.embed_text.tolist(), "search_document")
    asked = embed_texts(client, queries["query"].tolist(), "search_query")
    (work / "product_vectors.json").write_text(json.dumps(products))
    (work / "query_vectors.json").write_text(json.dumps(asked))
    print(f"embedded {len(products)} products and {len(asked)} queries")


def vector_text(vector: List[float]) -> str:
    """pgvector's text form at four decimals."""
    return "[" + ",".join(f"{x:.4f}" for x in vector) + "]"


def load(work_dir: str, dsn: str) -> None:
    """Load the corpus, then build the GIN and HNSW indexes Pellier uses."""
    import pandas as pd
    import psycopg

    work = Path(work_dir)
    corpus = pd.read_parquet(work / "corpus.parquet")
    vectors = json.loads((work / "product_vectors.json").read_text())
    if len(vectors) != len(corpus):
        raise SystemExit(f"{len(vectors)} vectors for {len(corpus)} products: rerun embed")
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(SCHEMA)
        with conn.cursor() as cur, cur.copy(
                "COPY product_catalog (product_id, name, brand, color, bullets, description, "
                "embedding) FROM STDIN") as copy:
            for row, vector in zip(corpus.itertuples(index=False), vectors):
                copy.write_row((row.product_id, row.title, row.brand, row.color, row.bullets,
                                row.desc, vector_text(vector)))
        conn.execute("CREATE INDEX ON product_catalog USING gin (description_tsv)")
        conn.execute("CREATE INDEX ON product_catalog USING hnsw (embedding vector_cosine_ops) "
                     "WITH (m = 16, ef_construction = 64)")
        conn.execute("ANALYZE product_catalog")
    print(f"loaded {len(corpus)} products")


def full_text(conn, tsquery: str, depth: int) -> List[str]:
    """The full-text branch; a query with no usable token, or one Postgres rejects, finds none."""
    import psycopg

    if not tsquery:
        return []
    try:
        return [r[0] for r in conn.execute(FTS_SQL, (tsquery, depth)).fetchall()]
    except psycopg.Error:
        return []


def retrieve(work_dir: str, dsn: str) -> None:
    """Run both branches at the shipped depth (20) and the deep depth (100)."""
    import pandas as pd
    import psycopg

    work = Path(work_dir)
    queries = pd.read_parquet(work / "queries.parquet").reset_index(drop=True)
    vectors = json.loads((work / "query_vectors.json").read_text())
    candidates: Dict[str, dict] = {}
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET hnsw.iterative_scan = 'strict_order'")
        conn.execute("SET hnsw.ef_search = 40")
        for row, vector in zip(queries.itertuples(index=False), vectors):
            tsquery = or_tsquery(row.query)
            record = {"query": row.query}
            for depth in (100, 20):
                found = conn.execute(VECTOR_SQL, (vector_text(vector), depth)).fetchall()
                record[f"vec{depth}"] = [r[0] for r in found]
                record[f"fts{depth}"] = full_text(conn, tsquery, depth)
            candidates[str(row.query_id)] = record
    (work / "candidates.json").write_text(json.dumps(candidates))
    print(f"retrieved candidates for {len(candidates)} queries")


def vector_check(work_dir: str, dsn: str) -> None:
    """What HNSW gives up: the vector arm at ef_search 40 and 160 against an exact scan."""
    import pandas as pd
    import psycopg

    work = Path(work_dir)
    queries = pd.read_parquet(work / "queries.parquet").reset_index(drop=True)
    vectors = [vector_text(v) for v in json.loads((work / "query_vectors.json").read_text())]
    labels = load_labels(work)
    settings = {"HNSW, ef_search = 40": ["SET hnsw.ef_search = 40"],
                "HNSW, ef_search = 160": ["SET hnsw.ef_search = 160"],
                "exact scan": ["SET enable_indexscan = off", "SET enable_bitmapscan = off"]}
    ranked: Dict[str, List[List[str]]] = {}
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET hnsw.iterative_scan = 'strict_order'")
        for name, statements in settings.items():
            for statement in statements:
                conn.execute(statement)
            ranked[name] = [[r[0] for r in conn.execute(VECTOR_SQL, (v, 100)).fetchall()]
                            for v in vectors]
    print("| Vector arm | NDCG@10 | Recall@10 | Recall@50 | MRR |\n|---|---|---|---|---|")
    for name, lists in ranked.items():
        rows = [query_metrics(r, labels[str(q)]) for r, q in zip(lists, queries.query_id)]
        keys = ("ndcg10", "recall10", "recall50", "mrr")
        means = [sum(r[k] for r in rows) / len(rows) for k in keys]
        print(f"| {name} | " + " | ".join(f"{m:.4f}" for m in means) + " |")
    overlap = [len(set(a) & set(b)) / 100 for a, b in
               zip(ranked["HNSW, ef_search = 40"], ranked["exact scan"])]
    share = sum(overlap) / len(overlap)
    print(f"\nHNSW at ef_search = 40 returned {share:.1%} of the exact top 100")


def load_labels(work: Path) -> Dict[str, Dict[str, str]]:
    """Judgments by query id, then product id."""
    import pandas as pd

    labels: Dict[str, Dict[str, str]] = {}
    for r in pd.read_parquet(work / "qrels.parquet").itertuples(index=False):
        labels.setdefault(str(r.query_id), {})[r.product_id] = r.esci_label
    return labels


def fuse(vector_ids: List[str], fts_ids: List[str]) -> List[str]:
    """Pellier's reciprocal rank fusion over two ranked id lists."""
    rows = rrf_merge([{"product_id": p} for p in vector_ids],
                     [{"product_id": p} for p in fts_ids], RRF_K)
    return [row["product_id"] for row in rows]


def pools(record: dict) -> dict:
    """The fused lists and the rerank pools for one query."""
    deep = fuse(record["vec100"], record["fts100"])
    shipped = fuse(record["vec20"], record["fts20"])[:30]
    union = list(dict.fromkeys(deep[:50] + shipped[:15]))
    return {"deep": deep, "shipped": shipped, "pool15": deep[:15], "pool50": deep[:50],
            "ship15": shipped[:15], "union": union}


def rerank(work_dir: str, region: str) -> None:
    """Score each query's union of rerank pools once with Cohere Rerank 3.5."""
    import boto3
    import pandas as pd

    work = Path(work_dir)
    client = boto3.client("bedrock-agent-runtime", region_name=region)
    model_arn = f"arn:aws:bedrock:{region}::foundation-model/{RERANK_MODEL}"
    text = pd.read_parquet(work / "corpus.parquet").set_index("product_id")["rerank_text"]
    candidates = json.loads((work / "candidates.json").read_text())
    scores: Dict[str, Dict[str, float]] = {}
    for query_id, record in candidates.items():
        union = pools(record)["union"]
        response = client.rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": record["query"]}}],
            sources=[{"type": "INLINE", "inlineDocumentSource": {
                "type": "TEXT", "textDocument": {"text": text[p]}}} for p in union],
            rerankingConfiguration={"type": "BEDROCK_RERANKING_MODEL",
                                    "bedrockRerankingConfiguration": {
                                        "modelConfiguration": {"modelArn": model_arn},
                                        "numberOfResults": len(union)}})
        scores[query_id] = {union[r["index"]]: r["relevanceScore"] for r in response["results"]}
    (work / "rerank_scores.json").write_text(json.dumps(scores))
    print(f"reranked {len(scores)} queries")


def reorder(pool: List[str], scores: Dict[str, float], tail: List[str]) -> List[str]:
    """The pool in rerank order, then the rest of the fused list."""
    head = sorted(pool, key=lambda p: -scores[p])
    return head + [p for p in tail if p not in set(head)]


def arms(record: dict, scores: Dict[str, float]) -> Dict[str, List[str]]:
    """Every arm's ranked list for one query."""
    p = pools(record)
    return {
        "deep: full-text": record["fts100"],
        "deep: vector": record["vec100"],
        "deep: RRF k=60": p["deep"][:100],
        "deep: RRF + rerank@15": reorder(p["pool15"], scores, p["deep"][:100]),
        "deep: RRF + rerank@50": reorder(p["pool50"], scores, p["deep"][:100]),
        "shipped: full-text@20": record["fts20"],
        "shipped: vector@20": record["vec20"],
        "shipped: RRF top 30": p["shipped"],
        "shipped: RRF + rerank@15": reorder(p["ship15"], scores, p["shipped"]),
    }


def dcg(gains: List[float]) -> float:
    """Discounted cumulative gain."""
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def query_metrics(ranked: List[str], labels: Dict[str, str]) -> Dict[str, float]:
    """NDCG@10, Recall@10, Recall@50 and reciprocal rank of the first Exact item."""
    ideal = dcg(sorted((GAIN[v] for v in labels.values()), reverse=True)[:10])
    exact = {p for p, v in labels.items() if v == "E"}
    first = next((i + 1 for i, p in enumerate(ranked) if p in exact), None)
    return {"ndcg10": dcg([GAIN[labels.get(p, "I")] for p in ranked[:10]]) / ideal,
            "recall10": len(exact.intersection(ranked[:10])) / len(exact),
            "recall50": len(exact.intersection(ranked[:50])) / len(exact),
            "mrr": 1 / first if first else 0.0}


def bootstrap(values: List[float], rnd: random.Random) -> tuple:
    """Mean and 95% bootstrap interval over queries."""
    n = len(values)
    means = sorted(sum(values[rnd.randrange(n)] for _ in range(n)) / n
                   for _ in range(BOOTSTRAP_SAMPLES))
    return sum(values) / n, means[int(0.025 * BOOTSTRAP_SAMPLES)], \
        means[int(0.975 * BOOTSTRAP_SAMPLES)]


def score(work_dir: str) -> None:
    """Print the metrics table and the paired NDCG@10 differences."""
    work = Path(work_dir)
    candidates = json.loads((work / "candidates.json").read_text())
    scores = json.loads((work / "rerank_scores.json").read_text())
    labels = load_labels(work)
    asked = [q for q in candidates if any(v == "E" for v in labels[q].values())]
    per_arm: Dict[str, List[Dict[str, float]]] = {}
    for query_id in asked:
        for name, ranked in arms(candidates[query_id], scores[query_id]).items():
            per_arm.setdefault(name, []).append(query_metrics(ranked, labels[query_id]))
    rnd = random.Random(BOOTSTRAP_SEED)
    print(f"{len(asked)} queries with an Exact item\n")
    print("| Arm | NDCG@10 (95% CI) | Recall@10 | Recall@50 | MRR |\n|---|---|---|---|---|")
    for name, rows in per_arm.items():
        mean, low, high = bootstrap([r["ndcg10"] for r in rows], rnd)
        averages = {k: sum(r[k] for r in rows) / len(rows) for k in ("recall10", "recall50", "mrr")}
        print(f"| {name} | {mean:.3f} ({low:.3f} to {high:.3f}) | {averages['recall10']:.3f} | "
              f"{averages['recall50']:.3f} | {averages['mrr']:.3f} |")
    print("\n| Paired NDCG@10 difference | Mean (95% CI) |\n|---|---|")
    for left, right in PAIRS:
        diffs = [a["ndcg10"] - b["ndcg10"] for a, b in zip(per_arm[left], per_arm[right])]
        mean, low, high = bootstrap(diffs, rnd)
        print(f"| {left} minus {right} | {mean:+.3f} ({low:+.3f} to {high:+.3f}) |")


def main() -> None:
    """Dispatch one step."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    steps = parser.add_subparsers(dest="step", required=True)
    step = steps.add_parser("prepare")
    step.add_argument("data_dir")
    step.add_argument("work_dir")
    for name in ("embed", "rerank"):
        step = steps.add_parser(name)
        step.add_argument("work_dir")
        step.add_argument("--region", default="us-east-1")
    for name in ("load", "retrieve", "vector-check"):
        step = steps.add_parser(name)
        step.add_argument("work_dir")
        step.add_argument("dsn")
    steps.add_parser("score").add_argument("work_dir")
    args = parser.parse_args()
    if args.step == "prepare":
        prepare(args.data_dir, args.work_dir)
    elif args.step in ("embed", "rerank"):
        {"embed": embed, "rerank": rerank}[args.step](args.work_dir, args.region)
    elif args.step in ("load", "retrieve", "vector-check"):
        steps = {"load": load, "retrieve": retrieve, "vector-check": vector_check}
        steps[args.step](args.work_dir, args.dsn)
    else:
        score(args.work_dir)


if __name__ == "__main__":
    main()
