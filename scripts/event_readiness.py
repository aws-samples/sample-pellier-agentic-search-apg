#!/usr/bin/env python3
"""Record, and read back, whether a workshop box is ready for the event.

Bootstrap runs ``--record`` once the environment is up: the same read-only checks as
``workshop-start.sh`` (Theo's AgentCore Memory included), capped so they cannot hold
provisioning. The result, with its UTC time and a final line that reads ``READY FOR LAB 1``
or names the first failing check, goes to ``~/.pellier/readiness.json`` in the participant's
home and to CloudWatch Logs, ``/aws/pellier/readiness``, one stream per instance. Nothing is
shown to participants; this is the facilitator's check before the event.

    uv run scripts/event_readiness.py            # on the box: the latest record and when it ran
    uv run scripts/event_readiness.py --live     # on the box only: run the checks again now
    uv run scripts/event_readiness.py --record   # bootstrap: run, cap and record

On the box (the repository at ``/workshop/sample-pellier-agentic-search-apg``, or a host with
``/etc/pellier``) the latest record is the local file, its Memory deep dive line is read again
from the background check's status, and ``--live`` records again. From a laptop with the event
account's Ops credentials, the latest record comes from CloudWatch Logs as it was recorded.
A laptop never runs the checks on a box: they include a managed AgentCore turn as Marco, which
would add to a participant's lab history, and the box cannot tell whether a lab has started.

A failing check is a line that starts ``x FAIL``; a ``Facilitator:`` warning also makes the
box not ready, because it names something a later lab needs even when Lab 1 could start.

Exit status: 0 when the record reads READY FOR LAB 1, 1 when it does not or there is none. A
record older than ``--max-age-hours`` is flagged STALE and keeps its status.

Every account of an event at once, from a laptop, without joining or claiming any of them.
Install the laptop's packages once, with their hashes required (the pins are the backend
lock's, held there by a test):

    uv venv --python 3.14 ~/.pellier-readiness
    uv pip install --python ~/.pellier-readiness --require-hashes \
        -r scripts/event_readiness_requirements.txt
    ~/.pellier-readiness/bin/python scripts/event_readiness.py --accounts DIR

DIR holds one ``*.env`` file per account, mode 0600: the event console's Teams > Access AWS
account > Ops role block, pasted as is, then ``AWS_DEFAULT_REGION=<region>`` on its own line.
The files are parsed, never sourced, and no credential is printed. Each account is read only:
its root CloudFormation stack, its newest record in CloudWatch Logs, and the three requests
a participant's browser makes, with no token or sign-in: the Storefront page, Pellier's health
with its database, and the Code Editor server's own health. Eight
accounts are read at a time, one row each, in file-name order:

    ✅ READY FOR LAB 1
    ❌ the record's first failing check, "setup failed: <CloudFormation's first failure>"
       or "storefront does not answer (<why>)" or "Code Editor does not answer (<why>)"
    ⚠️ STALE (<age>), no record (<stack status>), setup still running (<stack status>),
       setup not complete (<stack status>), no workshop stack in this Region,
       box clock off by <minutes> min, same account as <file>, or cannot read: <error>

It ends "N of M ready" and exits 0 only when every row is ✅ and there is at least one, 1
otherwise, and 2 on a usage error. ``--accounts`` never runs checks on a box: the box has no
guard for a lab in progress, so ``--live`` stays one account at a time.

``--accounts`` also saves each row, with the account's Pellier URL, in DIR/pellier-urls.json
(mode 0600), or in ``--save FILE`` when DIR is deleted after the run. Rows merge by account,
so a run over some teams keeps the others. On the morning of the session, when yesterday's
credentials have expired:

    ~/.pellier-readiness/bin/python scripts/event_readiness.py --recheck DIR_OR_FILE

needs no credentials and makes no AWS call; it allows records up to 36 hours old by default.
``--teams CSV`` (the event console's Teams > Download CSV, mode 0600) makes every team of the
event need a row in either run. Overnight nothing reruns a box's record or
changes its stack, so it asks only whether each account's browser path still answers: ✅ when
the account was ✅ at the last --accounts run and the browser path answers now. Given the
folder, every *.env file in it also gets a row, so a file no --accounts run read still shows.
"""

from __future__ import annotations

import argparse
import csv
import errno
import io
import json
import math
import os
import re
import socket
import stat
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
READY = "READY FOR LAB 1"
LOG_GROUP = "/aws/pellier/readiness"
DEFAULT_CAP_SECONDS = 180
DEFAULT_MAX_AGE_HOURS = 24
# The morning recheck follows a day-before --accounts run: records are about a day old by then.
DEFAULT_RECHECK_MAX_AGE_HOURS = 36
TEAMS_ACCOUNT_COLUMN = "AWS account ID"
TEAMS_NAME_COLUMN = "Team name"
NO_ACCOUNT = "no account, row "  # a Teams CSV row with a blank account cell
PRIVATE_FILE_BYTES = 4 * 1024 * 1024  # credential files, the Teams CSV and the saved run
ACL_ENTRY = re.compile(r"^\s*\d+: ", re.MULTILINE)
# A Workshop Studio event lasts at most 72 hours, so no account's record can honestly be older.
MAX_AGE_LIMIT_HOURS = 72
# The checker's own words: a saved row keeps only these, never CloudFormation's or a box's text.
OWN_WORDS = ("READY FOR LAB 1", "setup failed", "setup still running", "setup not complete",
             "no record", "no workshop stack in this Region", "STALE", "box clock off",
             "Code Editor instance not running", "storefront does not answer",
             "Code Editor does not answer", "cannot read", "not a team of this event")
BOX_REPO = "/workshop/sample-pellier-agentic-search-apg"
BOX_USER = "participant"
DEEP_DIVE_PREFIX = "i  Memory deep dive (optional appendix):"
CLOUDWATCH_DENIED = (f"Readiness: these credentials cannot read {LOG_GROUP} in CloudWatch Logs. "
                     "Use the event's Ops credentials.")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
Record = Dict[str, Any]
MAX_LOG_PAGES = 100
CLOCK_SKEW_SECONDS = 900
LOG_LOOKBACK_DAYS = 14
REGION_NAME = re.compile(r"^[a-z]{2}(-[a-z]+)+-[0-9]+$")
MAX_PARALLEL_ACCOUNTS = 8
STACK_PARAMETER = "InfrastructureRevision"
# Only a complete stack lets the record decide.
HEALTHY_STACK_STATES = ("CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE")
RUNNING_STACK_STATES = ("CREATE_IN_PROGRESS", "UPDATE_IN_PROGRESS",
                        "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS")
FAILED_STACK_MARKS = ("FAILED", "ROLLBACK")
NO_STACK = "no workshop stack in this Region"
SAME_ACCOUNT = "same account as"
NESTED_STACK = "AWS::CloudFormation::Stack"
MAX_STACKS_READ = 20
REASON_CHARS = 160
PROBE_SECONDS = 15
# Pellier's health gets three tries, five seconds apart, so a database resuming from a pause
# (about 15 s) still answers; the page and the editor get two. No request starts after an
# account's PROBE_BUDGET_SECONDS, so one account takes at most that plus one request's
# deadline, and a fleet of unreachable accounts still finishes in minutes.
PROBE_ATTEMPTS = 2
DATABASE_ATTEMPTS = 3
PROBE_PAUSE_SECONDS = 5
PROBE_BUDGET_SECONDS = 60
# The socket timeout does not cover the name lookup, so each request also has a hard deadline.
REQUEST_DEADLINE_SECONDS = PROBE_SECONDS + 5
URL_HOST_SUFFIX = ".cloudfront.net"
HEADERS = ("File", "Account", "Region", "Instance", "Recorded (UTC)", "Status")
SAVED_URLS = "pellier-urls.json"
RECORDED_FORMAT = "%Y-%m-%d %H:%M"
# KEY=value, quoted or bare. A bare value ends at the next KEY_NAME= so a region line glued
# onto the session token's line (the console block has no final newline) still parses.
ASSIGNMENT = re.compile(
    r"(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)="
    r"(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'"
    r"|(?P<bare>[^\s\"']*?)(?=\s|$|(?:export\s+)?[A-Z][A-Z0-9]*_[A-Z0-9_]*=))")


class CannotRead(Exception):
    """One account could not be read; ``code`` is the AWS error code or the reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CloudWatchDenied(RuntimeError):
    """The caller's credentials may not read the readiness log group."""


def running_on_box(repo: Path, etc: Path = Path("/etc/pellier")) -> bool:
    """Workshop Studio hosts have no /etc/pellier, but always clone the repository to BOX_REPO."""
    return repo == Path(BOX_REPO) or etc.is_dir()


def local_record_path() -> Path:
    override = os.environ.get("PELLIER_READINESS_FILE")
    return Path(override) if override else Path.home() / ".pellier" / "readiness.json"


def deep_dive_status_path() -> Path:
    override = os.environ.get("PELLIER_MEMORY_DEEP_DIVE_FILE")
    return Path(override) if override else Path("/var/lib/pellier/memory-deep-dive.json")


def deep_dive_note(path: Path) -> Optional[str]:
    """One informational line for the appendix's Memory deep dive; never a readiness gate.

    scripts/deploy/check_memory_deep_dive.py writes the status after handout, because an
    episode can form long after provisioning ends.
    """
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    prefix = DEEP_DIVE_PREFIX
    state = status.get("status")
    if state == "ready":
        return f"{prefix} every strategy holds a record"
    if state == "checking":
        return (f"{prefix} records still forming, checked in the background since "
                f"{status.get('startedAt', '')}")
    if state == "incomplete":
        missing = ", ".join(status.get("missing") or []) or "unknown"
        return (f"{prefix} {missing} not formed after {status.get('elapsedSeconds')} s; "
                "the deep dive shows what has")
    return f"{prefix} the background check could not read Memory ({status.get('error', state)})"


# ---------------------------------------------------------------------------
# the checks and their verdict
# ---------------------------------------------------------------------------


def _clean(text: str) -> List[str]:
    return [ANSI.sub("", line).rstrip() for line in text.splitlines() if line.strip()]


def run_checks(run: Callable[..., Any] = subprocess.run, cap: int = DEFAULT_CAP_SECONDS,
               repo: Path = REPO) -> Tuple[List[str], Optional[int]]:
    """workshop-start.sh's lines and exit status; ``None`` when it ran past ``cap``.

    ``PELLIER_READINESS_RECORD=1`` adds the checks only the facilitator's record runs, such
    as each AgentCore Runtime's platform version.
    """
    argv = ["bash", str(repo / "scripts" / "workshop-start.sh")]
    env = {**os.environ, "PELLIER_READINESS_RECORD": "1"}
    try:
        completed = run(argv, capture_output=True, text=True, timeout=cap, check=False, env=env)
    except subprocess.TimeoutExpired as exc:
        partial = exc.output if isinstance(exc.output, str) else (exc.output or b"").decode()
        return _clean(partial), None
    return _clean((completed.stdout or "") + (completed.stderr or "")), completed.returncode


def verdict(lines: List[str], code: Optional[int], cap: int) -> Tuple[bool, str]:
    """Ready, and the final line: READY FOR LAB 1, or the first check that failed."""
    if code is None:
        return False, f"x FAIL  the readiness check did not finish within {cap} s"
    failed = next((line.strip() for line in lines if line.strip().startswith("x FAIL")), "")
    if code != 0:
        return False, failed or f"x FAIL  workshop-start.sh exited {code}"
    issue = next((line.split("WARN", 1)[-1].strip() for line in lines
                  if "Facilitator:" in line), "")
    if issue:
        return False, issue
    if any("Ready for Lab 1" in line for line in lines):
        return True, READY
    return False, "x FAIL  workshop-start.sh did not report Ready for Lab 1"


def imds_instance_id() -> str:
    """This EC2 instance's id through IMDSv2, or the host name off EC2."""
    try:
        token_request = urllib.request.Request(
            "http://169.254.169.254/latest/api/token", method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"})
        with urllib.request.urlopen(token_request, timeout=2) as response:
            token = response.read().decode()
        id_request = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token})
        with urllib.request.urlopen(id_request, timeout=2) as response:
            return response.read().decode().strip()
    except OSError:
        return socket.gethostname()


# ---------------------------------------------------------------------------
# where a record lives
# ---------------------------------------------------------------------------


def write_local(record: Record, path: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    partial = path.with_suffix(".tmp")
    partial.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    partial.chmod(0o600)
    partial.replace(path)


def read_local(path: Path) -> Optional[Record]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _already_exists(exc: Exception) -> bool:
    return "ResourceAlreadyExists" in f"{type(exc).__name__} {exc}"


def write_cloudwatch(record: Record, logs: Any) -> None:
    stream = str(record["instanceId"])
    for create, kwargs in ((logs.create_log_group, {"logGroupName": LOG_GROUP}),
                           (logs.create_log_stream,
                            {"logGroupName": LOG_GROUP, "logStreamName": stream})):
        try:
            create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - only "already exists" is expected
            if not _already_exists(exc):
                raise
    stamp = int(datetime.fromisoformat(record["recordedAt"]).timestamp() * 1000)
    logs.put_log_events(logGroupName=LOG_GROUP, logStreamName=stream,
                        logEvents=[{"timestamp": stamp, "message": json.dumps(record)}])


def latest_from_cloudwatch(logs: Any) -> Optional[Record]:
    """The newest record across every instance's stream, or None when there is none.

    Reads with FilterLogEvents only, the call the event's Ops role is proven to have, over
    the last LOG_LOOKBACK_DAYS days.

    Raises:
        CloudWatchDenied: the credentials may not read the log group.
        CannotRead: more pages than MAX_LOG_PAGES, so the newest record is not known.
    """
    try:
        newest = _newest_event(logs)
    except CannotRead:
        raise
    except Exception as exc:  # noqa: BLE001 - a missing group is simply no record
        text = f"{type(exc).__name__} {exc}"
        if "ResourceNotFound" in text:
            return None
        if "AccessDenied" in text:
            raise CloudWatchDenied(CLOUDWATCH_DENIED) from exc
        raise
    if newest is None:
        return None
    record = json.loads(newest["message"])
    if isinstance(record, dict) and newest.get("ingestionTime"):
        # AWS's clock, not the box's: a fast box clock cannot make an old record look new.
        record["ingestedAt"] = datetime.fromtimestamp(newest["ingestionTime"] / 1000,
                                                      timezone.utc).isoformat()
    return record


def _newest_event(logs: Any) -> Optional[Dict[str, Any]]:
    """The log group's event CloudWatch took in last, within the look-back."""
    since = int((time.time() - LOG_LOOKBACK_DAYS * 86400) * 1000)
    query: Dict[str, Any] = {"logGroupName": LOG_GROUP, "startTime": since}
    newest: Optional[Dict[str, Any]] = None
    for _ in range(MAX_LOG_PAGES):
        page = logs.filter_log_events(**query)
        for event in page.get("events") or []:
            if newest is None or _arrived(event) >= _arrived(newest):
                newest = event
        if not page.get("nextToken"):
            return newest
        query["nextToken"] = page["nextToken"]
    raise CannotRead("TooManyLogEvents")


def _arrived(event: Dict[str, Any]) -> int:
    """When CloudWatch took the event in, by AWS's clock; the box's timestamp when absent."""
    return int(event.get("ingestionTime") or event["timestamp"])


# ---------------------------------------------------------------------------
# what the facilitator reads
# ---------------------------------------------------------------------------


def _age(recorded: datetime, now: datetime) -> Tuple[float, str]:
    hours = (now - recorded).total_seconds() / 3600
    text = f"{round(hours)} h ago" if hours >= 1 else f"{round(hours * 60)} min ago"
    return hours, text


def render(record: Record, now: datetime, max_age_hours: float) -> List[str]:
    recorded = datetime.fromisoformat(record["recordedAt"])
    hours, age = _age(recorded, now)
    out = [f"Recorded {record['recordedAt']} ({age}) on {record.get('instanceId', '?')}"]
    if hours > max_age_hours:
        out.append(f"STALE: recorded {round(hours)} h ago, more than {max_age_hours:g} h; "
                   "run with --live before the event")
    out += [f"  {line}" for line in record.get("lines", [])[:-1]]
    out.append(record.get("final", ""))
    return out


def with_current_deep_dive(record: Record, status_path: Path) -> Record:
    """The record with its deep-dive line as the background check reports it now.

    The check finishes after bootstrap records readiness, so the stored line can be stale.
    An unreadable status keeps the stored line.
    """
    note = deep_dive_note(status_path)
    if note is None:
        return record
    body = [line for line in record.get("lines", [])[:-1]
            if not line.startswith(DEEP_DIVE_PREFIX)]
    return {**record, "lines": [*body, note, record.get("final", "")]}


def record_now(run: Callable[..., Any], logs: Any, local: Path, now: datetime,
               instance_id: str, cap: int) -> Record:
    lines, code = run_checks(run=run, cap=cap)
    ready, final = verdict(lines, code, cap)
    note = deep_dive_note(deep_dive_status_path())
    if note:
        lines = [*lines, note]
    record = {"recordedAt": now.isoformat(), "instanceId": instance_id, "ready": ready,
              "final": final, "lines": [*lines, final]}
    write_local(record, local)
    try:
        write_cloudwatch(record, logs() if callable(logs) else logs)
    except Exception as exc:  # noqa: BLE001 - the local record stands; say what failed
        print(f"Readiness: could not write the CloudWatch record ({type(exc).__name__}: "
              f"{str(exc)[:160]}); the local record is {local}", file=sys.stderr)
    return record


# ---------------------------------------------------------------------------
# every account of an event, from a laptop: --accounts DIR, read only
# ---------------------------------------------------------------------------


class Row(NamedTuple):
    """One account in the fleet table."""

    file: str
    account: str = "-"
    region: str = "-"
    instance: str = "-"
    recorded: str = "-"
    icon: str = "⚠️"
    status: str = ""
    url: str = ""  # the stack's PellierURL; saved for --recheck, never printed
    editor: str = ""  # CodeEditorURL without its tkn= query; saved, never printed

    @property
    def ready(self) -> bool:
        return self.icon == "✅"


def error_code(error: BaseException) -> str:
    """The AWS error code of a botocore error, or the exception's type."""
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        code = (response.get("Error") or {}).get("Code")
        if code:
            return str(code)
    return type(error).__name__


def all_stacks(cfn: Any) -> List[Dict[str, Any]]:
    return [stack for page in cfn.get_paginator("describe_stacks").paginate()
            for stack in page.get("Stacks") or []]


def root_stack(stacks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The Workshop Studio root stack: no parent, and the InfrastructureRevision parameter."""
    roots = [stack for stack in stacks if not stack.get("ParentId")
             and STACK_PARAMETER in {p.get("ParameterKey") for p in stack.get("Parameters") or []}]
    return max(roots, key=lambda stack: stack["CreationTime"], default=None)


def editor_instance(stacks: List[Dict[str, Any]], root: Dict[str, Any]) -> str:
    """The Code Editor instance this root stack made: its nested stack's InstanceId output."""
    for stack in stacks:
        if stack.get("RootId") == root.get("StackId"):
            found = stack_output(stack, "InstanceId")
            if found.startswith("i-"):
                return found
    return ""


def instance_state(ec2: Any, instance_id: str) -> str:
    """The EC2 instance's state name; "gone" when EC2 no longer knows it."""
    try:
        reservations = ec2.describe_instances(InstanceIds=[instance_id]).get("Reservations")
    except Exception as exc:  # noqa: BLE001 - only "not found" is an answer; the rest raise
        if error_code(exc).startswith("InvalidInstanceID"):
            return "gone"
        raise
    states = [str((item.get("State") or {}).get("Name", "unknown"))
              for reservation in reservations or [] for item in reservation.get("Instances") or []]
    return states[0] if states else "gone"


def family_events(cfn: Any, root_id: str) -> List[Dict[str, Any]]:
    """Events of the root stack and of every nested stack it made, deleted ones included.

    A rollback deletes the nested stacks and DescribeStacks lists only live ones, so each
    nested stack is found by the ARN in its parent's events.
    """
    events: List[Dict[str, Any]] = []
    pending, seen = [root_id], set()
    while pending and len(seen) < MAX_STACKS_READ:
        stack_id = pending.pop()
        if stack_id in seen:
            continue
        seen.add(stack_id)
        pages = cfn.get_paginator("describe_stack_events").paginate(StackName=stack_id)
        found = [event for page in pages for event in page.get("StackEvents") or []]
        events += found
        pending += [str(event["PhysicalResourceId"]) for event in found
                    if event.get("ResourceType") == NESTED_STACK
                    and str(event.get("PhysicalResourceId", "")).startswith("arn:")]
    return events


def short_reason(text: str) -> str:
    """A reason that fits one row; a wait condition's cause ends its message."""
    reason = re.sub(r"'? for uniqueId: \S+$", "", " ".join(text.split()))
    if len(reason) <= REASON_CHARS:
        return reason
    return f"{reason[:40]} … {reason[-(REASON_CHARS - 43):]}"


def first_failure(cfn: Any, root: Dict[str, Any]) -> str:
    """The earliest failed resource across the root and its nested stacks, or ""."""
    try:
        failures = [event for event in family_events(cfn, root["StackId"])
                    if str(event.get("ResourceStatus", "")).endswith("_FAILED")
                    and "cancelled" not in event.get("ResourceStatusReason", "")
                    and "Embedded stack" not in event.get("ResourceStatusReason", "")]
    except Exception:  # noqa: BLE001 - the root's own reason still names the failure
        return ""
    if not failures:
        return ""
    first = min(failures, key=lambda event: event["Timestamp"])
    return f"{first['LogicalResourceId']}: {short_reason(first.get('ResourceStatusReason', ''))}"


def stack_failed(status: str) -> bool:
    return any(mark in status for mark in FAILED_STACK_MARKS)


def stack_row(base: Row, cfn: Any, stacks: List[Dict[str, Any]]
              ) -> Tuple[Optional[Row], Optional[Dict[str, Any]]]:
    """The row CloudFormation alone decides, or None, and the root stack when there is one."""
    root = root_stack(stacks)
    if root is None:
        return None, None
    status = str(root["StackStatus"])
    if stack_failed(status):
        reason = first_failure(cfn, root) or short_reason(root.get("StackStatusReason", ""))
        return base._replace(icon="❌", status=f"setup failed: {reason or status}"), root
    return None, root


def stack_output(root: Dict[str, Any], key: str) -> str:
    return next((str(o.get("OutputValue", "")) for o in root.get("Outputs") or []
                 if o.get("OutputKey") == key), "")


Fetch = Callable[[str], Tuple[int, str, str]]


def usable_url(url: str) -> bool:
    """An https URL on a CloudFront distribution's own host, with no user info and no port.

    The URLs come from stack outputs or a saved file, so anything else is never fetched.
    """
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    host = parts.hostname or ""
    return (parts.scheme == "https" and host.endswith(URL_HOST_SUFFIX)
            and len(host) > len(URL_HOST_SUFFIX) and "@" not in parts.netloc and port is None)


def editor_base(url: str) -> str:
    """The CodeEditorURL output without its query: the tkn= credential is dropped here."""
    parts = urllib.parse.urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}{parts.path or '/'}"


def _page(code: int, kind: str, body: str) -> str:
    if code != 200:
        return f"HTTP {code}"
    return "" if "text/html" in kind else "not an HTML page"


def _database(code: int, kind: str, body: str) -> str:
    if code != 200:
        return f"HTTP {code}"
    try:
        health = json.loads(body)
    except ValueError:
        return "the health answer is not JSON"
    if not isinstance(health, dict):
        return "the health answer is not a JSON object"
    if health.get("status") != "healthy" or health.get("database") != "connected":
        return (f"database not ready: status {health.get('status')}, "
                f"database {health.get('database')}")
    return ""


def _editor(code: int, kind: str, body: str) -> str:
    if code != 200:
        return f"HTTP {code}"
    try:
        health = json.loads(body)
    except ValueError:
        return "not the editor's health answer"
    return "" if isinstance(health, dict) and "hasActiveConnections" in health else \
        "not the editor's health answer"


def _ask(fetch: Fetch, url: str, judge: Callable[[int, str, str], str], attempts: int,
         deadline: float) -> str:
    """"" once ``judge`` accepts an answer, within ``attempts`` tries before ``deadline``."""
    if time.monotonic() >= deadline:
        return "no answer within the account's time budget"
    why = ""
    for attempt in range(attempts):
        if attempt:
            if time.monotonic() + PROBE_PAUSE_SECONDS >= deadline:
                break
            _pause(PROBE_PAUSE_SECONDS)
        try:
            why = judge(*fetch(url))
        except Exception as exc:  # noqa: BLE001 - any failure is a failed try, named by type
            why = type(exc).__name__
        if not why:
            return ""
    return why or "no answer"


def browser_path(url: str, editor: str, fetch: Optional[Fetch] = None) -> str:
    """"" when a participant's browser would get through now, else the row's reason.

    The three requests a participant's browser makes, through CloudFront and nginx, with no
    token and no sign-in: the Storefront page, Pellier's health (its database, and the one
    Bedrock embedding of "test" that every Storefront load also makes), and the Code Editor
    server's own health. No file, row or setting changes and no team is claimed. No URL is
    printed: each names the account's CloudFront distribution.
    """
    get = fetch or _get
    deadline = time.monotonic() + PROBE_BUDGET_SECONDS
    if not usable_url(url):
        return "storefront does not answer (no usable PellierURL)"
    for target, judge, attempts in ((url, _page, PROBE_ATTEMPTS),
                                    (url.rstrip("/") + "/api/health", _database,
                                     DATABASE_ATTEMPTS)):
        why = _ask(get, target, judge, attempts, deadline)
        if why:
            return f"storefront does not answer ({why})"
    if not usable_url(editor):
        return "Code Editor does not answer (no usable CodeEditorURL)"
    why = _ask(get, editor.rstrip("/") + "/healthz", _editor, PROBE_ATTEMPTS, deadline)
    return f"Code Editor does not answer ({why})" if why else ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is the answer, never followed: it could point anywhere."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _get(url: str) -> Tuple[int, str, str]:
    """One GET with a hard deadline, name lookup included.

    Raises:
        TimeoutError: no answer within REQUEST_DEADLINE_SECONDS.
    """
    box: Dict[str, Any] = {}

    def work() -> None:
        try:
            box["answer"] = _fetch(url)
        except Exception as exc:  # noqa: BLE001 - handed to the caller below
            box["error"] = exc

    worker = threading.Thread(target=work, daemon=True)  # a stuck lookup cannot hold the exit
    worker.start()
    worker.join(REQUEST_DEADLINE_SECONDS)
    if worker.is_alive():
        raise TimeoutError(f"no answer within {REQUEST_DEADLINE_SECONDS} s")
    if "error" in box:
        raise box["error"]
    return box["answer"]


def _fetch(url: str) -> Tuple[int, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "pellier-event-readiness"})
    try:
        with _OPENER.open(request, timeout=PROBE_SECONDS) as response:
            return (response.status, response.headers.get("Content-Type", ""),
                    response.read(65536).decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, "", ""


def _pause(seconds: float) -> None:
    time.sleep(seconds)


def _age_text(hours: float) -> str:
    return f"{round(hours)} h old" if hours < 48 else f"{round(hours / 24)} days old"


def _when(text: Any) -> Optional[datetime]:
    try:
        moment = datetime.fromisoformat(str(text)) if text else None
    except ValueError:
        return None
    return moment if moment is not None and moment.tzinfo is not None else None


def recorded_at(record: Record) -> Optional[datetime]:
    """The record's time with its zone, or None when it is missing or has no zone."""
    try:
        recorded = datetime.fromisoformat(str(record["recordedAt"]))
    except (KeyError, ValueError):
        return None
    return recorded if recorded.tzinfo is not None else None


def stack_formed(root: Dict[str, Any]) -> datetime:
    """When the stack took its current form: its last update, for an UPDATE_* status only.

    A freshly created stack also carries a LastUpdatedTime, about 30 s after creation, so
    using it for every status would call each fresh record older than its stack.
    """
    if str(root.get("StackStatus", "")).startswith("UPDATE_") and root.get("LastUpdatedTime"):
        return root["LastUpdatedTime"]
    return root["CreationTime"]


def record_doubt(base: Row, root: Dict[str, Any], recorded: datetime, arrived: datetime,
                 now: datetime, max_age: float) -> Optional[Row]:
    """Why this record cannot speak for this stack now, or None.

    ``arrived`` is when CloudWatch took the record in (AWS's clock); ``recorded`` is the box's
    own time, shown and used for its age.
    """
    status = str(root["StackStatus"])
    if status in RUNNING_STACK_STATES:
        return base._replace(status=f"setup still running ({status})")
    if status not in HEALTHY_STACK_STATES:
        return base._replace(status=f"setup not complete ({status})")
    if arrived < stack_formed(root):
        # The box makes the log group, so it outlives a stack: an older box's record.
        return base._replace(status="no record (the newest record predates this stack)")
    off = abs((recorded - arrived).total_seconds())
    if off > CLOCK_SKEW_SECONDS:
        # The record's age is the box's clock: a clock this far off makes the age wrong.
        return base._replace(status=f"box clock off by {round(off / 60)} min")
    hours = (now - recorded).total_seconds() / 3600
    if hours < -0.1:
        return base._replace(status="cannot read: MalformedRecord (recorded in the future)")
    if hours > max_age:
        return base._replace(status=f"STALE ({_age_text(hours)})")
    return None


def record_row(base: Row, root: Dict[str, Any], record: Record, now: datetime,
               max_age: float) -> Row:
    """The row a record decides, once CloudFormation has not failed the stack.

    ✅ here still needs instance_row: the instance and the browser path, checked now.
    """
    recorded = recorded_at(record)
    if recorded is None:
        return base._replace(status="cannot read: MalformedRecord")
    base = base._replace(instance=str(record.get("instanceId") or "-"),
                         recorded=recorded.astimezone(timezone.utc).strftime(RECORDED_FORMAT))
    arrived = _when(record.get("ingestedAt")) or recorded
    doubt = record_doubt(base, root, recorded, arrived, now, max_age)
    if doubt is not None:
        return doubt
    if record.get("ready") is not True or record.get("final") != READY:
        final = str(record.get("final") or "no final line")
        return base._replace(icon="❌", status=final.replace("x FAIL", "", 1).strip())
    return base._replace(icon="✅", status=READY)


def account_row(session: Any, base: Row, now: datetime, max_age: float,
                fetch: Optional[Fetch] = None) -> Row:
    """One account's row; every failure becomes the row's reason."""
    try:
        base = base._replace(account=str(_aws(session, "sts").get_caller_identity()["Account"]))
        cfn = _aws(session, "cloudformation")
        stacks = all_stacks(cfn)
        decided, root = stack_row(base, cfn, stacks)
        if decided is not None:
            return decided
        if root is not None:
            base = base._replace(url=stack_output(root, "PellierURL"),
                                 editor=editor_base(stack_output(root, "CodeEditorURL")))
        record, unreadable = _newest_record(session, base)
        if unreadable is not None:
            return unreadable
        if root is None:
            return base._replace(status=NO_STACK if record else f"no record ({NO_STACK})")
        if record is None:
            return base._replace(status=f"no record ({root['StackStatus']})")
        row = record_row(base, root, record, now, max_age)
        if not row.ready:
            return row
        return instance_row(row, session, editor_instance(stacks, root), fetch)
    except Exception as exc:  # noqa: BLE001 - one account must not hide the others
        return base._replace(status=f"cannot read: {error_code(exc)}")


def _newest_record(session: Any, base: Row) -> Tuple[Optional[Record], Optional[Row]]:
    """The account's newest record, or the row that says why it cannot be read."""
    try:
        return latest_from_cloudwatch(_aws(session, "logs")), None
    except CloudWatchDenied:
        return None, base._replace(status="cannot read: AccessDeniedException (logs)")
    except CannotRead as exc:
        return None, base._replace(status=f"cannot read: {exc.code}")
    except ValueError:
        return None, base._replace(status="cannot read: MalformedRecord")


def instance_row(row: Row, session: Any, expected: str, fetch: Optional[Fetch]) -> Row:
    """A ready record's row once the instance it names is this stack's, running now."""
    if not expected:
        return row._replace(icon="⚠️", status="cannot read: NoEditorInstanceOutput")
    if row.instance != expected:
        return row._replace(icon="⚠️", status="no record (the newest record is from another "
                                              "instance)")
    if instance_state(_aws(session, "ec2"), expected) != "running":
        return row._replace(icon="❌", status="Code Editor instance not running")
    why = browser_path(row.url, row.editor, fetch)
    return row._replace(icon="❌", status=why) if why else row


def private_text(path: Path, encoding: str = "utf-8") -> str:
    """A private file's text: a regular file, not a link, readable by its owner only, no ACL.

    It is opened without following a link, so the file checked is the file named, and
    without blocking, so a named pipe cannot hang the run. It is checked on the open file
    itself, so it cannot be swapped between the check and the read.

    Raises:
        CannotRead: a link or not a regular file, readable by others or through an ACL, too
            large, not text in ``encoding``, or not readable.
    """
    with os.fdopen(_open_private(path), "rb") as handle:
        data = _checked_bytes(handle, path)
    if len(data) > PRIVATE_FILE_BYTES:
        raise CannotRead(f"FileTooLarge ({path.name})")
    try:
        return data.decode(encoding)
    except UnicodeDecodeError as exc:
        raise CannotRead(f"NotText ({path.name}: save it as UTF-8)") from exc


def _open_private(path: Path) -> int:
    try:
        return os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise CannotRead(f"NotAFile ({path.name} is a link)") from exc
        raise CannotRead(f"{type(exc).__name__} ({path.name})") from exc


def _checked_bytes(handle: Any, path: Path) -> bytes:
    """Up to PRIVATE_FILE_BYTES + 1 bytes, once the open file has passed every check."""
    try:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise CannotRead(f"NotAFile ({path.name})")
        if info.st_mode & 0o077:
            raise CannotRead(f"FilePermissions (fix: chmod 600 {path.name})")
        acl = acl_problem(path)
        if acl:
            raise CannotRead(acl)
        return bytes(handle.read(PRIVATE_FILE_BYTES + 1))
    except OSError as exc:
        raise CannotRead(f"{type(exc).__name__} ({path.name})") from exc


def acl_problem(path: Path) -> str:
    """Why an access control list keeps the file from being private, or "" when none does.

    On macOS an ACL can let other users read a file whose mode is 0600, and the mode bits
    do not show it. A listing that fails refuses the file too (fails closed), named for what
    failed, since removing an ACL would not fix it. Off macOS, "".
    """
    if sys.platform != "darwin":
        return ""
    try:
        listed = subprocess.run(["/bin/ls", "-led", "--", str(path)], capture_output=True,
                                text=True, errors="replace", timeout=10, check=True).stdout
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return f"AclUnreadable ({type(exc).__name__}: {path.name})"
    entries = listed.split("\n", 1)[1] if "\n" in listed else ""
    return f"FileAcl (fix: chmod -N {path.name})" if ACL_ENTRY.search(entries) else ""


def parse_credentials(text: str) -> Dict[str, str]:
    """KEY=value pairs from a pasted console block; never sourced, never evaluated.

    Raises:
        CannotRead: one key has two different values, as when two blocks share a file.
    """
    values: Dict[str, str] = {}
    for raw in text.replace("\r", "").splitlines():
        if raw.lstrip().startswith("#"):
            continue
        for match in ASSIGNMENT.finditer(raw):
            value = next(group for group in (match["double"], match["single"], match["bare"])
                         if group is not None)
            if values.get(match["key"], value) != value:
                raise CannotRead(f"DuplicateKey ({match['key']})")
            values[match["key"]] = value
    return values


def file_session(path: Path) -> Tuple[Any, str]:
    """A boto3 session from one account file, and its Region.

    Raises:
        CannotRead: the file is not private (see private_text), or lacks keys or a Region.
    """
    values = parse_credentials(private_text(path))
    missing = [key for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
               if not values.get(key)]
    if missing:
        raise CannotRead(f"MissingCredentials ({', '.join(missing)})")
    region = values.get("AWS_DEFAULT_REGION") or values.get("AWS_REGION")
    if not region:
        raise CannotRead("MissingRegion (add AWS_DEFAULT_REGION=<region> on its own line)")
    if not REGION_NAME.match(region):
        raise CannotRead("MissingRegion (AWS_DEFAULT_REGION is not a Region name; put it "
                         "on its own line)")
    import boto3

    return boto3.Session(aws_access_key_id=values["AWS_ACCESS_KEY_ID"],
                         aws_secret_access_key=values["AWS_SECRET_ACCESS_KEY"],
                         aws_session_token=values.get("AWS_SESSION_TOKEN"),
                         region_name=region), region


def file_row(path: Path, now: datetime, max_age: float) -> Row:
    """One account file's row."""
    base = Row(file=path.name)
    try:
        session, region = file_session(path)
        return account_row(session, base._replace(region=region), now, max_age)
    except CannotRead as exc:
        return base._replace(status=f"cannot read: {exc.code}")
    except Exception as exc:  # noqa: BLE001 - only the type: the text may hold a secret
        return base._replace(status=f"cannot read: {type(exc).__name__}")


def fleet_rows(directory: Path, now: datetime, max_age: float,
               row: Optional[Callable[[Path, datetime, float], Row]] = None) -> List[Row]:
    """One row per *.env file, in file-name order, eight accounts at a time."""
    read = row or file_row

    def safe(path: Path) -> Row:
        try:
            return read(path, now, max_age)
        except Exception as exc:  # noqa: BLE001 - one account must not end the run
            return Row(file=path.name, status=f"cannot read: {type(exc).__name__}")

    files = sorted(directory.glob("*.env"))
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_ACCOUNTS) as pool:
        rows = list(pool.map(safe, files))
    return same_account_marked(rows)


def same_account_marked(rows: List[Row]) -> List[Row]:
    """A second file for an account already listed is not a second ready account."""
    first: Dict[str, str] = {}
    marked = []
    for row in rows:
        if row.account != "-" and row.account in first:
            row = row._replace(icon="⚠️", status=f"{SAME_ACCOUNT} {first[row.account]}")
        else:
            first.setdefault(row.account, row.file)
        marked.append(row)
    return marked


def _printable(text: str) -> str:
    """A cell with every control and format character replaced: no terminal escapes.

    A record's final line and CloudFormation's reasons are printed, and whoever can write to an
    account's log group writes the former.
    """
    return "".join("?" if unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn") else ch
                   for ch in text)


def table(rows: List[Row]) -> List[str]:
    cells = [tuple(_printable(cell) for cell in
                   (r.file, r.account, r.region, r.instance, r.recorded, f"{r.icon} {r.status}"))
             for r in rows]
    widths = [max([len(header), *(len(c[i]) for c in cells)])
              for i, header in enumerate(HEADERS[:-1])]

    def line(values: Sequence[str]) -> str:
        return "   ".join([*(v.ljust(w) for v, w in zip(values[:-1], widths)), values[-1]])

    ready = sum(row.ready for row in rows)
    return [line(HEADERS), *(line(c) for c in cells), f"{ready} of {len(rows)} ready"]


def exit_status(rows: List[Row]) -> int:
    return 0 if rows and all(row.ready for row in rows) else 1


def _aws(session: Any, service: str) -> Any:
    from botocore.config import Config

    config = Config(connect_timeout=10, read_timeout=30,
                    retries={"total_max_attempts": 3, "mode": "standard"})
    return session.client(service, config=config)


# ---------------------------------------------------------------------------
# the morning recheck: --recheck DIR, from the URLs --accounts saved, no credentials
# ---------------------------------------------------------------------------


def saved_rows(path: Path) -> Dict[str, Row]:
    """The rows saved in ``path``, keyed by account (by file when the account is unknown).

    Raises:
        CannotRead: the saved file is not the JSON --accounts writes: a repeated key, an entry
            that is not an object, a value that is not text, or nesting too deep to read.
    """
    if not os.path.lexists(path):
        return {}
    text = private_text(path)
    try:
        saved = json.loads(text, object_pairs_hook=_unique_keys)
        rows = [_saved_row(entry) for entry in saved["rows"]]
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        # RecursionError: some Python versions' parsers raise it on deep nesting; 3.14 parses
        # it, and the entry is then refused as not a saved row.
        raise CannotRead(f"MalformedSavedFile ({path.name})") from exc
    return {_saved_key(row): row for row in rows}


def _unique_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("a key is repeated")
    return dict(pairs)


def _saved_row(entry: Any) -> Row:
    # --accounts writes every field of a row as text: anything else was not written by it.
    if not isinstance(entry, dict) or set(entry) != set(Row._fields):
        raise ValueError("not a saved row")
    if not all(isinstance(value, str) for value in entry.values()):
        raise ValueError("a saved value is not text")
    return Row(**entry)


def _saved_key(row: Row) -> str:
    # By account, so a file renamed between runs (the collector numbers files in sweep order)
    # replaces its account's row instead of adding a second one.
    return row.account if row.account != "-" else f"file {row.file}"


def own_words(status: str) -> str:
    """The checker's own words a status starts with; a box's failing line is not kept."""
    return next((word for word in OWN_WORDS if status.startswith(word)),
                "the box's record is not ready")


def save_rows(path: Path, rows: List[Row], now: datetime) -> Path:
    """Merge these rows into the saved file, mode 0600; a newer row replaces its account's.

    A run over some of the teams, after a repair, keeps every other team's row. A row that only
    says it repeats another file's account is not saved over that account's own row.
    """
    fresh = {_saved_key(row): row._replace(status=own_words(row.status)) for row in rows
             if not row.status.startswith(SAME_ACCOUNT)}
    files = {row.file for row in rows}  # every file this run read, repeats of an account too
    try:
        earlier = saved_rows(path)
    except CannotRead:
        aside = path.with_name(f"{path.name}.damaged-{now.strftime('%Y%m%dT%H%M%SZ')}")
        path.replace(aside)
        print(f"{path.name} could not be read; moved aside to {aside.name}")
        earlier = {}
    # The newest run's row for a file replaces any older one, whatever the older one's key.
    merged = {**{key: row for key, row in earlier.items() if row.file not in files}, **fresh}
    partial = path.parent / f".{path.name}.tmp"
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"savedAt": now.isoformat(),
                   "rows": [row._asdict() for row in sorted(merged.values())]}, handle, indent=1)
    partial.chmod(0o600)
    partial.replace(path)
    return path


def recheck_row(saved: Optional[Row], name: str, now: datetime, max_age: float,
                fetch: Optional[Fetch] = None) -> Row:
    """One account's morning row: ready at --accounts, and the browser path answers now."""
    if saved is None:
        return Row(file=name, status="no --accounts result for this file; run --accounts")
    if not saved.ready:
        return saved._replace(icon="⚠️", status=f"not ready at the saved run ({saved.status})")
    try:
        recorded = datetime.strptime(saved.recorded, RECORDED_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return saved._replace(icon="⚠️", status="cannot read: MalformedRecord")
    hours = (now - recorded).total_seconds() / 3600
    if hours > max_age:
        return saved._replace(icon="⚠️", status=f"STALE ({_age_text(hours)})")
    why = browser_path(saved.url, saved.editor, fetch)
    if why:
        return saved._replace(icon="❌", status=why)
    return saved._replace(icon="✅", status=READY)


def recheck_rows(path: Path, now: datetime, max_age: float,
                 fetch: Optional[Fetch] = None) -> List[Row]:
    """Every saved row, eight at a time, in file-name order.

    ``path`` is the saved file, or a folder holding it; for a folder every *.env file in it
    also gets a row, so a team the last --accounts run did not read still shows.
    """
    saved_file = path / SAVED_URLS if path.is_dir() else path
    saved = list(saved_rows(saved_file).values())
    known = {row.file for row in saved}
    unread = sorted(p.name for p in path.glob("*.env") if p.name not in known) \
        if path.is_dir() else []
    work: List[Tuple[Optional[Row], str]] = [(row, row.file) for row in saved]
    work += [(None, name) for name in unread]

    def safe(item: Tuple[Optional[Row], str]) -> Row:
        try:
            return recheck_row(item[0], item[1], now, max_age, fetch)
        except Exception as exc:  # noqa: BLE001 - one account must not end the run
            failed = f"cannot read: {type(exc).__name__}"
            return (item[0]._replace(icon="⚠️", status=failed) if item[0] is not None
                    else Row(file=item[1], status=failed))

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_ACCOUNTS) as pool:
        rows = list(pool.map(safe, work))
    return sorted(rows, key=lambda row: (row.file, row.account))


def event_teams(path: Path) -> Dict[str, str]:
    """Each team's AWS account ID and name, from the event console's Teams > Download CSV.

    Only those two columns are read. The file also holds each team's join link, which claims
    the team for whoever opens it, so it must be private (mode 0600), as account files are.

    Raises:
        CannotRead: the file is not private (see private_text), not UTF-8 CSV, or lacks the
            two columns.
    """
    text = private_text(path, encoding="utf-8-sig")
    try:
        return _teams_from(csv.DictReader(io.StringIO(text, newline="")), path)
    except csv.Error as exc:
        raise CannotRead(f"TeamsFile ({path.name}: {type(exc).__name__})") from exc


def _teams_from(reader: Any, path: Path) -> Dict[str, str]:
    """Each team's account and name from the CSV's rows; see event_teams."""
    columns = set(reader.fieldnames or [])
    if not {TEAMS_ACCOUNT_COLUMN, TEAMS_NAME_COLUMN} <= columns:
        raise CannotRead(f"TeamsColumns ({path.name} needs {TEAMS_ACCOUNT_COLUMN!r} and "
                         f"{TEAMS_NAME_COLUMN!r})")
    teams: Dict[str, str] = {}
    for number, entry in enumerate(reader, 1):
        account = (entry.get(TEAMS_ACCOUNT_COLUMN) or "").strip()
        if account.isdigit():
            account = account.zfill(12)  # a spreadsheet may have dropped leading zeros
        name = (entry.get(TEAMS_NAME_COLUMN) or "").strip()[:60] or f"row {number}"
        teams[account or f"{NO_ACCOUNT}{number}"] = name
    return teams


def against_teams(rows: List[Row], teams: Dict[str, str], missing: str) -> List[Row]:
    """Every team of the event has a row, and every read account is a team of the event."""
    read = {row.account for row in rows}
    checked = [row if row.account == "-" or row.account in teams
               else row._replace(icon="⚠️", status="not a team of this event") for row in rows]
    return checked + [_missing_team(account, name, missing)
                      for account, name in sorted(teams.items()) if account not in read]


def _missing_team(account: str, name: str, missing: str) -> Row:
    if account.startswith(NO_ACCOUNT):
        return Row(file="-", status=f"no AWS account in the Teams CSV ({name})")
    return Row(file="-", account=account, status=f"{missing} ({name})")


def _max_age(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """--max-age-hours, or this mode's default; a usage error when it is not positive."""
    if args.max_age_hours is None:
        args.max_age_hours = (DEFAULT_RECHECK_MAX_AGE_HOURS
                              if getattr(args, "recheck", None) is not None
                              else DEFAULT_MAX_AGE_HOURS)
    if not (math.isfinite(args.max_age_hours) and 0 < args.max_age_hours <= MAX_AGE_LIMIT_HOURS):
        parser.error(f"--max-age-hours must be more than 0 and at most {MAX_AGE_LIMIT_HOURS}, "
                     f"not {args.max_age_hours:g}")


def _usage(parser: argparse.ArgumentParser, args: argparse.Namespace) -> Path:
    """The folder or file --accounts or --recheck names; a usage error (exit 2) otherwise."""
    if args.accounts is not None and args.recheck is not None:
        parser.error("--accounts and --recheck are separate runs")
    if args.record or args.live:
        parser.error("--accounts and --recheck only read: they never run checks on a box, "
                     "because the box has no guard for a lab in progress")
    if args.save is not None and args.accounts is None:
        parser.error("--save belongs to --accounts; give --recheck the saved file itself")
    _max_age(parser, args)
    if args.teams is not None and not args.teams.is_file():
        parser.error(f"--teams {args.teams} is not a file")
    if args.accounts is not None:
        return _accounts_folder(parser, args)
    target = args.recheck
    if not (target.is_file() or (target / SAVED_URLS).is_file()):
        parser.error(f"{target} holds no {SAVED_URLS}: run --accounts first")
    return target


def _accounts_folder(parser: argparse.ArgumentParser, args: argparse.Namespace) -> Path:
    if not args.accounts.is_dir():
        parser.error(f"{args.accounts} is not a directory")
    if args.save is not None and not args.save.parent.is_dir():
        parser.error(f"--save {args.save}: {args.save.parent} is not a directory")
    return args.accounts


def _fleet(parser: argparse.ArgumentParser, args: argparse.Namespace, now: datetime) -> int:
    target = _usage(parser, args)
    try:
        teams = event_teams(args.teams) if args.teams is not None else None
    except CannotRead as exc:
        parser.error(f"--teams: {exc.code}")
    rows = _fleet_rows(args, target, now)
    if rows is None:
        return 1
    if teams is not None:
        missing = "not in the saved run" if args.recheck is not None else "not in this run"
        rows = against_teams(rows, teams, missing)
    if not rows:
        print(f"No *.env files in {target}.")
    print("\n".join(table(rows)))
    return exit_status(rows)


def _fleet_rows(args: argparse.Namespace, target: Path, now: datetime) -> Optional[List[Row]]:
    """The rows of --recheck or --accounts; None when the saved run cannot be read."""
    if args.recheck is not None:
        try:
            return recheck_rows(target, now, args.max_age_hours)
        except CannotRead as exc:
            print(f"Cannot recheck: {exc.code}. Run --accounts again.")
            return None
    rows = fleet_rows(target, now, args.max_age_hours)
    if rows:
        try:
            print(f"Saved for --recheck: {save_rows(args.save or target / SAVED_URLS, rows, now)}")
        except (OSError, CannotRead) as exc:
            reason = exc.code if isinstance(exc, CannotRead) else type(exc).__name__
            print(f"Could not save for --recheck ({reason}); --recheck will need a "
                  "clean --accounts run")
    return rows


# ---------------------------------------------------------------------------


def _client(name: str, region: Optional[str]) -> Any:
    import boto3

    return boto3.client(name, region_name=region)


def main(argv: Optional[Sequence[str]] = None, *, run: Callable[..., Any] = subprocess.run,
         logs: Any = None, local: Optional[Path] = None,
         now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
         instance: Callable[[], str] = imds_instance_id,
         on_box: Optional[bool] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true", help="run the checks and record them")
    mode.add_argument("--live", action="store_true", help="run the checks again now")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION"))
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP_SECONDS,
                        help="seconds the checks may run before they count as failed")
    parser.add_argument("--max-age-hours", type=float, default=None,
                        help=f"a record older than this is STALE (default "
                             f"{DEFAULT_MAX_AGE_HOURS}; {DEFAULT_RECHECK_MAX_AGE_HOURS} "
                             "for --recheck)")
    parser.add_argument("--accounts", type=Path, metavar="DIR",
                        help="from a laptop: one *.env Ops credential file per account; read only")
    parser.add_argument("--save", type=Path, metavar="FILE",
                        help="with --accounts: where to keep the rows for --recheck "
                             "(default DIR/pellier-urls.json)")
    parser.add_argument("--teams", type=Path, metavar="CSV",
                        help="with --accounts or --recheck: the event console's Teams CSV "
                             "(mode 0600); every team must have a row")
    parser.add_argument("--recheck", type=Path, metavar="PATH",
                        help="from a laptop, no credentials: ask each account's Pellier again, "
                             "from the rows --accounts saved (the file, or the folder holding it)")
    args = parser.parse_args(argv)
    if args.accounts is not None or args.recheck is not None:
        return _fleet(parser, args, now())
    if args.teams is not None or args.save is not None:
        parser.error("--teams and --save belong to --accounts or --recheck")
    _max_age(parser, args)
    local = local or local_record_path()
    on_box = running_on_box(REPO) if on_box is None else on_box
    logs = logs or (lambda: _client("logs", args.region))

    if args.live and not on_box:
        parser.error("--live runs only on the box: from a laptop it would run a managed "
                     "AgentCore turn on a participant's box. Read the record, or use "
                     "--accounts and --recheck")
    if args.record or args.live:
        record = record_now(run, logs, local, now(), instance(), args.cap)
        print("\n".join(render(record, now(), args.max_age_hours)))
        return 0 if record["ready"] else 1
    try:
        record = _latest(local, logs, on_box)
    except CloudWatchDenied as exc:
        print(exc)
        return 1
    if record is None:
        print("No readiness record yet. On the box, uv run scripts/event_readiness.py --live "
              "checks it now.")
        return 1
    print("\n".join(render(record, now(), args.max_age_hours)))
    return 0 if record.get("ready") else 1


def _latest(local: Path, logs: Any, on_box: bool) -> Optional[Record]:
    if not on_box:
        return latest_from_cloudwatch(logs() if callable(logs) else logs)
    record = read_local(local)
    return record and with_current_deep_dive(record, deep_dive_status_path())


if __name__ == "__main__":
    sys.exit(main())
