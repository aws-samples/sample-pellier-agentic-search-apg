"""Give the store tools' Lambda its own database login, and prove it works before deploying.

The Gateway's Lambda reaches Aurora through the RDS Data API with a secret. It used to be the
master secret. It is now ``pellier_store_tools``, a login that holds no privilege on customer
data and can only become ``pellier_agent`` or ``pellier_credit_writer``
(``scripts/migrations/001_schema.sql``). The role exists from the schema; this module gives it
LOGIN and the password in its secret, then checks through the Data API that the secret signs in
as that login. A deploy that cannot prove it stops before the Lambda changes.

The password never travels as SQL. It is turned into a SCRAM-SHA-256 verifier here, the form
PostgreSQL stores, and only the verifier is sent, so no log or ``pg_stat_statements`` row can
hold the password.

Run by ``scripts/provision_agentcore_end_to_end.py`` before every Lambda deploy. Idempotent:
the same secret sets the same password.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from typing import Any, Optional

LOGIN = "pellier_store_tools"
SCRAM_ITERATIONS = 4096
# The secret's password is letters and digits (ExcludePunctuation), so SASLprep, which
# PostgreSQL applies before hashing, leaves it unchanged.
_PASSWORD = re.compile(r"[A-Za-z0-9]{24,128}")
# What a verifier can contain: no quote, so it is safe inside the ALTER ROLE literal.
_VERIFIER = re.compile(r"SCRAM-SHA-256\$\d+:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def scram_verifier(password: str, salt: Optional[bytes] = None,
                   iterations: int = SCRAM_ITERATIONS) -> str:
    """The SCRAM-SHA-256 verifier PostgreSQL stores for ``password`` (RFC 5802, RFC 7677).

    Args:
        password: Letters and digits only, so no SASLprep normalization applies.
        salt: Sixteen random bytes when omitted.
        iterations: PBKDF2 iterations; PostgreSQL's default is 4096.
    """
    if not _PASSWORD.fullmatch(password):
        raise ValueError("the store tools' password must be 24 to 128 letters and digits")
    salt = salt if salt is not None else os.urandom(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("ascii"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    return f"SCRAM-SHA-256${iterations}:{_b64(salt)}${_b64(stored_key)}:{_b64(server_key)}"


def password_from_secret(secrets: Any, secret_arn: str, login: str = LOGIN) -> str:
    """The login's password, after checking the secret names this login."""
    raw = secrets.get_secret_value(SecretId=secret_arn)["SecretString"]
    value = json.loads(raw)
    if value.get("username") != login:
        raise SystemExit(f"{secret_arn} must hold the {login} login, not "
                         f"{value.get('username')!r}; check the database stack's secret")
    return str(value.get("password") or "")


def _statement(rds_data: Any, cluster_arn: str, secret_arn: str, database: str,
               sql: str) -> list:
    response = rds_data.execute_statement(resourceArn=cluster_arn, secretArn=secret_arn,
                                          database=database, sql=sql)
    return response.get("records", [])


def ensure_login(*, secrets: Any, rds_data: Any, cluster_arn: str, master_secret_arn: str,
                 login_secret_arn: str, database: str, login: str = LOGIN) -> None:
    """Give the login its password, then prove the login secret signs in as it.

    Raises:
        SystemExit: The secret names another user, or the login does not sign in as
            ``pellier_store_tools``. The message says which.
    """
    if login not in {LOGIN, "pellier_operator_tools"}:
        raise ValueError("unrecognized tool login")
    verifier = scram_verifier(password_from_secret(secrets, login_secret_arn, login))
    if not _VERIFIER.fullmatch(verifier):
        raise SystemExit("refusing to send a malformed SCRAM verifier")
    _statement(rds_data, cluster_arn, master_secret_arn, database,
               f"ALTER ROLE {login} WITH LOGIN PASSWORD '{verifier}'")
    records = _statement(rds_data, cluster_arn, login_secret_arn, database,
                         "SELECT current_user::text")
    signed_in = records[0][0].get("stringValue") if records and records[0] else None
    if signed_in != login:
        raise SystemExit(f"the tools' secret signs in as {signed_in!r}, not {login}; "
                         "the Lambda was not deployed")
