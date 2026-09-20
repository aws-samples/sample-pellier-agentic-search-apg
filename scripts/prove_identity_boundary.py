#!/usr/bin/env python3
"""Prove that identity, not intent, decides whether a governed write executes.

This command produces the return and RLS subset of the Lab 4 boundary proof.
The combined driver is prove_governance_outcomes.py. Nothing here is guessed
by the operator and nothing is inferred from a time window.

Section 1 — Cedar, four cases targeting the same customer
---------------------------------------------------------

Every case targets the same protected customer::

    initiate_return(customer_id="CUST-JESSICA", product_id=<resolved>, reason="damaged")

Four attempts, four different outcomes, so each layer is seen doing its own job:

    marco   -> DENY    another shopper targets Jessica: one keyed policy receipt,
                       zero execution, zero effect (permission)
    jessica -> REFUSE  Jessica asks for a piece she never ordered: Cedar allows,
                       the tool runs, the business rule refuses, no committed
                       return (eligibility, which policy cannot judge)
    jessica -> ALLOW   one keyed policy receipt, one execution, one canonical effect
    jessica -> replay  same idempotency key: second receipt, no second effect

The canonical effect is exactly one ``pellier.write_operations`` row. That table
is keyed by ``idempotency_key`` as its primary key, so "exactly one" is enforced
by PostgreSQL rather than asserted by this script — which is what makes the
replay case a real test instead of a restatement.

Section 2 — Aurora, the same question with Cedar out of the picture
------------------------------------------------------------------

The interesting asymmetry, and the reason two layers is not rhetoric::

    unauthorized read   -> empty result   (the USING clause filters)
    unauthorized write  -> error, rollback (the WITH CHECK clause refuses)

Both run as ``pellier_agent``, which is ``NOBYPASSRLS`` and not the table owner.
Cedar is not consulted for either.

Why a storefront persona never appears here
-------------------------------------------

Choosing Marco, Anna, or Theo in Pellier selects a workshop scenario and
authenticates nobody. Jessica is an Operator client and Lab 4 Cognito principal,
not a fourth Storefront selector. Every identity below comes from a Cognito
access token the Gateway validated. Keeping those roles apart is the lesson.

Nothing printed here is an access token, a password, or a Secrets Manager value.
Subjects are truncated for display.

Usage::

    python3 scripts/prove_identity_boundary.py
    python3 scripts/prove_identity_boundary.py --product-id 7
    python3 scripts/prove_identity_boundary.py --json evidence.json
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple

_REPO = pathlib.Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "pellier" / "backend"
_GATEWAY_CALLER = _REPO / "scripts" / "deploy" / "gateway_initiate_return.py"

# The owner of the return being attempted. Every case sends this same value;
# the business-refusal case uses a product Jessica never ordered.
TARGET_CUSTOMER = "CUST-JESSICA"

# The runtime role the Aurora section assumes. Not the table owner, and
# NOBYPASSRLS, so the policies actually apply to it.
RUNTIME_ROLE = "pellier_agent"

_EXIT_OK = 0
_EXIT_PROOF_FAILED = 1
_EXIT_UNCONFIGURED = 3


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def _load_env(path: pathlib.Path) -> Dict[str, str]:
    """Parse a dotenv file without shell interpolation.

    Sourcing through a shell would word-split a password containing shell
    metacharacters and could echo it into a log.
    """
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _quote(value: str) -> str:
    """Single-quote a literal for psql -c, doubling embedded quotes."""
    return "'" + str(value).replace("'", "''") + "'"


def _psql(cfg: Dict[str, str], sql: str, *, role: Optional[str] = None) -> Tuple[int, str, str]:
    """Run one statement through psql, passing the password via the env only."""
    child = os.environ.copy()
    child["PGPASSWORD"] = cfg.get("DB_PASSWORD", "")
    if role:
        sql = f"SET ROLE {role}; {sql}"
    result = subprocess.run(
        [
            "psql",
            "-h", cfg["DB_HOST"],
            "-p", cfg.get("DB_PORT", "5432"),
            "-U", cfg["DB_USER"],
            "-d", cfg["DB_NAME"],
            "-X", "-q", "-A", "-t",
            "-v", "ON_ERROR_STOP=1",
            "-c", sql,
        ],
        env=child,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _scalar(cfg: Dict[str, str], sql: str) -> Optional[str]:
    code, out, _err = _psql(cfg, sql)
    if code != 0:
        return None
    rows = [line for line in out.splitlines() if line.strip()]
    return rows[-1] if rows else None


def _truncate_sub(sub: str) -> str:
    """Show enough of a subject to correlate it, not enough to reuse it."""
    clean = (sub or "").strip()
    return clean if len(clean) <= 12 else f"{clean[:8]}…{clean[-4:]}"


# ---------------------------------------------------------------------------
# Preflight: pick a product the ALLOW case can actually return
# ---------------------------------------------------------------------------


def _eligible_products(cfg: Dict[str, str]) -> List[Tuple[int, str]]:
    """Products on Jessica's authoritative order rows, lowest product id first.

    Authoritative because it reads the order rows, not a fixture list: if the
    seed changes the proof follows it instead of failing on a stale literal.
    Ordered so repeated runs pick the same product and stay comparable.
    """
    # Keep the legacy bare-alias fallback because older workshop datasets used
    # that shape for Theo. Jessica's current seed is canonical-only, so the
    # first predicate is the one expected to match in Lab 4.
    alias = TARGET_CUSTOMER.split("-", 1)[-1].lower()
    owner_filter = (
        f"(o.customer_id = {_quote(TARGET_CUSTOMER)} OR lower(o.customer_id) = {_quote(alias)})"
    )
    code, out, _err = _psql(
        cfg,
        "SELECT o.product_id, pc.name "
        "  FROM pellier.orders o "
        "  JOIN pellier.product_catalog pc ON pc.product_id = o.product_id "
        f" WHERE {owner_filter} "
        " GROUP BY o.customer_id, o.product_id, pc.name "
        " HAVING sum(o.quantity) > ("
        "   SELECT COALESCE(sum(r.quantity), 0) FROM pellier.returns r"
        "   WHERE r.customer_id = o.customer_id AND r.product_id = o.product_id"
        "     AND r.status <> 'rejected') "
        " ORDER BY o.product_id",
    )
    if code != 0:
        return []
    products: List[Tuple[int, str]] = []
    for line in out.splitlines():
        if "|" not in line:
            continue
        raw_id, _, name = line.partition("|")
        if raw_id.strip().isdigit():
            products.append((int(raw_id.strip()), name.strip()))
    return products


def _ineligible_product(cfg: Dict[str, str]) -> Optional[int]:
    """A piece Jessica never ordered, lowest curated id first.

    The business-refusal case needs a request that policy permits and the
    business rule refuses. "Never ordered" is that rule's clearest form, and
    reading it from the order rows keeps the case true after a reseed.
    """
    alias = TARGET_CUSTOMER.split("-", 1)[-1].lower()
    owner_filter = (
        f"(o.customer_id = {_quote(TARGET_CUSTOMER)} OR lower(o.customer_id) = {_quote(alias)})"
    )
    value = _scalar(
        cfg,
        "SELECT min(pc.product_id) "
        "  FROM pellier.product_catalog pc "
        " WHERE NOT (pc.tags ? 'archive') "
        "   AND pc.product_id NOT IN ("
        f"       SELECT o.product_id FROM pellier.orders o WHERE {owner_filter})",
    )
    return int(value) if value and str(value).strip().isdigit() else None


def _resolve_product(
    cfg: Dict[str, str], requested: Optional[int]
) -> Tuple[Optional[int], List[Tuple[int, str]], str]:
    """Choose or validate the product, before anything is invoked.

    Returns ``(product_id, candidates, note)``. A requested id that Jessica does not
    own is refused with the eligible list, so the operator never has to guess and
    never discovers the mistake as a confusing DENY.
    """
    candidates = _eligible_products(cfg)
    if not candidates:
        return None, [], (
            f"No unreturned ordered quantity remains for {TARGET_CUSTOMER}; the "
            "ALLOW case cannot succeed. Use an authorized fresh workshop dataset; "
            "do not delete prior evidence or add orders just to pass the proof."
        )
    owned = {pid for pid, _name in candidates}
    if requested is None:
        # Deterministic: lowest owned product id, so repeated runs are comparable.
        chosen = sorted(owned)[0]
        name = next(n for pid, n in candidates if pid == chosen)
        return chosen, candidates, f"resolved from {TARGET_CUSTOMER}'s orders: {chosen} ({name})"
    if requested not in owned:
        return None, candidates, (
            f"product {requested} has no unreturned quantity on a {TARGET_CUSTOMER} "
            "order, so an ALLOW is impossible and a DENY would prove nothing about identity."
        )
    name = next(n for pid, n in candidates if pid == requested)
    return requested, candidates, f"validated against {TARGET_CUSTOMER}'s orders: {requested} ({name})"


# ---------------------------------------------------------------------------
# Section 1: Cedar, four cases
# ---------------------------------------------------------------------------


def _invoke(
    *,
    username: str,
    product_id: int,
    receipt_key: str,
    idempotency_key: str,
    expect: str,
    extra_env: Dict[str, str],
) -> Dict[str, Any]:
    """Invoke the protected tool once as one named principal."""
    cmd = [
        sys.executable, str(_GATEWAY_CALLER),
        "--user", username,
        "--customer-id", TARGET_CUSTOMER,
        "--product-id", str(product_id),
        "--reason", "damaged",
        "--expect", expect,
        # A receipt records one invocation. A replay is a second invocation of
        # the same idempotency key, so its receipt key must stay distinct.
        "--session-id", receipt_key,
        "--idempotency-key", idempotency_key,
        "--record-receipt",
    ]
    env = os.environ.copy()
    env.update(extra_env)
    # An inherited PELLIER_TOKEN would make every case the same principal. The
    # caller now refuses --user alongside it, so removing it here keeps the
    # driver working rather than relying on that error.
    env.pop("PELLIER_TOKEN", None)
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    payload: Dict[str, Any] = {}
    stdout = proc.stdout.strip()
    if "{" in stdout:
        try:
            payload = json.loads(stdout[stdout.index("{"):])
        except (ValueError, json.JSONDecodeError):
            payload = {}
    tool_status = ""
    tool_message = ""
    result = payload.get("tool_result") or payload.get("result") or {}
    for block in (result.get("content") or []) if isinstance(result, dict) else []:
        text = block.get("text") if isinstance(block, dict) else None
        if not text:
            continue
        try:
            body = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(body, dict):
            tool_status = str(body.get("status") or "")
            tool_message = str(body.get("message") or "")[:200]
            break
    return {
        "observed_outcome": payload.get("outcome", "unknown"),
        "tool_status": tool_status,
        "tool_message": tool_message,
        "exit_code": proc.returncode,
        "stderr": proc.stderr.strip()[:400],
    }


def _keyed_evidence(
    cfg: Dict[str, str], *, receipt_key: str, idempotency_key: str
) -> Dict[str, Any]:
    """The complete evidence contract for one invocation and one write key.

    A receipt key names exactly one Gateway invocation. The idempotency key
    names the durable write it attempted. They are identical for a first
    attempt and intentionally differ for a replay, which is another invocation
    of an existing write. Absence is only ever claimed for a searched key.
    """
    code, out, err = _psql(
        cfg,
        "SELECT "
        f"  (SELECT count(*) FROM pellier.governed_receipts WHERE session_id = {_quote(receipt_key)}), "
        f"  (SELECT count(*) FROM pellier.tool_audit WHERE args->>'idempotency_key' = {_quote(idempotency_key)}), "
        f"  (SELECT count(*) FROM pellier.write_operations WHERE idempotency_key = {_quote(idempotency_key)}), "
        f"  (SELECT count(*) FROM pellier.write_operations "
        f"     WHERE idempotency_key = {_quote(idempotency_key)} "
        "       AND completed_at IS NOT NULL "
        "       AND result->>'status' = 'success'), "
        f"  (SELECT count(*) FROM pellier.inventory_ledger WHERE idempotency_key = {_quote(idempotency_key)}), "
        f"  (SELECT coalesce(string_agg(DISTINCT decision, ','), '') "
        f"     FROM pellier.governed_receipts WHERE session_id = {_quote(receipt_key)}), "
        "  (SELECT coalesce(ta.result->>'idempotent_replay', '') "
        "     FROM pellier.governed_receipts gr "
        "     LEFT JOIN pellier.tool_audit ta ON ta.audit_id = gr.audit_id "
        f"    WHERE gr.session_id = {_quote(receipt_key)} "
        "    ORDER BY gr.receipt_id DESC LIMIT 1)",
    )
    if code != 0:
        return {"queried": False, "error": err[:300]}
    parts = out.split("|")
    if len(parts) != 7:
        return {"queried": False, "error": f"unexpected psql output: {out!r}"}
    return {
        "queried": True,
        "policy_receipts": int(parts[0]),
        "execution_rows": int(parts[1]),
        "write_rows": int(parts[2]),
        "canonical_writes": int(parts[3]),
        "ledger_rows": int(parts[4]),
        "recorded_decision": parts[5].strip().upper(),
        "idempotent_replay": parts[6].strip().lower() == "true",
    }


def _return_evidence(cfg: Dict[str, str], idempotency_key: str) -> Dict[str, Any]:
    """Read the exact return referenced by one finalized write key.

    A product may have many historic returns. Joining through the durable write
    result is the only way to prove which domain row this invocation produced.
    """
    encoded = _scalar(
        cfg,
        "SELECT json_build_object("
        "         'return_id', r.id, "
        "         'customer_id', r.customer_id, "
        "         'product_id', r.product_id::integer, "
        "         'reason', r.reason"
        "       )::text "
        "  FROM pellier.write_operations wo "
        "  JOIN pellier.returns r "
        "    ON r.id = CASE "
        "         WHEN coalesce(wo.result->>'return_id', '') ~ '^[0-9]+$' "
        "         THEN (wo.result->>'return_id')::bigint "
        "       END "
        f" WHERE wo.idempotency_key = {_quote(idempotency_key)} "
        "   AND wo.completed_at IS NOT NULL "
        "   AND wo.result->>'status' = 'success' "
        " LIMIT 1",
    )
    if not encoded:
        return {}
    try:
        value = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _verdict(case: Dict[str, Any], ev: Dict[str, Any]) -> Tuple[bool, str]:
    """Whether one case proved what it claimed."""
    if not ev.get("queried"):
        return False, f"could not read keyed evidence: {ev.get('error', 'unknown')}"
    expect = case["expected_outcome"]
    if case["observed_outcome"] != expect:
        return False, f"expected {expect}, observed {case['observed_outcome']}"

    receipts = ev["policy_receipts"]
    execs = ev["execution_rows"]
    write_rows = ev["write_rows"]
    writes = ev["canonical_writes"]

    if receipts != 1:
        return False, f"expected exactly one keyed policy receipt, found {receipts}"

    if case["kind"] == "deny":
        if ev["recorded_decision"] != "DENY":
            return False, f"receipt records {ev['recorded_decision']!r}, not DENY"
        if execs or write_rows or ev["ledger_rows"]:
            return False, (
                f"a refusal must leave nothing under its key: {execs} execution / "
                f"{write_rows} write / {ev['ledger_rows']} ledger rows"
            )
        return True, "refused before execution; no artifact carries this key"

    if case["kind"] == "refuse":
        # Permission and eligibility are different judges. Cedar allowed the
        # owner; the tool ran; the business rule refused; nothing committed.
        if ev["recorded_decision"] != "ALLOW":
            return False, f"receipt records {ev['recorded_decision']!r}, not ALLOW"
        if execs != 1:
            return False, f"expected exactly one execution row, found {execs}"
        if writes or ev["ledger_rows"]:
            return False, (
                f"a business refusal must commit nothing: {writes} finalized write / "
                f"{ev['ledger_rows']} ledger rows"
            )
        if case.get("tool_status") != "error":
            return False, (
                f"expected the tool to refuse with status 'error', got "
                f"{case.get('tool_status')!r} ({case.get('tool_message')!r})"
            )
        if case.get("domain_return"):
            return False, "a refused request produced a return row"
        return True, "permitted, executed, refused by the business rule; nothing committed"
    domain_return = case.get("domain_return") or {}
    expected_product = case.get("product_id")
    domain_matches = (
        domain_return.get("customer_id") == TARGET_CUSTOMER
        and domain_return.get("product_id") == expected_product
        and domain_return.get("reason") == "damaged"
    )

    if case["kind"] == "allow":
        if ev["recorded_decision"] != "ALLOW":
            return False, f"receipt records {ev['recorded_decision']!r}, not ALLOW"
        if execs != 1:
            return False, f"expected exactly one execution row, found {execs}"
        if write_rows != 1:
            return False, f"expected exactly one keyed write row, found {write_rows}"
        if writes != 1:
            return False, f"expected exactly one finalized successful write, found {writes}"
        if not domain_matches:
            return False, (
                "the finalized write did not reference the requested return "
                f"(found {domain_return!r})"
            )
        return True, f"executed once, one finalized write, row owned by {TARGET_CUSTOMER}"

    # Replay: a new invocation and receipt, but the same durable write key.
    if ev["recorded_decision"] != "ALLOW":
        return False, f"receipt records {ev['recorded_decision']!r}, not ALLOW"
    if case.get("first_execution_count") is not None and execs != case["first_execution_count"] + 1:
        return False, (
            "replay did not produce exactly one additional execution row "
            f"({execs} rows after {case['first_execution_count']} before)"
        )
    if write_rows != 1:
        return False, f"replay created {write_rows} keyed write rows for one key"
    if writes != 1:
        return False, f"replay created a second finalized write ({writes} rows for one key)"
    if case.get("first_write_count") is not None and writes != case["first_write_count"]:
        return False, "replay changed the canonical write count"
    if not ev["idempotent_replay"]:
        return False, "the second invocation did not report an idempotent replay"
    if not domain_matches:
        return False, (
            "the finalized write did not reference the requested return "
            f"(found {domain_return!r})"
        )
    return True, "a second invocation replayed one durable write; state stayed singular"


# ---------------------------------------------------------------------------
# Section 2: Aurora, read scoping and the write-side refusal
# ---------------------------------------------------------------------------


def _receipt_subs(cfg: Dict[str, str], cases: List[Dict[str, Any]]) -> Dict[str, str]:
    """Recover each tested principal's verified subject from its receipt.

    `principal_customers` intentionally permits several logins for one
    customer. Reading an arbitrary row for `CUST-MARCO` would no longer prove
    that the RLS probe used the same Marco who signed the Gateway request. The
    append-only receipt has the exact Cognito-validated subject for this run.
    """
    receipt_keys = [case["receipt_key"] for case in cases]
    if not receipt_keys:
        return {}
    key_list = ", ".join(_quote(key) for key in receipt_keys)
    code, out, _err = _psql(
        cfg,
        "SELECT verified_username || '|' || verified_subject "
        "  FROM pellier.governed_receipts "
        f" WHERE session_id IN ({key_list}) "
        "   AND verified_username IS NOT NULL "
        "   AND verified_subject IS NOT NULL",
    )
    subjects_by_username: Dict[str, set[str]] = {}
    if code == 0:
        for line in out.splitlines():
            if "|" not in line:
                continue
            username, _, subject = line.partition("|")
            clean_username = username.strip().lower()
            clean_subject = subject.strip()
            if clean_username and clean_subject:
                subjects_by_username.setdefault(clean_username, set()).add(clean_subject)
    return {
        username: next(iter(subjects))
        for username, subjects in subjects_by_username.items()
        if len(subjects) == 1
    }


def _rls_read(cfg: Dict[str, str], sub: str) -> Dict[str, Any]:
    """How many of the target's orders this subject can see. Empty is the denial."""
    code, out, err = _psql(
        cfg,
        "BEGIN; "
        f"SELECT set_config('pellier.principal_sub', {_quote(sub)}, true); "
        f"SELECT count(*) FROM pellier.orders WHERE customer_id = {_quote(TARGET_CUSTOMER)}; "
        "COMMIT;",
        role=RUNTIME_ROLE,
    )
    if code != 0:
        return {"queried": False, "error": err[:300]}
    rows = [line for line in out.splitlines() if line.strip().isdigit()]
    return {"queried": True, "visible_rows": int(rows[-1]) if rows else -1}


def _rls_write(cfg: Dict[str, str], sub: str, product_id: int) -> Dict[str, Any]:
    """Attempt a scoped INSERT and prove the exact RLS refusal.

    Always rolled back, including on success: this proves the boundary, it does
    not mutate the workshop's data.
    """
    code, _out, err = _psql(
        cfg,
        "BEGIN; "
        "SELECT CASE WHEN current_user = 'pellier_agent' "
        "            THEN 'RLS_PROBE_ROLE_OK' ELSE 'RLS_PROBE_ROLE_WRONG' END; "
        f"SELECT set_config('pellier.principal_sub', {_quote(sub)}, true); "
        "DO $probe$ "
        "DECLARE v_message TEXT; "
        "BEGIN "
        "  BEGIN "
        "    INSERT INTO pellier.returns (customer_id, product_id, reason, quantity) "
        f"    VALUES ({_quote(TARGET_CUSTOMER)}, {product_id}, 'other', 1); "
        "    RAISE NOTICE 'RLS_PROBE_SQLSTATE:00000'; "
        "  EXCEPTION WHEN insufficient_privilege THEN "
        "    GET STACKED DIAGNOSTICS v_message = MESSAGE_TEXT; "
        "    IF position('row-level security policy' IN v_message) > 0 THEN "
        "      RAISE NOTICE 'RLS_PROBE_SQLSTATE:%', SQLSTATE; "
        "    ELSE "
        "      RAISE NOTICE 'RLS_PROBE_OTHER_42501:%', v_message; "
        "    END IF; "
        "  END; "
        "END; "
        "$probe$; "
        "ROLLBACK;",
        role=RUNTIME_ROLE,
    )
    marker = "RLS_PROBE_SQLSTATE:42501"
    if code != 0:
        return {
            "queried": False,
            "refused": False,
            "sqlstate": "other",
            "error": err.splitlines()[0][:200] if err else "psql failed",
        }
    role_ok = "RLS_PROBE_ROLE_OK" in _out
    refused = role_ok and marker in err
    permitted = role_ok and "RLS_PROBE_SQLSTATE:00000" in err
    return {
        "queried": role_ok and (refused or permitted),
        "refused": refused,
        "sqlstate": "42501" if refused else "00000" if permitted else "other",
        "error": (
            ""
            if refused or permitted
            else ("runtime role was not pellier_agent" if not role_ok else err.splitlines()[0][:200])
        ),
    }


def _aurora_section(cfg: Dict[str, str], subs: Dict[str, str], product_id: int) -> List[Dict[str, Any]]:
    """Read scoping and write refusal, for the wrong principal and the right one."""
    probes: List[Dict[str, Any]] = []
    for username, expect_visible, expect_write in (
        ("marco", False, False),
        ("jessica", True, True),
    ):
        sub = subs.get(username, "")
        if not sub:
            probes.append(
                {"username": username, "queried": False, "error": "no mapped subject"}
            )
            continue
        read = _rls_read(cfg, sub)
        write = _rls_write(cfg, sub, product_id)
        read_ok = read.get("queried") and (
            (read["visible_rows"] > 0) if expect_visible else (read["visible_rows"] == 0)
        )
        write_ok = write.get("queried") and (
            (not write["refused"])
            if expect_write
            else (write["refused"] and write.get("sqlstate") == "42501")
        )
        probes.append(
            {
                "username": username,
                "queried": True,
                "principal_sub": _truncate_sub(sub),
                "role": RUNTIME_ROLE,
                "read_visible_rows": read.get("visible_rows"),
                "read_expected": "non-empty" if expect_visible else "empty",
                "read_passed": bool(read_ok),
                "write_refused": write.get("refused"),
                "write_sqlstate": write.get("sqlstate"),
                "write_expected": "permitted" if expect_write else "error and rollback",
                "write_passed": bool(write_ok),
                "passed": bool(read_ok and write_ok),
            }
        )
    return probes


# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prove Cedar and Aurora each enforce customer ownership, using three "
            "authenticated Cognito principals, one identical tool input, and a replay."
        )
    )
    parser.add_argument(
        "--product-id",
        type=int,
        default=None,
        help=(
            "Optional. A product Jessica actually ordered. Resolved from her order "
            "rows when omitted; validated against them when supplied."
        ),
    )
    parser.add_argument("--env", default=str(_BACKEND / ".env"))
    parser.add_argument("--json", default="", metavar="PATH")
    parser.add_argument(
        "--skip-aurora",
        action="store_true",
        help="Run only the Cedar section (section 2 needs migration 016's RLS roles).",
    )
    args = parser.parse_args(argv)

    cfg = _load_env(pathlib.Path(args.env))
    cfg.update({k: v for k, v in os.environ.items() if k.startswith(("DB_", "COGNITO_", "AWS_"))})

    missing = [k for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not cfg.get(k)]
    if missing:
        print(f"Database not configured (missing {', '.join(missing)}).")
        return _EXIT_UNCONFIGURED
    if not _GATEWAY_CALLER.is_file():
        print(f"Missing {_GATEWAY_CALLER}.")
        return _EXIT_UNCONFIGURED

    product_id, candidates, note = _resolve_product(cfg, args.product_id)
    print("Preflight")
    print(f"  {note}")
    if product_id is None:
        if candidates:
            print(f"  eligible {TARGET_CUSTOMER} products:")
            for pid, name in candidates:
                print(f"    {pid:>4}  {name}")
        print("\nNOT PROVED")
        return _EXIT_PROOF_FAILED

    run_id = uuid.uuid4().hex[:10]
    gateway_env = {k: v for k, v in cfg.items() if k.startswith(("COGNITO_", "AWS_", "DB_"))}
    allow_key = f"identity-boundary-{run_id}-jessica"
    replay_receipt_key = f"identity-boundary-{run_id}-jessica-replay"

    ineligible_product = _ineligible_product(cfg)
    if ineligible_product is None:
        print(f"FAIL  could not find a curated product {TARGET_CUSTOMER} never ordered")
        return 2
    cases: List[Dict[str, Any]] = [
        {"kind": "deny", "username": "marco", "expected_outcome": "deny",
         "receipt_key": f"identity-boundary-{run_id}-marco",
         "idempotency_key": f"identity-boundary-{run_id}-marco"},
        # Same owner, a piece she never ordered. Cedar permits the owner; the
        # business rule refuses; nothing commits. Policy cannot make this call.
        {"kind": "refuse", "username": "jessica", "expected_outcome": "allow",
         "product_id": ineligible_product,
         "receipt_key": f"identity-boundary-{run_id}-jessica-ineligible",
         "idempotency_key": f"identity-boundary-{run_id}-jessica-ineligible"},
        {"kind": "allow", "username": "jessica", "expected_outcome": "allow",
         "receipt_key": allow_key, "idempotency_key": allow_key},
        # A distinct receipt proves a second invocation; the write key remains
        # the same on purpose so the replay cannot create a second effect.
        {"kind": "replay", "username": "jessica", "expected_outcome": "allow",
         "receipt_key": replay_receipt_key, "idempotency_key": allow_key},
    ]

    print(f"\nSection 1: Cedar and return outcomes, run {run_id}")
    print(f"  target customer: {TARGET_CUSTOMER}; returnable product: {product_id}")
    print("  deny and allow compare principals; refusal uses an unowned product")
    print("  replay repeats the allowed write key\n")

    all_passed = True
    first_execution_count: Optional[int] = None
    first_write_count: Optional[int] = None
    aurora: List[Dict[str, Any]] = []
    for case in cases:
        if case["kind"] == "allow" and not args.skip_aurora:
            # The deny/refuse receipts already establish both subjects. Probe
            # INSERT under RLS before the one committed return can consume the
            # last eligible unit. Both RLS probes always roll back.
            aurora = _aurora_section(cfg, _receipt_subs(cfg, cases[:2]), product_id)
        result = _invoke(
            username=case["username"],
            product_id=case.get("product_id", product_id),
            receipt_key=case["receipt_key"],
            idempotency_key=case["idempotency_key"],
            expect=case["expected_outcome"],
            extra_env=gateway_env,
        )
        case.update(result)
        ev = _keyed_evidence(
            cfg,
            receipt_key=case["receipt_key"],
            idempotency_key=case["idempotency_key"],
        )
        if case["kind"] == "refuse":
            case["domain_return"] = _return_evidence(cfg, case["idempotency_key"])
        if case["kind"] == "allow":
            case["domain_return"] = _return_evidence(cfg, case["idempotency_key"])
            case["product_id"] = product_id
            first_execution_count = ev.get("execution_rows")
            first_write_count = ev.get("canonical_writes")
        if case["kind"] == "replay":
            case["domain_return"] = _return_evidence(cfg, case["idempotency_key"])
            case["product_id"] = product_id
            case["first_write_count"] = first_write_count
            case["first_execution_count"] = first_execution_count
        passed, why = _verdict(case, ev)
        all_passed = all_passed and passed
        case["keyed_evidence"] = ev
        case["passed"] = passed
        case["note"] = why
        label = {"deny": "deny ", "refuse": "refuse"}.get(case["kind"], case["kind"])
        print(f"  [{'PASS' if passed else 'FAIL'}] {case['username']:<6} {label:<7} "
              f"-> {case['observed_outcome']:<7} {why}")
        print(f"         receipt {case['receipt_key']}")
        print(f"         write   {case['idempotency_key']}")

    if not args.skip_aurora:
        print(f"\nSection 2: Aurora, role {RUNTIME_ROLE}, Cedar not consulted")
        print("  unauthorized read -> empty result; unauthorized write -> error and rollback\n")
        for probe in aurora:
            if not probe.get("queried"):
                all_passed = False
                print(f"  [FAIL] {probe['username']:<6} {probe.get('error')}")
                continue
            all_passed = all_passed and probe["passed"]
            print(f"  [{'PASS' if probe['passed'] else 'FAIL'}] {probe['username']:<6} "
                  f"sub {probe['principal_sub']}")
            print(f"         read  {probe['read_visible_rows']} rows "
                  f"(expected {probe['read_expected']})")
            print(f"         write {'refused ' + probe['write_sqlstate'] if probe['write_refused'] else 'permitted'} "
                  f"(expected {probe['write_expected']})")

    bundle = {
        "run_id": run_id,
        "target_customer_id": TARGET_CUSTOMER,
        "product_id": product_id,
        "preflight": note,
        "cases": cases,
        "aurora": aurora,
        "passed": all_passed,
    }
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(bundle, indent=2, sort_keys=True, default=str))
        print(f"\nEvidence bundle: {args.json}")

    print("\n" + ("PROVED" if all_passed else "NOT PROVED"))
    if all_passed:
        print("  Cedar refused the cross-customer request. The owner's unowned product")
        print("  was refused by the business rule. The eligible return committed once,")
        print("  replay added no effect, and Aurora independently enforced ownership.")
    return _EXIT_OK if all_passed else _EXIT_PROOF_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
