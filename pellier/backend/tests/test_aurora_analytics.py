"""The optional aurora_analytics page's script: settings, lake files, waits and error mapping.

AWS and Aurora are replaced by fakes; the waits are bounded by a fake clock. The live behavior
these fakes stand for was measured on a test event on 2026-11-23.
"""
from __future__ import annotations

from contextlib import nullcontext
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
    def transaction(self):
        return nullcontext()

    def fetchone(self):
        return (42,)  # Pre-existing extension.

    def execute(self, _statement, *_args):
        return self


def _tables_failing(errors: list[Exception]):
    def create(_conn, _bucket, _region, _state) -> None:
        if errors:
            raise errors.pop(0)
    return create


def test_lake_tables_wait_while_the_role_credentials_are_unavailable(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    unavailable = psycopg.errors.InternalError("credential to access AWS service is unavailable")
    monkeypatch.setattr(analytics, "_create_tables", _tables_failing([unavailable] * 4))
    clock = Clock()
    analytics.create_lake_tables(FakeConn(), "pellier-lake-p1", "us-east-1", None,
                                 sleep=clock.sleep, clock=clock)
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
        analytics.create_lake_tables(FakeConn(), "b", "us-east-1", None, sleep=Clock().sleep)


def test_lake_tables_stop_waiting_at_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    unavailable = psycopg.errors.InternalError("credential to access AWS service is unavailable")
    monkeypatch.setattr(analytics, "_create_tables", _tables_failing([unavailable] * 10**4))
    clock = Clock()
    with pytest.raises(analytics.AnalyticsError):
        analytics.create_lake_tables(FakeConn(), "b", "us-east-1", None, sleep=clock.sleep, clock=clock)
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
    def __init__(self, *, exists=False, create_error=""):
        self.exists = exists
        self.create_error = create_error
        self.objects = {}
        self.calls = []

    def head_bucket(self, **request):
        self.calls.append(("head_bucket", request))
        if not self.exists:
            raise ClientError("404")

    def create_bucket(self, **request):
        self.calls.append(("create_bucket", request))
        if self.create_error:
            raise ClientError(self.create_error)
        self.exists = True

    def put_public_access_block(self, **request):
        self.calls.append(("put_public_access_block", request))

    def put_object(self, **request):
        self.calls.append(("put_object", request))
        key = request["Key"]
        assert request["IfNoneMatch"] == "*"
        if key in self.objects:
            raise ClientError("PreconditionFailed")
        self.objects[key] = f'"etag-{key}"'
        return {"ETag": self.objects[key]}

    def list_objects_v2(self, **request):
        self.calls.append(("list_objects_v2", request))
        if not self.exists:
            raise ClientError("NoSuchBucket")
        keys = sorted(k for k in self.objects if k.startswith(request["Prefix"]))
        return {"Contents": [{"Key": k, "ETag": self.objects[k]} for k in keys[:1]]}

    def delete_object(self, **request):
        self.calls.append(("delete_object", request))
        key = request["Key"]
        if "IfMatch" in request and self.objects.get(key) != request["IfMatch"]:
            raise ClientError("PreconditionFailed")
        self.objects.pop(key)

    def delete_bucket(self, **request):
        self.calls.append(("delete_bucket", request))
        if self.objects:
            raise ClientError("BucketNotEmpty")
        self.exists = False


@pytest.fixture
def state(tmp_path):
    return analytics.SetupRecord(tmp_path / "setup.json", "target", "my-run", {})


def test_fresh_bucket_cycle_names_owner_and_writes_private_per_run_keys(state):
    s3 = FakeS3()
    analytics.upload_lake(s3, "bucket", "us-west-2", "owner", state)
    assert s3.calls[1] == ("create_bucket", {"Bucket": "bucket", "CreateBucketConfiguration":
                          {"LocationConstraint": "us-west-2"}})
    assert len(s3.objects) == 5
    assert all(key.startswith(state.prefix) for key in s3.objects)
    analytics.upload_lake(s3, "bucket", "us-west-2", "owner", state)
    assert not analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    assert not s3.exists and not s3.objects
    assert all(r["ExpectedBucketOwner"] == "owner" for op, r in s3.calls if op != "create_bucket")
    assert sum(op == "put_object" for op, _ in s3.calls) == 5


@pytest.mark.parametrize("pre_existing", [False, True])
def test_cleanup_never_deletes_unrelated_keys(state, pre_existing):
    s3 = FakeS3(exists=pre_existing)
    analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    other = {"keep": "book", "lake/other-project/important.parquet": "external",
             state.prefix + "another.parquet": "also external"}
    changed = next(iter(s3.objects))
    other[changed] = "newer"
    s3.objects.update(other)
    assert analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    assert s3.objects == other
    if pre_existing:
        assert not {op for op, _ in s3.calls} & {"put_public_access_block", "delete_bucket",
                                                "create_bucket"}


def test_partial_upload_retries_only_its_confirmed_keys_and_preserves_a_collision(state):
    s3 = FakeS3(exists=True)
    names = list(analytics.lake_files())
    blocked = state.prefix + names[1]
    s3.objects[blocked] = "unrelated"
    with pytest.raises(analytics.AnalyticsError, match="already exists"):
        analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    assert state.prefix + names[0] in state.resources
    assert blocked not in state.resources
    analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    assert s3.objects == {blocked: "unrelated"}


def test_a_bucket_name_taken_by_another_account_is_named(state):
    with pytest.raises(analytics.AnalyticsError, match="another AWS account owns"):
        analytics.upload_lake(FakeS3(create_error="BucketAlreadyExists"), "bucket", "us-east-1",
                              "owner", state)


def test_an_existing_role_attachment_is_not_claimed(state):
    rds = FakeRds()
    rds.status = "ACTIVE"
    analytics.attach_role(rds, "pellier-cluster-p1", ROLE_ARN, state=state)
    assert "attachment" not in state.resources


def test_an_accepted_role_attachment_is_recorded_even_if_the_wait_fails(state):
    rds, clock = FakeRds(pending=100), Clock()
    with pytest.raises(analytics.AnalyticsError, match="did not become"):
        analytics.attach_role(rds, "pellier-cluster-p1", ROLE_ARN, state=state,
                              clock=clock, sleep=clock.sleep)
    assert state.resources["attachment"] is True


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


def test_empty_replacement_bucket_survives_cleanup(state):
    s3 = FakeS3()
    analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    s3.objects.clear()  # Empty, same-name bucket in the same account.
    s3.calls.clear()
    assert analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    assert s3.exists and not any(op == "delete_bucket" for op, _ in s3.calls)


def test_no_receipt_leaves_legacy_credentials_and_never_contacts_aws_or_postgres(tmp_path):
    cfg = dict.fromkeys(["DB_CLUSTER_ARN", "DB_NAME", "AURORA_ANALYTICS_ROLE_ARN",
                         "AWS_REGION", "BUCKET"], "test")
    (tmp_path / "reader.json").write_text("old settings")
    assert analytics.cleanup(cfg, tmp_path) == (
        "No setup record on this host. Existing resources were kept.")
    with pytest.raises(analytics.AnalyticsError, match="has no setup record"):
        analytics.SetupRecord.open(tmp_path, cfg, create=True)
    assert (tmp_path / "reader.json").read_text() == "old settings"


def test_a_saved_receipt_cannot_be_used_against_a_different_target(tmp_path):
    cfg = dict.fromkeys(["DB_CLUSTER_ARN", "DB_NAME", "AURORA_ANALYTICS_ROLE_ARN",
                         "AWS_REGION", "BUCKET"], "test")
    state = analytics.SetupRecord.open(tmp_path, cfg, create=True)
    state.record("attachment", True)
    restored = analytics.SetupRecord.open(tmp_path, cfg, create=False)
    assert restored.resources == {"attachment": True}
    assert restored.prefix == state.prefix and state.path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(analytics.AnalyticsError, match="another workshop"):
        analytics.SetupRecord.open(tmp_path, dict(cfg, DB_NAME="different"), create=False)


def test_replacement_between_read_and_delete_is_kept_and_never_retried_unconditionally(
        state, monkeypatch):
    s3 = FakeS3()
    analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    first = next(iter(s3.objects))
    original_delete = s3.delete_object

    def replace_before_delete(**request):
        if request["Key"] == first:
            s3.objects[first] = "another-upload"
        original_delete(**request)

    monkeypatch.setattr(s3, "delete_object", replace_before_delete)
    assert analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    assert s3.objects == {first: "another-upload"}


def test_repeated_prepare_does_not_claim_an_empty_replacement_bucket(state):
    s3 = FakeS3()
    analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    s3.objects.clear()
    s3.calls.clear()
    analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    assert analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    assert s3.exists and not s3.objects
    assert not {op for op, _ in s3.calls} & {"put_public_access_block", "delete_bucket"}


def test_older_role_preserves_remaining_objects_and_receipt_on_access_denied(state, monkeypatch):
    s3 = FakeS3()
    analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    initial = s3.objects.copy()
    attempts = []

    def denied(**request):
        attempts.append(request)
        raise ClientError("AccessDenied")

    monkeypatch.setattr(s3, "delete_object", denied)
    with pytest.raises(analytics.AnalyticsError, match="ask a facilitator"):
        analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    assert len(attempts) == 1 and attempts[0]["IfMatch"] == initial[attempts[0]["Key"]]
    assert s3.objects == initial and state.path.is_file()


def test_retry_after_an_interrupted_upload_completes_then_cleans_up(state, monkeypatch):
    s3 = FakeS3()
    original = s3.put_object

    def interrupt(**request):
        if len(s3.objects) == 2:
            raise ClientError("SlowDown")
        return original(**request)

    monkeypatch.setattr(s3, "put_object", interrupt)
    with pytest.raises(ClientError, match="SlowDown"):
        analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    assert len(s3.objects) == 2
    monkeypatch.setattr(s3, "put_object", original)
    analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    assert len(s3.objects) == 5
    assert not analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    assert not s3.objects and not s3.exists


@pytest.mark.parametrize("version", ["v1", "null"])
def test_versioned_cleanup_deletes_only_the_uploaded_version(state, monkeypatch, version):
    s3 = FakeS3(exists=True)
    put = s3.put_object
    monkeypatch.setattr(s3, "put_object", lambda **r: {**put(**r), "VersionId": version})
    analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    first = next(iter(s3.objects))
    if version != "null":
        s3.objects[first] = "current-version-from-someone-else"
    deleted = []

    def remove_version(**request):
        assert request["VersionId"] == version
        if version == "null":
            assert request["IfMatch"] == s3.objects[request["Key"]]
        deleted.append(request["Key"])
        if request["Key"] != first or version == "null":
            s3.objects.pop(request["Key"])

    monkeypatch.setattr(s3, "delete_object", remove_version)
    assert analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    assert len(deleted) == 5
    assert s3.objects == ({first: "current-version-from-someone-else"} if version == "v1" else {})


def test_resumed_cleanup_never_reclaims_a_key_it_already_deleted(state, monkeypatch):
    s3 = FakeS3()
    analytics.upload_lake(s3, "bucket", "us-east-1", "owner", state)
    original = s3.objects.copy()
    first, second, *_ = original
    delete = s3.delete_object

    def interrupted(**request):
        if request["Key"] == second:
            raise ClientError("SlowDown")
        delete(**request)

    monkeypatch.setattr(s3, "delete_object", interrupted)
    with pytest.raises(ClientError, match="SlowDown"):
        analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    s3.objects[first] = original[first]  # Different upload, identical bytes.
    monkeypatch.setattr(s3, "delete_object", delete)
    assert analytics.delete_lake_bucket(s3, "bucket", "owner", state)
    assert s3.objects == {first: original[first]}
