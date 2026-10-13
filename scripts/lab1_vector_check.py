#!/usr/bin/env python3
"""Lab 1A's check: the vector branch ranks Anna's eligible products by meaning.

The search embeds the shopper's words and asks pgvector for the products
closest to them in meaning. This check runs your ``vector_branch_sql`` from
``pellier/backend/services/store_tools.py`` against the catalog with vectors
whose nearest product is known in advance: a product's own stored embedding,
which sits at cosine distance 0 from itself. Ranked by meaning, that product
comes back first, the rest follow in order of rising distance, similarity
reads 1 minus the distance, and the branch returns as many rows as the search
asked for.

The last probe applies Anna's three limits and searches with the Sunday
Morning Candle's own embedding. The candle is the closest product to that
vector by meaning, and it must still not come back: the limits decide what is
eligible before meaning decides the order.

No model is called; every vector the check searches with is already in the
catalog.

    python3 scripts/lab1_vector_check.py
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workshop_check as check  # noqa: E402  (sibling module)

BACKEND = check.REPO / "pellier" / "backend"
TITLE = "the vector branch ranks by meaning"
EXPECTED = ("each product's own embedding finds that product first, the rest by rising "
            "distance, similarity = 1 - distance, a full branch, and Anna's limits kept")
NEXT_STEP = ("open the Vector branch - order by meaning region in "
             "pellier/backend/services/store_tools.py: which pgvector operator measures how "
             "far a product is from the query embedding, and which way should the rows run? "
             "Then rerun this check.")

SELF_PROBES = ("Stoneware Mugs, Set of 2", "Hadley Linen Shirt", "Sunday Morning Candle")
LIMITS_PROBE = "Sunday Morning Candle"
ANNA_REQUEST = ("A housewarming gift for a friend who loves slow mornings. "
                "In stock, under $100, and no candles.")
ANNA_LIMITS = {"price_max_usd": 100, "in_stock_only": True, "exclusions": ["candle"]}

_EMBEDDING = ('SELECT "productId" AS product_id, embedding::text AS embedding '
              "FROM pellier.product_catalog WHERE name = %s")
_DISTANCES = ('SELECT "productId" AS product_id, embedding <=> %s::vector AS distance '
              'FROM pellier.product_catalog WHERE "productId" = ANY(%s)')
_TOLERANCE = 1e-6


def _probe(run: Callable[..., List[Dict[str, Any]]], branch_sql: str, params: Sequence[Any],
           embedding: str, size: int) -> Tuple[List[Dict[str, Any]], List[float]]:
    """The branch's rows for one query vector, and each row's true distance to it."""
    rows = run(branch_sql, params)
    ids = [str(row["product_id"]) for row in rows]
    truth = {str(row["product_id"]): float(row["distance"])
             for row in run(_DISTANCES, (embedding, ids))}
    return rows, [truth[product_id] for product_id in ids]


def _ordering_problem(name: str, rows: List[Dict[str, Any]], distances: List[float],
                      size: int) -> Optional[str]:
    """What is wrong with one probe's ranking, or None when it is ranked by meaning."""
    if not rows:
        return "the vector branch returned no rows, so nothing is ranked by meaning yet"
    if len(rows) != size:
        return f"{len(rows)} rows came back for {name}; the search asked for {size}"
    if any(later < earlier - _TOLERANCE for earlier, later in zip(distances, distances[1:])):
        return f"the rows for {name} are not in order of rising distance; closest comes first"
    for row, distance in zip(rows, distances):
        similarity = row.get("similarity")
        if similarity is None or abs(float(similarity) - (1 - distance)) > _TOLERANCE:
            return (f"{row['name']} reports similarity {similarity}, where 1 minus its "
                    f"distance is {1 - distance:.4f}")
    return None


def _self_probe(run: Callable[..., List[Dict[str, Any]]], store_tools: Any, name: str,
                size: int) -> Tuple[Sequence[Any], Optional[str]]:
    target = run(_EMBEDDING, (name,))[0]
    rows, distances = _probe(run, store_tools.vector_branch_sql(()), (target["embedding"], size),
                             target["embedding"], size)
    problem = _ordering_problem(name, rows, distances, size)
    names = [str(row["name"]) for row in rows]
    if problem is None and names[0] != name:
        place = names.index(name) + 1 if name in names else None
        problem = (f"{name} came back {place} of {len(rows)} for its own embedding"
                   if place else f"{name} did not come back for its own embedding")
    first = names[0] if names else "(none)"
    similarity = f"{float(rows[0]['similarity']):.3f}" if rows and rows[0].get(
        "similarity") is not None else "-"
    return (name, first, similarity, len(rows), "ok" if problem is None else "fails"), problem


def _limits_probe(run: Callable[..., List[Dict[str, Any]]], store_tools: Any,
                  size: int) -> Tuple[Sequence[Any], Optional[str]]:
    from services.search_plan import build_plan

    clauses, params = build_plan(ANNA_REQUEST, dict(ANNA_LIMITS)).compile_predicates(
        include_soft=False)
    target = run(_EMBEDDING, (LIMITS_PROBE,))[0]
    rows, distances = _probe(run, store_tools.vector_branch_sql(clauses),
                             (target["embedding"], *params, size), target["embedding"], size)
    eligible = run('SELECT count(*) AS n FROM pellier.product_catalog WHERE "imgUrl" IS NOT '
                   "NULL AND " + " AND ".join(clauses), params)[0]["n"]
    problem = _ordering_problem("Anna's limits", rows, distances, min(size, int(eligible)))
    for row in rows:
        broken = [label for label, bad in (
            ("over $100", float(row["price"]) > 100),
            ("sold out", int(row["quantity"] or 0) <= 0),
            ("a candle", "candle" in [str(tag) for tag in (row.get("tags") or [])]
             + [str(material) for material in (row.get("materials") or [])]),
        ) if bad]
        if broken and problem is None:
            problem = f"{row['name']} came back under Anna's limits, and it is {broken[0]}"
    first = str(rows[0]["name"]) if rows else "(none)"
    label = f"{LIMITS_PROBE}, Anna's limits"
    return (label, first, "-", len(rows), "ok" if problem is None else "fails"), problem


def evaluate(conn: Any) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Run every probe through the live ``vector_branch_sql``; the first problem decides."""
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    try:
        from services import store_tools
    except Exception as exc:  # noqa: BLE001 - a broken edit is the finding
        return check.Finding("1A", TITLE, check.CONTRADICTED, EXPECTED,
                             "store_tools.py does not import",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"], NEXT_STEP), []
    size = int(store_tools.DEFAULT_RETRIEVAL_CONFIG["k_vector"])

    def run(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [dict(row) for row in cur.fetchall()] if cur.description else []

    rows: List[Sequence[Any]] = []
    problems: List[str] = []
    probes = [lambda name=name: _self_probe(run, store_tools, name, size) for name in SELF_PROBES]
    probes.append(lambda: _limits_probe(run, store_tools, size))
    for probe in probes:
        try:
            row, problem = probe()
        except Exception as exc:  # noqa: BLE001 - the participant's SQL raised
            return check.Finding("1A", TITLE, check.CONTRADICTED, EXPECTED,
                                 "your vector branch raised an error",
                                 [f"{type(exc).__name__}: {str(exc)[:200]}"], NEXT_STEP), rows
        rows.append(row)
        if problem and problem not in problems:
            problems.append(problem)
    evidence = [f"pellier.product_catalog, {len(SELF_PROBES)} products searched with their "
                f"own embeddings, then {LIMITS_PROBE} under Anna's limits; branch size {size}"]
    if problems:
        return check.Finding("1A", TITLE, check.CONTRADICTED, EXPECTED, problems[0],
                             evidence + problems[1:], NEXT_STEP), rows
    return check.Finding("1A", TITLE, check.PROVED, EXPECTED,
                         f"every probe ranks by meaning: {len(SELF_PROBES)} products found "
                         "themselves first, and Anna's limits held", evidence), rows


def run(env_path: pathlib.Path = check.DEFAULT_ENV) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Connect with the backend's settings and evaluate; never raises."""
    cfg = check.db_config(env_path)
    if cfg is None:
        return check.Finding("1A", TITLE, check.UNCHECKED, EXPECTED, "the check could not look",
                             [check.missing_settings_reason(env_path)]), []
    try:
        with check.connect(cfg) as conn:
            conn.autocommit = True
            return evaluate(conn)
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return check.Finding("1A", TITLE, check.UNCHECKED, EXPECTED, "the check could not look",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"],
                             "check that the database in pellier/backend/.env is reachable."), []


def main(argv: Optional[Sequence[str]] = None) -> int:
    del argv
    finding, rows = run()
    print("Lab 1A: the vector branch ranks Anna's eligible products by meaning")
    if rows:
        print(check.table(("searched with", "came back first", "similarity", "rows", "verdict"),
                          rows))
    print(check.render(finding))
    passed = finding.state == check.PROVED
    print("Lab 1A check passed" if passed else "Lab 1A check failed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
