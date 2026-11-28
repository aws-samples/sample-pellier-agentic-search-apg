"""Lab 1B's check: Anna's latest search kept every requirement she asked for.

When the first search is sparse, the fallback retries with fewer preferences;
it must never retry with fewer requirements. This reads the retrieval receipts of
Anna's newest turn (``persona-anna-...``, the session
``uv run scripts/lab_run.py send --lab 1`` starts), takes the search that
needed the fallback (else the newest), and compares two things it records: the
requirements the shopper asked for (``retrieval_config.requested``, the plan built
from her words before any fallback) and the requirements the search that
answered kept. It then reads every product that search returned from the
catalog and checks each requested requirement against it.

The search must have needed the fallback: a receipt with no recorded
relaxation never ran Task 1B's code, so it proves nothing either way. A
request that stated no requirement proves nothing either, so the check asks for the
guide's request.

Run on the box, it also reads when search_plan.py last changed and when the
backend last started. A backend started before the edit is still running the
old code, and a search older than the edit was made by it, so neither is
judged: the finding says to restart, or to send Anna's request again. A later
restart for another lab does not date the search. Without that timeline (the
Wrap-up summary reads rows alone) it judges the newest search as it is.

    uv run scripts/lab1_check.py --task 1B
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workshop_check as check  # noqa: E402  (sibling module)

ANNA_SESSION_PREFIX = "persona-anna-"
SEND = "uv run scripts/lab_run.py send --lab 1 --task 1B"
# The guide's request, the one Anna's first suggestion sends: three requirements the
# first search cannot fill, so the fallback has to run.
ANNA_REQUEST = ("A housewarming gift for a friend who loves slow mornings. "
                "In stock, $100 or less, and no candles.")
TITLE = "Anna's requirements survive the retry"
EXPECTED = (
    "the retry ran and the search that answered kept every requirement the shopper "
    "asked for; every product it returned meets them"
)
NEXT_STEP = (
    "open _next_attempt in pellier/backend/services/search_plan.py: does the "
    "next attempt keep the budget, the stock rule and the exclusions? Send Anna's request "
    f"again ({SEND}), then rerun this check."
)
NEXT_REQUEST = f"send Anna's request with {SEND}, then rerun this check."
# What the compact view tells the participant, one diagnosis in at most two short lines.
SHORT_NEXT_SEND = ('In the guide, open Task 1B and read "Send her full request".\n'
                   f"Then run: {SEND}")
SHORT_NEXT_FIX = ("In 1B-search-plan.py, copy the plan and change only the relaxations.\n"
                  f"Then send Anna's request again: {SEND}")
HEADLINE = ("Lab 1B: Anna's budget, stock rule and exclusion filter first, and survive every "
            "retry.")
# After the pass line: where the same turn shows in Pellier. The participant switches tabs.
SEE_IT_IN_PELLIER = (
    "See it in Pellier (optional)",
    "Open the Pellier tab \u2192 Ask Pellier \u2192 Anna.",
    "Find her latest \u201cSent from the terminal\u201d request. Turn on Builder view.",
    "Under \u201cHow it ranked\u201d, look for \u201cKept\u201d.",
)
LAB_1_ROW = ("1 \u00b7 Retrieve", "Search by meaning and a retry that keeps Anna’s rules")
_NUMBER_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                 "ten")
SEARCH_PLAN = check.REPO / "pellier" / "backend" / "services" / "search_plan.py"


Timeline = check.Timeline
service_started = check.service_started
_clock = check.clock


def timeline() -> Timeline:
    """This box's timeline: search_plan.py's modification time and pellier's systemd start."""
    return check.edit_timeline(SEARCH_PLAN)


def stale(receipt: Dict[str, Any], when: Optional[Timeline]) -> Optional[Tuple[str, str]]:
    """Why the newest search cannot show the code now running, and the next step; else None."""
    if when is None:
        return None
    edited, started = when.edited_at, when.started_at
    if edited and started and started < edited:
        return (f"pellier last started at {_clock(started)}, before your last change to "
                f"search_plan.py at {_clock(edited)}, so the code running is not your edit yet",
                f"send Anna's request again ({SEND}); it restarts the backend first, so your "
                "edit runs. Then rerun this check.")
    created = receipt.get("created_at")
    if not isinstance(created, datetime) or edited is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if created < edited:
        return (f"Anna's newest search ran at {_clock(created)}, before your last change to "
                f"search_plan.py at {_clock(edited)}, so the code before your edit made it",
                f"send Anna's request again ({SEND}), then rerun this check.")
    return None

# Anna's newest turn, not just her newest receipt: a turn can run more than one
# search, and the one that needed the fallback is the one Task 1B decides. A
# receipt with no turn id stands alone.
_LATEST_RECEIPT = f"""
WITH newest AS (
  SELECT receipt_id, turn_id
    FROM pellier.retrieval_receipts
   WHERE session_id LIKE %(session)s
     AND created_at >= {check.SINCE_SQL}
   ORDER BY receipt_id DESC
   LIMIT 1
)
SELECT r.receipt_id, r.session_id, r.created_at, r.query_preview, r.citation_ids,
       r.relaxations, r.hard_constraints, r.exclusions, r.retrieval_config
  FROM pellier.retrieval_receipts r, newest
 WHERE r.session_id LIKE %(session)s
   AND r.created_at >= {check.SINCE_SQL}
   AND (r.receipt_id = newest.receipt_id OR r.turn_id = newest.turn_id)
 ORDER BY jsonb_array_length(r.relaxations) > 0 DESC, r.receipt_id DESC
 LIMIT 1
"""

# The search of Anna's full request as the last 1B send recorded its turn (lab_run.py send
# writes .local/lab-1b-turn.json), so a later turn that ran no search can never borrow an
# earlier turn's retry.
_TURN_RECEIPT = f"""
SELECT r.receipt_id, r.session_id, r.created_at, r.query_preview, r.citation_ids,
       r.relaxations, r.hard_constraints, r.exclusions, r.retrieval_config
  FROM pellier.retrieval_receipts r
 WHERE r.turn_id = %(turn)s
   AND r.session_id LIKE %(session)s
   AND r.created_at >= {check.SINCE_SQL}
 ORDER BY jsonb_array_length(r.relaxations) > 0 DESC, r.receipt_id DESC
 LIMIT 1
"""
NO_RECEIPT = "There is no search receipt for Anna's latest request."
UNFINISHED = "There is no completed turn recorded for Anna's latest send."


def recorded_turn() -> Tuple[bool, Optional[str]]:
    """``(present, turn)``: whether a 1B send left a record, and the turn it recorded.

    No record at all means no 1B send on this machine since the record began, so the check
    reads Anna's newest search as before. A record without a turn is a send that did not
    finish."""
    path = check.lab1_retry_turn_path()
    try:
        saved = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return path.is_symlink(), None
    except (OSError, UnicodeDecodeError):
        return True, None
    try:
        turn = json.loads(saved).get("turn") if saved.strip() else None
    except (ValueError, AttributeError):
        turn = None
    return True, turn if isinstance(turn, str) and turn.strip() else None


def receipt_context() -> str:
    """Pass the same local send and reset state to the participant's psql session."""
    present, turn = recorded_turn()
    since = check.reset_point(1)
    return json.dumps({"unfinished": present and turn is None, "turn": turn,
                       "since": since.isoformat() if since else None})


_PRODUCTS = """
SELECT "productId" AS product_id, name, price, quantity, category, tags, materials
  FROM pellier.product_catalog
 WHERE "productId" = ANY(%s)
"""


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, str):
        value = json.loads(value or "[]")
    return list(value or [])


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value or "{}")
    return dict(value or {})


def _plural(word: str) -> str:
    if word.endswith("s"):
        return word
    return word + ("es" if re.search(r"(ch|sh|x|z)$", word) else "s")


def limits_of(hard_constraints: Any, exclusions: Any) -> Dict[str, Any]:
    """One plan's requirements: budget, stock, exclusions and departments."""
    hard = _as_dict(hard_constraints)
    price = hard.get("price_max_usd")
    return {
        "price": float(price) if price is not None else None,
        "in_stock": bool(hard.get("in_stock_only")),
        "exclusions": sorted({str(value).lower() for value in _as_list(exclusions) if value}),
        "categories": sorted({str(value).lower() for value in
                              _as_list(hard.get("categories")) if value}),
    }


def requested_limits(receipt: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """What the shopper asked for, or None on a receipt that predates recording it."""
    requested = _as_dict(receipt.get("retrieval_config")).get("requested")
    if not isinstance(requested, dict):
        return None
    return limits_of(requested.get("hard_constraints"), requested.get("exclusions"))


def kept_limits(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """What the search that answered applied, after any fallback."""
    return limits_of(receipt.get("hard_constraints"), receipt.get("exclusions"))


def _money(dollars: float) -> str:
    return f"${dollars:g}" if dollars == int(dollars) else f"${dollars:.2f}"


def budget_words(price: Any) -> str:
    """A price ceiling in words that say exactly which prices it admits.

    The same rule as ``budget_phrase`` in pellier/backend/services/turn_steps.py, which
    writes Ask Pellier's tag and the send output. Prices are whole cents, so a ceiling of
    $99.99 reads "under $100" and a ceiling of $100, which also admits a $100.00 product,
    reads "$100 or less". This check reads rows without importing the backend, so the rule
    is written twice; tests/test_lab1_retry.py holds the two together.
    """
    cents = round(float(price) * 100)
    if cents % 100 == 99:
        return f"under {_money((cents + 1) / 100)}"
    return f"{_money(cents / 100)} or less"


def phrases(limits: Dict[str, Any]) -> List[str]:
    """The requirements in the shopper's words: "$100 or less", "in stock", "no candles"."""
    said = []
    if limits["price"] is not None:
        said.append(budget_words(limits["price"]))
    if limits["in_stock"]:
        said.append("in stock")
    said.extend(f"no {_plural(value)}" for value in limits["exclusions"])
    if limits["categories"]:
        said.append(" or ".join(limits["categories"]) + " only")
    return said


def dropped(requested: Dict[str, Any], kept: Dict[str, Any]) -> List[str]:
    """Each requested limit the search that answered no longer applied."""
    lost = []
    if requested["price"] is not None and (kept["price"] is None
                                           or kept["price"] > requested["price"]):
        lost.append(budget_words(requested["price"]))
    if requested["in_stock"] and not kept["in_stock"]:
        lost.append("in stock")
    lost.extend(f"no {_plural(value)}" for value in requested["exclusions"]
                if value not in kept["exclusions"])
    narrowed = set(kept["categories"]) <= set(requested["categories"])
    if requested["categories"] and not (kept["categories"] and narrowed):
        lost.append(" or ".join(requested["categories"]) + " only")
    return lost


def product_breaks(product: Dict[str, Any], limits: Dict[str, Any]) -> List[str]:
    """The requested requirements one catalog row breaks, in the shopper's words."""
    broken = []
    if limits["price"] is not None and float(product["price"]) > limits["price"]:
        broken.append(f"${float(product['price']):.2f}")
    if limits["in_stock"] and int(product["quantity"] or 0) <= 0:
        broken.append("sold out")
    labels = {str(value).lower() for value in
              _as_list(product.get("tags")) + _as_list(product.get("materials"))}
    broken.extend(f"excluded {value}" for value in limits["exclusions"] if value in labels)
    category = str(product.get("category") or "").lower()
    if limits["categories"] and category not in limits["categories"]:
        broken.append(f"in {product.get('category') or 'no department'}")
    return broken


def _relaxations(receipt: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [step for step in _as_list(receipt.get("relaxations")) if isinstance(step, dict)]


def _evidence(receipt: Dict[str, Any], requested: Optional[Dict[str, Any]]) -> List[str]:
    steps = _relaxations(receipt)
    retried = "; ".join(
        f"{step.get('step')} (dropped {', '.join(step.get('dropped') or []) or 'nothing'})"
        for step in steps
    ) or "no relaxation recorded"
    created = receipt.get("created_at")
    when = created.strftime("%H:%M:%S UTC") if hasattr(created, "strftime") else str(created)
    asked = (", ".join(phrases(requested)) or "no requirement") if requested else "not recorded"
    return [
        f"pellier.retrieval_receipts receipt {receipt['receipt_id']}, session "
        f"{check.short(receipt.get('session_id'), 22)}, {when}",
        f"query: \"{receipt.get('query_preview') or ''}\"",
        f"the shopper asked: {asked}",
        f"the search that answered recorded: {retried}; requirements it kept: "
        f"{', '.join(phrases(kept_limits(receipt))) or 'none'}",
    ]


def _waiting(finding: check.Finding) -> check.Verdict:
    """A finding that has no verdict yet: one rule that says what is missing and to send again."""
    rule = check.Rule("Anna's retry", ok=False, expected="a retry on her full request",
                      observed=finding.observed, next_step=SHORT_NEXT_SEND)
    return check.with_rules(finding, HEADLINE, [rule])


def kept_words(limits: Dict[str, Any]) -> List[str]:
    """The requirements in the order the receipt lists them: stock, budget, exclusions."""
    said = ["in stock"] if limits["in_stock"] else []
    if limits["price"] is not None:
        said.append(budget_words(limits["price"]))
    said.extend(f"no {_plural(value)}" for value in limits["exclusions"])
    if limits["categories"]:
        said.append(" or ".join(limits["categories"]) + " only")
    return said


def pass_summary(requested: Dict[str, Any], count: int) -> List[str]:
    """A passing retry in two sentences: what it kept, and how many gifts met all of it."""
    kept = ", ".join(kept_words(requested))
    met = (f"All {count} gifts met those requirements." if count != 1
           else "The one gift met those requirements.")
    return [f"The retry kept   {kept[:1].upper()}{kept[1:]}", met]


def _counted(number: int) -> str:
    return _NUMBER_WORDS[number] if number < len(_NUMBER_WORDS) else str(number)


def lab_1_row(requested: Optional[Dict[str, Any]]) -> Tuple[str, str, Optional[str]]:
    """Lab 1's row of the grid: what Anna's retry kept, or no proof when it is not passing."""
    if requested is None:
        return (*LAB_1_ROW, None)
    rules = len(kept_words(requested))
    proved = (f"Anna\u2019s retry kept all {_counted(rules)} rules." if rules != 1
              else "Anna\u2019s retry kept her rule.")
    return (*LAB_1_ROW, proved)


def completion_row(requested: Dict[str, Any], width: Optional[int] = None) -> List[str]:
    """Lab 1's row of what the participant has proved, once both Lab 1 checks pass."""
    import pellier_map

    return pellier_map.proved_grid([lab_1_row(requested)], width)


def proved_requirements() -> Optional[Dict[str, Any]]:
    """What Anna asked for, when both Lab 1 checks pass now; else None. A later lab's grid
    reads Lab 1's row through this, so its proof is as live as Lab 1's own."""
    finding, _rows = run()
    requested = getattr(finding, "data", {}).get("requested")
    if finding.state != check.PASSED or not requested or not lab_1_complete():
        return None
    return requested


def lab_1_complete() -> bool:
    """Task 1A's check passes now too, read live, so a broken vector search shows no row."""
    import lab1_vector

    finding, _ = lab1_vector.run()
    return finding.state == check.PASSED


def after_pass(requested: Dict[str, Any], complete: bool) -> List[str]:
    """What prints under Lab 1B's pass line: where to see the turn, then Lab 1's row."""
    lines = list(SEE_IT_IN_PELLIER) if check.says_next() else []
    if complete:
        lines += ([""] if lines else []) + completion_row(requested)
    return lines


def _pass_rules(receipt: Dict[str, Any], requested: Dict[str, Any], count: int) -> List[check.Rule]:
    """The rules a passing retry satisfied, one per requirement and one for what it dropped."""
    everywhere = f"all {count} products" if count != 1 else "the 1 product"
    rules = []
    if requested["price"] is not None:
        rules.append(check.Rule(f"Budget {budget_words(requested['price'])}", everywhere))
    if requested["in_stock"]:
        rules.append(check.Rule("In stock", everywhere))
    for value in requested["exclusions"]:
        rules.append(check.Rule(f"No {_plural(value)}", f"none among the {count}"))
    words = sorted({str(word) for step in _relaxations(receipt)
                    for word in step.get("dropped") or []})
    rules.append(check.Rule("The retry dropped",
                            f"only the words {', '.join(words)}" if words else "nothing"))
    return rules


def _fail_rules(requested: Dict[str, Any], ids: Sequence[str], broken_lines: Sequence[str],
                lost: Sequence[str]) -> List[check.Rule]:
    """One rule for the requirements the retry lost, else one for the products that break one."""
    rules = []
    if lost:
        kept = [name for name in kept_words(requested) if name not in lost]
        rules.append(check.Rule("Anna's requirements on the retry", ok=False,
                                expected=", ".join(kept_words(requested)),
                                observed=(f"kept {', '.join(kept)}; dropped {', '.join(lost)}"
                                          if kept else f"dropped all {_counted(len(lost))}"),
                                next_step=SHORT_NEXT_FIX))
    if broken_lines and not lost:
        rules.append(check.Rule("Products meet the requirements", ok=False,
                                expected=f"all {len(ids)} meet them",
                                observed=f"{len(broken_lines)} of {len(ids)} break one",
                                next_step=SHORT_NEXT_FIX))
    return rules


def evaluate(conn: Any, when: Optional[Timeline] = None
             ) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Judge the search of the turn the last 1B send recorded, or of Anna's newest turn when
    no send has recorded one: the search that needed the fallback, else the newest.

    Returns the finding and one row per product. With ``when``, a search older than
    the last edit or restart is not judged, and no product rows are returned. A recorded turn
    with no search of its own is not yet a pass, whatever an older turn's search kept.
    """
    present, turn = recorded_turn()
    if present and turn is None:
        return _waiting(check.Finding("1B", TITLE, check.NOT_YET, EXPECTED, UNFINISHED,
                                      [f"{check.lab1_retry_turn_path().name} holds no turn"],
                                      NEXT_REQUEST)), []
    with conn.cursor() as cur:
        cur.execute(_TURN_RECEIPT if turn else _LATEST_RECEIPT,
                    {"session": ANNA_SESSION_PREFIX + "%", "since": check.reset_point(1),
                     "turn": turn})
        receipt = cur.fetchone()
        if not receipt and turn:
            return _waiting(check.Finding(
                "1B", TITLE, check.NOT_YET, EXPECTED, NO_RECEIPT,
                [f"pellier.retrieval_receipts has no row for turn {check.short(turn, 22)}"],
                NEXT_REQUEST + check.since_note(1, SEND))), []
        if not receipt:
            return _waiting(check.Finding(
                "1B", TITLE, check.NOT_YET, EXPECTED,
                "no search receipt in a session of Anna's yet",
                ["pellier.retrieval_receipts has no row whose session starts persona-anna-"],
                NEXT_REQUEST + check.since_note(1, SEND),
            )), []
        reason = stale(receipt, when)
        if reason:
            edited = _clock(when.edited_at) if when.edited_at else "unknown"
            started = _clock(when.started_at) if when.started_at else "unknown"
            evidence = _evidence(receipt, requested_limits(receipt)) + [
                f"search_plan.py last changed: {edited}", f"pellier last started: {started}",
            ]
            return _waiting(check.Finding("1B", TITLE, check.NOT_YET, EXPECTED, reason[0],
                                          evidence, reason[1])), []
        ids = [str(value) for value in _as_list(receipt.get("citation_ids"))]
        cur.execute(_PRODUCTS, (ids,))
        catalog = {str(row["product_id"]): row for row in cur.fetchall()}
    requested = requested_limits(receipt)
    rows, broken_lines = _rows(ids, catalog, requested or limits_of({}, []))
    return _judge(receipt, requested, ids, broken_lines), rows


def _cut(name: str, width: int = 30) -> str:
    """A product name cut to ``width``, ending in ``...`` so the cut shows."""
    return name if len(name) <= width else name[: width - 3] + "..."


def _rows(
    ids: Sequence[str], catalog: Dict[str, Dict[str, Any]], limits: Dict[str, Any],
) -> Tuple[List[Sequence[Any]], List[str]]:
    rows: List[Sequence[Any]] = []
    broken_lines: List[str] = []
    for product_id in ids:
        product = catalog.get(product_id)
        if product is None:
            rows.append((product_id, "(not in the catalog)", "", "", "missing"))
            broken_lines.append(f"{product_id} is not in the catalog")
            continue
        broken = product_breaks(product, limits)
        verdict = ("breaks: " + ", ".join(broken)) if broken else "ok"
        rows.append((
            product_id, _cut(str(product["name"])), f"${float(product['price']):.2f}",
            int(product["quantity"] or 0), verdict,
        ))
        if broken:
            broken_lines.append(f"{product_id} {product['name']} is " + " and ".join(broken))
    return rows, broken_lines


def _judge(
    receipt: Dict[str, Any], requested: Optional[Dict[str, Any]], ids: Sequence[str],
    broken_lines: Sequence[str],
) -> check.Finding:
    evidence = _evidence(receipt, requested)
    if not ids:
        return _waiting(check.Finding("1B", TITLE, check.NOT_YET, EXPECTED,
                                      "Anna's latest search returned no products", evidence,
                                      NEXT_REQUEST))
    if requested is None or not phrases(requested):
        observed = ("the receipt does not record what the shopper asked" if requested is None
                    else "the request stated no requirement, so there was nothing to keep")
        return _waiting(check.Finding("1B", TITLE, check.NOT_YET, EXPECTED, observed, evidence,
                                      NEXT_REQUEST))
    if not _relaxations(receipt):
        observed = "No retry ran for this request."
        return _waiting(check.Finding("1B", TITLE, check.NOT_YET, EXPECTED, observed, evidence,
                                      NEXT_REQUEST))
    # The scenario, not the extractor's own output, is the oracle. An initial
    # plan and a retry that both omit the same requirement must not pass.
    scenario = {"price": 100.0, "in_stock": True, "exclusions": ["candle"], "categories": []}
    missing = dropped(scenario, requested)
    if missing:
        finding = check.Finding("1B", TITLE, check.FAILED, EXPECTED,
                                "the initial reading omitted " + ", ".join(missing),
                                evidence, NEXT_REQUEST)
        rule = check.Rule("Anna's request was read in full", ok=False,
                          expected="budget, stock and exclusion all read",
                          observed="the first reading omitted " + ", ".join(missing),
                          next_step=SHORT_NEXT_SEND)
        return check.with_rules(finding, HEADLINE, [rule])
    lost = dropped(requested, kept_limits(receipt))
    if broken_lines or lost:
        observed = f"{len(ids) - len(broken_lines)} of {len(ids)} keep every requirement asked for"
        if broken_lines:
            observed += "; " + "; ".join(broken_lines)
        if lost:
            observed += "; the search that answered dropped " + ", ".join(lost)
        finding = check.Finding("1B", TITLE, check.FAILED, EXPECTED, observed, evidence,
                                NEXT_STEP)
        return check.with_rules(finding, HEADLINE,
                                _fail_rules(requested, ids, broken_lines, lost))
    finding = check.Finding("1B", TITLE, check.PASSED, EXPECTED,
                            f"all {len(ids)} keep {', '.join(phrases(requested))} after the "
                            "retry", evidence)
    told = check.with_rules(finding, HEADLINE, _pass_rules(receipt, requested, len(ids)))
    told.summary = pass_summary(requested, len(ids))
    told.data["requested"] = requested
    return told


def run(env_path: pathlib.Path = check.DEFAULT_ENV) -> Tuple[check.Finding, List[Sequence[Any]]]:
    """Connect with the backend's settings and evaluate; never raises."""
    cfg = check.db_config(env_path)
    if cfg is None:
        return check.Finding("1B", TITLE, check.COULD_NOT_CHECK, EXPECTED,
                             "the check could not look",
                             [check.missing_settings_reason(env_path)]), []
    try:
        with check.connect(cfg) as conn:
            return evaluate(conn, timeline())
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return check.Finding("1B", TITLE, check.COULD_NOT_CHECK, EXPECTED,
                             "the check could not look",
                             [f"{type(exc).__name__}: {str(exc)[:160]}"],
                             "check that the database in pellier/backend/.env is reachable."), []


def main(argv: Optional[Sequence[str]] = None) -> int:
    if check.refuse_missing_lab_file(1):
        return 1
    finding, rows = run()
    tables = [check.wrapped("", "Lab 1B: every product in Anna's latest search keeps the "
                                "requirements she asked for")]
    if rows:
        tables.append(check.table(("product", "name", "price", "in stock", "verdict"), rows))
    requested = getattr(finding, "data", {}).get("requested")
    after = (after_pass(requested, lab_1_complete())
             if finding.state == check.PASSED and requested else [])
    return 0 if check.emit(finding, argv, "Lab 1B check", "1B", tables, after=after) else 1
