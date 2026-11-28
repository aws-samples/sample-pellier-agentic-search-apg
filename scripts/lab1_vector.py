"""Lab 1A's check: the vector search ranks Anna's eligible products by meaning.

The search embeds the shopper's words and asks pgvector for the products
closest to them in meaning. This check runs your ``vector_search_sql`` from
``pellier/backend/services/store_tools.py`` against the catalog with vectors
whose nearest product is known in advance: a product's own stored embedding,
which sits at cosine distance 0 from itself. Ranked by meaning, that product
comes back first, the rest follow in order of rising distance, similarity
reads 1 minus the distance, and the vector search returns as many rows as
were asked for.

The last probe applies Anna's three requirements and searches with the Sunday
Morning Candle's own embedding. The candle is the closest product to that
vector by meaning, and it must still not come back: the requirements decide
what is eligible before meaning decides the order.

No model is called; every vector the check searches with is already in the
catalog.

    uv run scripts/lab1_check.py --task 1A
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workshop_check as check  # noqa: E402  (sibling module)

BACKEND = check.REPO / "pellier" / "backend"
TITLE = "the vector search ranks by meaning"
EXPECTED = ("each product's own embedding finds that product first, the rest by rising "
            "distance, similarity = 1 - distance, a full pool, and Anna's requirements kept; "
            "the five Storefront products closest to the Stoneware Pour-Over Set, the set first")
NEXT_STEP = ("apply Task 1A (uv run scripts/lab_run.py solution --lab 1 --task 1A), then rerun "
             "this check.")
SOLUTION_COMMAND = "uv run scripts/lab_run.py solution --lab 1 --task 1A"

SELF_PROBES = ("Stoneware Mugs, Set of 2", "Hadley Linen Shirt", "Sunday Morning Candle")
LIMITS_PROBE = "Sunday Morning Candle"
ANNA_REQUEST = ("A housewarming gift for a friend who loves slow mornings. "
                "In stock, $100 or less, and no candles.")
ANNA_LIMITS = {"price_max_usd": 100, "in_stock_only": True, "exclusions": ["candle"]}

_EMBEDDING = ('SELECT "productId" AS product_id, embedding::text AS embedding '
              "FROM pellier.product_catalog WHERE name = %s")
_DISTANCES = ('SELECT "productId" AS product_id, embedding <=> %s::vector AS distance '
              'FROM pellier.product_catalog WHERE "productId" = ANY(%s)')
_TOLERANCE = 1e-6

# The reference lookup both the 1A send and this check print: the Storefront products closest
# in meaning to the product the participant just found by its words in plain psql.
REFERENCE = "Stoneware Pour-Over Set"
REFERENCE_HEADING = f"Storefront products closest to the {REFERENCE}"
REFERENCE_LIMIT = 5


@dataclass
class Lookup:
    """The reference lookup's result: its rows, closest first as the search returned them, or
    why it could not run. No rows and no error is an empty result, not a failure.

    Attributes:
        rows: ``(product, distance, similarity)``; similarity is what the search reported.
        error: Why the lookup failed: no stored embedding, or the database or search raised.
        distinct_products: Number of distinct product IDs in a completed lookup.
        missing_reference: The named input product has no usable catalog embedding.
    """

    rows: List[Tuple[str, float, Optional[float]]] = field(default_factory=list)
    error: str = ""
    distinct_products: Optional[int] = None
    missing_reference: bool = False


def _store_tools() -> Any:
    """The backend's store tools as the participant's file now defines them."""
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from services import store_tools

    return store_tools


def reference_lookup(conn: Any) -> Lookup:
    """The five Storefront products closest to the reference product, through Pellier's active
    ``vector_search_sql`` with the Storefront visibility filter and the product's stored
    embedding. No model is called. Never raises: a failure is the result's ``error``."""
    try:
        store_tools = _store_tools()
        with conn.cursor() as cur:
            cur.execute(_EMBEDDING, (REFERENCE,))
            target = cur.fetchone()
            if not target or target["embedding"] is None:
                return Lookup(error=f"the {REFERENCE} has no stored embedding",
                              missing_reference=True)
            embedding = target["embedding"]
            cur.execute(store_tools.vector_search_sql((store_tools.VISIBLE_CATALOG_SQL,)),
                        (embedding, REFERENCE_LIMIT))
            found = [dict(row) for row in cur.fetchall()]
            ids = [str(row["product_id"]) for row in found]
            cur.execute(_DISTANCES, (embedding, ids))
            truth = {str(row["product_id"]): float(row["distance"]) for row in cur.fetchall()}
    except Exception as exc:  # noqa: BLE001 - any failure is the lookup's result
        return Lookup(error=f"{type(exc).__name__}: {' '.join(str(exc).split())[:160]}")
    return Lookup(rows=[(str(row["name"]), truth[str(row["product_id"])],
                         None if row.get("similarity") is None else float(row["similarity"]))
                        for row in found], distinct_products=len(set(ids)))


def lookup(env_path: pathlib.Path = check.DEFAULT_ENV) -> Lookup:
    """The reference lookup on the backend's database; never raises."""
    cfg = check.db_config(env_path)
    if cfg is None:
        return Lookup(error=check.missing_settings_reason(env_path))
    try:
        with check.connect(cfg) as conn:
            conn.autocommit = True
            return reference_lookup(conn)
    except Exception as exc:  # noqa: BLE001 - the reason is the result
        return Lookup(error=f"{type(exc).__name__}: {' '.join(str(exc).split())[:160]}")


def lookup_lines(found: Lookup) -> List[str]:
    """The lookup as the terminal prints it: heading, how many came back, then the rows."""
    if found.error:
        return [REFERENCE_HEADING, f"Lookup failed: {found.error}"]
    count = len(found.rows)
    if found.distinct_products is not None and found.distinct_products < count:
        noun = "product" if found.distinct_products == 1 else "products"
        total = f"{count} rows returned for {found.distinct_products} distinct {noun}."
    else:
        total = f"{count} product{'' if count == 1 else 's'} returned."
    lines = [REFERENCE_HEADING, total]
    if not found.rows:
        return lines
    width = max(len(name) for name, _, _ in found.rows + [("product", 0.0, None)]) + 2
    lines.append(f"{'product':<{width}}{'distance':>8}  {'similarity':>10}")
    for name, distance, similarity in found.rows:
        shown = "none" if similarity is None else f"{similarity:.3f}"
        lines.append(f"{name:<{width}}{distance:>8.3f}  {shown:>10}")
    return lines


def _probe(run: Callable[..., List[Dict[str, Any]]], search_sql: str, params: Sequence[Any],
           embedding: str, size: int) -> Tuple[List[Dict[str, Any]], List[float]]:
    """The vector search's rows for one query vector, and each row's true distance."""
    rows = run(search_sql, params)
    ids = [str(row["product_id"]) for row in rows]
    truth = {str(row["product_id"]): float(row["distance"])
             for row in run(_DISTANCES, (embedding, ids))}
    return rows, [truth[product_id] for product_id in ids]


def _ordering_problem(name: str, rows: List[Dict[str, Any]], distances: List[float],
                      size: int) -> Optional[str]:
    """What is wrong with one probe's ranking, or None when it is ranked by meaning."""
    if not rows:
        return "the vector search returned no rows, so nothing is ranked by meaning yet"
    if len(rows) != size:
        return f"{len(rows)} rows came back for {name}; the search asked for {size}"
    if len({row["product_id"] for row in rows}) != size:
        return f"the search for {name} returned repeated IDs; it needs {size} distinct products"
    if any(later < earlier - _TOLERANCE for earlier, later in zip(distances, distances[1:])):
        return f"the rows for {name} are not in order of rising distance; closest comes first"
    for row, distance in zip(rows, distances):
        similarity = row.get("similarity")
        if similarity is None or abs(float(similarity) - (1 - distance)) > _TOLERANCE:
            return (f"{row['name']} reports similarity {similarity}, where 1 minus its "
                    f"distance is {1 - distance:.4f}")
    return None


def _first(rows: List[Dict[str, Any]]) -> Tuple[str, str]:
    """The first row's name and similarity, as the table prints them."""
    if not rows:
        return "(none)", "none"
    similarity = rows[0].get("similarity")
    return str(rows[0]["name"]), "none" if similarity is None else f"{float(similarity):.3f}"


class MissingSeedEmbedding(Exception):
    """A known workshop product cannot supply the check's input vector."""


def _seed_embedding(run: Callable[..., List[Dict[str, Any]]], name: str) -> str:
    rows = run(_EMBEDDING, (name,))
    if not rows or rows[0]["embedding"] is None:
        raise MissingSeedEmbedding(f"the workshop catalog has no stored embedding for {name}")
    return rows[0]["embedding"]


def _self_probe(run: Callable[..., List[Dict[str, Any]]], store_tools: Any, name: str,
                size: int) -> Tuple[Sequence[Any], Optional[str]]:
    embedding = _seed_embedding(run, name)
    rows, distances = _probe(run, store_tools.vector_search_sql(()), (embedding, size),
                             embedding, size)
    problem = _ordering_problem(name, rows, distances, size)
    names = [str(row["name"]) for row in rows]
    if problem is None and names[0] != name:
        place = names.index(name) + 1 if name in names else None
        problem = (f"{name} came back {place} of {len(rows)} for its own embedding"
                   if place else f"{name} did not come back for its own embedding")
    return (name, *_first(rows), len(rows), "ok" if problem is None else "fails"), problem


def _limits_probe(run: Callable[..., List[Dict[str, Any]]], store_tools: Any,
                  size: int) -> Tuple[Sequence[Any], Optional[str]]:
    from services.search_plan import build_plan

    clauses, params = build_plan(ANNA_REQUEST, dict(ANNA_LIMITS)).compile_predicates(
        include_soft=False)
    embedding = _seed_embedding(run, LIMITS_PROBE)
    rows, distances = _probe(run, store_tools.vector_search_sql(clauses),
                             (embedding, *params, size), embedding, size)
    eligible = run('SELECT count(*) AS n FROM pellier.product_catalog WHERE '
                   + store_tools.VISIBLE_CATALOG_SQL + " AND " + " AND ".join(clauses),
                   params)[0]["n"]
    problem = _ordering_problem("Anna's requirements", rows, distances, min(size, int(eligible)))
    for row in rows:
        broken = [label for label, bad in (
            ("over $100", float(row["price"]) > 100),
            ("sold out", int(row["quantity"] or 0) <= 0),
            ("a candle", "candle" in [str(tag) for tag in (row.get("tags") or [])]
             + [str(material) for material in (row.get("materials") or [])]),
        ) if bad]
        if broken and problem is None:
            problem = (f"{row['name']} came back with Anna's requirements applied, "
                       f"and it is {broken[0]}")
    return (f"{LIMITS_PROBE}, Anna's requirements", *_first(rows), len(rows),
            "ok" if problem is None else "fails"), problem


def evaluate(conn: Any) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """The check's finding and probe rows; see :func:`evaluate_all`."""
    finding, rows, _found = evaluate_all(conn)
    return finding, rows


def evaluate_all(conn: Any) -> Tuple[check.Finding, List[Sequence[Any]], Lookup]:
    """The four probes, then the reference lookup the participant reads: both must hold."""
    finding, rows = _probes(conn)
    found = reference_lookup(conn)
    return judge_lookup(finding, found), rows, found


def lookup_problem(found: Lookup) -> Optional[str]:
    """What keeps the visible lookup from proving the repair, or None when it does."""
    if found.error:
        return f"the pour-over lookup failed: {found.error}"
    if len(found.rows) != REFERENCE_LIMIT:
        return (f"the pour-over lookup returned {len(found.rows)} products, "
                f"not {REFERENCE_LIMIT}")
    if found.distinct_products is not None and found.distinct_products < REFERENCE_LIMIT:
        return (f"the pour-over lookup returned repeated IDs; "
                f"it needs {REFERENCE_LIMIT} distinct products")
    if found.rows[0][0] != REFERENCE:
        return f"the pour-over lookup put {found.rows[0][0]} first, not the {REFERENCE}"
    return None


LOOKUP_NEXT = ('In the guide, open Task 1A and use "Troubleshoot with Claude Code or go '
               'deeper".\nPaste this command and the lookup lines above.')


def judge_lookup(finding: check.Finding, found: Lookup) -> check.Finding:
    """The probes' finding, held back when the lookup the participant reads cannot show the
    repair: a failed lookup could not check, a wrong one failed. A probe failure stands."""
    problem = lookup_problem(found)
    if (problem is None or finding.state == check.COULD_NOT_CHECK
            or (finding.state == check.FAILED and not found.missing_reference)):
        return finding
    state = check.COULD_NOT_CHECK if found.error else check.FAILED
    return check.Finding("1A", TITLE, state, EXPECTED, problem,
                         list(finding.evidence) + [f"probes: {finding.observed}"], LOOKUP_NEXT)


def _probes(conn: Any) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Run every probe through the live ``vector_search_sql``; the first problem decides."""
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    try:
        from services import store_tools
    except Exception as exc:  # noqa: BLE001 - a broken edit is the finding
        return check.Finding("1A", TITLE, check.FAILED, EXPECTED,
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
        except MissingSeedEmbedding as exc:
            next_step = ('Open "Troubleshoot with Claude Code or go deeper" in Task 1A. '
                         "Paste this command and the line naming the missing embedding.")
            return check.Finding("1A", TITLE, check.COULD_NOT_CHECK, EXPECTED, str(exc), [],
                                 next_step), rows
        except Exception as exc:  # noqa: BLE001 - the participant's SQL raised
            return check.Finding("1A", TITLE, check.FAILED, EXPECTED,
                                 "your vector search raised an error",
                                 [f"{type(exc).__name__}: {str(exc)[:200]}"], NEXT_STEP), rows
        rows.append(row)
        if problem and problem not in problems:
            problems.append(problem)
    evidence = [f"pellier.product_catalog, {len(SELF_PROBES)} products searched with their "
                f"own embeddings, then {LIMITS_PROBE} with Anna's requirements; pool size {size}"]
    if problems:
        return check.Finding("1A", TITLE, check.FAILED, EXPECTED, problems[0],
                             evidence + problems[1:], NEXT_STEP), rows
    return check.Finding("1A", TITLE, check.PASSED, EXPECTED,
                         f"every test ranks by meaning: {len(SELF_PROBES)} products found "
                         "themselves first, and Anna's requirements held", evidence), rows


def run(env_path: pathlib.Path = check.DEFAULT_ENV) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """The check's finding and probe rows; see :func:`run_all`."""
    finding, rows, _found = run_all(env_path)
    return finding, rows


def run_all(env_path: pathlib.Path = check.DEFAULT_ENV
            ) -> Tuple[check.Finding, List[Sequence[Any]], Lookup]:
    """Connect with the backend's settings and evaluate everything; never raises."""
    cfg = check.db_config(env_path)
    if cfg is None:
        reason = check.missing_settings_reason(env_path)
        return check.Finding("1A", TITLE, check.COULD_NOT_CHECK, EXPECTED,
                             "the check could not look", [reason]), [], Lookup(error=reason)
    try:
        with check.connect(cfg) as conn:
            conn.autocommit = True
            return evaluate_all(conn)
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        reason = f"{type(exc).__name__}: {str(exc)[:160]}"
        return check.Finding("1A", TITLE, check.COULD_NOT_CHECK, EXPECTED,
                             "the check could not look", [reason],
                             "check that the database in pellier/backend/.env is reachable."
                             ), [], Lookup(error=reason)


APPLY_NEXT = ('In the guide, open Task 1A and read "Find the line and apply the provided fix".\n'
              f"Then run: {SOLUTION_COMMAND}")


def _rule(row: Sequence[Any], next_step: str = APPLY_NEXT, problem: str = "") -> check.Rule:
    """One probe row as a rule: a product searched with its own embedding, or the last probe."""
    searched, first, similarity, _, verdict = row
    own = searched in SELF_PROBES
    label = (f"{searched}, searched by its own embedding" if own
             else f"{LIMITS_PROBE} again, with Anna's requirements")
    if verdict == "ok":
        result = (f"came back first ({similarity})" if own
                  else f"{first} ({similarity}); the candle is excluded")
        return check.Rule(label, result)
    expected = "that product first, closest first" if own else "the candle left out"
    observed = (f"{first} came back first (similarity {similarity})" if rows_back(row)
                else "nothing came back")
    if problem:
        observed = f"{observed}. {problem}"
    return check.Rule(label, ok=False, expected=expected, observed=observed,
                      next_step=next_step)


def rows_back(row: Sequence[Any]) -> bool:
    """True when the probe's search returned at least one product."""
    return int(row[3] or 0) > 0


def verdict(finding: check.Finding, rows: Sequence[Sequence[Any]],
            found: Optional[Lookup] = None) -> check.Verdict:
    """The compact view of the check: the reference lookup, then on a failure each failing
    probe with why it failed and what to do next. Both the four probes and the visible lookup
    must pass. Successful probe details print with ``--details``."""
    if len(rows) < len(SELF_PROBES) + 1:
        # A probe could not finish. Show its cause and recovery, even if earlier probes ran.
        rules = []
    elif found is not None and lookup_problem(found) and (
            found.missing_reference or all(row[4] == "ok" for row in rows)):
        # A missing catalog input needs attention even with the starter still in place.
        rules = [check.Rule("The pour-over lookup", ok=None if found.error else False,
                            expected="the five Storefront products closest to the "
                                     f"{REFERENCE}, the set first",
                            observed=str(lookup_problem(found)), next_step=LOOKUP_NEXT)]
    elif not any(rows_back(row) for row in rows):
        # The starter's fault: the vector search ranks nothing, so every probe fails alike.
        rules = [check.Rule("The vector search", ok=False,
                            expected="the products closest in meaning, closest first",
                            observed=f"nothing came back for any of the {len(rows)} searches",
                            next_step=APPLY_NEXT)]
    else:
        failing = [row for row in rows if row[4] != "ok"]
        first_failure = failing[0] if failing else None
        rules = [_rule(row, APPLY_NEXT, finding.observed) if row is first_failure
                 else _rule(row, "") for row in rows]
    told = check.with_rules(finding, "Lab 1A: pgvector ranks products by meaning.", rules)
    if found is not None:
        told.summary = lookup_lines(found)
    return told


def main(argv: Optional[Sequence[str]] = None) -> int:
    if check.refuse_missing_lab_file(1):
        return 1
    finding, rows, found = run_all()
    tables = [*lookup_lines(found), "",
              "Lab 1A: the vector search ranks Anna's eligible products by meaning"]
    if rows:
        tables.append(check.table(
            ("searched with", "came back first", "similarity", "rows", "verdict"), rows))
    # On a pass, the pass line is the last line: the guide's Next leads on to Task 1B.
    last = (check.paint("Lab 1A check passed", check.PASSED)
            if finding.state == check.PASSED else "")
    return 0 if check.emit(verdict(finding, rows, found), argv, "Lab 1A check", "1A", tables,
                           closing_line=last) else 1
