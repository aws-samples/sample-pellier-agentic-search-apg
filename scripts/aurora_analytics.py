#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3==1.43.51", "botocore==1.43.51", "s3transfer==0.19.1",
#                 "psycopg[binary]==3.3.4"]
# ///
"""Optional Go deeper example: one Aurora query across live stock and Parquet files in S3.

Never used by the app or the required labs. uv installs it from aurora_analytics.py.lock, the
same versions pellier/backend/requirements.lock pins. prepare uploads the fixed lake files in
workshop/lake/ to its own folder in the workshop bucket, enables the AuroraAnalytics role
attachment and creates foreign tables and a separate read-only login. query and check use
only that login. cleanup uses setup receipts on the original host to preserve shared resources.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workshop_check  # noqa: E402  (sibling module)

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local" / "aurora-analytics"
LAKE = ROOT / "workshop" / "lake"
QUERY = ROOT / "workshop" / "aurora-analytics.sql"
ROLE = "pellier_lake_reader"
FEATURE = "AuroraAnalytics"
TABLES = {"daily_sales": "daily_sales/", "deliveries": "deliveries/plan.parquet"}
# The engine notices the cancel only at its network check, about every 30 seconds, so with this
# limit a read that cannot reach S3 fails at about 30 s instead of hanging for two minutes.
STATEMENT_TIMEOUT = "10s"
# Measured once (test event, 2026-11-23): Aurora reported the role's credentials unavailable
# for about 3 minutes after the attach turned ACTIVE, then worked with no reboot.
ROLE_WAIT_SECONDS = 300
# IAM refused the attach for a 10-second-old role and accepted it at about 55 seconds.
ATTACH_WAIT_SECONDS = 180
SHOWN_ROWS = 10


class AnalyticsError(Exception):
    """A failure whose message is safe to print: no hosts, ARNs or credentials."""


def _extra_authority(what: str) -> AnalyticsError:
    """The reader holds more than prepare grants. cleanup cannot revoke a grant it did not make,
    so the participant hands this to a facilitator instead of retrying."""
    return AnalyticsError(f"the lake reader {what}; keep this message and ask a facilitator")


def _private_file(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(text)


class SetupRecord:
    """Private, per-host receipts. Names alone do not establish ownership."""
    def __init__(self, path: Path, target: str, run: str, resources: dict) -> None:
        self.path, self.target, self.prefix = path, target, f"lake/{run}/"
        self.resources = resources
        self.run = run

    @classmethod
    def open(cls, directory: Path, cfg: dict, *, create: bool):
        path = directory / "setup.json"
        target = hashlib.sha256(json.dumps([cfg[k] for k in (
            "DB_CLUSTER_ARN", "DB_NAME", "AURORA_ANALYTICS_ROLE_ARN", "AWS_REGION", "BUCKET"
        )]).encode()).hexdigest()
        if not path.exists():
            if not create:
                return None
            if any((directory / name).exists() for name in ("reader.json", "reader.pgpass")):
                raise AnalyticsError("the existing lake login has no setup record on this host; "
                                     "ask a facilitator")
            record = cls(path, target, secrets.token_hex(16), {})
            record.save()
            return record
        data = json.loads(path.read_text())
        if data["target"] != target:
            raise AnalyticsError("the saved analytics setup belongs to another workshop; "
                                 "ask a facilitator")
        return cls(path, target, data["run"], data["resources"])

    def save(self) -> None:
        data = {"target": self.target, "run": self.run, "resources": self.resources}
        with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as stream:
            try:
                json.dump(data, stream)
                stream.flush()
                os.fsync(stream.fileno())
                os.replace(stream.name, self.path)
            finally:
                Path(stream.name).unlink(missing_ok=True)

    def record(self, name: str, identity) -> None:
        self.resources[name] = identity
        self.save()

    def forget(self, name: str) -> None:
        del self.resources[name]
        self.save()


@contextmanager
def locked_setup(directory: Path):
    """A second terminal must see the first command's completed receipts."""
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    with (directory / "lifecycle.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def settings() -> dict:
    """The box's settings: database, Region, cluster and the stack's lake reader role."""
    cfg = workshop_check.db_config()
    if not cfg:
        raise AnalyticsError("database settings missing; run this on the workshop host")
    for key in ("AWS_REGION", "DB_CLUSTER_ARN", "AURORA_ANALYTICS_ROLE_ARN"):
        cfg[key] = os.environ.get(key) or cfg.get(key) or ""
    if not cfg["AURORA_ANALYTICS_ROLE_ARN"]:
        raise AnalyticsError("this workshop stack has no lake reader role; the optional page "
                             "needs a stack built for it")
    arn = cfg["DB_CLUSTER_ARN"].split(":")
    if len(arn) != 7 or arn[0] != "arn" or arn[2] != "rds" or arn[5] != "cluster":
        raise AnalyticsError("DB_CLUSTER_ARN in the workshop settings is not a full Aurora "
                             "cluster ARN; keep this message and ask a facilitator")
    cluster = arn[6]
    if not cluster.startswith("pellier-cluster-"):
        raise AnalyticsError("unexpected Aurora cluster name in DB_CLUSTER_ARN")
    cfg["CLUSTER_ID"] = cluster
    cfg["BUCKET"] = "pellier-lake-" + cluster.removeprefix("pellier-cluster-")
    # Every bucket call names its owner, so a bucket of that name in another account is refused.
    cfg["ACCOUNT"] = arn[4]
    return cfg


def lake_files() -> dict[str, Path]:
    """The committed lake files, each checked against workshop/lake/manifest.json."""
    manifest = json.loads((LAKE / "manifest.json").read_text())
    files = {}
    for name, entry in manifest["files"].items():
        path = LAKE / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise AnalyticsError(f"workshop/lake/{name} differs from the manifest")
        files[name] = path
    return files


def manifest_rows() -> dict[str, int]:
    manifest = json.loads((LAKE / "manifest.json").read_text())["files"]
    sales = sum(entry["rows"] for name, entry in manifest.items()
                if name.startswith("daily_sales/"))
    return {"daily_sales": sales,
            "deliveries": manifest["deliveries/plan.parquet"]["rows"]}


def _error_code(exc: Exception) -> str:
    return getattr(exc, "response", {}).get("Error", {}).get("Code", "")


def _young_role(exc: Exception) -> bool:
    """RDS's refusal of a role IAM has not finished creating (test event, 2026-11-23)."""
    message = getattr(exc, "response", {}).get("Error", {}).get("Message", "")
    return "does not include the required permissions" in message


def _object_etag(s3, request: dict, key: str):
    objects = s3.list_objects_v2(**request, Prefix=key, MaxKeys=1).get("Contents", [])
    return objects[0]["ETag"] if objects and objects[0]["Key"] == key else None


def upload_lake(s3, bucket: str, region: str, owner: str, state: SetupRecord) -> None:
    """Keep existing bucket settings. Use five keys private to this preparation."""
    request = {"Bucket": bucket, "ExpectedBucketOwner": owner}
    created = False
    try:
        s3.head_bucket(**request)
    except Exception as exc:
        if _error_code(exc) not in {"404", "NoSuchBucket", "NotFound"}:
            raise AnalyticsError("cannot confirm the lake bucket belongs to this account; "
                                 "ask a facilitator") from exc
        create = {"Bucket": bucket}
        if region != "us-east-1":
            create["CreateBucketConfiguration"] = {"LocationConstraint": region}
        try:
            s3.create_bucket(**create)
            created = True
            state.record("bucket", True)
        except Exception as error:
            if _error_code(error) == "BucketAlreadyExists":
                raise AnalyticsError("another AWS account owns the lake bucket name; "
                                     "ask a facilitator") from error
            if _error_code(error) != "BucketAlreadyOwnedByYou":
                raise
    if not created and state.resources.get("bucket"):
        # A bucket name can be reused. Retain the bucket if none of our private uploads
        # can still identify it before we write anything into it.
        matching = any(_object_etag(s3, request, key) == receipt["ETag"]
                       for key, receipt in state.resources.items() if key.startswith(state.prefix))
        if not matching:
            state.record("bucket", False)
    if created:
        # Existing buckets may have their own access settings, including after a replacement.
        s3.put_public_access_block(**request, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    for name, path in lake_files().items():
        key = state.prefix + name
        if key in state.resources:
            etag = _object_etag(s3, request, key)
            receipt = state.resources[key]
            if etag == receipt["ETag"]:
                continue
            if etag is not None or receipt.get("VersionId") is not None:
                raise AnalyticsError("a lake file changed since prepare; ask a facilitator")
        # If a previous upload succeeded but its receipt was lost, fail closed on retry.
        try:
            uploaded = s3.put_object(**request, Key=key, Body=path.read_bytes(), IfNoneMatch="*")
        except Exception as exc:
            if _error_code(exc) == "PreconditionFailed":
                raise AnalyticsError("a lake file already exists without a matching setup "
                                     "record; ask a facilitator") from exc
            raise
        state.record(key, {field: uploaded[field] for field in ("ETag", "VersionId")
                           if field in uploaded})


def _lake_role(rds, cluster: str, role_arn: str) -> str:
    described = rds.describe_db_clusters(DBClusterIdentifier=cluster)["DBClusters"][0]
    for role in described.get("AssociatedRoles", []):
        if role.get("RoleArn") == role_arn and role.get("FeatureName") == FEATURE:
            return role.get("Status", "")
    return ""


def _request_attach(rds, cluster: str, role_arn: str, state: SetupRecord | None) -> bool:
    """Ask RDS to attach the role. False when IAM has not finished creating it yet.

    IAM refuses the attach for a role created seconds earlier with the same error as a role
    that lacks permissions, so the caller retries that refusal for a bounded time.
    """
    try:
        rds.add_role_to_db_cluster(DBClusterIdentifier=cluster, RoleArn=role_arn,
                                   FeatureName=FEATURE)
    except Exception as exc:
        if _error_code(exc) in {"DBClusterRoleAlreadyExists", "InvalidDBClusterStateFault"}:
            return True
        if _error_code(exc) in {"AccessDenied", "AccessDeniedException"}:
            raise AnalyticsError("this host may not attach the lake reader role") from exc
        if not _young_role(exc):
            raise AnalyticsError("Aurora refused the lake reader role") from exc
        return False
    if state is not None:
        state.record("attachment", True)
    return True


def attach_role(rds, cluster: str, role_arn: str, sleep=time.sleep, clock=time.monotonic,
                *, state: SetupRecord | None = None) -> None:
    """Attach the lake reader role for AuroraAnalytics and wait until it is ACTIVE.

    RDS lists a role as PENDING both while it attaches and while an earlier cleanup removes it,
    so this waits for either ACTIVE or the role's absence, and attaches again after a removal.
    """
    deadline, accepted = clock() + ATTACH_WAIT_SECONDS, True
    while (status := _lake_role(rds, cluster, role_arn)) != "ACTIVE":
        if clock() > deadline:
            raise AnalyticsError("Aurora refused the lake reader role; retry prepare in a minute"
                                 if not accepted else "the lake reader role did not become "
                                 "ACTIVE; retry prepare in a minute")
        if not status:
            accepted = _request_attach(rds, cluster, role_arn, state)
        sleep(5 if status else 15)


def detach_role(rds, cluster: str, role_arn: str, sleep=time.sleep, clock=time.monotonic) -> None:
    """Remove the lake reader role from the cluster and wait until RDS no longer lists it."""
    deadline = clock() + ATTACH_WAIT_SECONDS
    while status := _lake_role(rds, cluster, role_arn):
        if status != "PENDING":
            try:
                rds.remove_role_from_db_cluster(DBClusterIdentifier=cluster, RoleArn=role_arn,
                                                FeatureName=FEATURE)
            except Exception as exc:
                if _error_code(exc) != "InvalidDBClusterStateFault":
                    raise
        if clock() > deadline:
            raise AnalyticsError("the lake reader role is still being removed; retry cleanup "
                                 "in a minute")
        sleep(5)


def owner_connection(cfg: dict, directory: Path):
    """The workshop's owner login, with Aurora's certificate checked against the RDS CA bundle."""
    import psycopg

    host = cfg.get("DB_TUNNEL_REMOTE_HOST") or cfg["DB_HOST"]
    options = {"host": host, "port": int(cfg.get("DB_PORT") or 5432),
               "dbname": cfg["DB_NAME"], "user": cfg["DB_USER"],
               "password": cfg.get("DB_PASSWORD") or "", "connect_timeout": 10}
    if cfg.get("DB_TUNNEL_REMOTE_HOST"):
        options["hostaddr"] = cfg["DB_HOST"]
    if not host.startswith("/"):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        certificate = directory / "rds-global-bundle.pem"
        if not certificate.is_file():
            with urllib.request.urlopen("https://truststore.pki.rds.amazonaws.com/global/"
                                        "global-bundle.pem", timeout=20) as response:
                _private_file(certificate, response.read().decode())
        options.update(sslmode="verify-full", sslrootcert=str(certificate.resolve()))
    return psycopg.connect(**options, autocommit=True), options


def _oid(conn, name: str):
    """Use the current object's identity so a replacement with the same name is kept."""
    if name == ROLE:
        row = conn.execute("SELECT oid FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone()
    elif name == "aurora_analytics":
        row = conn.execute("SELECT oid FROM pg_extension WHERE extname = %s", (name,)).fetchone()
    elif name == "lake":
        row = conn.execute("SELECT to_regnamespace('lake')::oid").fetchone()
    else:
        row = conn.execute("SELECT to_regclass(%s)::oid", (name,)).fetchone()
    return row[0] if row else None


def _existing_owned(conn, name: str, state: SetupRecord) -> bool:
    oid = _oid(conn, name)
    if oid is None:
        return False
    if state.resources.get(name) != oid:
        raise AnalyticsError(f"{name} already exists outside this setup; it was kept. "
                             "Ask a facilitator")
    return True


def _create_tables(conn, bucket: str, region: str, state: SetupRecord) -> None:
    from psycopg import sql

    with conn.transaction():
        conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
        if _oid(conn, "lake") is None:
            conn.execute("CREATE SCHEMA lake")
            state.record("lake", _oid(conn, "lake"))
        for table, path in TABLES.items():
            name = f"lake.{table}"
            if _existing_owned(conn, name, state):
                continue
            # Aurora reads the columns from the Parquet files.
            conn.execute(sql.SQL("CREATE FOREIGN TABLE {} () SERVER aurora_analytics_server "
                                 "OPTIONS (location {}, format 'parquet', region {})").format(
                sql.Identifier("lake", table), sql.Literal(f"s3://{bucket}/{state.prefix}{path}"),
                sql.Literal(region)))
            state.record(name, _oid(conn, name))


def create_lake_tables(conn, bucket: str, region: str, state: SetupRecord, sleep=time.sleep,
                       clock=time.monotonic) -> None:
    """Create the extension and the two foreign tables, waiting out the role's first minutes."""
    import psycopg

    try:
        with conn.transaction():
            if _oid(conn, "aurora_analytics") is None:
                conn.execute("CREATE EXTENSION aurora_analytics")
                state.record("aurora_analytics", _oid(conn, "aurora_analytics"))
    except psycopg.Error as exc:
        raise AnalyticsError("Aurora could not create the aurora_analytics extension; it needs "
                             "Aurora PostgreSQL 17.11 or later, or 18.6 or later") from exc
    deadline, said = clock() + ROLE_WAIT_SECONDS, False
    while True:
        try:
            _create_tables(conn, bucket, region, state)
            return
        except psycopg.errors.QueryCanceled as exc:
            raise AnalyticsError("Aurora timed out reading the lake files in Amazon S3; check "
                                 "that the cluster can reach S3, then run prepare again") from exc
        except psycopg.Error as exc:
            message = str(exc)
            if "not enabled" in message:
                raise AnalyticsError("aurora_analytics is not enabled in this cluster's "
                                     "parameter group") from exc
            if "unavailable" not in message or clock() > deadline:
                raise AnalyticsError("Aurora could not read the lake files") from exc
        if not said:
            print(workshop_check.wrapped("", "Waiting for Aurora to start using the lake reader "
                                             "role. This can take about 3 minutes."), flush=True)
            said = True
        sleep(15)


ALLOWED_COLUMNS = {("pellier", "product_catalog", "productId"),
                   ("pellier", "product_catalog", "name"),
                   ("pellier", "warehouse_inventory", "product_id"),
                   ("pellier", "warehouse_inventory", "warehouse_code"),
                   ("pellier", "warehouse_inventory", "quantity")}
# What the reader must be refused, each tried in a direct session by check.
REFUSALS = (
    "SELECT id FROM pellier.customers LIMIT 1",
    "UPDATE pellier.warehouse_inventory SET quantity = quantity WHERE false",
    "CREATE FOREIGN TABLE lake.copy () SERVER aurora_analytics_server "
    "OPTIONS (location 's3://elsewhere/x.parquet', format 'parquet')",
    "ALTER FOREIGN TABLE lake.deliveries OPTIONS (SET location 's3://elsewhere/x.parquet')",
    "SET ROLE pellier_credit_writer",
)


def _role_is_plain(conn) -> None:
    flags = conn.execute("SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolinherit, "
                         "rolreplication, rolconfig IS NOT NULL FROM pg_roles WHERE rolname = %s",
                         (ROLE,)).fetchone()
    if flags != (False,) * 7:
        raise _extra_authority("has unexpected role attributes")
    if conn.execute("SELECT 1 FROM pg_auth_members WHERE member = %s::regrole", (ROLE,)).fetchone():
        raise _extra_authority("is a member of another role")


def _columns_are_bounded(conn) -> None:
    # Column grants do not appear as table grants, so inspect every column in both schemas;
    # inherited or PUBLIC grants must not expand access to other tables.
    columns = conn.execute(
        "SELECT n.nspname, c.relname, a.attname, "
        "has_column_privilege(%s, c.oid, a.attnum, 'SELECT'), "
        "has_column_privilege(%s, c.oid, a.attnum, 'INSERT,UPDATE,REFERENCES') "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid "
        "WHERE n.nspname IN ('pellier', 'lake') AND c.relkind IN ('r','p','v','m','f') "
        "AND a.attnum > 0 AND NOT a.attisdropped", (ROLE, ROLE)).fetchall()
    for schema, table, column, reads, writes in columns:
        allowed = ((schema, table, column) in ALLOWED_COLUMNS
                   or (schema == "lake" and table in TABLES))
        if writes or (reads and not allowed):
            raise _extra_authority("has unexpected column privileges")


def _creates_nothing(conn) -> None:
    held = conn.execute(
        "SELECT has_database_privilege(%s, current_database(), 'CREATE') "
        "OR EXISTS (SELECT 1 FROM pg_namespace WHERE has_schema_privilege(%s, oid, 'CREATE')) "
        "OR NOT has_schema_privilege(%s, 'lake', 'USAGE')", (ROLE, ROLE, ROLE)).fetchone()[0]
    if held:
        raise _extra_authority("has unexpected schema or database privileges")
    # Functions PUBLIC may run (check_stock, the triggers) are fine; anything more, such as
    # pellier.give_store_credit, is not.
    extra = conn.execute(
        "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
        "AND has_function_privilege(%s, p.oid, 'EXECUTE') "
        "AND NOT has_function_privilege('public', p.oid, 'EXECUTE')", (ROLE,)).fetchone()[0]
    if extra:
        raise _extra_authority("may run functions PUBLIC may not")


def reader_grants(conn) -> None:
    """Fail if the dedicated role has authority outside this optional example."""
    _role_is_plain(conn)
    _columns_are_bounded(conn)
    _creates_nothing(conn)


def prepare_reader(conn, directory: Path, connection: dict, state: SetupRecord) -> None:
    """Owner-only setup; the password is sent to PostgreSQL only as a SCRAM verifier."""
    from deploy.store_tools_login import scram_verifier
    from psycopg import sql

    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    password = secrets.token_hex(24)
    role = sql.Identifier(ROLE)
    with conn.transaction():
        if not _existing_owned(conn, ROLE, state):
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT NOBYPASSRLS").format(role))
            state.record(ROLE, _oid(conn, ROLE))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA pellier, lake TO {}").format(role))
        conn.execute(sql.SQL('GRANT SELECT ("productId", name) ON pellier.product_catalog '
                             "TO {}").format(role))
        conn.execute(sql.SQL("GRANT SELECT (product_id, warehouse_code, quantity) "
                             "ON pellier.warehouse_inventory TO {}").format(role))
        conn.execute(sql.SQL("GRANT SELECT ON lake.daily_sales, lake.deliveries "
                             "TO {}").format(role))
        reader_grants(conn)
        conn.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {} CONNECTION LIMIT 4").format(
            role, sql.Literal(scram_verifier(password))))
    # libpq reads a private passfile; no command line or error carries the password.
    passfile = directory / "reader.pgpass"
    escape = lambda value: str(value).replace("\\", "\\\\").replace(":", "\\:")  # noqa: E731
    fields = (connection["host"], connection.get("port", 5432), connection["dbname"], ROLE,
              password)
    _private_file(passfile, ":".join(escape(value) for value in fields) + "\n")
    options = {key: value for key, value in connection.items() if key not in {"user", "password"}}
    options.update(user=ROLE, passfile=str(passfile.resolve()), connect_timeout=10)
    _private_file(directory / "reader.json", json.dumps(options))


def reader_connection(directory: Path):
    """The read-only login. libpq prefers PGPASSWORD to a passfile, and the workshop terminal
    exports the owner's password, so drop it from this process first (test event, 2026-11-09)."""
    import psycopg

    os.environ.pop("PGPASSWORD", None)
    reader = directory / "reader.json"
    if not reader.is_file():
        raise AnalyticsError("no lake login yet; run prepare first")
    conn = psycopg.connect(**json.loads(reader.read_text()), autocommit=True)
    conn.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")
    return conn


def questions() -> tuple[str, str]:
    """Marco's question and the catalog-wide one, as workshop/aurora-analytics.sql writes them."""
    statements = [s.strip() for s in QUERY.read_text().split(";") if "SELECT" in s]
    if len(statements) != 2:
        raise AnalyticsError("workshop/aurora-analytics.sql should hold two queries")
    return statements[0], statements[1]


def run(conn, statement: str) -> tuple[list[str], list[tuple]]:
    result = conn.execute(statement)
    return [column.name for column in result.description], result.fetchall()


def check_reader(directory: Path) -> None:
    """Check the answers against separate reads, and the refusals in a direct session."""
    import psycopg

    marco, catalog = questions()
    with reader_connection(directory) as reader:
        if reader.execute("SELECT current_user").fetchone()[0] != ROLE:
            raise AnalyticsError("wrong lake login")
        reader_grants(reader)
        counts = {table: reader.execute(f"SELECT count(*) FROM lake.{table}").fetchone()[0]
                  for table in TABLES}
        if counts != manifest_rows():
            raise AnalyticsError("the lake tables do not hold the files' rows")
        live = dict(reader.execute("SELECT product_id || ' ' || warehouse_code, quantity "
                                   "FROM pellier.warehouse_inventory").fetchall())
        _, marco_rows = run(reader, marco)
        if [row[1] for row in marco_rows] != [live[f"2 {row[0]}"] for row in marco_rows] \
                or len(marco_rows) != 3:
            raise AnalyticsError("Marco's rows do not match current PostgreSQL stock")
        _, rows = run(reader, catalog)
        if not rows or any(row[2] <= 0 or row[4] >= row[5] for row in rows):
            raise AnalyticsError("a listed product is out of stock or does not run out in time")
        for statement in REFUSALS:
            try:
                reader.execute(statement)
            except psycopg.errors.InsufficientPrivilege:
                continue
            raise AnalyticsError("the lake reader admitted a forbidden operation")


def drop_lake_objects(conn, state: SetupRecord) -> bool:
    """Drop only recorded objects, with RESTRICT protecting anything that depends on them."""
    import psycopg
    from psycopg import sql

    def ours(name):
        oid = _oid(conn, name)
        return oid is not None and oid == state.resources.get(name)

    kept = False
    with conn.transaction():
        for table in TABLES:
            if ours(f"lake.{table}"):
                conn.execute(sql.SQL("DROP FOREIGN TABLE {} RESTRICT").format(
                    sql.Identifier("lake", table)))
        if ours(ROLE):
            role = sql.Identifier(ROLE)
            # Dropping our foreign tables already removed the reader's grants on them.
            if _oid(conn, "lake") is not None:
                conn.execute(sql.SQL("REVOKE USAGE ON SCHEMA lake FROM {}").format(role))
            conn.execute(sql.SQL('REVOKE SELECT ("productId", name) ON pellier.product_catalog '
                                 "FROM {}").format(role))
            conn.execute(sql.SQL("REVOKE SELECT (product_id, warehouse_code, quantity) "
                                 "ON pellier.warehouse_inventory FROM {}").format(role))
            conn.execute(sql.SQL("REVOKE USAGE ON SCHEMA pellier FROM {}").format(role))
            conn.execute(sql.SQL("DROP ROLE {}").format(role))
        for name, statement in (("lake", "DROP SCHEMA lake RESTRICT"),
                                ("aurora_analytics", "DROP EXTENSION aurora_analytics RESTRICT")):
            if ours(name):
                try:
                    with conn.transaction():
                        conn.execute(statement)
                except psycopg.errors.DependentObjectsStillExist:
                    kept = True
            elif _oid(conn, name) is not None:
                kept = True
    return kept


def delete_lake_bucket(s3, bucket: str, owner: str, state: SetupRecord) -> bool:
    """Clean up individual uploaded keys. S3 refuses to delete a nonempty bucket."""
    request = {"Bucket": bucket, "ExpectedBucketOwner": owner}
    kept = False
    saw_our_upload = False
    try:
        for key, receipt in list(state.resources.items()):
            if not key.startswith(state.prefix):
                continue
            current = _object_etag(s3, request, key)
            etag = receipt["ETag"]
            version = receipt.get("VersionId")
            delete = {**request, "Key": key}
            if version is not None:
                delete["VersionId"] = version
            # A real version ID identifies immutable bytes, even behind a newer version.
            # The null version is mutable when versioning is suspended.
            if version in (None, "null"):
                if current != etag:
                    kept |= current is not None
                    state.forget(key)
                    continue
                delete["IfMatch"] = etag
            try:
                s3.delete_object(**delete)
                saw_our_upload |= current == etag
            except Exception as exc:
                code = _error_code(exc)
                if code in {"PreconditionFailed", "ConditionalRequestConflict", "412", "409"}:
                    kept = True
                elif code in {"AccessDenied", "403"}:
                    raise AnalyticsError("the Code Editor role could not delete the remaining "
                                         "files by version or ETag; keep the setup record and "
                                         "ask a facilitator before retrying cleanup") from exc
                elif code not in {"NoSuchKey", "NoSuchVersion", "404", "NotFound"}:
                    raise
            state.forget(key)
        # An empty same-name bucket may be a replacement. Require a matching private
        # upload on this invocation before asking S3 to remove the now-empty bucket.
        if state.resources.get("bucket") and saw_our_upload:
            s3.delete_bucket(**request)
        else:
            kept = True
    except Exception as exc:
        if _error_code(exc) == "BucketNotEmpty":
            return True
        if _error_code(exc) != "NoSuchBucket":
            raise
    return kept


def cleanup(cfg: dict, directory: Path) -> str:
    """A missing or legacy receipt never authorizes deleting resources by name."""
    import boto3

    with locked_setup(directory):
        state = SetupRecord.open(directory, cfg, create=False)
        if state is None:
            return "No setup record on this host. Existing resources were kept."
        owner, _ = owner_connection(cfg, directory)
        with owner:
            _lock_cluster(owner)
            kept = drop_lake_objects(owner, state)
            if state.resources.get("attachment"):
                # Another foreign table may have begun using the same role after prepare.
                shared = owner.execute(
                    "SELECT 1 FROM pg_foreign_table t JOIN pg_foreign_server s "
                    "ON s.oid = t.ftserver WHERE s.srvname = 'aurora_analytics_server' LIMIT 1"
                ).fetchone()
                if shared:
                    kept = True
                else:
                    detach_role(boto3.client("rds", region_name=cfg["AWS_REGION"]),
                                cfg["CLUSTER_ID"], cfg["AURORA_ANALYTICS_ROLE_ARN"])
                state.forget("attachment")
            else:
                kept = True
            shared_bucket = delete_lake_bucket(boto3.client("s3", region_name=cfg["AWS_REGION"]),
                                               cfg["BUCKET"], cfg["ACCOUNT"], state)
        for name in ("reader.json", "reader.pgpass", "rds-global-bundle.pem"):
            (directory / name).unlink(missing_ok=True)
        state.path.unlink()
        if kept or shared_bucket:
            return "Cleaned up this analytics run. Shared resources were kept."
        return ("Removed the lake tables, the read-only login, the role attachment "
                "and the lake bucket.")


def _lock_cluster(conn) -> None:
    # The fixed table and role names are shared even when two hosts have different receipts.
    conn.execute("SELECT pg_advisory_lock(hashtextextended('Pellier lake setup', 0))")


def prepare(cfg: dict) -> None:
    import boto3

    with locked_setup(LOCAL):
        state = SetupRecord.open(LOCAL, cfg, create=True)
        owner, options = owner_connection(cfg, LOCAL)
        with owner:
            _lock_cluster(owner)
            # Catch an old setup or a name collision before touching the bucket or attachment.
            for name in [ROLE, *(f"lake.{table}" for table in TABLES)]:
                _existing_owned(owner, name, state)
            upload_lake(boto3.client("s3", region_name=cfg["AWS_REGION"]), cfg["BUCKET"],
                        cfg["AWS_REGION"], cfg["ACCOUNT"], state)
            attach_role(boto3.client("rds", region_name=cfg["AWS_REGION"]), cfg["CLUSTER_ID"],
                        cfg["AURORA_ANALYTICS_ROLE_ARN"], state=state)
            create_lake_tables(owner, cfg["BUCKET"], cfg["AWS_REGION"], state)
            prepare_reader(owner, LOCAL, options, state)


def show(explain: bool) -> None:
    marco, catalog = questions()
    with reader_connection(LOCAL) as reader:
        if explain:
            for (line,) in reader.execute("EXPLAIN (ANALYZE, COSTS OFF) " + catalog).fetchall():
                print(line)
            return
        header, rows = run(reader, marco)
        print("Hadley Linen Shirt")
        cells = [["NULL" if value is None else value for value in row] for row in rows]
        print(workshop_check.table(header, cells))
        header, rows = run(reader, catalog)
        print(workshop_check.wrapped("", f"{len(rows)} product and warehouse pairs in stock "
                                         "today sell out before their next delivery."))
        print(f"The {SHOWN_ROWS} longest gaps:")
        print(workshop_check.table(header, rows[:SHOWN_ROWS]))
    print(workshop_check.wrapped("", "Stock is live. Sales and deliveries are fixed sample data "
                                     "for the 28 days to 22 November 2026."))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("operation", choices=("prepare", "query", "check", "cleanup"))
    parser.add_argument("--explain", action="store_true", help="show how Aurora runs the query")
    args = parser.parse_args()
    try:
        if args.operation == "prepare":
            prepare(settings())
            print(workshop_check.wrapped("", "Prepared the lake tables in Aurora and a read-only "
                                             "login for them."))
        elif args.operation == "query":
            show(args.explain)
        elif args.operation == "check":
            check_reader(LOCAL)
            print(workshop_check.paint("Aurora analytics check passed", workshop_check.PASSED))
            print(workshop_check.wrapped("", "Live stock and the lake files' rows match; customer "
                                             "reads, writes and table changes are denied."))
        else:
            print(workshop_check.wrapped("", cleanup(settings(), LOCAL)))
        return 0
    except AnalyticsError as exc:
        print(workshop_check.wrapped("", f"Optional analytics {args.operation} could not "
                                         f"finish: {exc}."), file=sys.stderr)
        return 1
    except Exception as exc:
        # Driver and AWS errors can include hosts and ARNs. Keep them off the terminal.
        print(workshop_check.wrapped("", f"Optional analytics {args.operation} could not finish "
                                         f"({type(exc).__name__}). Run it again on the workshop "
                                         "host."), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
