"""The store tools' own database login, pellier_store_tools, on a fresh Pellier database.

The Gateway's Lambda reaches Aurora through the RDS Data API with this login's secret. What
must hold:

* on its own the login reads only the catalog, the stock and the return policy, opens a credit
  request and writes the audit ledger. Customers, orders, tickets and credits are closed to it;
* it can become pellier_agent or pellier_credit_writer for one transaction, and inherits nothing
  from either until it does. It can never become the owner;
* every store tool still works when the Lambda runs as this login, reads and the credit path
  alike, and every audit row and retrieval receipt it writes lands. Both writers swallow their
  own failures, so a missing grant would otherwise drop evidence silently;
* pgAudit can log the credit it writes: the login is a member of the credit function's owner,
  through a membership that grants it nothing.
"""

from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import psycopg
import pytest
from psycopg.rows import dict_row

from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

_DEPLOY = Path(__file__).resolve().parents[3] / "scripts" / "deploy"
if str(_DEPLOY) not in sys.path:
    sys.path.insert(0, str(_DEPLOY))

import pellier_store_tools as lambda_tools  # noqa: E402
from common import dataapi  # noqa: E402

LOGIN = "pellier_store_tools"
_NAMED = re.compile(r"(?<!:):(\w+)\b")
_SCALARS = ("stringValue", "longValue", "doubleValue", "booleanValue")


def _connect(cluster: Any, user: str, autocommit: bool = True) -> psycopg.Connection:
    return psycopg.connect(host=str(cluster.socket), port=5432, user=user, dbname="postgres",
                           autocommit=autocommit, row_factory=dict_row)


def _value(field: Dict[str, Any]) -> Any:
    if field.get("isNull"):
        return None
    return next(field[kind] for kind in _SCALARS if kind in field)


class DataApiAsLogin:
    """ExecuteStatement and the transaction calls, run by PostgreSQL as the store tools' login."""

    def __init__(self, cluster: Any) -> None:
        self.cluster = cluster
        self.open: Dict[str, psycopg.Connection] = {}
        self.ids = itertools.count(1)

    def _run(self, conn: psycopg.Connection, sql: str, parameters: Any) -> List[Dict[str, Any]]:
        values = {item["name"]: _value(item["value"]) for item in parameters or []}
        with conn.cursor() as cur:
            cur.execute(_NAMED.sub(r"%(\1)s", sql) if values else sql, values or None)
            return [dict(row) for row in cur.fetchall()] if cur.description else []

    def execute_sql(self, sql: str, parameters: Any = None) -> List[Dict[str, Any]]:
        with _connect(self.cluster, LOGIN) as conn:
            return self._run(conn, sql, parameters)

    def execute_write(self, sql: str, parameters: Any = None) -> None:
        self.execute_sql(sql, parameters)

    def begin_transaction(self) -> str:
        transaction_id = f"tx-{next(self.ids)}"
        self.open[transaction_id] = _connect(self.cluster, LOGIN, autocommit=False)
        return transaction_id

    def execute_in_transaction(self, transaction_id: str, sql: str,
                               parameters: Any = None) -> List[Dict[str, Any]]:
        return self._run(self.open[transaction_id], sql, parameters)

    def commit_transaction(self, transaction_id: str) -> None:
        conn = self.open.pop(transaction_id)
        conn.commit()
        conn.close()

    def rollback_transaction(self, transaction_id: str) -> None:
        conn = self.open.pop(transaction_id)
        conn.rollback()
        conn.close()


@pytest.fixture
def as_login(fresh_db, monkeypatch: pytest.MonkeyPatch):  # noqa: F811
    with _connect(fresh_db, "postgres") as conn:
        conn.execute(f"ALTER ROLE {LOGIN} LOGIN")
    api = DataApiAsLogin(fresh_db)
    for name in ("execute_sql", "execute_write", "begin_transaction", "execute_in_transaction",
                 "commit_transaction", "rollback_transaction"):
        monkeypatch.setattr(dataapi, name, getattr(api, name))
    monkeypatch.setattr(lambda_tools, "query_embedding",
                        lambda _query: [0.01] * dataapi.EMBED_DIMENSION)
    monkeypatch.setattr(lambda_tools, "rerank_documents", lambda *, query, documents, top_n: [
        {"index": index, "relevance_score": 1.0 - index / 100}
        for index in range(min(top_n, len(documents)))])
    return fresh_db


def _denied(cluster: Any, sql: str) -> bool:
    with _connect(cluster, LOGIN) as conn:
        try:
            conn.execute(sql)
        except psycopg.errors.InsufficientPrivilege:
            return True
    return False


def test_the_login_inherits_nothing_and_cannot_bypass_row_security(as_login) -> None:
    with _connect(as_login, "postgres") as conn:
        role = conn.execute("SELECT rolinherit, rolbypassrls, rolsuper, rolcreaterole "
                            "FROM pg_roles WHERE rolname = %s", (LOGIN,)).fetchone()
        members = conn.execute(
            "SELECT g.rolname AS role, m.inherit_option, m.set_option "
            "FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid "
            "JOIN pg_roles u ON u.oid = m.member WHERE u.rolname = %s ORDER BY 1",
            (LOGIN,)).fetchall()
    assert role == {"rolinherit": False, "rolbypassrls": False, "rolsuper": False,
                    "rolcreaterole": False}
    assert members == [
        {"role": "pellier_agent", "inherit_option": False, "set_option": True},
        # Membership only, for pgAudit: no privilege, no SET ROLE, no BYPASSRLS.
        {"role": "pellier_credit_owner", "inherit_option": False, "set_option": False},
        {"role": "pellier_credit_writer", "inherit_option": False, "set_option": True},
    ]


@pytest.mark.parametrize("sql", [
    "SELECT 1 FROM pellier.customers LIMIT 1",
    "SELECT 1 FROM pellier.orders LIMIT 1",
    "SELECT 1 FROM pellier.support_tickets LIMIT 1",
    "SELECT 1 FROM pellier.store_credits LIMIT 1",
    "SELECT args FROM pellier.approvals LIMIT 1",
    "SELECT 1 FROM pellier.tool_audit LIMIT 1",
    "UPDATE pellier.approvals SET status = 'open' WHERE false",
    "DELETE FROM pellier.tool_audit WHERE false",
    "INSERT INTO pellier.store_credits (customer_id) VALUES ('CUST-THEO')",
    "SELECT pellier.give_store_credit('CUST-THEO', 'r', 1, 'k', 'x')",
    "CREATE TABLE pellier.lab_probe (id int)",
    "SET ROLE postgres",
])
def test_on_its_own_the_login_cannot_reach_customer_data_or_credits(as_login, sql: str) -> None:
    assert _denied(as_login, sql)


def test_it_reads_customer_rows_only_as_pellier_agent_under_row_security(as_login) -> None:
    with _connect(as_login, LOGIN, autocommit=False) as conn:
        conn.execute("SET LOCAL ROLE pellier_agent")
        conn.execute("SELECT set_config('pellier.principal_username', 'theo', true)")
        owners = {row["customer_id"] for row in conn.execute(
            "SELECT customer_id FROM pellier.orders").fetchall()}
        conn.rollback()
    assert owners == {"CUST-THEO"}


def test_which_customer_it_reads_is_still_the_binding_codes_choice(as_login) -> None:
    # The login limits what a faulty Lambda can do, not whom it acts for: row-level security
    # shows whichever customer the session names. Cedar's owner-only permit at the Gateway is
    # the check on that name. This test keeps the claim honest.
    with _connect(as_login, LOGIN, autocommit=False) as conn:
        conn.execute("SET LOCAL ROLE pellier_agent")
        conn.execute("SELECT set_config('pellier.principal_username', 'jessica', true)")
        owners = {row["customer_id"] for row in conn.execute(
            "SELECT customer_id FROM pellier.orders").fetchall()}
        conn.rollback()
    assert owners == {"CUST-JESSICA"}


def test_it_writes_credits_only_as_the_credit_writer(as_login) -> None:
    with _connect(as_login, LOGIN, autocommit=False) as conn:
        assert conn.execute("SELECT has_function_privilege(current_user, "
                            "'pellier.give_store_credit(text,text,integer,text,text)', "
                            "'EXECUTE') AS ok").fetchone() == {"ok": False}
        conn.execute("SET LOCAL ROLE pellier_credit_writer")
        assert conn.execute("SELECT has_function_privilege(current_user, "
                            "'pellier.give_store_credit(text,text,integer,text,text)', "
                            "'EXECUTE') AS ok").fetchone() == {"ok": True}
        conn.rollback()


@pytest.mark.parametrize("tool,args", [
    ("search_products", {"query": "a bowl for slow mornings", "limit": 3}),
    ("browse_department", {"department": "Home", "limit": 3}),
    ("check_stock", {"product_query": "bowl"}),
    ("get_return_policy", {}),
])
def test_every_catalog_tool_runs_as_the_login(as_login, tool: str, args: Dict[str, Any]) -> None:
    result = lambda_tools.TOOLS[tool](args, None)
    assert "error" not in result, result


def test_a_customer_read_runs_as_the_login_and_sees_only_that_customer(as_login) -> None:
    tickets = lambda_tools.TOOLS["get_tickets"]({"customer_id": "CUST-THEO"}, None)
    orders = lambda_tools.TOOLS["get_orders"]({"customer_id": "CUST-THEO"}, None)
    assert "error" not in tickets and "error" not in orders
    with _connect(as_login, "postgres") as conn:
        theos = {row["ticket_id"] for row in conn.execute(
            "SELECT ticket_id FROM pellier.support_tickets WHERE customer_id = 'CUST-THEO'")}
    assert theos and {t["ticket_id"] for t in tickets["tickets"]} == theos


def test_a_credit_request_and_its_audit_row_land_as_the_login(as_login) -> None:
    turn = "turn-storetoolslogin01"
    result = lambda_tools.TOOLS["ask_a_person"](
        {"customer_id": "CUST-JESSICA", "credit_request": True,
         "reason": "Two returned pieces"}, turn)
    assert "error" not in result, result
    dataapi.write_tool_audit_independently(
        tool="ask_a_person", args={"turn_id": turn}, result=result, latency_ms=5,
        session_id=turn, build_fingerprint=None)
    with _connect(as_login, "postgres") as conn:
        request = conn.execute("SELECT source_turn_id FROM pellier.approvals "
                               "WHERE tool = 'store_credit_request' AND customer_id = %s "
                               "AND status = 'open'", ("CUST-JESSICA",)).fetchone()
        audit = conn.execute("SELECT caller FROM pellier.tool_audit WHERE session_id = %s",
                             (turn,)).fetchone()
    assert request == {"source_turn_id": turn}
    assert audit == {"caller": "gateway"}


def test_a_search_writes_its_retrieval_receipt_as_the_login(as_login) -> None:
    # The receipt writer swallows its own failure too, so only the row proves the grant.
    turn = "turn-storetoolsreceipt01"
    result = lambda_tools.TOOLS["search_products"](
        {"query": "a bowl for slow mornings", "limit": 3}, turn)
    assert "error" not in result, result
    with _connect(as_login, "postgres") as conn:
        receipt = conn.execute("SELECT rail FROM pellier.retrieval_receipts WHERE turn_id = %s",
                               (turn,)).fetchall()
    assert receipt == [{"rail": lambda_tools.RAIL}]


def _approved_review(cluster: Any, customer: str) -> str:
    """A customer with two received returns and a review a person approved for $25.00."""
    with _connect(cluster, "postgres") as conn:
        conn.execute("INSERT INTO pellier.customers (id, name, cognito_username) "
                     "VALUES (%s, %s, %s)", (customer, customer, customer.lower()))
        conn.execute("INSERT INTO pellier.orders (customer_id, product_id, amount_paid_cents, "
                     "ship_to, return_status) SELECT %s, (SELECT min(\"productId\") FROM "
                     "pellier.product_catalog), 1250, 'login', 'received' "
                     "FROM generate_series(1, 2)", (customer,))
        return conn.execute(
            "INSERT INTO pellier.approvals (customer_id, tool, args, status, order_ids, "
            "action_hash, requester_kind, decided_by, decided_at) "
            "SELECT %s, 'give_store_credit', jsonb_build_object('customer_id', %s::text, "
            "'amount_cents', 2500, 'reason', 'login'), 'approved', array_agg(id ORDER BY id), "
            "repeat('c', 64), 'operator', 'login', now() "
            "FROM pellier.orders WHERE customer_id = %s "
            "RETURNING 'operator-review:' || id || ':' || left(action_hash, 32) AS key",
            (customer, customer, customer)).fetchone()["key"]


def test_a_credit_the_login_writes_lands_once(as_login) -> None:
    customer = "CUST-STORETOOLSLOGIN"
    args = {"customer_id": customer, "amount_cents": 2500, "reason": "login",
            "idempotency_key": _approved_review(as_login, customer)}
    first = lambda_tools.TOOLS["give_store_credit"](args, None)
    retry = lambda_tools.TOOLS["give_store_credit"](args, None)
    assert first["status"] == "success", first
    assert retry["credit_id"] == first["credit_id"] and retry["idempotent_replay"] is True
    assert sorted(first["order_ids"]) == first["order_ids"] and len(first["order_ids"]) == 2


def test_pgaudit_can_log_the_credit_the_login_writes(as_login) -> None:
    # pgAudit skips a statement whose current role the session's login is not a member of
    # (pgaudit.c, log_select_dml), which is every statement inside a SECURITY DEFINER
    # function owned by a role the login does not belong to. So the login belongs to the
    # credit function's owner, through a membership that grants it nothing.
    with _connect(as_login, "postgres") as conn:
        owner = conn.execute(
            "SELECT proowner::regrole::text AS owner, "
            "pg_has_role(%s, proowner, 'MEMBER') AS member, "
            "pg_has_role(%s, proowner, 'USAGE') AS usage, "
            "pg_has_role(%s, proowner, 'SET') AS can_set "
            "FROM pg_proc WHERE oid = "
            "'pellier.give_store_credit(text,text,integer,text,text)'::regprocedure",
            (LOGIN, LOGIN, LOGIN)).fetchone()
    assert owner == {"owner": "pellier_credit_owner", "member": True, "usage": False,
                     "can_set": False}


def _seen(conn: psycopg.Connection) -> Dict[str, Any]:
    import trace_agentcore_calls as trace
    row = conn.execute(trace.PGAUDIT_STATUS_SQL).fetchone()
    return {"runs_as": row["runs_as"], "seen": row["gateway_login_seen"]}


def test_the_trace_checks_pgaudit_can_see_the_gateways_credit_before_claiming_none(
        as_login) -> None:
    # The Lab 4A trace and the Wrap-up's check run this query before they trust an empty log.
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    fn = "pellier.give_store_credit(text, text, integer, text, text)"
    with _connect(as_login, "postgres") as conn:
        assert _seen(conn) == {"runs_as": "pellier_credit_owner", "seen": True}
        conn.execute(f"REVOKE pellier_credit_owner FROM {LOGIN}")
        try:
            assert _seen(conn) == {"runs_as": "pellier_credit_owner", "seen": False}
        finally:
            conn.execute(f"GRANT pellier_credit_owner TO {LOGIN} WITH INHERIT FALSE, SET FALSE")
        conn.execute(f"ALTER FUNCTION {fn} SECURITY INVOKER")
        try:  # Lab 4B's starter: the function runs as the credit writer, which the login becomes
            assert _seen(conn) == {"runs_as": "pellier_credit_writer", "seen": True}
        finally:
            conn.execute(f"ALTER FUNCTION {fn} SECURITY DEFINER")


import base64 as _base64  # noqa: E402
import json as _json  # noqa: E402

import store_tools_login  # noqa: E402

PASSWORD = "Abcdefghijklmnopqrstuvwxyz0123456789"
CLUSTER = "arn:aws:rds:us-east-1:123456789012:cluster:pellier"
MASTER = "arn:aws:secretsmanager:us-east-1:123456789012:secret:pellier-db-secret-x"
LOGIN_SECRET = "arn:aws:secretsmanager:us-east-1:123456789012:secret:pellier/store-tools-db-x"


def test_the_verifier_is_the_one_libpq_computes(fresh_db) -> None:  # noqa: F811
    with _connect(fresh_db, "postgres") as conn:
        libpq = conn.pgconn.encrypt_password(PASSWORD.encode(), LOGIN.encode(),
                                             b"scram-sha-256").decode()
    iterations, salt = libpq.split("$")[1].split(":")
    assert store_tools_login.scram_verifier(
        PASSWORD, salt=_base64.b64decode(salt), iterations=int(iterations)) == libpq


@pytest.mark.parametrize("password", ["short", "has'quote" + "x" * 24, "spa ce" + "x" * 24])
def test_only_letter_and_digit_passwords_are_accepted(password: str) -> None:
    with pytest.raises(ValueError):
        store_tools_login.scram_verifier(password)


class _Secrets:
    def __init__(self, username: str = LOGIN) -> None:
        self.username = username

    def get_secret_value(self, SecretId: str) -> Dict[str, str]:
        assert SecretId == LOGIN_SECRET
        return {"SecretString": _json.dumps({"username": self.username, "password": PASSWORD})}


class _RdsData:
    def __init__(self, signs_in_as: str = LOGIN) -> None:
        self.calls: List[Dict[str, str]] = []
        self.signs_in_as = signs_in_as

    def execute_statement(self, **kw: str) -> Dict[str, Any]:
        self.calls.append(kw)
        if kw["sql"].startswith("SELECT current_user"):
            return {"records": [[{"stringValue": self.signs_in_as}]]}
        return {"records": []}


def _ensure(secrets: Any, rds: Any) -> None:
    store_tools_login.ensure_login(secrets=secrets, rds_data=rds, cluster_arn=CLUSTER,
                                   master_secret_arn=MASTER, login_secret_arn=LOGIN_SECRET,
                                   database="pellier")


def test_the_owner_sets_a_verifier_and_the_login_secret_proves_it() -> None:
    rds = _RdsData()
    _ensure(_Secrets(), rds)
    alter, check = rds.calls
    assert alter["secretArn"] == MASTER and check["secretArn"] == LOGIN_SECRET
    assert alter["sql"].startswith(f"ALTER ROLE {LOGIN} WITH LOGIN PASSWORD 'SCRAM-SHA-256$4096:")
    assert PASSWORD not in alter["sql"]


def test_a_secret_for_another_user_or_a_wrong_sign_in_stops_the_deploy() -> None:
    with pytest.raises(SystemExit, match="must hold the pellier_store_tools login"):
        _ensure(_Secrets("postgres"), _RdsData())
    with pytest.raises(SystemExit, match="signs in as 'postgres'"):
        _ensure(_Secrets(), _RdsData(signs_in_as="postgres"))


def test_the_lambda_is_deployed_with_the_store_tools_secret_not_the_masters(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    provision = __import__("provision_agentcore_end_to_end")
    commands: List[List[str]] = []
    monkeypatch.setattr(provision, "_run", lambda command, **_: commands.append(command))
    monkeypatch.setattr(provision.boto3, "client", lambda *_a, **_k: type("Lambda", (), {
        "get_function": lambda self, **kw: {"Configuration": {"FunctionArn": "arn:fn"}}})())
    provision._deploy_lambdas(
        repo=tmp_path, deploy_dir=tmp_path, region="us-east-1", db_region="us-east-1",
        db_cluster_arn=CLUSTER, store_tools_secret_arn=LOGIN_SECRET, db_name="pellier")
    assert commands
    for command in commands:
        assert command[command.index("--secret-arn") + 1] == LOGIN_SECRET
        assert MASTER not in command


def test_the_secret_flows_from_the_database_stack_to_the_instance() -> None:
    templates = Path(__file__).resolve().parents[3] / "deploy" / "own-account" / "templates"
    database = (templates / "pellier-database.yml").read_text(encoding="utf-8")
    parent = (templates / "pellier-governed.yml").read_text(encoding="utf-8")
    editor = (templates / "pellier-code-editor.yml").read_text(encoding="utf-8")
    assert "Name: !Sub pellier/store-tools-db-${WorkshopId}" in database
    assert """SecretStringTemplate: '{"username":"pellier_store_tools"}'""" in database
    assert "ExcludePunctuation: true" in database
    assert "StoreToolsSecretArn: !GetAtt DatabaseStack.Outputs.StoreToolsSecretArn" in parent
    assert 'export STORE_TOOLS_SECRET_ARN="${StoreToolsSecretArn}"' in editor
    # The instance reads it under its existing pellier/* secret grant; no new IAM is needed.
    assert ":secret:pellier/*" in editor
