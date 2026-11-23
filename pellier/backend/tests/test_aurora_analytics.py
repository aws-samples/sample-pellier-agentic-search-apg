"""The optional aurora_analytics page's script: settings, lake files, waits and error mapping.

AWS and Aurora are replaced by fakes; the waits are bounded by a fake clock. The live behavior
these fakes stand for was measured on a test event on 2026-11-23.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import shutil
import sys

import psycopg
import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
analytics = importlib.import_module("aurora_analytics")
ROLE_ARN = "arn:aws:iam::123456789012:role/lake-reader"


class ClientError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code, "Message": message}}


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeRds:
    """Refuses the attach `refusals` times as for a young role, then lists the role PENDING for
    `pending` reads before ACTIVE. A removal lists it PENDING for `pending` reads, then drops it,
    and RDS refuses a second request while one is in progress."""

    def __init__(self, refusals: int = 0, error: ClientError | None = None,
                 pending: int = 1) -> None:
        self.refusals, self.error, self.status, self.attaches = refusals, error, "", 0
        self.pending, self.reads_left, self.after, self.removals = pending, 0, "", 0

    def describe_db_clusters(self, DBClusterIdentifier: str) -> dict:  # noqa: N803 (boto3)
        roles = [{"RoleArn": ROLE_ARN, "FeatureName": "AuroraAnalytics", "Status": self.status}]
        listed = roles if self.status else []
        if self.status == "PENDING":
            self.reads_left -= 1
            if self.reads_left < 0:
                self.status = self.after
        return {"DBClusters": [{"AssociatedRoles": listed}]}

    def remove_role_from_db_cluster(self, **_request) -> None:
        if self.status == "PENDING":
            raise ClientError("InvalidDBClusterStateFault", "role is being removed")
        self.removals += 1
        self.status, self.after, self.reads_left = "PENDING", "", self.pending

    def add_role_to_db_cluster(self, **request) -> None:
        self.attaches += 1
        assert request == {"DBClusterIdentifier": "pellier-cluster-p1", "RoleArn": ROLE_ARN,
                           "FeatureName": "AuroraAnalytics"}
        if self.error:
            raise self.error
        if self.refusals:
            self.refusals -= 1
            raise ClientError("InvalidParameterValue", "IAM role ARN value is invalid or does not "
                              "include the required permissions for: AWS_ROLE_INTEGRATION")
        self.status, self.after, self.reads_left = "PENDING", "ACTIVE", self.pending


def test_attach_retries_a_young_role_then_waits_for_active() -> None:
    clock, rds = Clock(), FakeRds(refusals=3)
    analytics.attach_role(rds, "pellier-cluster-p1", ROLE_ARN, sleep=clock.sleep, clock=clock)
    assert rds.attaches == 4 and rds.status == "ACTIVE"


def test_attach_gives_up_on_a_role_that_never_works() -> None:
    clock, rds = Clock(), FakeRds(refusals=10**6)
    with pytest.raises(analytics.AnalyticsError, match="refused the lake reader role"):
        analytics.attach_role(rds, "pellier-cluster-p1", ROLE_ARN, sleep=clock.sleep, clock=clock)
    assert clock.now <= analytics.ATTACH_WAIT_SECONDS + 15


def test_attach_names_a_host_without_permission() -> None:
    rds = FakeRds(error=ClientError("AccessDenied", "not authorized"))
    with pytest.raises(analytics.AnalyticsError, match="may not attach"):
        analytics.attach_role(rds, "pellier-cluster-p1", ROLE_ARN, sleep=Clock().sleep)


def test_cleanup_waits_until_the_role_is_gone_and_asks_only_once() -> None:
    clock, rds = Clock(), FakeRds(pending=4)
    rds.status = "ACTIVE"
    analytics.detach_role(rds, "pellier-cluster-p1", ROLE_ARN, sleep=clock.sleep, clock=clock)
    assert (rds.status, rds.removals) == ("", 1)


def test_a_second_cleanup_during_the_removal_waits_instead_of_failing() -> None:
    clock, rds = Clock(), FakeRds(pending=4)
    rds.status, rds.reads_left = "PENDING", 3
    analytics.detach_role(rds, "pellier-cluster-p1", ROLE_ARN, sleep=clock.sleep, clock=clock)
    assert (rds.status, rds.removals) == ("", 0)


def test_prepare_right_after_cleanup_waits_for_the_removal_then_attaches() -> None:
    """Rehearsal, 2026-11-23: RDS lists a role being removed as PENDING, as one attaching."""
    clock, rds = Clock(), FakeRds(pending=3)
    rds.status, rds.reads_left, rds.after = "PENDING", 3, ""
    analytics.attach_role(rds, "pellier-cluster-p1", ROLE_ARN, sleep=clock.sleep, clock=clock)
    assert (rds.status, rds.attaches) == ("ACTIVE", 1)


def test_attach_is_a_no_op_once_active() -> None:
    rds = FakeRds()
    rds.status = "ACTIVE"
    analytics.attach_role(rds, "pellier-cluster-p1", ROLE_ARN)
    assert rds.attaches == 0


class FakeConn:
    def execute(self, _statement, *_args):
        return self


def _tables_failing(errors: list[Exception]):
    def create(_conn, _bucket, _region) -> None:
        if errors:
            raise errors.pop(0)
    return create


def test_lake_tables_wait_while_the_role_credentials_are_unavailable(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    unavailable = psycopg.errors.InternalError("credential to access AWS service is unavailable")
    monkeypatch.setattr(analytics, "_create_tables", _tables_failing([unavailable] * 4))
    clock = Clock()
    analytics.create_lake_tables(FakeConn(), "pellier-lake-p1", "us-east-1", sleep=clock.sleep,
                                 clock=clock)
    assert capsys.readouterr().out.count("about 3 minutes") == 1


@pytest.mark.parametrize(("error", "says"), [
    (psycopg.errors.QueryCanceled("canceling statement due to statement timeout"),
     "timed out reading the lake files"),
    (psycopg.errors.FeatureNotSupported("aurora_analytics is not enabled"), "parameter group"),
    (psycopg.errors.InternalError("access denied reading object"), "could not read the lake files"),
])
def test_lake_table_failures_name_their_cause(monkeypatch: pytest.MonkeyPatch,
                                              error: Exception, says: str) -> None:
    monkeypatch.setattr(analytics, "_create_tables", _tables_failing([error]))
    with pytest.raises(analytics.AnalyticsError, match=says):
        analytics.create_lake_tables(FakeConn(), "b", "us-east-1", sleep=Clock().sleep)


def test_lake_tables_stop_waiting_at_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    unavailable = psycopg.errors.InternalError("credential to access AWS service is unavailable")
    monkeypatch.setattr(analytics, "_create_tables", _tables_failing([unavailable] * 10**4))
    clock = Clock()
    with pytest.raises(analytics.AnalyticsError):
        analytics.create_lake_tables(FakeConn(), "b", "us-east-1", sleep=clock.sleep, clock=clock)
    assert clock.now <= analytics.ROLE_WAIT_SECONDS + 15


def _no_box_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("AWS_REGION", "DB_CLUSTER_ARN", "AURORA_ANALYTICS_ROLE_ARN"):
        monkeypatch.delenv(key, raising=False)


def test_settings_derive_the_cluster_and_bucket_from_the_stack(
        monkeypatch: pytest.MonkeyPatch) -> None:
    _no_box_environment(monkeypatch)
    monkeypatch.setattr(analytics.workshop_check, "db_config", lambda: {
        "DB_HOST": "h", "DB_NAME": "pellier", "DB_USER": "postgres", "AWS_REGION": "us-west-2",
        "DB_CLUSTER_ARN": "arn:aws:rds:us-west-2:123456789012:cluster:pellier-cluster-p1a2b3c4d",
        "AURORA_ANALYTICS_ROLE_ARN": ROLE_ARN})
    cfg = analytics.settings()
    assert cfg["CLUSTER_ID"] == "pellier-cluster-p1a2b3c4d"
    assert cfg["BUCKET"] == "pellier-lake-p1a2b3c4d"
    assert (cfg["ACCOUNT"], cfg["AWS_REGION"]) == ("123456789012", "us-west-2")


@pytest.mark.parametrize("value", ["pellier-cluster-p1", "arn:aws:rds:us-east-1:123456789012",
                                   "arn:aws:rds:us-east-1:123456789012:db:pellier-writer-p1"])
def test_settings_name_a_cluster_setting_that_is_not_a_full_arn(
        monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    _no_box_environment(monkeypatch)
    monkeypatch.setattr(analytics.workshop_check, "db_config", lambda: {
        "DB_HOST": "h", "DB_NAME": "pellier", "DB_USER": "postgres", "DB_CLUSTER_ARN": value,
        "AURORA_ANALYTICS_ROLE_ARN": ROLE_ARN})
    with pytest.raises(analytics.AnalyticsError, match="not a full Aurora cluster ARN"):
        analytics.settings()


def test_settings_refuse_a_stack_without_the_lake_role(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_box_environment(monkeypatch)
    monkeypatch.setattr(analytics.workshop_check, "db_config", lambda: {
        "DB_HOST": "h", "DB_NAME": "pellier", "DB_USER": "postgres",
        "DB_CLUSTER_ARN": "arn:aws:rds:us-east-1:123456789012:cluster:pellier-cluster-p1"})
    with pytest.raises(analytics.AnalyticsError, match="no lake reader role"):
        analytics.settings()


def test_the_committed_lake_files_match_their_manifest() -> None:
    files = analytics.lake_files()
    assert sorted(files) == ["daily_sales/week-1.parquet", "daily_sales/week-2.parquet",
                             "daily_sales/week-3.parquet", "daily_sales/week-4.parquet",
                             "deliveries/plan.parquet"]
    assert analytics.manifest_rows() == {"daily_sales": 45139, "deliveries": 604}


class FakeS3:
    """Records each call; lists two pages of lake files for list_objects_v2."""

    def __init__(self, create_error: str = "") -> None:
        self.create_error, self.calls = create_error, []

    def get_paginator(self, operation: str):
        fake = self

        class Pages:
            def paginate(self, **request):
                fake.calls.append((operation, request))
                return [{"Contents": [{"Key": "lake/daily_sales/week-1.parquet"}]},
                        {"Contents": [{"Key": "lake/deliveries/plan.parquet"}]}]
        return Pages()

    def __getattr__(self, name: str):
        def call(**request):
            self.calls.append((name, request))
            if name == "create_bucket" and self.create_error:
                raise ClientError(self.create_error)
        return call


def test_every_upload_names_the_bucket_owner() -> None:
    s3 = FakeS3(create_error="BucketAlreadyOwnedByYou")
    analytics.upload_lake(s3, "pellier-lake-p1", "us-west-2", "123456789012")
    create = [request for name, request in s3.calls if name == "create_bucket"][0]
    assert create["CreateBucketConfiguration"] == {"LocationConstraint": "us-west-2"}
    rest = [request for name, request in s3.calls if name != "create_bucket"]
    assert len(rest) == 6 and all(r["ExpectedBucketOwner"] == "123456789012" for r in rest)


def test_deleting_the_bucket_names_its_owner_on_every_call() -> None:
    s3 = FakeS3()
    analytics.delete_lake_bucket(s3, "pellier-lake-p1", "123456789012")
    assert [name for name, _ in s3.calls] == [
        "list_objects_v2", "delete_objects", "delete_objects", "delete_bucket"]
    assert all(request["ExpectedBucketOwner"] == "123456789012" for _, request in s3.calls)
    assert all(request["Bucket"] == "pellier-lake-p1" for _, request in s3.calls)


def test_a_bucket_name_taken_by_another_account_is_named() -> None:
    with pytest.raises(analytics.AnalyticsError, match="another AWS account owns"):
        analytics.upload_lake(FakeS3(create_error="BucketAlreadyExists"), "pellier-lake-p1",
                              "us-east-1", "123456789012")


def test_a_changed_lake_file_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    shutil.copytree(analytics.LAKE, tmp_path / "lake")
    (tmp_path / "lake" / "deliveries" / "plan.parquet").write_bytes(b"not the plan")
    monkeypatch.setattr(analytics, "LAKE", tmp_path / "lake")
    with pytest.raises(analytics.AnalyticsError, match="differs from the manifest"):
        analytics.lake_files()


def test_the_sql_file_holds_marcos_question_then_the_catalog_one() -> None:
    marco, catalog = analytics.questions()
    assert "WHERE w.product_id = '2'" in marco and "LEFT JOIN lake.deliveries" in marco
    # Round 2 of the hand test listed only sold-out pairs until stock > 0 was required.
    assert "w.quantity > 0" in catalog and "JOIN lake.deliveries" in catalog
    assert "LIMIT" not in catalog


def test_the_manifest_pins_the_generator_version() -> None:
    manifest = json.loads((analytics.LAKE / "manifest.json").read_text())
    builder = (REPO / "scripts" / "build_lake_files.py").read_text()
    assert f'"pyarrow=={manifest["pyarrow"]}"' in builder


def test_the_script_lock_matches_the_backend_lock_for_every_shared_package() -> None:
    """uv runs the script from its own lockfile; one version set everywhere (versions.md)."""
    import re
    import tomllib

    lock = tomllib.loads((REPO / "scripts" / "aurora_analytics.py.lock").read_text())
    script = {package["name"]: package["version"] for package in lock["package"]}
    backend = dict(re.findall(r"^([a-z0-9-]+)==(\S+) \\$",
                              (REPO / "pellier/backend/requirements.lock").read_text(), re.M))
    shared = {name for name in script if name in backend}
    assert {"boto3", "botocore", "s3transfer", "psycopg", "psycopg-binary"} <= shared
    assert {name: script[name] for name in shared} == {name: backend[name] for name in shared}


def test_the_script_header_pins_exactly_what_its_lock_holds() -> None:
    """A header edited without `uv lock --script` would let uv re-resolve silently."""
    import re
    import tomllib

    header = (REPO / "scripts" / "aurora_analytics.py").read_text().split("# ///", 2)[1]
    pins = dict(re.findall(r'"([a-z0-9-]+)(?:\[[a-z]+\])?==([^"]+)"', header))
    lock = tomllib.loads((REPO / "scripts" / "aurora_analytics.py.lock").read_text())
    locked = {package["name"]: package["version"] for package in lock["package"]}
    assert pins == {"boto3": "1.43.51", "botocore": "1.43.51", "s3transfer": "0.19.1",
                    "psycopg": "3.3.4"}
    assert {name: locked[name] for name in pins} == pins
    requirements = {(r["name"], r.get("specifier")) for r in lock["manifest"]["requirements"]}
    assert requirements == {(name, f"=={version}") for name, version in pins.items()}
