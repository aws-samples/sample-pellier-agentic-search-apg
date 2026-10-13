#!/usr/bin/env python3
"""Lab 3B, live: your deployed predicate stops a wrong query on both database paths.

``workshop/lab-3-rls.sql`` probes your predicate and, when every probe matches,
commits it as the live policy on ``orders_owner`` and ``support_tickets_owner``,
commented with its sha256. This check first confirms both live policies carry
the predicate now in your file, so the policies it probes are yours and not the
ones the database shipped with. Then it probes them through each way Pellier
binds a customer before it reads their rows:

    in process   DatabaseService.principal_session, which Ask Pellier and the
                 Operator's Investigator use
    Gateway      bind_runtime_principal over the RDS Data API, which the
                 store-tools Lambda uses for get_orders and get_tickets

Each path binds Theo, then asks for what a correct tool never would: Jessica's
orders and tickets, and a new ticket in her name. Row-level security must
return none of her rows and refuse the write (SQLSTATE 42501), while Theo's own
tickets still come back. Every probe ends in a rollback, so nothing is kept.

Row-level security stops a wrong query; it does not choose the customer.
On the Gateway path the Lambda binds the customer the call carries, which
Cedar's owner-only permit has already matched to the caller's token (Task 3A).

    python3 scripts/lab3_rls_check.py
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import pathlib
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import workshop_check as check  # noqa: E402  (sibling module)

REPO = check.REPO
BACKEND = REPO / "pellier" / "backend"
DEPLOY = SCRIPTS / "deploy"

THEO_USERNAME, THEO = "theo", "CUST-THEO"

WORKSHEET = REPO / "workshop" / "lab-3-rls.sql"
STARTER = REPO / "workshop" / "starters" / "lab-3-rls.sql"
REGION = "Row ownership - predicate"
STAMP_PREFIX = "Lab 3B predicate sha256 "
POLICY_NAMES = ("orders_owner", "support_tickets_owner")
RUN_WORKSHEET = "psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-3-rls.sql"
DEPLOYED_TITLE = "your predicate is the live policy on both tables"
DEPLOYED_EXPECTED = ("orders_owner and support_tickets_owner carry the predicate now in "
                     "workshop/lab-3-rls.sql, committed by its passing run")
DEPLOYED_SQL = """
SELECT pol.polname AS policy,
       coalesce(obj_description(pol.oid, 'pg_policy'), '') AS stamp,
       pg_get_expr(pol.polqual, pol.polrelid) AS qual,
       pg_get_expr(pol.polwithcheck, pol.polrelid) AS with_check
  FROM pg_policy pol
  JOIN pg_class c ON c.oid = pol.polrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'pellier' AND pol.polname IN ('orders_owner', 'support_tickets_owner')
"""

# What each probe asks for, bound as Theo. The first is his own; the rest are a
# wrong query's: rows a correct tool, filtering by the bound customer, never reads.
READS: Tuple[Tuple[str, str], ...] = (
    ("Theo's own tickets",
     "SELECT count(*) AS n FROM pellier.support_tickets WHERE customer_id = 'CUST-THEO'"),
    ("Jessica's orders",
     "SELECT count(*) AS n FROM pellier.orders WHERE customer_id = 'CUST-JESSICA'"),
    ("Jessica's tickets",
     "SELECT count(*) AS n FROM pellier.support_tickets WHERE customer_id = 'CUST-JESSICA'"),
)
WRITE_LABEL = "a new ticket in Jessica's name"
WRITE_JESSICA = (
    "INSERT INTO pellier.support_tickets (ticket_id, customer_id, subject, status, channel) "
    "VALUES ('TKT-LAB3-LIVE', 'CUST-JESSICA', 'Lab 3 live row-level security probe', "
    "'open', 'chat')"
)
REFUSED, WRITTEN = "42501", "00000"
# A write that failed for any other reason (a lost connection, throttling) says
# nothing about the policy, so it makes the path UNCHECKED rather than wrong.
ERROR = "error:"

EXPECTED = ("bound as Theo: his own tickets come back, none of Jessica's orders or tickets "
            "do, and a ticket written in her name is refused with 42501")
_PATHS = {
    "in process": "DatabaseService.principal_session (Ask Pellier, the Operator)",
    "Gateway": "bind_runtime_principal over the RDS Data API (the store-tools Lambda)",
}


class _Undo(Exception):
    """Raised inside a transaction so it ends in a rollback."""


# ---------------------------------------------------------------------------
# Deployed: the live policies carry the predicate in the participant's file
# ---------------------------------------------------------------------------


def file_stamp(worksheet: bytes) -> Optional[str]:
    """The comment a passing run leaves on both policies, from the file's own bytes.

    psql hashes the text between the two ``$predicate$`` quotes exactly as read,
    so the file is read as bytes, without newline translation.
    """
    parts = worksheet.decode("utf-8").split("$predicate$")
    if len(parts) < 3:
        return None
    return STAMP_PREFIX + hashlib.sha256(parts[1].encode("utf-8")).hexdigest()


def _stamp_line(policy: str, comment: str) -> str:
    if comment.startswith(STAMP_PREFIX):
        return f"{policy}: sha256 {comment[len(STAMP_PREFIX):][:12]}..."
    return f"{policy}: no Lab 3B comment"


def judge_deployed(stamp: Optional[str], is_starter: bool,
                   deployed: Dict[str, str]) -> check.Finding:
    """Whether both live policies carry the predicate now in the worksheet.

    Args:
        stamp: ``file_stamp`` of the worksheet, or None when its region is gone.
        is_starter: The region still holds the starter predicate.
        deployed: Each policy's comment, empty when it has none.
    """
    if stamp is None:
        return check.Finding("3B", DEPLOYED_TITLE, check.UNCHECKED, DEPLOYED_EXPECTED,
                             "the worksheet's predicate region could not be read",
                             ["workshop/lab-3-rls.sql: no $predicate$ quotes"],
                             "restore the region from workshop/starters/lab-3-rls.sql.")
    if is_starter:
        return check.Finding("3B", DEPLOYED_TITLE, check.NOT_YET, DEPLOYED_EXPECTED,
                             "the worksheet still holds the starter predicate",
                             ["workshop/lab-3-rls.sql: Row ownership - predicate is false"],
                             "write the predicate in workshop/lab-3-rls.sql, then run "
                             f"{RUN_WORKSHEET}.")
    short = stamp[len(STAMP_PREFIX):][:12]
    evidence = [_stamp_line(name, deployed.get(name, "")) for name in POLICY_NAMES]
    evidence.append(f"workshop/lab-3-rls.sql: sha256 {short}...")
    if all(deployed.get(name) == stamp for name in POLICY_NAMES):
        return check.Finding("3B", DEPLOYED_TITLE, check.PROVED, DEPLOYED_EXPECTED,
                             f"both policies carry your predicate, sha256 {short}", evidence)
    if not any(deployed.get(name, "").startswith(STAMP_PREFIX) for name in POLICY_NAMES):
        return check.Finding("3B", DEPLOYED_TITLE, check.NOT_YET, DEPLOYED_EXPECTED,
                             "the live policies are still the ones the database shipped with",
                             evidence, f"run {RUN_WORKSHEET}; it deploys your predicate once "
                             "every probe matches.")
    return check.Finding("3B", DEPLOYED_TITLE, check.NOT_YET, DEPLOYED_EXPECTED,
                         "the live policies carry a different predicate from the one in your "
                         "file", evidence, f"your file changed after it was deployed; run "
                         f"{RUN_WORKSHEET} again.")


def deployed_policies(connect: Callable[[], Any]) -> Dict[str, Dict[str, str]]:
    """Each owner policy's comment and expressions, read from the catalog."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(DEPLOYED_SQL)
        names = [column.name for column in cur.description]
        rows = [row if isinstance(row, dict) else dict(zip(names, row)) for row in cur.fetchall()]
    return {row["policy"]: {key: row[key] or "" for key in ("stamp", "qual", "with_check")}
            for row in rows}


def deployed_finding(connect: Callable[[], Any],
                     worksheet: pathlib.Path = WORKSHEET) -> check.Finding:
    is_starter = check.region_state(worksheet, REGION, STARTER) == check.STARTER
    stamp = file_stamp(worksheet.read_bytes())
    policies = deployed_policies(connect)
    finding = judge_deployed(stamp, is_starter,
                             {name: row["stamp"] for name, row in policies.items()})
    qual = policies.get("orders_owner", {}).get("qual", "")
    if qual:
        finding.evidence.append(f"live USING on orders: {' '.join(qual.split())}")
    return finding


# ---------------------------------------------------------------------------
# The verdict, from what one path observed
# ---------------------------------------------------------------------------


def judge_path(path: str, observed: Dict[str, Any], own_tickets: int) -> check.Finding:
    """One path's verdict.

    Args:
        path: ``in process`` or ``Gateway``.
        observed: Each read's count by label, and the write's SQLSTATE under
            ``WRITE_LABEL``.
        own_tickets: Theo's tickets, counted as the owner, whom the policy
            does not bind.
    """
    title = f"{path} path: the live policy stops a wrong query"
    failed = str(observed.get(WRITE_LABEL, ""))
    if failed.startswith(ERROR):
        return check.Finding("3B", title, check.UNCHECKED, EXPECTED,
                             "the write probe failed for a reason other than the policy",
                             [f"{WRITE_LABEL}: {failed}"],
                             "check the database is reachable from this box, then run it again.")
    expected = {READS[0][0]: str(own_tickets), READS[1][0]: "0", READS[2][0]: "0",
                WRITE_LABEL: REFUSED}
    evidence = [f"bound as {THEO_USERNAME} through {_PATHS[path]}"]
    differs = []
    for label, want in expected.items():
        got = str(observed.get(label, "not read"))
        evidence.append(f"{label}: expected {want}, observed {got}")
        if got != want:
            differs.append(f"{label} came back {got}")
    if not differs:
        return check.Finding("3B", title, check.PROVED, EXPECTED,
                             f"{len(expected)} of {len(expected)} probes match", evidence)
    return check.Finding(
        "3B", title, check.CONTRADICTED, EXPECTED, "; ".join(differs), evidence,
        "read the live policies with: SELECT tablename, qual, with_check FROM pg_policies "
        "WHERE schemaname = 'pellier'. Compare them with the predicate your worksheet passed.")


def unchecked(path: str, exc: BaseException) -> check.Finding:
    return check.Finding("3B", f"{path} path: the live policy stops a wrong query",
                         check.UNCHECKED, EXPECTED, "the check could not run this path",
                         [f"{type(exc).__name__}: {str(exc)[:200]}"],
                         "run this on the workshop box, where pellier/backend/.env names "
                         "the cluster.")


def _unchecked_deployed(exc: BaseException) -> check.Finding:
    return check.Finding("3B", DEPLOYED_TITLE, check.UNCHECKED, DEPLOYED_EXPECTED,
                         "the check could not read the live policies",
                         [f"{type(exc).__name__}: {str(exc)[:200]}"],
                         "run this on the workshop box, where pellier/backend/.env names "
                         "the cluster.")


def _count(row: Any) -> int:
    return int(row["n"] if isinstance(row, dict) else row[0])


# ---------------------------------------------------------------------------
# In process: the same session Ask Pellier and the Operator open
# ---------------------------------------------------------------------------


async def probe_in_process(db: Any) -> Dict[str, Any]:
    """Theo's reads and write through ``db.principal_session``, each rolled back.

    Args:
        db: A connected ``services.database.DatabaseService``.
    """
    import psycopg

    observed: Dict[str, Any] = {}
    try:
        async with db.principal_session(THEO_USERNAME) as conn:
            async with conn.cursor() as cur:
                for label, sql in READS:
                    await cur.execute(sql)
                    observed[label] = _count(await cur.fetchone())
            raise _Undo
    except _Undo:
        pass
    try:
        async with db.principal_session(THEO_USERNAME) as conn:
            async with conn.cursor() as cur:
                await cur.execute(WRITE_JESSICA)
            observed[WRITE_LABEL] = WRITTEN
            raise _Undo
    except _Undo:
        pass
    except psycopg.Error as exc:
        state = exc.sqlstate or type(exc).__name__
        observed[WRITE_LABEL] = REFUSED if state == REFUSED else f"{ERROR} {state}"
    return observed


async def _in_process(cfg: Dict[str, str]) -> Dict[str, Any]:
    for key, value in cfg.items():
        os.environ.setdefault(key, value)
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from services.database import DatabaseService

    # The session logs every rollback as an error; here each one, and the
    # refused write, is the outcome being checked, so they are reported below.
    logging.getLogger("services.database").setLevel(logging.CRITICAL)

    db = DatabaseService()
    await db.connect()
    try:
        return await probe_in_process(db)
    finally:
        await db.disconnect()


# ---------------------------------------------------------------------------
# Gateway: the store-tools Lambda's own binding, over the RDS Data API
# ---------------------------------------------------------------------------


def probe_gateway(dataapi: Any) -> Dict[str, Any]:
    """Theo's reads and write through the Lambda's ``bind_runtime_principal``, rolled back.

    Args:
        dataapi: ``common.dataapi``, configured for the cluster.
    """
    observed: Dict[str, Any] = {}
    transaction = dataapi.begin_transaction()
    try:
        dataapi.bind_runtime_principal(transaction, customer_id=THEO)
        for label, sql in READS:
            observed[label] = _count(dataapi.execute_in_transaction(transaction, sql)[0])
    finally:
        dataapi.rollback_transaction(transaction)
    transaction = dataapi.begin_transaction()
    try:
        dataapi.bind_runtime_principal(transaction, customer_id=THEO)
        dataapi.execute_in_transaction(transaction, WRITE_JESSICA)
        observed[WRITE_LABEL] = WRITTEN
    except Exception as exc:  # noqa: BLE001 - the Data API reports a refusal as an error
        text = str(exc)
        refused = REFUSED in text or "row-level security" in text
        observed[WRITE_LABEL] = REFUSED if refused else f"{ERROR} {type(exc).__name__}"
    finally:
        dataapi.rollback_transaction(transaction)
    return observed


def _dataapi(env: Dict[str, str]) -> Any:
    """``common.dataapi`` configured as the Lambda is, from the box's settings."""
    cluster = env.get("DB_CLUSTER_ARN") or os.environ.get("DB_CLUSTER_ARN", "")
    secret = env.get("DB_SECRET_ARN") or os.environ.get("DB_SECRET_ARN", "")
    if not cluster or not secret:
        raise RuntimeError("DB_CLUSTER_ARN and DB_SECRET_ARN are not set")
    region = cluster.split(":")[3] if cluster.count(":") >= 3 else ""
    os.environ.update({"DB_CLUSTER_ARN": cluster, "SECRET_ARN": secret,
                       "DATABASE": env.get("DB_NAME") or "postgres"})
    if region:
        os.environ.setdefault("REGION", region)
        os.environ["DB_REGION"] = region
    if str(DEPLOY) not in sys.path:
        sys.path.insert(0, str(DEPLOY))
    import boto3
    from common import dataapi

    # The module reads these at import; set them here too, so an earlier import
    # in this process cannot leave the probe pointed at another cluster.
    dataapi.DB_CLUSTER_ARN, dataapi.SECRET_ARN = cluster, secret
    dataapi.DATABASE = os.environ["DATABASE"]
    if region:
        dataapi.rds_client = boto3.client("rds-data", region_name=region)
    return dataapi


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def owner_tickets(cfg: Dict[str, str], connect: Callable[..., Any] = check.connect) -> int:
    """Theo's tickets read as the tables' owner, whom row-level security does not bind."""
    with connect(cfg) as conn, conn.cursor() as cur:
        cur.execute(READS[0][1])
        return _count(cur.fetchone())


def collect(env_path: pathlib.Path = check.DEFAULT_ENV) -> List[check.Finding]:
    cfg = check.db_config(env_path)
    if cfg is None:
        reason = RuntimeError(check.missing_settings_reason(env_path))
        return [_unchecked_deployed(reason)] + [unchecked(path, reason) for path in _PATHS]
    try:
        deployed = deployed_finding(lambda: check.connect(cfg))
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        deployed = _unchecked_deployed(exc)
    try:
        own = owner_tickets(cfg)
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        return [deployed] + [unchecked(path, exc) for path in _PATHS]
    findings: List[check.Finding] = [deployed]
    probes: Sequence[Tuple[str, Callable[[], Dict[str, Any]]]] = (
        ("in process", lambda: asyncio.run(_in_process(cfg))),
        ("Gateway", lambda: probe_gateway(_dataapi(check.parse_dotenv(env_path)))),
    )
    for path, probe in probes:
        try:
            findings.append(judge_path(path, probe(), own))
        except Exception as exc:  # noqa: BLE001 - one path's failure is its finding
            findings.append(unchecked(path, exc))
    return findings


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    findings = collect()
    print("Lab 3B, live: your deployed predicate, then the policies as Theo on both "
          "database paths")
    for finding in findings:
        print(check.render(finding))
    passed = all(finding.state == check.PROVED for finding in findings)
    print("Lab 3B row ownership live check passed" if passed
          else "Lab 3B row ownership live check failed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
