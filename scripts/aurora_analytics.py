#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3==1.43.51", "botocore==1.43.51", "s3transfer==0.19.1",
#                 "psycopg[binary]==3.3.4"]
# ///
"""Optional Go deeper example: one Aurora query across live stock and Parquet files in S3.

Never used by the app or the required labs. uv installs it from aurora_analytics.py.lock, the
same versions pellier/backend/requirements.lock pins. prepare uploads the fixed lake files in
workshop/lake/ to a new bucket, attaches the stack's lake reader role to the Aurora cluster
for the AuroraAnalytics feature, creates foreign tables over the files with the
aurora_analytics extension, and creates a separate read-only login. query and check use only
that login. cleanup removes everything prepare made. No customer data, agent tools, RLS
policies or business rows are changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
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


def upload_lake(s3, bucket: str, region: str, owner: str) -> None:
    """Create the bucket (private, this account only) and upload the lake files under lake/."""
    request = {"Bucket": bucket}
    if region != "us-east-1":
        request["CreateBucketConfiguration"] = {"LocationConstraint": region}
    try:
        s3.create_bucket(**request)
    except Exception as exc:
        if _error_code(exc) == "BucketAlreadyExists":
            raise AnalyticsError(f"another AWS account owns the bucket name {bucket}; ask a "
                                 "facilitator") from exc
        if _error_code(exc) != "BucketAlreadyOwnedByYou":
            raise
    s3.put_public_access_block(Bucket=bucket, ExpectedBucketOwner=owner,
                               PublicAccessBlockConfiguration={
                                   "BlockPublicAcls": True, "IgnorePublicAcls": True,
                                   "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    for name, path in lake_files().items():
        s3.put_object(Bucket=bucket, Key=f"lake/{name}", Body=path.read_bytes(),
                      ExpectedBucketOwner=owner)


def _lake_role(rds, cluster: str, role_arn: str) -> str:
    described = rds.describe_db_clusters(DBClusterIdentifier=cluster)["DBClusters"][0]
    for role in described.get("AssociatedRoles", []):
        if role.get("RoleArn") == role_arn and role.get("FeatureName") == FEATURE:
            return role.get("Status", "")
    return ""


def _request_attach(rds, cluster: str, role_arn: str) -> bool:
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
    return True


def attach_role(rds, cluster: str, role_arn: str, sleep=time.sleep, clock=time.monotonic) -> None:
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
            accepted = _request_attach(rds, cluster, role_arn)
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


def _create_tables(conn, bucket: str, region: str) -> None:
    from psycopg import sql

    with conn.transaction():
        conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
        conn.execute("CREATE SCHEMA IF NOT EXISTS lake")
        for table, path in TABLES.items():
            name = sql.Identifier("lake", table)
            conn.execute(sql.SQL("DROP FOREIGN TABLE IF EXISTS {}").format(name))
            # An empty column list: Aurora reads the columns from the Parquet files.
            conn.execute(sql.SQL("CREATE FOREIGN TABLE {} () SERVER aurora_analytics_server "
                                 "OPTIONS (location {}, format 'parquet', region {})").format(
                sql.Identifier("lake", table), sql.Literal(f"s3://{bucket}/lake/{path}"),
                sql.Literal(region)))


def create_lake_tables(conn, bucket: str, region: str, sleep=time.sleep,
                       clock=time.monotonic) -> None:
    """Create the extension and the two foreign tables, waiting out the role's first minutes."""
    import psycopg

    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS aurora_analytics")
    except psycopg.Error as exc:
        raise AnalyticsError("Aurora could not create the aurora_analytics extension; it needs "
                             "Aurora PostgreSQL 17.11 or later, or 18.6 or later") from exc
    deadline, said = clock() + ROLE_WAIT_SECONDS, False
    while True:
        try:
            _create_tables(conn, bucket, region)
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
    # a role that existed before prepare cannot keep customer access.
    columns = conn.execute(
        "SELECT n.nspname, c.relname, a.attname, "
        "has_column_privilege(%s, c.oid, a.attnum, 'SELECT'), "
        "has_column_privilege(%s, c.oid, a.attnum, 'INSERT,UPDATE,REFERENCES') "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid "
        "WHERE n.nspname IN ('pellier', 'lake') AND c.relkind IN ('r','p','v','m','f') "
        "AND a.attnum > 0 AND NOT a.attisdropped", (ROLE, ROLE)).fetchall()
    for schema, table, column, reads, writes in columns:
        if writes or (reads and schema == "pellier" and (schema, table, column)
                      not in ALLOWED_COLUMNS):
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


def prepare_reader(conn, directory: Path, connection: dict) -> None:
    """Owner-only setup; the password is sent to PostgreSQL only as a SCRAM verifier."""
    from deploy.store_tools_login import scram_verifier
    from psycopg import sql

    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    password = secrets.token_hex(24)
    role = sql.Identifier(ROLE)
    with conn.transaction():
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone():
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT NOBYPASSRLS").format(role))
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


def drop_lake_objects(conn) -> None:
    """Drop the lake tables, the read-only login and the extension; safe to run again."""
    from psycopg import sql

    with conn.transaction():
        conn.execute("DROP SCHEMA IF EXISTS lake CASCADE")
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone():
            # Not DROP OWNED BY: Aurora's master user holds only ADMIN on the roles it creates.
            # Revoke what prepare_reader granted; DROP ROLE refuses if anything remains.
            for statement in ("REVOKE ALL ON pellier.product_catalog, "
                              "pellier.warehouse_inventory FROM {}",
                              "REVOKE ALL ON SCHEMA pellier FROM {}"):
                conn.execute(sql.SQL(statement).format(sql.Identifier(ROLE)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(ROLE)))
        conn.execute("DROP EXTENSION IF EXISTS aurora_analytics")


def delete_lake_bucket(s3, bucket: str, owner: str) -> None:
    try:
        pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket,
                                                             ExpectedBucketOwner=owner)
        for page in pages:
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": keys},
                                  ExpectedBucketOwner=owner)
        s3.delete_bucket(Bucket=bucket, ExpectedBucketOwner=owner)
    except Exception as exc:
        if _error_code(exc) != "NoSuchBucket":
            raise


def cleanup(conn, cfg: dict, directory: Path) -> None:
    """Remove what prepare made: tables, extension, login, the role attachment and the bucket."""
    import boto3

    drop_lake_objects(conn)
    detach_role(boto3.client("rds", region_name=cfg["AWS_REGION"]), cfg["CLUSTER_ID"],
                cfg["AURORA_ANALYTICS_ROLE_ARN"])
    delete_lake_bucket(boto3.client("s3", region_name=cfg["AWS_REGION"]), cfg["BUCKET"],
                       cfg["ACCOUNT"])
    for name in ("reader.json", "reader.pgpass", "rds-global-bundle.pem"):
        (directory / name).unlink(missing_ok=True)


def prepare(cfg: dict) -> None:
    import boto3

    upload_lake(boto3.client("s3", region_name=cfg["AWS_REGION"]), cfg["BUCKET"],
                cfg["AWS_REGION"], cfg["ACCOUNT"])
    attach_role(boto3.client("rds", region_name=cfg["AWS_REGION"]), cfg["CLUSTER_ID"],
                cfg["AURORA_ANALYTICS_ROLE_ARN"])
    owner, options = owner_connection(cfg, LOCAL)
    with owner:
        create_lake_tables(owner, cfg["BUCKET"], cfg["AWS_REGION"])
        prepare_reader(owner, LOCAL, options)


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
            cfg = settings()
            owner, _ = owner_connection(cfg, LOCAL)
            with owner:
                cleanup(owner, cfg, LOCAL)
            print(workshop_check.wrapped("", "Removed the lake tables, the read-only login, the "
                                             "role attachment and the lake bucket."))
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
