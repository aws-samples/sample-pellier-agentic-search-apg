"""Lab 4B's check: your deployed privileges hold the credit-writer role to the credit function.

``workshop/lab-4-credit-writer.sql`` probes your statements for
``pellier_credit_writer`` and, when every probe matches, commits them, stamping
``pellier.give_store_credit`` with their sha256. This check first confirms the
live function carries the statements now in your file, so the privileges it
probes are yours and not the ones the database shipped with, and reads what the
catalog says the role holds. Then it opens each way Pellier writes a credit:

    in process   DatabaseService.credit_writer_session, which the Operator's
                 in-process rail uses
    Gateway      run_as_credit_writer over the RDS Data API, which the
                 store-tools Lambda uses for give_store_credit

Each path asks what the role is, calls the credit function for a credit no one
approved, and then tries what a credit path never should: insert a credit row
and raise a credit's amount directly. The function must answer
approval_required, and both direct writes must be refused with SQLSTATE 42501, a
privilege the role does not hold. Every probe ends in a rollback and the direct
writes match no row, so nothing is kept.

    uv run scripts/lab4_check.py --task 4B
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

WORKSHEET = REPO / "workshop" / "lab-4-credit-writer.sql"
STARTER = REPO / "workshop" / "starters" / "lab-4-credit-writer.sql"
REGION = "Credit writer - privileges"
STAMP_PREFIX = "Lab 4B privileges sha256 "
ROLE = "pellier_credit_writer"
FUNCTION = "pellier.give_store_credit(text, text, integer, text, text)"
RUN_WORKSHEET = "psql -f workshop/lab-4-credit-writer.sql"
DEPLOYED_TITLE = "your privileges are the live ones"
DEPLOYED_EXPECTED = ("give_store_credit carries the statements now in "
                     "workshop/lab-4-credit-writer.sql, and the role holds EXECUTE on it and "
                     "nothing else")
LIVE_RIGHTS = "definer, search_path=pg_catalog, pg_temp"
LIVE_EXECUTE = "pellier_credit_writer yes, pellier_agent no, public no"
DEPLOYED_SQL = f"""
SELECT coalesce(obj_description(p.oid, 'pg_proc'), '') AS stamp,
       (CASE WHEN p.prosecdef THEN 'definer' ELSE 'invoker' END) || ', '
         || coalesce(array_to_string(p.proconfig, ' '), 'no settings') AS rights,
       (SELECT string_agg(r || ' ' || CASE WHEN has_function_privilege(r, p.oid, 'EXECUTE')
                                           THEN 'yes' ELSE 'no' END, ', ' ORDER BY ord)
          FROM unnest(ARRAY['{ROLE}', 'pellier_agent', 'public']) WITH ORDINALITY AS t (r, ord))
         AS execute,
       (SELECT count(*) FROM information_schema.role_table_grants
         WHERE grantee = '{ROLE}') AS table_grants,
       (SELECT count(*) FROM pg_policies WHERE '{ROLE}' = ANY (roles)) AS policies
  FROM pg_proc p WHERE p.oid = '{FUNCTION}'::regprocedure
"""

# What each path asks, as the credit-writer role. The first two are what the role is
# for; the last two are what a credit path must never be able to do. Both direct
# writes match no row, so a role that wrongly held the privilege changes nothing.
WHO = "the role it runs as"
DOOR = "the credit function, for a credit no one approved"
INSERT = "insert a credit row directly"
UPDATE = "raise a credit's amount directly"
PROBES: Tuple[Tuple[str, str], ...] = (
    (WHO, "SELECT current_user AS answer"),
    (DOOR, "SELECT pellier.give_store_credit('lab4-live-check', 'CUST-NOBODY', 100, "
           "'Lab 4B live check', NULL)->>'status' AS answer"),
    (INSERT, "INSERT INTO pellier.store_credits (approval_id, customer_id, amount_cents, reason, "
             "idempotency_key) SELECT id, customer_id, 100, 'Lab 4B live check', 'lab4-live-check' "
             "FROM pellier.approvals WHERE false"),
    (UPDATE, "UPDATE pellier.store_credits SET amount_cents = 50000 WHERE false"),
)
WANT = {WHO: ROLE, DOOR: "approval_required", INSERT: "42501", UPDATE: "42501"}
WRITTEN = "00000"
ERROR = "error:"
EXPECTED = ("as pellier_credit_writer: the function refuses a credit no one approved, and a "
            "direct insert or update of a credit is refused with 42501")
_PATHS = {
    "in process": "DatabaseService.credit_writer_session (the Operator's in-process rail)",
    "Gateway": "run_as_credit_writer over the RDS Data API (the store-tools Lambda)",
}


class _Undo(Exception):
    """Raised inside a transaction so it ends in a rollback."""


# ---------------------------------------------------------------------------
# Deployed: the live function carries the statements in the participant's file
# ---------------------------------------------------------------------------


def file_stamp(worksheet: bytes) -> Optional[str]:
    """The comment a passing run leaves on the function, from the file's own bytes.

    psql hashes the text between the two ``$privileges$`` quotes exactly as read,
    so the file is read as bytes, without newline translation.
    """
    parts = worksheet.decode("utf-8").split("$privileges$")
    if len(parts) < 3:
        return None
    return STAMP_PREFIX + hashlib.sha256(parts[1].encode("utf-8")).hexdigest()


def judge_deployed(stamp: Optional[str], is_starter: bool, live: Dict[str, Any]) -> check.Finding:
    """Whether the live function carries the file's statements, and what the role holds.

    Args:
        stamp: ``file_stamp`` of the SQL file, or None when its region is gone.
        is_starter: The region still holds the starter's grants.
        live: The ``DEPLOYED_SQL`` row.
    """
    if stamp is None:
        return check.Finding("4B", DEPLOYED_TITLE, check.UNCHECKED, DEPLOYED_EXPECTED,
                             "the file's privileges region could not be read",
                             ["workshop/lab-4-credit-writer.sql: no $privileges$ quotes"],
                             "restore the region from workshop/starters/lab-4-credit-writer.sql.")
    if is_starter:
        return check.Finding("4B", DEPLOYED_TITLE, check.NOT_YET, DEPLOYED_EXPECTED,
                             "the file still holds the grants it ships with",
                             ["workshop/lab-4-credit-writer.sql: Credit writer - privileges is "
                              "as shipped"],
                             f"write the role's privileges in the file, then run "
                             f"{RUN_WORKSHEET}.")
    short = stamp[len(STAMP_PREFIX):][:12]
    deployed = str(live.get("stamp") or "")
    evidence = [
        "give_store_credit: " + (f"sha256 {deployed[len(STAMP_PREFIX):][:12]}..."
                                  if deployed.startswith(STAMP_PREFIX) else "no Lab 4B comment"),
        f"workshop/lab-4-credit-writer.sql: sha256 {short}...",
        f"function rights: {live.get('rights')}",
        f"EXECUTE: {live.get('execute')}",
        f"{ROLE}: {live.get('table_grants')} table grants, {live.get('policies')} row policies",
    ]
    if deployed != stamp:
        observed = ("the live function still carries the privileges the database shipped with"
                    if not deployed.startswith(STAMP_PREFIX)
                    else "the live function carries different statements from the ones in your "
                         "file")
        return check.Finding("4B", DEPLOYED_TITLE, check.NOT_YET, DEPLOYED_EXPECTED, observed,
                             evidence, f"run {RUN_WORKSHEET}; it deploys your statements once "
                             "every probe matches.")
    drift = [line for line, ok in (
        (f"function rights are {live.get('rights')}", live.get("rights") == LIVE_RIGHTS),
        (f"EXECUTE is {live.get('execute')}", live.get("execute") == LIVE_EXECUTE),
        (f"the role holds {live.get('table_grants')} table grants",
         int(live.get("table_grants") or 0) == 0),
        (f"{live.get('policies')} row policies name the role", int(live.get("policies") or 0) == 0),
    ) if not ok]
    if drift:
        return check.Finding("4B", DEPLOYED_TITLE, check.CONTRADICTED, DEPLOYED_EXPECTED,
                             "the live state changed after your run: " + "; ".join(drift),
                             evidence, f"run {RUN_WORKSHEET} again; it resets the role first.")
    return check.Finding("4B", DEPLOYED_TITLE, check.PROVED, DEPLOYED_EXPECTED,
                         f"the live function carries your statements, sha256 {short}", evidence)


def deployed_state(connect: Callable[[], Any]) -> Dict[str, Any]:
    """The function's comment and rights, and what the role holds, from the catalog."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(DEPLOYED_SQL)
        names = [column.name for column in cur.description]
        row = cur.fetchone()
    return row if isinstance(row, dict) else dict(zip(names, row))


def deployed_finding(connect: Callable[[], Any],
                     worksheet: pathlib.Path = WORKSHEET) -> check.Finding:
    is_starter = check.region_state(worksheet, REGION, STARTER) == check.STARTER
    return judge_deployed(file_stamp(worksheet.read_bytes()), is_starter, deployed_state(connect))


# ---------------------------------------------------------------------------
# The verdict, from what one path observed
# ---------------------------------------------------------------------------


def judge_path(path: str, observed: Dict[str, str]) -> check.Finding:
    """One path's verdict from each probe's answer or SQLSTATE."""
    title = f"{path} path: the credit-writer role writes only through the function"
    broken = [f"{label}: {answer}" for label, answer in observed.items()
              if str(answer).startswith(ERROR)]
    if broken:
        return check.Finding("4B", title, check.UNCHECKED, EXPECTED,
                             "a probe failed for a reason other than the role's privileges",
                             broken, "check the database is reachable from this box, then run "
                             "it again.")
    evidence = [f"as {ROLE} through {_PATHS[path]}"]
    differs = []
    for label, want in WANT.items():
        got = str(observed.get(label, "not asked"))
        evidence.append(f"{label}: expected {want}, observed {got}")
        if got != want:
            differs.append(f"{label} came back {got}")
    if not differs:
        return check.Finding("4B", title, check.PROVED, EXPECTED,
                             f"{len(WANT)} of {len(WANT)} probes match", evidence)
    return check.Finding("4B", title, check.CONTRADICTED, EXPECTED, "; ".join(differs), evidence,
                         f"which statement in the {REGION} region grants a table privilege a "
                         f"direct write can use? Fix it, then run {RUN_WORKSHEET}.")


def unchecked(path: str, exc: BaseException) -> check.Finding:
    return check.Finding("4B", f"{path} path: the credit-writer role writes only through the function",
                         check.UNCHECKED, EXPECTED, "the check could not run this path",
                         [f"{type(exc).__name__}: {str(exc)[:200]}"],
                         "run this on the workshop box, where pellier/backend/.env names the "
                         "cluster.")


def _unchecked_deployed(exc: BaseException) -> check.Finding:
    return check.Finding("4B", DEPLOYED_TITLE, check.UNCHECKED, DEPLOYED_EXPECTED,
                         "the check could not read the live function",
                         [f"{type(exc).__name__}: {str(exc)[:200]}"],
                         "run this on the workshop box, where pellier/backend/.env names the "
                         "cluster.")


def _answer(rows: Sequence[Any]) -> str:
    if not rows:
        return WRITTEN
    row = rows[0]
    return str(row["answer"] if isinstance(row, dict) else row[0])


# ---------------------------------------------------------------------------
# In process: the session the Operator's in-process rail opens
# ---------------------------------------------------------------------------


async def probe_in_process(db: Any) -> Dict[str, str]:
    """Each probe in its own ``db.credit_writer_session``, rolled back.

    Args:
        db: A connected ``services.database.DatabaseService``.
    """
    import psycopg

    observed: Dict[str, str] = {}
    for label, sql in PROBES:
        try:
            async with db.credit_writer_session() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql)
                    observed[label] = _answer(await cur.fetchall() if cur.description else [])
                raise _Undo
        except _Undo:
            pass
        except psycopg.Error as exc:
            observed[label] = exc.sqlstate or f"{ERROR} {type(exc).__name__}"
    return observed


async def _in_process(cfg: Dict[str, str]) -> Dict[str, str]:
    for key, value in cfg.items():
        os.environ.setdefault(key, value)
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from services.database import DatabaseService

    # The session logs every rollback as an error; here each one, and each refused
    # write, is the outcome being checked, so they are reported below instead.
    logging.getLogger("services.database").setLevel(logging.CRITICAL)
    db = DatabaseService()
    await db.connect()
    try:
        return await probe_in_process(db)
    finally:
        await db.disconnect()


# ---------------------------------------------------------------------------
# Gateway: the store-tools Lambda's own role switch, over the RDS Data API
# ---------------------------------------------------------------------------


def probe_gateway(dataapi: Any) -> Dict[str, str]:
    """Each probe in its own ``run_as_credit_writer`` transaction, rolled back.

    The Data API reports a refused statement as an error whose message carries
    the SQLSTATE, and it leaves the transaction to the caller, which rolls it back.

    Args:
        dataapi: ``common.dataapi``, configured for the cluster.
    """
    observed: Dict[str, str] = {}
    for label, sql in PROBES:
        def work(run: Callable[..., List[Dict[str, Any]]], sql: str = sql) -> None:
            observed[label] = _answer(run(sql))
            raise _Undo

        try:
            dataapi.run_as_credit_writer(work)
        except _Undo:
            pass
        except Exception as exc:  # noqa: BLE001 - the Data API reports a refusal as an error
            text = str(exc)
            refused = "42501" in text or "permission denied" in text
            observed[label] = "42501" if refused else f"{ERROR} {type(exc).__name__}"
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


def collect(env_path: pathlib.Path = check.DEFAULT_ENV) -> List[check.Finding]:
    cfg = check.db_config(env_path)
    if cfg is None:
        reason = RuntimeError(check.missing_settings_reason(env_path))
        return [_unchecked_deployed(reason)] + [unchecked(path, reason) for path in _PATHS]
    try:
        deployed = deployed_finding(lambda: check.connect(cfg))
    except Exception as exc:  # noqa: BLE001 - the reason is the finding
        deployed = _unchecked_deployed(exc)
    findings: List[check.Finding] = [deployed]
    probes: Sequence[Tuple[str, Callable[[], Dict[str, str]]]] = (
        ("in process", lambda: asyncio.run(_in_process(cfg))),
        ("Gateway", lambda: probe_gateway(_dataapi(check.parse_dotenv(env_path)))),
    )
    for path, probe in probes:
        try:
            findings.append(judge_path(path, probe()))
        except Exception as exc:  # noqa: BLE001 - one path's failure is its finding
            findings.append(unchecked(path, exc))
    return findings


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    if check.refuse_missing_lab_file(4):
        return 1
    findings = collect()
    print("Lab 4B: your deployed privileges, then the credit-writer role on both database paths")
    for finding in findings:
        print(check.render(finding))
    passed = all(finding.state == check.PROVED for finding in findings)
    print("Lab 4B check passed" if passed else "Lab 4B check failed")
    return 0 if passed else 1
