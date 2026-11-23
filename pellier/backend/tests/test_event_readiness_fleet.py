"""Every event account at once, read only: ``event_readiness.py --accounts DIR``.

The facilitator pastes each team's Ops credentials into one file per account and gets one
row per account. These tests drive the reader with fakes for STS, CloudFormation,
CloudWatch Logs and Pellier's health URL: no AWS, no box, no participant.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "event_readiness.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("pellier_event_readiness_fleet", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


readiness = _load()
NOW = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)
PELLIER_URL = "https://d111111abcdef8.cloudfront.net/ports/8000/"
HEALTH_URL = PELLIER_URL + "api/health"
EDITOR_TOKEN = "editor-token-never-printed"
EDITOR_URL = f"https://d111111abcdef8.cloudfront.net/editor/?tkn={EDITOR_TOKEN}"
EDITOR_BASE = "https://d111111abcdef8.cloudfront.net/editor/"
EDITOR_HEALTH = EDITOR_BASE + "healthz"
HEALTHY = json.dumps({"status": "healthy", "database": "connected"})
ANSWERS = {
    PELLIER_URL: (200, "text/html; charset=utf-8", "<!doctype html><title>Pellier</title>"),
    HEALTH_URL: (200, "application/json", HEALTHY),
    EDITOR_HEALTH: (200, "application/json", '{"hasActiveConnections":false}'),
}


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch: pytest.MonkeyPatch) -> List[float]:
    paused: List[float] = []
    monkeypatch.setattr(readiness, "_pause", paused.append)
    return paused


class AwsError(Exception):
    """A botocore ClientError's shape: the code is in ``response``."""

    def __init__(self, code: str) -> None:
        super().__init__(f"An error occurred ({code}) when calling the operation")
        self.response = {"Error": {"Code": code}}


class Pager:
    def __init__(self, pages: Callable[..., List[Dict[str, Any]]]) -> None:
        self.pages = pages

    def paginate(self, **kwargs: Any) -> Any:
        return iter(self.pages(**kwargs))


class Cfn:
    def __init__(self, stacks: List[Dict[str, Any]],
                 events: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                 events_error: str = "", stacks_error: Optional[Exception] = None) -> None:
        self.stacks, self.events = stacks, events or {}
        self.events_error, self.stacks_error = events_error, stacks_error

    def get_paginator(self, name: str) -> Pager:
        if name == "describe_stacks":
            return Pager(self._stacks)
        assert name == "describe_stack_events"
        return Pager(self._events)

    def _stacks(self) -> List[Dict[str, Any]]:
        if self.stacks_error:
            raise self.stacks_error
        return [{"Stacks": self.stacks}]

    def _events(self, StackName: str) -> List[Dict[str, Any]]:  # noqa: N803 - boto3's name
        if self.events_error:
            raise AwsError(self.events_error)
        return [{"StackEvents": self.events.get(StackName, [])}]


class Logs:
    def __init__(self, records: Optional[List[Dict[str, Any]]] = None, error: str = "") -> None:
        self.records, self.error = records or [], error

    def filter_log_events(self, **kwargs: Any) -> Dict[str, Any]:
        assert kwargs["logGroupName"] == "/aws/pellier/readiness"
        if self.error:
            raise AwsError(self.error)
        return {"events": [{"timestamp": int(datetime.fromisoformat(r["recordedAt"])
                                             .timestamp() * 1000),
                            "message": json.dumps(r)} for r in self.records]}


class Sts:
    def __init__(self, account: str, error: str) -> None:
        self.account, self.error = account, error

    def get_caller_identity(self) -> Dict[str, str]:
        if self.error:
            raise AwsError(self.error)
        return {"Account": self.account}


class Ec2:
    def __init__(self, states: Optional[Dict[str, str]] = None, error: str = "") -> None:
        self.states = {"i-0abc": "running"} if states is None else states
        self.error = error

    def describe_instances(self, InstanceIds: List[str]) -> Dict[str, Any]:  # noqa: N803
        if self.error:
            raise AwsError(self.error)
        (instance_id,) = InstanceIds
        if instance_id not in self.states:
            raise AwsError("InvalidInstanceID.NotFound")
        return {"Reservations": [{"Instances": [{"InstanceId": instance_id,
                                                 "State": {"Name": self.states[instance_id]}}]}]}


class Session:
    """The four read-only services an account row may use, and nothing else."""

    def __init__(self, cfn: Cfn, logs: Optional[Logs] = None, account: str = "account-a",
                 sts_error: str = "", ec2: Optional[Ec2] = None) -> None:
        self.services = {"sts": Sts(account, sts_error), "cloudformation": cfn,
                         "logs": logs or Logs(), "ec2": ec2 or Ec2()}
        self.asked: List[str] = []

    def client(self, service: str, config: Any = None) -> Any:
        self.asked.append(service)
        return self.services[service]


def _root(status: str = "CREATE_COMPLETE", reason: str = "", outputs: bool = True,
          created_hours: float = 3, editor: bool = True) -> Dict[str, Any]:
    return {"StackName": "pellier-governed", "StackId": "root-stack", "StackStatus": status,
            "StackStatusReason": reason, "CreationTime": NOW - timedelta(hours=created_hours),
            "Parameters": [{"ParameterKey": "InfrastructureRevision", "ParameterValue": "r"}],
            "Outputs": ([{"OutputKey": "PellierURL", "OutputValue": PELLIER_URL},
                         *([{"OutputKey": "CodeEditorURL", "OutputValue": EDITOR_URL}]
                           if editor else [])] if outputs else [])}


OTHER_STACKS = [
    {"StackName": "pellier-governed-Editor", "StackId": "nested", "StackStatus": "CREATE_COMPLETE",
     "ParentId": "root-stack", "RootId": "root-stack", "CreationTime": NOW,
     "Parameters": [{"ParameterKey": "InfrastructureRevision", "ParameterValue": "r"}],
     "Outputs": [{"OutputKey": "InstanceId", "OutputValue": "i-0abc"}]},
    {"StackName": "AgentCore-pellier-default", "StackId": "agentcore",
     "StackStatus": "UPDATE_COMPLETE", "CreationTime": NOW, "Parameters": []},
]


EDITOR_STACK = OTHER_STACKS[:1]


def _cfn(stacks: List[Dict[str, Any]], *args: Any, **kwargs: Any) -> Cfn:
    """CloudFormation as a provisioned account has it: these stacks plus the editor stack."""
    return Cfn([*EDITOR_STACK, *stacks], *args, **kwargs)


def _record(ready: bool = True, final: str = "READY FOR LAB 1",
            age_hours: float = 1) -> Dict[str, Any]:
    return {"recordedAt": (NOW - timedelta(hours=age_hours)).isoformat(),
            "instanceId": "i-0abc", "ready": ready, "final": final,
            "lines": ["+ OK    Pellier backend is healthy", final]}


def _healthy(url: str) -> Tuple[int, str, str]:
    return ANSWERS[url]


def _answering(**changed: Any) -> Callable[[str], Tuple[int, str, str]]:
    """The healthy answers, with some URLs answering differently (a callable may raise)."""
    names = {"page": PELLIER_URL, "health": HEALTH_URL, "editor": EDITOR_HEALTH}
    answers = {**ANSWERS, **{names[key]: value for key, value in changed.items()}}

    def fetch(url: str) -> Tuple[int, str, str]:
        answer = answers[url]
        return answer(url) if callable(answer) else answer

    return fetch


def _row(session: Session, max_age: float = 24,
         fetch: Callable[[str], Tuple[int, str, str]] = _healthy) -> Any:
    base = readiness.Row(file="team-01.env", region="us-east-1")
    return readiness.account_row(session, base, NOW, max_age, fetch)


# ---------------------------------------------------------------------------
# one account's row
# ---------------------------------------------------------------------------


def test_a_ready_account_is_ready_for_lab_one_once_pellier_answers_now() -> None:
    asked: List[str] = []

    def fetch(url: str) -> Tuple[int, str, str]:
        asked.append(url)
        return _healthy(url)

    row = _row(Session(_cfn([_root(), *OTHER_STACKS]), Logs([_record()])), fetch=fetch)
    assert (row.icon, row.status, row.account, row.instance) == (
        "✅", "READY FOR LAB 1", "account-a", "i-0abc")
    assert row.recorded == "2026-12-01 07:00"
    assert asked == [PELLIER_URL, HEALTH_URL, EDITOR_HEALTH]
    assert row.editor == EDITOR_BASE and EDITOR_TOKEN not in "".join(row)


def test_an_account_still_provisioning_has_no_record_and_names_the_stack_status() -> None:
    row = _row(Session(_cfn([_root("CREATE_IN_PROGRESS")]), Logs([])))
    assert (row.icon, row.status) == ("⚠️", "no record (CREATE_IN_PROGRESS)")


def test_a_ready_record_while_the_stack_still_runs_is_not_ready() -> None:
    row = _row(Session(_cfn([_root("CREATE_IN_PROGRESS")]), Logs([_record()])))
    assert (row.icon, row.status) == ("⚠️", "setup still running (CREATE_IN_PROGRESS)")


def test_a_rolled_back_stack_is_setup_failed_even_with_a_ready_record() -> None:
    # Bootstrap records readiness before the health gate fails the stack, and the box makes
    # the log group itself, so a READY record can outlive a rollback.
    nested = "arn:partition:cloudformation:us-east-1:123456789012:stack/editor/1"
    start = NOW - timedelta(hours=2)
    events = {
        "root-stack": [
            {"LogicalResourceId": "CodeEditorStack", "ResourceType": "AWS::CloudFormation::Stack",
             "PhysicalResourceId": nested, "ResourceStatus": "CREATE_FAILED",
             "ResourceStatusReason": "Embedded stack was not successfully created",
             "Timestamp": start + timedelta(minutes=40)}],
        nested: [
            {"LogicalResourceId": "BootstrapWaitCondition",
             "ResourceType": "AWS::CloudFormation::WaitCondition", "PhysicalResourceId": "wait",
             "ResourceStatus": "CREATE_FAILED",
             "ResourceStatusReason": "WaitCondition received failed message: 'Governed workshop "
                                     "readiness failed' for uniqueId: i-0abc",
             "Timestamp": start + timedelta(minutes=38)},
            {"LogicalResourceId": "Later", "ResourceType": "AWS::EC2::Instance",
             "PhysicalResourceId": "x", "ResourceStatus": "CREATE_FAILED",
             "ResourceStatusReason": "Resource creation cancelled",
             "Timestamp": start + timedelta(minutes=39)}],
    }
    row = _row(Session(_cfn([_root("ROLLBACK_COMPLETE")], events), Logs([_record()])))
    assert row.icon == "❌"
    assert row.status == ("setup failed: BootstrapWaitCondition: WaitCondition received failed "
                          "message: 'Governed workshop readiness failed")


def test_setup_failed_uses_the_root_reason_when_its_events_cannot_be_read() -> None:
    cfn = _cfn([_root("ROLLBACK_COMPLETE", reason="The following resource(s) failed to create")],
              events_error="AccessDenied")
    row = _row(Session(cfn))
    assert row.status == "setup failed: The following resource(s) failed to create"


def test_a_failing_record_shows_its_first_failing_check() -> None:
    row = _row(Session(_cfn([_root()]), Logs([_record(False, "x FAIL  Pellier backend down")])))
    assert (row.icon, row.status) == ("❌", "Pellier backend down")


def test_the_newest_record_decides_the_row() -> None:
    logs = Logs([_record(age_hours=3), _record(False, "x FAIL  Memory empty", age_hours=1)])
    assert _row(Session(_cfn([_root()]), logs)).status == "Memory empty"


def test_a_stale_record_is_not_ready_and_a_longer_limit_accepts_it() -> None:
    session = Session(_cfn([_root(created_hours=27)]), Logs([_record(age_hours=26)]))
    stale = _row(session)
    assert (stale.icon, stale.status) == ("⚠️", "STALE (26 h old)")
    assert _row(session, max_age=36).icon == "✅"


def _times_out(url: str) -> Tuple[int, str, str]:
    raise TimeoutError("timed out")


@pytest.mark.parametrize("changed, status", [
    ({"page": (502, "text/html", "")}, "storefront does not answer (HTTP 502)"),
    ({"page": (200, "application/json", "{}")}, "storefront does not answer (not an HTML page)"),
    ({"health": (200, "application/json",
                 json.dumps({"status": "degraded", "database": "disconnected"}))},
     "storefront does not answer (database not ready: status degraded, database disconnected)"),
    ({"health": (200, "text/html", "<html>")},
     "storefront does not answer (the health answer is not JSON)"),
    ({"health": _times_out}, "storefront does not answer (TimeoutError)"),
    ({"editor": (403, "text/plain", "Forbidden.")}, "Code Editor does not answer (HTTP 403)"),
    ({"editor": (200, "text/html", "<html>")},
     "Code Editor does not answer (not the editor's health answer)"),
])
def test_a_browser_path_that_does_not_answer_is_not_ready(changed: Dict[str, Any],
                                                          status: str) -> None:
    row = _row(Session(_cfn([_root()]), Logs([_record()])), fetch=_answering(**changed))
    assert (row.icon, row.status) == ("❌", status)


def test_each_request_gets_another_try_before_the_row_fails(_no_pause: List[float]) -> None:
    tries: List[str] = []

    def flaky(url: str) -> Tuple[int, str, str]:
        tries.append(url)
        return (502, "", "") if tries.count(url) == 1 else ANSWERS[url]

    assert _row(Session(_cfn([_root()]), Logs([_record()])), fetch=flaky).icon == "✅"
    assert tries == [PELLIER_URL, PELLIER_URL, HEALTH_URL, HEALTH_URL, EDITOR_HEALTH,
                     EDITOR_HEALTH]
    assert _no_pause == [5, 5, 5]


@pytest.mark.parametrize("failing, tries", [(PELLIER_URL, 2), (HEALTH_URL, 3),
                                            (EDITOR_HEALTH, 2)])
def test_the_database_gets_three_tries_and_the_others_two(failing: str, tries: int) -> None:
    asked: List[str] = []

    def down(url: str) -> Tuple[int, str, str]:
        asked.append(url)
        return (502, "", "") if url == failing else ANSWERS[url]

    row = _row(Session(_cfn([_root()]), Logs([_record()])), fetch=down)
    assert row.icon == "❌" and row.status.endswith("(HTTP 502)")
    assert asked.count(failing) == tries


def test_no_account_takes_longer_than_its_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock[0])

    def slow(url: str) -> Tuple[int, str, str]:
        if url != HEALTH_URL:
            return ANSWERS[url]
        clock[0] += 40  # each unanswered health request costs 40 s
        raise TimeoutError("timed out")

    row = _row(Session(_cfn([_root()]), Logs([_record()])), fetch=slow)
    assert row.status == "storefront does not answer (TimeoutError)"
    # Three tries would take 120 s; the budget stops at the try that crosses 60 s.
    assert clock[0] - 1000.0 == 80


def test_a_broken_http_answer_is_a_failed_try_not_an_unreadable_account() -> None:
    import http.client

    def broken(url: str) -> Tuple[int, str, str]:
        raise http.client.IncompleteRead(b"")

    row = _row(Session(_cfn([_root()]), Logs([_record()])), fetch=broken)
    assert (row.icon, row.status) == ("❌", "storefront does not answer (IncompleteRead)")


def test_a_stack_without_its_urls_is_not_ready() -> None:
    row = _row(Session(_cfn([_root(outputs=False)]), Logs([_record()])))
    assert row.status == "storefront does not answer (no usable PellierURL)"
    row = _row(Session(_cfn([_root(editor=False)]), Logs([_record()])))
    assert row.status == "Code Editor does not answer (no usable CodeEditorURL)"


def test_the_editor_token_is_dropped_before_anything_keeps_the_url() -> None:
    assert readiness.editor_base(EDITOR_URL) == EDITOR_BASE
    assert readiness.editor_base("") == ""
    assert readiness.editor_base("not a url") == ""


def test_an_account_with_no_workshop_stack_says_so_in_the_shared_words() -> None:
    row = _row(Session(Cfn(OTHER_STACKS[1:]), Logs([_record()])))
    assert (row.icon, row.status) == ("⚠️", "no workshop stack in this Region")
    empty = _row(Session(Cfn([]), Logs([])))
    assert (empty.icon, empty.status) == ("⚠️", "no record (no workshop stack in this Region)")


@pytest.mark.parametrize("status, expected", [
    ("UPDATE_IN_PROGRESS", "setup still running (UPDATE_IN_PROGRESS)"),
    ("UPDATE_COMPLETE_CLEANUP_IN_PROGRESS", "setup still running "
                                            "(UPDATE_COMPLETE_CLEANUP_IN_PROGRESS)"),
    ("DELETE_IN_PROGRESS", "setup not complete (DELETE_IN_PROGRESS)"),
    ("REVIEW_IN_PROGRESS", "setup not complete (REVIEW_IN_PROGRESS)"),
])
def test_an_unfinished_stack_never_lets_the_record_decide(status: str, expected: str) -> None:
    row = _row(Session(_cfn([_root(status)]), Logs([_record()])))
    assert (row.icon, row.status) == ("⚠️", expected)


def test_an_imported_stack_is_complete() -> None:
    assert _row(Session(_cfn([_root("IMPORT_COMPLETE")]), Logs([_record()]))).icon == "✅"


@pytest.mark.parametrize("session, status", [
    (lambda: Session(_cfn([_root()]), sts_error="ExpiredToken"), "cannot read: ExpiredToken"),
    (lambda: Session(_cfn([_root()]), Logs(error="AccessDeniedException")),
     "cannot read: AccessDeniedException (logs)"),
    (lambda: Session(Cfn([], stacks_error=AwsError("Throttling"))), "cannot read: Throttling"),
    (lambda: Session(Cfn([], stacks_error=RuntimeError("boom"))), "cannot read: RuntimeError"),
])
def test_what_cannot_be_read_is_the_row_reason(session: Callable[[], Session],
                                               status: str) -> None:
    row = _row(session())
    assert (row.icon, row.status) == ("⚠️", status)


def test_a_malformed_record_cannot_be_read() -> None:
    class Garbled(Logs):
        def filter_log_events(self, **kwargs: Any) -> Dict[str, Any]:
            return {"events": [{"timestamp": 1, "message": "{not json"}]}

    assert _row(Session(_cfn([_root()]), Garbled())).status == "cannot read: MalformedRecord"


# ---------------------------------------------------------------------------
# the account files
# ---------------------------------------------------------------------------

CONSOLE_BLOCK = (
    'export AWS_DEFAULT_REGION="us-east-1"\n'
    'export AWS_ACCESS_KEY_ID="ASIAEXAMPLEKEY"\n'
    'export AWS_SECRET_ACCESS_KEY="secret/with+chars="\n'
    'export AWS_SESSION_TOKEN="token+abc/def=="')


def _account_file(directory: Path, name: str, text: str, mode: int = 0o600) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def test_the_console_block_parses_as_pasted() -> None:
    values = readiness.parse_credentials(CONSOLE_BLOCK)
    assert values == {"AWS_DEFAULT_REGION": "us-east-1", "AWS_ACCESS_KEY_ID": "ASIAEXAMPLEKEY",
                      "AWS_SECRET_ACCESS_KEY": "secret/with+chars=",
                      "AWS_SESSION_TOKEN": "token+abc/def=="}


def test_a_region_glued_onto_the_token_line_still_parses() -> None:
    # The console block has no final newline: `>>` puts the region on the token's line.
    glued = "AWS_ACCESS_KEY_ID=AKEY\nAWS_SECRET_ACCESS_KEY=s\nAWS_SESSION_TOKEN=tok+/=" \
            "AWS_DEFAULT_REGION=us-west-2\n"
    values = readiness.parse_credentials(glued)
    assert values["AWS_SESSION_TOKEN"] == "tok+/="
    assert values["AWS_DEFAULT_REGION"] == "us-west-2"


def test_a_value_is_read_as_text_never_run(tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    values = readiness.parse_credentials(f'export AWS_SESSION_TOKEN="$(touch {marker})"')
    assert values["AWS_SESSION_TOKEN"] == f"$(touch {marker})"
    assert not marker.exists()


@pytest.mark.parametrize("text, mode, reason", [
    (CONSOLE_BLOCK, 0o644, "FilePermissions (fix: chmod 600 team-01.env)"),
    (CONSOLE_BLOCK.replace('export AWS_DEFAULT_REGION="us-east-1"\n', ""), 0o600,
     "MissingRegion (add AWS_DEFAULT_REGION=<region> on its own line)"),
    ('export AWS_DEFAULT_REGION="us-east-1"\n', 0o600,
     "MissingCredentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)"),
])
def test_an_account_file_must_be_private_and_complete(
    tmp_path: Path, text: str, mode: int, reason: str,
) -> None:
    row = readiness.file_row(_account_file(tmp_path, "team-01.env", text, mode), NOW, 24)
    assert (row.icon, row.status) == ("⚠️", f"cannot read: {reason}")


def test_a_complete_file_reads_its_account_in_its_region(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: Dict[str, Any] = {}

    def fake_row(session: Any, base: Any, now: datetime, max_age: float) -> Any:
        credentials = session.get_credentials()
        seen.update(region=session.region_name, key=credentials.access_key,
                    token=credentials.token, base=base)
        return base

    monkeypatch.setattr(readiness, "account_row", fake_row)
    readiness.file_row(_account_file(tmp_path, "team-01.env", CONSOLE_BLOCK), NOW, 24)
    assert (seen["region"], seen["key"], seen["token"]) == (
        "us-east-1", "ASIAEXAMPLEKEY", "token+abc/def==")
    assert (seen["base"].file, seen["base"].region) == ("team-01.env", "us-east-1")


# ---------------------------------------------------------------------------
# the fleet table and the exit status
# ---------------------------------------------------------------------------


def _ready_row(path: Path, now: datetime, max_age: float) -> Any:
    return readiness.Row(file=path.name, account=f"account-{path.stem}", region="us-east-1",
                         instance="i-0abc", recorded="2026-12-01 07:00", icon="✅",
                         status="READY FOR LAB 1", url=PELLIER_URL, editor=EDITOR_BASE)


def test_rows_keep_file_name_order_and_read_at_most_eight_accounts_at_once(
    tmp_path: Path,
) -> None:
    for number in range(20, 0, -1):
        _account_file(tmp_path, f"team-{number:02d}.env", CONSOLE_BLOCK)
    _account_file(tmp_path, "notes.txt", "not an account")
    lock, running, peak = threading.Lock(), [0], [0]

    def row(path: Path, now: datetime, max_age: float) -> Any:
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
        return _ready_row(path, now, max_age)

    rows = readiness.fleet_rows(tmp_path, NOW, 24, row=row)
    assert [r.file for r in rows] == [f"team-{n:02d}.env" for n in range(1, 21)]
    assert 1 < peak[0] <= 8


def test_a_second_file_for_the_same_account_is_not_a_second_ready_account(
    tmp_path: Path,
) -> None:
    _account_file(tmp_path, "team-01.env", CONSOLE_BLOCK)
    _account_file(tmp_path, "team-02.env", CONSOLE_BLOCK)

    def same(path: Path, now: datetime, max_age: float) -> Any:
        return _ready_row(path, now, max_age)._replace(account="account-a")

    rows = readiness.fleet_rows(tmp_path, NOW, 24, row=same)
    assert [(r.icon, r.status) for r in rows] == [
        ("✅", "READY FOR LAB 1"), ("⚠️", "same account as team-01.env")]
    assert readiness.exit_status(rows) == 1


def _fleet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: Dict[str, Any],
           extra: Optional[List[str]] = None) -> int:
    for name in rows:
        _account_file(tmp_path, name, CONSOLE_BLOCK)
    monkeypatch.setattr(readiness, "file_row", lambda path, now, max_age: rows[path.name])
    return readiness.main(["--accounts", str(tmp_path), *(extra or [])], now=lambda: NOW)


def test_every_row_ready_exits_zero_and_counts_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    rows = {name: _ready_row(tmp_path / name, NOW, 24) for name in ("a.env", "b.env")}
    assert _fleet(tmp_path, monkeypatch, rows) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"Saved for --recheck: {tmp_path / 'pellier-urls.json'}"
    assert out[1].split() == ["File", "Account", "Region", "Instance", "Recorded", "(UTC)",
                              "Status"]
    assert out[-1] == "2 of 2 ready"


def test_one_row_not_ready_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    rows = {"a.env": _ready_row(tmp_path / "a.env", NOW, 24),
            "b.env": readiness.Row(file="b.env", status="no record (CREATE_IN_PROGRESS)")}
    assert _fleet(tmp_path, monkeypatch, rows) == 1
    out = capsys.readouterr().out
    assert "⚠️ no record (CREATE_IN_PROGRESS)" in out and out.rstrip().endswith("1 of 2 ready")


def test_an_empty_folder_is_not_a_ready_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert readiness.main(["--accounts", str(tmp_path)], now=lambda: NOW) == 1
    out = capsys.readouterr().out
    assert "No *.env files" in out and out.rstrip().endswith("0 of 0 ready")


@pytest.mark.parametrize("extra", [["--live"], ["--record"], ["--instance-id", "i-0abc"],
                                   ["--max-age-hours", "0"]])
def test_fleet_mode_only_reads_and_a_wrong_flag_is_a_usage_error(
    tmp_path: Path, extra: List[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        readiness.main(["--accounts", str(tmp_path), *extra], now=lambda: NOW)
    assert stopped.value.code == 2


def test_a_folder_that_does_not_exist_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as stopped:
        readiness.main(["--accounts", str(tmp_path / "missing")], now=lambda: NOW)
    assert stopped.value.code == 2


def test_no_credential_is_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _account_file(tmp_path, "team-01.env", CONSOLE_BLOCK, 0o644)
    assert readiness.main(["--accounts", str(tmp_path)], now=lambda: NOW) == 1
    out = capsys.readouterr()
    for secret in ("ASIAEXAMPLEKEY", "secret/with+chars=", "token+abc/def=="):
        assert secret not in out.out + out.err


# ---------------------------------------------------------------------------
# records and files that must never read as ready
# ---------------------------------------------------------------------------


def test_a_record_older_than_this_stack_speaks_for_an_older_box() -> None:
    # The box makes the log group, so a READY record outlives the stack that wrote it.
    row = _row(Session(_cfn([_root(created_hours=3)]), Logs([_record(age_hours=5)])))
    assert (row.icon, row.status) == ("⚠️", "no record (the newest record predates this stack)")


@pytest.mark.parametrize("recorded, status", [
    ((NOW + timedelta(hours=2)).isoformat(),
     "cannot read: MalformedRecord (recorded in the future)"),
    ("2026-12-01T07:00:00", "cannot read: MalformedRecord"),
    ("yesterday", "cannot read: MalformedRecord"),
])
def test_a_record_time_that_cannot_be_trusted_is_not_ready(recorded: str, status: str) -> None:
    record = {**_record(), "recordedAt": recorded}

    class OneEvent(Logs):
        def filter_log_events(self, **kwargs: Any) -> Dict[str, Any]:
            return {"events": [{"timestamp": 1, "message": json.dumps(record)}]}

    row = _row(Session(_cfn([_root()]), OneEvent()))
    assert (row.icon, row.status) == ("⚠️", status)


def test_an_update_rolled_back_stack_is_setup_failed() -> None:
    row = _row(Session(_cfn([_root("UPDATE_ROLLBACK_COMPLETE", reason="update failed")],
                           events_error="AccessDenied"), Logs([_record()])))
    assert (row.icon, row.status) == ("❌", "setup failed: update failed")


def test_the_newest_root_stack_decides_when_there_are_two() -> None:
    newer = {**_root("ROLLBACK_COMPLETE", reason="second try failed", created_hours=1),
             "StackId": "root-2"}
    row = _row(Session(_cfn([_root(created_hours=5), newer], events_error="AccessDenied"),
                       Logs([_record(age_hours=4)])))
    assert row.status == "setup failed: second try failed"


def test_too_many_log_pages_cannot_be_read_rather_than_guessed() -> None:
    class Endless(Logs):
        def filter_log_events(self, **kwargs: Any) -> Dict[str, Any]:
            return {"events": [], "nextToken": "more"}

    row = _row(Session(_cfn([_root()]), Endless()))
    assert (row.icon, row.status) == ("⚠️", "cannot read: TooManyLogEvents")


def test_fleet_mode_asks_only_sts_cloudformation_logs_and_ec2() -> None:
    sessions = [Session(_cfn([_root()]), Logs([_record()])),
                Session(_cfn([_root("CREATE_IN_PROGRESS")])),
                Session(_cfn([_root("ROLLBACK_COMPLETE")], events_error="AccessDenied")),
                Session(Cfn([], stacks_error=AwsError("Throttling")))]
    for session in sessions:
        _row(session)
        assert set(session.asked) <= {"sts", "cloudformation", "logs", "ec2"}, session.asked


def test_two_blocks_in_one_file_are_not_one_account() -> None:
    with pytest.raises(readiness.CannotRead) as refused:
        readiness.parse_credentials(CONSOLE_BLOCK + "\n" +
                                    CONSOLE_BLOCK.replace("ASIAEXAMPLEKEY", "ASIAOTHERKEY"))
    assert refused.value.code == "DuplicateKey (AWS_ACCESS_KEY_ID)"


def test_a_region_that_is_not_a_region_name_is_refused_and_not_printed(tmp_path: Path) -> None:
    text = CONSOLE_BLOCK.replace('"us-east-1"', '"us-east-1token+abc/def"')
    row = readiness.file_row(_account_file(tmp_path, "team-01.env", text), NOW, 24)
    assert row.status.startswith("cannot read: MissingRegion")
    assert "token" not in "".join(row)


def test_one_account_that_raises_does_not_end_the_run(tmp_path: Path) -> None:
    for name in ("a.env", "b.env", "c.env"):
        _account_file(tmp_path, name, CONSOLE_BLOCK)

    def row(path: Path, now: datetime, max_age: float) -> Any:
        if path.name == "b.env":
            raise KeyError("secret/with+chars=")
        return _ready_row(path, now, max_age)

    rows = readiness.fleet_rows(tmp_path, NOW, 24, row=row)
    assert [(r.file, r.icon, r.status) for r in rows] == [
        ("a.env", "✅", "READY FOR LAB 1"), ("b.env", "⚠️", "cannot read: KeyError"),
        ("c.env", "✅", "READY FOR LAB 1")]


def test_an_error_that_quotes_a_credential_prints_only_its_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _account_file(tmp_path, "team-01.env", CONSOLE_BLOCK)

    def leaky(session: Any, base: Any, now: datetime, max_age: float) -> Any:
        raise ValueError("bad token token+abc/def== for secret/with+chars=")

    monkeypatch.setattr(readiness, "account_row", leaky)
    assert readiness.main(["--accounts", str(tmp_path)], now=lambda: NOW) == 1
    out = capsys.readouterr()
    assert "cannot read: ValueError" in out.out
    for secret in ("ASIAEXAMPLEKEY", "secret/with+chars=", "token+abc/def=="):
        assert secret not in out.out + out.err


# ---------------------------------------------------------------------------
# the morning recheck: no credentials, only "does Pellier answer now?"
# ---------------------------------------------------------------------------

MORNING = NOW + timedelta(hours=20)
DOWN_URL = "https://d222222abcdef8.cloudfront.net/ports/8000/"


def _check_one(directory: Path, monkeypatch: pytest.MonkeyPatch, rows: Dict[str, Any]) -> None:
    """Run --accounts over these rows, as the day before."""
    for name in rows:
        if not (directory / name).exists():
            _account_file(directory, name, CONSOLE_BLOCK)
    monkeypatch.setattr(readiness, "file_row", lambda path, now, max_age: rows[path.name])
    readiness.main(["--accounts", str(directory)], now=lambda: NOW)


def _no_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("--recheck must not use credentials or AWS")

    for name in ("file_session", "account_row", "file_row", "_aws"):
        monkeypatch.setattr(readiness, name, refuse)


def test_check_one_saves_every_row_with_its_pellier_url_privately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = {"a.env": _ready_row(tmp_path / "a.env", NOW, 24),
            "b.env": readiness.Row(file="b.env", account="account-b", icon="❌",
                                   status="Pellier backend down", url=PELLIER_URL)}
    _check_one(tmp_path, monkeypatch, rows)
    saved_file = tmp_path / "pellier-urls.json"
    assert saved_file.stat().st_mode & 0o777 == 0o600
    saved = readiness.saved_rows(saved_file)
    # Only the checker's own words are saved: the box's failing line is not.
    assert sorted(saved.values()) == sorted([
        rows["a.env"], rows["b.env"]._replace(status="the box's record is not ready")])
    assert not list(tmp_path.glob("*.tmp")) and not list(tmp_path.glob(".*.tmp"))


def _sweep(directory: Path, monkeypatch: pytest.MonkeyPatch, rows: Dict[str, Any],
           save: Path) -> int:
    """One collector run: a new folder of team files, --accounts --save, then the folder goes."""
    directory.mkdir()
    for name in rows:
        _account_file(directory, name, CONSOLE_BLOCK)
    monkeypatch.setattr(readiness, "file_row", lambda path, now, max_age: rows[path.name])
    status = readiness.main(["--accounts", str(directory), "--save", str(save)], now=lambda: NOW)
    for name in rows:
        (directory / name).unlink()
    directory.rmdir()
    return status


def test_a_run_over_some_teams_keeps_the_other_teams_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    save = tmp_path / "saved.json"
    first = {name: _ready_row(tmp_path / name, NOW, 24) for name in ("001-a.env", "002-b.env")}
    _sweep(tmp_path / "sweep-1", monkeypatch, first, save)
    _sweep(tmp_path / "sweep-2", monkeypatch, {"001-b.env": first["002-b.env"]._replace(
        file="001-b.env")}, save)
    saved = readiness.saved_rows(save)
    # The collector numbered b's file 001 the second time: one row for b, not two.
    assert sorted((row.account, row.file) for row in saved.values()) == [
        ("account-001-a", "001-a.env"), ("account-002-b", "001-b.env")]


def test_a_file_that_repeats_an_account_is_not_saved_over_that_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = _ready_row(tmp_path / "a.env", NOW, 24)
    repeat = real._replace(file="b.env", icon="⚠️", status="same account as a.env")
    save = tmp_path / "saved.json"
    _sweep(tmp_path / "sweep", monkeypatch, {"a.env": real, "b.env": repeat}, save)
    assert list(readiness.saved_rows(save).values()) == [real]


def test_the_collector_flow_rechecks_from_the_saved_file_after_its_folder_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    save = tmp_path / "saved.json"
    rows = {name: _ready_row(tmp_path / name, NOW, 24) for name in ("001-a.env", "002-b.env")}
    assert _sweep(tmp_path / "sweep", monkeypatch, rows, save) == 0
    _no_aws(monkeypatch)
    monkeypatch.setattr(readiness, "_get", _healthy)
    capsys.readouterr()
    assert readiness.main(["--recheck", str(save)], now=lambda: MORNING) == 0
    assert capsys.readouterr().out.rstrip().endswith("2 of 2 ready")


@pytest.mark.parametrize("argv", [
    ["--recheck", "{dir}", "--save", "{dir}/x.json"],
    ["--accounts", "{dir}", "--save", "{dir}/missing/x.json"],
])
def test_save_belongs_to_accounts_and_needs_its_folder(tmp_path: Path, argv: List[str]) -> None:
    (tmp_path / "pellier-urls.json").write_text('{"rows": []}', encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        readiness.main([part.replace("{dir}", str(tmp_path)) for part in argv],
                       now=lambda: MORNING)
    assert stopped.value.code == 2


def test_the_morning_recheck_asks_only_the_browser_path_and_counts_every_team(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    rows = {"a.env": _ready_row(tmp_path / "a.env", NOW, 24),
            "b.env": _ready_row(tmp_path / "b.env", NOW, 24)._replace(url=DOWN_URL),
            "c.env": readiness.Row(file="c.env", account="account-c",
                                   status="no record (CREATE_IN_PROGRESS)")}
    _check_one(tmp_path, monkeypatch, rows)
    _account_file(tmp_path, "d.env", CONSOLE_BLOCK)  # copied after the last --accounts run
    _no_aws(monkeypatch)
    monkeypatch.setattr(readiness, "_get",
                        lambda url: ANSWERS.get(url, (502, "text/html", "")))
    capsys.readouterr()
    assert readiness.main(["--recheck", str(tmp_path)], now=lambda: MORNING) == 1
    lines = capsys.readouterr().out.splitlines()
    statuses = sorted(line.split("   ")[-1] for line in lines[1:-1])
    assert statuses == sorted([
        "✅ READY FOR LAB 1", "❌ storefront does not answer (HTTP 502)",
        "⚠️ not ready at the saved run (no record)",
        "⚠️ no --accounts result for this file; run --accounts"])
    assert lines[-1] == "1 of 4 ready"


def test_every_team_answering_in_the_morning_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _check_one(tmp_path, monkeypatch,
               {name: _ready_row(tmp_path / name, NOW, 24) for name in ("a.env", "b.env")})
    _no_aws(monkeypatch)
    monkeypatch.setattr(readiness, "_get", _healthy)
    assert readiness.main(["--recheck", str(tmp_path)], now=lambda: MORNING) == 0
    assert capsys.readouterr().out.rstrip().endswith("2 of 2 ready")


def test_a_record_too_old_by_the_morning_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _check_one(tmp_path, monkeypatch, {"a.env": _ready_row(tmp_path / "a.env", NOW, 24)})
    _no_aws(monkeypatch)
    monkeypatch.setattr(readiness, "_get", _healthy)
    # The recheck's own default is 36 h: a record about a day old passes, one older does not.
    assert readiness.main(["--recheck", str(tmp_path)], now=lambda: NOW + timedelta(hours=30)) == 0
    later = NOW + timedelta(hours=40)
    assert readiness.main(["--recheck", str(tmp_path)], now=lambda: later) == 1
    assert "⚠️ STALE (41 h old)" in capsys.readouterr().out
    assert readiness.main(["--recheck", str(tmp_path), "--max-age-hours", "48"],
                          now=lambda: later) == 0


def test_a_damaged_saved_file_asks_for_a_new_accounts_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    saved = tmp_path / "pellier-urls.json"
    saved.write_text("{not json", encoding="utf-8")
    saved.chmod(0o600)
    assert readiness.main(["--recheck", str(tmp_path)], now=lambda: MORNING) == 1
    assert "Cannot recheck: MalformedSavedFile" in capsys.readouterr().out
    saved.write_text('{"rows": []}', encoding="utf-8")
    saved.chmod(0o644)
    assert readiness.main(["--recheck", str(tmp_path)], now=lambda: MORNING) == 1
    assert "Cannot recheck: FilePermissions" in capsys.readouterr().out


@pytest.mark.parametrize("extra", [["--live"], ["--record"], ["--instance-id", "i-0abc"],
                                   ["--accounts", "."]])
def test_the_recheck_only_reads_and_a_wrong_flag_is_a_usage_error(
    tmp_path: Path, extra: List[str],
) -> None:
    (tmp_path / "pellier-urls.json").write_text('{"rows": []}', encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        readiness.main(["--recheck", str(tmp_path), *extra], now=lambda: MORNING)
    assert stopped.value.code == 2


def test_a_recheck_before_any_accounts_run_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as stopped:
        readiness.main(["--recheck", str(tmp_path)], now=lambda: MORNING)
    assert stopped.value.code == 2


def test_the_pellier_url_is_never_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _check_one(tmp_path, monkeypatch, {"a.env": _ready_row(tmp_path / "a.env", NOW, 24)})
    _no_aws(monkeypatch)
    monkeypatch.setattr(readiness, "_get", _healthy)
    readiness.main(["--recheck", str(tmp_path)], now=lambda: MORNING)
    assert "d111111abcdef8.cloudfront.net" not in capsys.readouterr().out


def test_an_account_row_carries_its_pellier_url_for_the_recheck() -> None:
    row = _row(Session(_cfn([_root()]), Logs([_record()])))
    assert row.url == PELLIER_URL


def test_no_editor_token_reaches_the_saved_file_or_the_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _account_file(tmp_path, "team-01.env", CONSOLE_BLOCK)

    def real_row(path: Path, now: datetime, max_age: float) -> Any:
        session = Session(_cfn([_root()]), Logs([_record()]))
        base = readiness.Row(file=path.name, region="us-east-1")
        return readiness.account_row(session, base, now, max_age, _healthy)

    monkeypatch.setattr(readiness, "file_row", real_row)
    assert readiness.main(["--accounts", str(tmp_path)], now=lambda: NOW) == 0
    saved = (tmp_path / "pellier-urls.json").read_text(encoding="utf-8")
    out = capsys.readouterr()
    for text in (saved, out.out, out.err):
        assert EDITOR_TOKEN not in text and "tkn=" not in text
    assert "d111111abcdef8.cloudfront.net" not in out.out


# ---------------------------------------------------------------------------
# the record speaks for the instance and the stack as they are now
# ---------------------------------------------------------------------------


def test_a_record_from_another_instance_does_not_speak_for_this_box() -> None:
    row = _row(Session(_cfn([_root()]), Logs([{**_record(), "instanceId": "i-0old"}])))
    assert (row.icon, row.status) == ("⚠️", "no record (the newest record is from another instance)")


@pytest.mark.parametrize("ec2, status", [
    (Ec2({"i-0abc": "stopped"}), ("❌", "Code Editor instance not running")),
    (Ec2({}), ("❌", "Code Editor instance not running")),
    (Ec2(error="UnauthorizedOperation"), ("⚠️", "cannot read: UnauthorizedOperation")),
])
def test_the_editor_instance_must_be_running_now(ec2: Ec2, status: Tuple[str, str]) -> None:
    row = _row(Session(_cfn([_root()]), Logs([_record()]), ec2=ec2))
    assert (row.icon, row.status) == status


def test_a_stack_without_its_editor_instance_output_cannot_be_read() -> None:
    row = _row(Session(Cfn([_root()]), Logs([_record()])))
    assert (row.icon, row.status) == ("⚠️", "cannot read: NoEditorInstanceOutput")


def test_an_updated_stack_needs_a_record_newer_than_its_update() -> None:
    updated = {**_root("UPDATE_COMPLETE"), "LastUpdatedTime": NOW - timedelta(minutes=30)}
    row = _row(Session(_cfn([updated]), Logs([_record(age_hours=1)])))
    assert row.status == "no record (the newest record predates this stack)"


def test_a_fresh_stack_s_own_last_updated_time_does_not_age_its_record() -> None:
    # A CREATE_COMPLETE root carries a LastUpdatedTime about 30 s after its creation.
    fresh = {**_root(), "LastUpdatedTime": NOW - timedelta(minutes=10)}
    assert _row(Session(_cfn([fresh]), Logs([_record(age_hours=1)]))).icon == "✅"


# ---------------------------------------------------------------------------
# only a CloudFront URL is ever fetched, and a redirect is never followed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url, usable", [
    ("https://d111111abcdef8.cloudfront.net/ports/8000/", True),
    ("https://D111111ABCDEF8.CloudFront.net/editor/", True),
    ("http://d111111abcdef8.cloudfront.net/ports/8000/", False),
    ("https://cloudfront.net/ports/8000/", False),
    ("https://d111111abcdef8.cloudfront.net.example.com/", False),
    ("https://user:pw@d111111abcdef8.cloudfront.net/", False),
    ("https://d111111abcdef8.cloudfront.net:8443/", False),
    ("https://d111111abcdef8.cloudfront.net:abc/", False),
    ("https://169.254.169.254/latest/meta-data/", False),
    ("https://localhost/ports/8000/", False),
    ("", False),
])
def test_only_a_cloudfront_https_url_is_usable(url: str, usable: bool) -> None:
    assert readiness.usable_url(url) is usable


def test_an_unusable_url_is_never_fetched() -> None:
    fetched: List[str] = []
    bad = {**_root(), "Outputs": [
        {"OutputKey": "PellierURL", "OutputValue": "https://169.254.169.254/ports/8000/"},
        {"OutputKey": "CodeEditorURL", "OutputValue": EDITOR_URL}]}
    row = _row(Session(_cfn([bad]), Logs([_record()])),
               fetch=lambda url: fetched.append(url) or ANSWERS[url])
    assert row.status == "storefront does not answer (no usable PellierURL)"
    assert fetched == []


def test_a_tampered_saved_url_is_never_fetched_by_the_recheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    rows = {"a.env": _ready_row(tmp_path / "a.env", NOW, 24)._replace(
        url="https://127.0.0.1/ports/8000/")}
    _check_one(tmp_path, monkeypatch, rows)
    _no_aws(monkeypatch)
    monkeypatch.setattr(readiness, "_get", lambda url: pytest.fail(f"fetched {url}"))
    assert readiness.main(["--recheck", str(tmp_path)], now=lambda: MORNING) == 1
    assert "no usable PellierURL" in capsys.readouterr().out


def test_a_redirect_is_the_answer_and_is_never_followed() -> None:
    import http.server

    hits: List[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server's name
            hits.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/elsewhere")
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        code, _, _ = readiness._fetch(f"http://127.0.0.1:{server.server_address[1]}/start")
    finally:
        server.shutdown()
        server.server_close()
    assert code == 302 and hits == ["/start"]


# ---------------------------------------------------------------------------
# the laptop's packages: the backend lock's pins and hashes, installed with hashes required
# ---------------------------------------------------------------------------


def _blocks(text: str) -> Dict[str, str]:
    """Each requirement's pin line and hash lines, by package name."""
    blocks: Dict[str, str] = {}
    name = ""
    for line in text.splitlines():
        if line and not line.startswith((" ", "#")):
            name = line.split("==", 1)[0]
            blocks[name] = line
        elif line.strip().startswith("--hash=") and name:
            blocks[name] += "\n" + line.strip()
    return blocks


def test_the_laptop_requirements_are_the_backend_lock_s_pins_with_hashes() -> None:
    laptop = _blocks((REPO / "scripts" / "event_readiness_requirements.txt").read_text())
    backend = _blocks((REPO / "pellier" / "backend" / "requirements.lock").read_text())
    assert sorted(laptop) == ["boto3", "botocore", "jmespath", "python-dateutil", "s3transfer",
                              "six", "urllib3"]
    for name, block in laptop.items():
        assert "==" in block and "--hash=sha256:" in block, name
        assert block == backend[name], f"{name} drifted from pellier/backend/requirements.lock"


def test_the_runbook_installs_the_laptop_packages_with_hashes_required() -> None:
    runbook = (REPO / "docs" / "AGENTCORE-READINESS.md").read_text()
    assert "--require-hashes" in runbook
    assert "scripts/event_readiness_requirements.txt" in runbook
    assert "--with boto3" not in runbook


class Ingested(Logs):
    """FilterLogEvents with CloudWatch's own ingestion time for each record."""

    def __init__(self, events: List[Tuple[Dict[str, Any], datetime]]) -> None:
        super().__init__()
        self.ingested = events

    def filter_log_events(self, **kwargs: Any) -> Dict[str, Any]:
        def millis(moment: datetime) -> int:
            return int(moment.timestamp() * 1000)

        return {"events": [{"timestamp": millis(datetime.fromisoformat(r["recordedAt"])),
                            "ingestionTime": millis(at), "message": json.dumps(r)}
                           for r, at in self.ingested]}


def test_a_fast_box_clock_cannot_make_a_record_older_than_the_update_look_current() -> None:
    updated = {**_root("UPDATE_COMPLETE"), "LastUpdatedTime": NOW - timedelta(minutes=30)}
    # The box says 10 minutes ago; CloudWatch took it in two hours ago, before the update.
    logs = Ingested([(_record(age_hours=1 / 6), NOW - timedelta(hours=2))])
    row = _row(Session(_cfn([updated]), logs))
    assert row.status == "no record (the newest record predates this stack)"


def test_the_newest_record_is_the_one_cloudwatch_took_in_last() -> None:
    # By the boxes' clocks the READY record is newer; CloudWatch took the failing one in later.
    failing = _record(False, "x FAIL  backend down", age_hours=2 + 5 / 60)
    ready = _record(age_hours=2)
    logs = Ingested([(ready, NOW - timedelta(hours=2)),
                     (failing, NOW - timedelta(hours=1, minutes=55))])
    assert _row(Session(_cfn([_root()]), logs)).status == "backend down"


def test_a_box_clock_far_off_is_not_ready() -> None:
    logs = Ingested([(_record(age_hours=1), NOW - timedelta(hours=2))])
    row = _row(Session(_cfn([_root()]), logs))
    assert (row.icon, row.status) == ("⚠️", "box clock off by 60 min")


def test_a_normal_ingestion_delay_is_not_a_clock_problem() -> None:
    logs = Ingested([(_record(age_hours=1), NOW - timedelta(minutes=59, seconds=37))])
    assert _row(Session(_cfn([_root()]), logs)).icon == "✅"


@pytest.mark.parametrize("record", [
    {**_record(), "ready": False},                       # says READY, but not ready
    {**_record(), "final": "x FAIL  backend down"},      # says ready, final line failing
])
def test_ready_needs_both_the_flag_and_the_final_line(record: Dict[str, Any]) -> None:
    assert _row(Session(_cfn([_root()]), Logs([record]))).icon == "❌"


@pytest.mark.parametrize("health", [{"status": "healthy", "database": "disconnected"},
                                    {"status": "degraded", "database": "connected"}])
def test_healthy_needs_both_the_status_and_the_database(health: Dict[str, str]) -> None:
    row = _row(Session(_cfn([_root()]), Logs([_record()])),
               fetch=_answering(health=(200, "application/json", json.dumps(health))))
    assert row.icon == "❌" and row.status.startswith("storefront does not answer (database")


def test_an_editor_answer_without_its_health_field_is_not_the_editor() -> None:
    row = _row(Session(_cfn([_root()]), Logs([_record()])),
               fetch=_answering(editor=(200, "application/json", "{}")))
    assert row.status == "Code Editor does not answer (not the editor's health answer)"


def test_a_cell_cannot_carry_terminal_escapes() -> None:
    row = readiness.Row(file="a.env", icon="❌", status="x\x1b[2J\x1b]0;owned\x07\u202ey")
    printed = "\n".join(readiness.table([row]))
    assert "\x1b" not in printed and "\x07" not in printed and "\u202e" not in printed
    assert "⚠️" in "\n".join(readiness.table([readiness.Row(file="b.env", status="ok")]))


def test_a_damaged_saved_file_is_moved_aside_and_saving_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pellier-urls.json").write_text("{not json", encoding="utf-8")
    _check_one(tmp_path, monkeypatch, {"a.env": _ready_row(tmp_path / "a.env", NOW, 24)})
    assert list(readiness.saved_rows(tmp_path / "pellier-urls.json"))
    assert len(list(tmp_path.glob("pellier-urls.json.damaged-*"))) == 1


def test_a_leftover_world_readable_temp_file_is_made_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    leftover = tmp_path / ".pellier-urls.json.tmp"
    leftover.write_text("{}", encoding="utf-8")
    leftover.chmod(0o644)
    _check_one(tmp_path, monkeypatch, {"a.env": _ready_row(tmp_path / "a.env", NOW, 24)})
    assert (tmp_path / "pellier-urls.json").stat().st_mode & 0o777 == 0o600


def test_the_log_read_looks_back_fourteen_days_only() -> None:
    seen: List[Dict[str, Any]] = []

    class Watching(Logs):
        def filter_log_events(self, **kwargs: Any) -> Dict[str, Any]:
            seen.append(kwargs)
            return super().filter_log_events(**kwargs)

    readiness.latest_from_cloudwatch(Watching([_record()]))
    age_days = (time.time() * 1000 - seen[0]["startTime"]) / 86_400_000
    assert 13.9 < age_days < 14.1


def test_a_request_that_hangs_in_its_name_lookup_still_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = threading.Event()
    monkeypatch.setattr(readiness, "REQUEST_DEADLINE_SECONDS", 0.2)
    monkeypatch.setattr(readiness, "_fetch", lambda url: gate.wait(5) and (200, "", ""))
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        readiness._get("https://d111111abcdef8.cloudfront.net/ports/8000/")
    assert time.monotonic() - started < 1
    gate.set()


def test_an_error_inside_the_request_reaches_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(url: str) -> Tuple[int, str, str]:
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(readiness, "_fetch", refused)
    with pytest.raises(ConnectionRefusedError):
        readiness._get("https://d111111abcdef8.cloudfront.net/ports/8000/")



def test_a_newer_run_s_row_for_a_file_replaces_the_older_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    save = tmp_path / "saved.json"
    ready = _ready_row(tmp_path / "a.env", NOW, 24)
    _sweep(tmp_path / "sweep-1", monkeypatch, {"a.env": ready}, save)
    expired = readiness.Row(file="a.env", region="us-east-1", status="cannot read: ExpiredToken")
    _sweep(tmp_path / "sweep-2", monkeypatch, {"a.env": expired}, save)
    assert list(readiness.saved_rows(save).values()) == [expired._replace(status="cannot read")]


@pytest.mark.parametrize("body", ["[]", "null", '"healthy"', "42"])
def test_a_health_answer_that_is_not_an_object_is_not_ready(body: str) -> None:
    row = _row(Session(_cfn([_root()]), Logs([_record()])),
               fetch=_answering(health=(200, "application/json", body)))
    assert (row.icon, row.status) == (
        "❌", "storefront does not answer (the health answer is not a JSON object)")


def test_no_request_starts_once_the_account_s_budget_is_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock[0])
    asked: List[str] = []

    def slow_page(url: str) -> Tuple[int, str, str]:
        asked.append(url)
        if url == PELLIER_URL:
            clock[0] += readiness.PROBE_BUDGET_SECONDS + 1
        return ANSWERS[url]

    row = _row(Session(_cfn([_root()]), Logs([_record()])), fetch=slow_page)
    assert row.status == ("storefront does not answer (no answer within the account's time "
                          "budget)")
    assert asked == [PELLIER_URL]


def test_a_judging_error_is_a_failed_try_not_a_crash() -> None:
    def odd(url: str) -> Tuple[int, str, str]:
        raise RuntimeError("unexpected")

    row = _row(Session(_cfn([_root()]), Logs([_record()])), fetch=odd)
    assert (row.icon, row.status) == ("❌", "storefront does not answer (RuntimeError)")


def test_a_recheck_failure_keeps_the_account_it_belongs_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _check_one(tmp_path, monkeypatch, {"a.env": _ready_row(tmp_path / "a.env", NOW, 24)})
    _no_aws(monkeypatch)

    def broken(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(readiness, "browser_path", broken)
    (row,) = readiness.recheck_rows(tmp_path, MORNING, 24)
    assert (row.account, row.icon, row.status) == ("account-a", "⚠️", "cannot read: RuntimeError")



def test_a_file_that_now_repeats_another_account_drops_its_old_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    save = tmp_path / "saved.json"
    old_z = _ready_row(tmp_path / "z.env", NOW, 24)._replace(account="account-b")
    _sweep(tmp_path / "sweep-1", monkeypatch, {"z.env": old_z}, save)
    x = _ready_row(tmp_path / "x.env", NOW, 24)._replace(account="account-a")
    z_repeat = x._replace(file="z.env", icon="⚠️", status="same account as x.env")
    _sweep(tmp_path / "sweep-2", monkeypatch, {"x.env": x, "z.env": z_repeat}, save)
    assert list(readiness.saved_rows(save).values()) == [x]



# ---------------------------------------------------------------------------
# --teams: every team of the event has a row, and every row is a team of the event
# ---------------------------------------------------------------------------

JOIN_LINK = "https://catalog.example.invalid/join?access-code=team-secret-code"
TEAMS_HEADER = ("Team name,Team code,Participant count,Participant IDs,State,Deployment duration,"
                "AWS account ID,Join event URL,Last joined,Last account login,Last updated\n")


def _teams_csv(directory: Path, teams: List[Tuple[str, str]], mode: int = 0o600) -> Path:
    path = directory / "teams.csv"
    lines = [f"{name},code-{i},0,,Deployed,00:44:12,{account},{JOIN_LINK},-,-,-"
             for i, (name, account) in enumerate(teams)]
    path.write_text(TEAMS_HEADER + "\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(mode)
    return path


def test_every_team_of_the_event_must_have_a_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    accounts = tmp_path / "accounts"
    accounts.mkdir()
    rows = {name: _ready_row(accounts / name, NOW, 24) for name in ("a.env", "b.env")}
    for name in rows:
        _account_file(accounts, name, CONSOLE_BLOCK)
    monkeypatch.setattr(readiness, "file_row", lambda path, now, max_age: rows[path.name])
    teams = _teams_csv(tmp_path, [("Team 1", "account-a"), ("Team 2", "account-b"),
                                  ("Team 3", "account-c")])
    assert readiness.main(["--accounts", str(accounts), "--teams", str(teams)],
                          now=lambda: NOW) == 1
    out = capsys.readouterr().out
    assert "⚠️ not in this run (Team 3)" in out and out.rstrip().endswith("2 of 3 ready")
    assert "team-secret-code" not in out


def test_an_account_that_is_not_a_team_of_the_event_is_not_ready() -> None:
    rows = [_ready_row(Path("a.env"), NOW, 24), _ready_row(Path("x.env"), NOW, 24)]
    checked = readiness.against_teams(rows, {"account-a": "Team 1"}, "not in this run")
    assert [(r.file, r.icon, r.status) for r in checked] == [
        ("a.env", "✅", "READY FOR LAB 1"), ("x.env", "⚠️", "not a team of this event")]


def test_the_morning_recheck_counts_the_event_s_teams_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _check_one(tmp_path, monkeypatch, {"a.env": _ready_row(tmp_path / "a.env", NOW, 24)})
    teams = _teams_csv(tmp_path / "..", [("Team 1", "account-a"), ("Team 2", "account-b")])
    _no_aws(monkeypatch)
    monkeypatch.setattr(readiness, "_get", _healthy)
    assert readiness.main(["--recheck", str(tmp_path / "pellier-urls.json"),
                           "--teams", str(teams)], now=lambda: MORNING) == 1
    out = capsys.readouterr().out
    assert "⚠️ not in the saved run (Team 2)" in out and out.rstrip().endswith("1 of 2 ready")


def test_a_teams_file_others_can_read_is_refused(tmp_path: Path) -> None:
    teams = _teams_csv(tmp_path, [("Team 1", "account-a")], mode=0o644)
    (tmp_path / "pellier-urls.json").write_text('{"rows": []}', encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        readiness.main(["--recheck", str(tmp_path), "--teams", str(teams)], now=lambda: MORNING)
    assert stopped.value.code == 2


def test_a_teams_file_without_its_columns_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "teams.csv"
    path.write_text("Name,Account\nTeam 1,123456789012\n", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(readiness.CannotRead) as refused:
        readiness.event_teams(path)
    assert refused.value.code.startswith("TeamsColumns")


def test_only_the_account_and_name_columns_are_kept_and_zeros_come_back(tmp_path: Path) -> None:
    # A spreadsheet may drop an account ID's leading zeros; the padded ID below is fabricated.
    teams = _teams_csv(tmp_path, [("Team 1", "11112222"), ("Team 2", "123456789012")])
    assert readiness.event_teams(teams) == {"000011112222": "Team 1", "123456789012": "Team 2"}


def test_teams_and_save_need_a_fleet_run(tmp_path: Path) -> None:
    for extra in (["--teams", str(tmp_path / "t.csv")], ["--save", str(tmp_path / "s.json")]):
        with pytest.raises(SystemExit) as stopped:
            readiness.main(extra, now=lambda: NOW, on_box=False)
        assert stopped.value.code == 2



@pytest.mark.parametrize("status, saved", [
    ("READY FOR LAB 1", "READY FOR LAB 1"),
    ("setup failed: BootstrapWaitCondition: WaitCondition received failed message",
     "setup failed"),
    ("x FAIL  something the box printed", "the box's record is not ready"),
    ("storefront does not answer (HTTP 502)", "storefront does not answer"),
    ("cannot read: ExpiredToken", "cannot read"),
])
def test_a_saved_row_keeps_only_the_checker_s_own_words(status: str, saved: str) -> None:
    assert readiness.own_words(status) == saved


@pytest.mark.parametrize("text", [
    '{"rows": [{"file": "a.env", "file": "b.env"}]}',          # a repeated key
    '{"rows": ["a.env"]}',                                       # an entry that is not an object
    '{"rows": [{"file": "a.env", "account": 7}]}',               # a value that is not text
    '{"rows": [{"file": "a.env", "secret": "x"}]}',              # a field a row does not have
    '{"rows": [{"account": "account-a"}]}',                      # no file
    '{"rows": [{"file": "a.env", "account": "account-a"}]}',     # not every field
    '{"rows": ' + '[' * 100_000 + ']' * 100_000 + '}',            # nesting too deep to read
    '{"nothing": []}',
])
def test_a_saved_file_that_is_not_what_accounts_writes_is_refused(tmp_path: Path,
                                                                  text: str) -> None:
    path = tmp_path / "pellier-urls.json"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(readiness.CannotRead) as refused:
        readiness.saved_rows(path)
    assert refused.value.code == "MalformedSavedFile (pellier-urls.json)"


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "0", "-1", "73", "1e9"])
def test_the_age_limit_must_be_a_real_number_of_hours_an_event_can_last(
    tmp_path: Path, value: str,
) -> None:
    with pytest.raises(SystemExit) as stopped:
        readiness.main(["--accounts", str(tmp_path), "--max-age-hours", value], now=lambda: NOW)
    assert stopped.value.code == 2


def test_a_team_with_no_account_in_the_csv_is_a_finding(tmp_path: Path) -> None:
    path = tmp_path / "teams.csv"
    path.write_text(TEAMS_HEADER + f"Team 1,c-1,0,,Deployed,1,account-a,{JOIN_LINK},-,-,-\n"
                    + f"Team 2,c-2,0,,Failed,1,,{JOIN_LINK},-,-,-\n" + "Team 3\n",
                    encoding="utf-8")
    path.chmod(0o600)
    rows = readiness.against_teams([_ready_row(Path("a.env"), NOW, 24)],
                                   readiness.event_teams(path), "not in this run")
    assert sorted(r.status for r in rows if not r.ready) == [
        "no AWS account in the Teams CSV (Team 2)", "no AWS account in the Teams CSV (Team 3)"]



# ---------------------------------------------------------------------------
# private files: regular, owner-only, no ACL, bounded, text
# ---------------------------------------------------------------------------


def test_a_named_pipe_is_refused_without_hanging(tmp_path: Path) -> None:
    import os

    for name in ("team-01.env", "teams.csv", "pellier-urls.json"):
        pipe = tmp_path / name
        os.mkfifo(pipe, 0o600)
        started = time.monotonic()
        with pytest.raises(readiness.CannotRead) as refused:
            readiness.private_text(pipe)
        assert refused.value.code == f"NotAFile ({name})"
        assert time.monotonic() - started < 1
    row = readiness.file_row(tmp_path / "team-01.env", NOW, 24)
    assert row.status == "cannot read: NotAFile (team-01.env)"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS access control lists")
def test_a_file_shared_through_an_acl_is_refused(tmp_path: Path) -> None:
    import subprocess

    path = _account_file(tmp_path, "team-01.env", CONSOLE_BLOCK)
    assert readiness.private_text(path).startswith("export")
    subprocess.run(["/bin/chmod", "+a", "everyone allow read", str(path)], check=True)
    with pytest.raises(readiness.CannotRead) as refused:
        readiness.private_text(path)
    assert refused.value.code == "FileAcl (fix: chmod -N team-01.env)"


def test_a_teams_csv_saved_in_another_encoding_is_a_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "teams.csv"
    path.write_bytes((TEAMS_HEADER + f"Caf\u00e9,c,0,,Deployed,1,account-a,{JOIN_LINK},-,-,-\n")
                     .encode("cp1252"))
    path.chmod(0o600)
    with pytest.raises(readiness.CannotRead) as refused:
        readiness.event_teams(path)
    assert refused.value.code == "NotText (teams.csv: save it as UTF-8)"


def test_a_broken_csv_field_is_a_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "teams.csv"
    path.write_text(TEAMS_HEADER + "Team 1," + "x" * 200_000 + ",0,,D,1,account-a,,-,-,-\n",
                    encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(readiness.CannotRead) as refused:
        readiness.event_teams(path)
    assert refused.value.code == "TeamsFile (teams.csv: Error)"


def test_a_teams_problem_is_a_usage_error_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    teams = tmp_path / "teams.csv"
    teams.write_bytes("Team name,AWS account ID\nCaf\u00e9,1\n".encode("cp1252"))
    teams.chmod(0o600)
    (tmp_path / "pellier-urls.json").write_text('{"rows": []}', encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        readiness.main(["--recheck", str(tmp_path), "--teams", str(teams)], now=lambda: MORNING)
    assert stopped.value.code == 2
    assert "NotText" in capsys.readouterr().err


def test_an_oversized_private_file_is_refused(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readiness, "PRIVATE_FILE_BYTES", 100)
    path = _account_file(tmp_path, "team-01.env", CONSOLE_BLOCK + "#" * 200)
    with pytest.raises(readiness.CannotRead) as refused:
        readiness.private_text(path)
    assert refused.value.code == "FileTooLarge (team-01.env)"



def test_a_link_is_refused_even_to_a_private_file(tmp_path: Path) -> None:
    target = _account_file(tmp_path, "real.env", CONSOLE_BLOCK)
    link = tmp_path / "team-01.env"
    link.symlink_to(target)
    with pytest.raises(readiness.CannotRead) as refused:
        readiness.private_text(link)
    assert refused.value.code == "NotAFile (team-01.env is a link)"
    assert readiness.file_row(link, NOW, 24).status == ("cannot read: NotAFile (team-01.env is "
                                                       "a link)")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS ACL listing")
def test_a_file_name_like_an_option_is_still_a_file_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A relative folder (--accounts .) gives relative names, so "-le ..." reaches ls as is.
    _account_file(tmp_path, "-le team é.env", CONSOLE_BLOCK)
    monkeypatch.chdir(tmp_path)
    assert readiness.private_text(Path("-le team é.env")).startswith("export")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS ACL listing")
def test_an_acl_that_cannot_be_listed_refuses_the_file_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _account_file(tmp_path, "team-01.env", CONSOLE_BLOCK)

    def undecodable(*args: Any, **kwargs: Any) -> Any:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(readiness.subprocess, "run", undecodable)
    with pytest.raises(readiness.CannotRead) as refused:
        readiness.private_text(path)
    assert refused.value.code == "AclUnreadable (UnicodeDecodeError: team-01.env)"


def test_a_read_error_after_opening_is_a_clear_error(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    path = _account_file(tmp_path, "team-01.env", CONSOLE_BLOCK)

    def failing_fstat(descriptor: int) -> Any:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "fstat", failing_fstat)
    with pytest.raises(readiness.CannotRead) as refused:
        readiness.private_text(path)
    assert refused.value.code == "OSError (team-01.env)"
