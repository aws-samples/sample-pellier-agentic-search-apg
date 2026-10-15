#!/usr/bin/env python3
"""Record, and read back, whether a workshop box is ready for the event.

Bootstrap runs ``--record`` once the environment is up: the same read-only checks as
``workshop-start.sh`` (Theo's AgentCore Memory included), capped so they cannot hold
provisioning. The result, with its UTC time and a final line that reads ``READY FOR LAB 1``
or names the first failing check, goes to ``~/.pellier/readiness.json`` in the participant's
home and to CloudWatch Logs, ``/aws/pellier/readiness``, one stream per instance. Nothing is
shown to participants; this is the facilitator's check before the event.

    python3 scripts/event_readiness.py            # the latest record and when it ran
    python3 scripts/event_readiness.py --live     # run the checks again now
    python3 scripts/event_readiness.py --record   # bootstrap: run, cap and record

On the box the latest record is the local file, and ``--live`` records again. From a laptop
with the event account's credentials, the latest record comes from CloudWatch Logs, and
``--live`` runs ``--record`` on the box through SSM Run Command: on the instance the record
names, or the one ``--instance-id`` names (the stack's ``InstanceId`` output).

A failing check is a line that starts ``x FAIL``; a ``Facilitator:`` warning also makes the
box not ready, because it names something a later lab needs even when Lab 1 could start.

Exit status: 0 when the record reads READY FOR LAB 1, 1 when it does not or there is none. A
record older than ``--max-age-hours`` is flagged STALE and keeps its status.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
READY = "READY FOR LAB 1"
LOG_GROUP = "/aws/pellier/readiness"
DEFAULT_CAP_SECONDS = 180
DEFAULT_MAX_AGE_HOURS = 24
SSM_WAIT_SECONDS = 600
BOX_REPO = "/workshop/sample-pellier-agentic-search-apg"
BOX_USER = "participant"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
Record = Dict[str, Any]


def local_record_path() -> Path:
    override = os.environ.get("PELLIER_READINESS_FILE")
    return Path(override) if override else Path.home() / ".pellier" / "readiness.json"


# ---------------------------------------------------------------------------
# the checks and their verdict
# ---------------------------------------------------------------------------


def _clean(text: str) -> List[str]:
    return [ANSI.sub("", line).rstrip() for line in text.splitlines() if line.strip()]


def run_checks(run: Callable[..., Any] = subprocess.run, cap: int = DEFAULT_CAP_SECONDS,
               repo: Path = REPO) -> Tuple[List[str], Optional[int]]:
    """workshop-start.sh's lines and exit status; ``None`` when it ran past ``cap``."""
    argv = ["bash", str(repo / "scripts" / "workshop-start.sh")]
    try:
        completed = run(argv, capture_output=True, text=True, timeout=cap, check=False)
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
    """The newest record in the newest stream, or None when there is none."""
    try:
        streams = logs.describe_log_streams(logGroupName=LOG_GROUP, orderBy="LastEventTime",
                                            descending=True, limit=1).get("logStreams") or []
        if not streams:
            return None
        events = logs.get_log_events(logGroupName=LOG_GROUP,
                                     logStreamName=streams[0]["logStreamName"], limit=1,
                                     startFromHead=False).get("events") or []
    except Exception as exc:  # noqa: BLE001 - a missing group is simply no record
        if "ResourceNotFound" in f"{type(exc).__name__} {exc}":
            return None
        raise
    return json.loads(events[-1]["message"]) if events else None


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


def record_now(run: Callable[..., Any], logs: Any, local: Path, now: datetime,
               instance_id: str, cap: int) -> Record:
    lines, code = run_checks(run=run, cap=cap)
    ready, final = verdict(lines, code, cap)
    record = {"recordedAt": now.isoformat(), "instanceId": instance_id, "ready": ready,
              "final": final, "lines": [*lines, final]}
    write_local(record, local)
    try:
        write_cloudwatch(record, logs() if callable(logs) else logs)
    except Exception as exc:  # noqa: BLE001 - the local record stands; say what failed
        print(f"Readiness: could not write the CloudWatch record ({type(exc).__name__}: "
              f"{str(exc)[:160]}); the local record is {local}", file=sys.stderr)
    return record


def live_via_ssm(ssm: Any, instance_id: str, sleep: Callable[[float], None]) -> Tuple[int, str]:
    """Run --record on the box; return its exit status and its output."""
    command = (f"sudo -u {BOX_USER} -H bash -lc 'cd {BOX_REPO} && "
               "python3.14 scripts/event_readiness.py --record'")
    sent = ssm.send_command(InstanceIds=[instance_id], DocumentName="AWS-RunShellScript",
                            Parameters={"commands": [command]},
                            Comment="Pellier event readiness")
    command_id = sent["Command"]["CommandId"]
    deadline = time.monotonic() + SSM_WAIT_SECONDS
    while time.monotonic() < deadline:
        sleep(3)
        try:
            result = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except Exception as exc:  # noqa: BLE001 - the invocation appears a moment later
            if "InvocationDoesNotExist" in f"{type(exc).__name__} {exc}":
                continue
            raise
        if result["Status"] not in ("Pending", "InProgress", "Delayed"):
            output = (result.get("StandardOutputContent") or "") + (
                result.get("StandardErrorContent") or "")
            return int(result.get("ResponseCode", 1)), output
    return 1, f"SSM command {command_id} did not finish within {SSM_WAIT_SECONDS} s"


# ---------------------------------------------------------------------------


def _client(name: str, region: Optional[str]) -> Any:
    import boto3

    return boto3.client(name, region_name=region)


def main(argv: Optional[Sequence[str]] = None, *, run: Callable[..., Any] = subprocess.run,
         logs: Any = None, ssm: Any = None, local: Optional[Path] = None,
         now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
         instance: Callable[[], str] = imds_instance_id, on_box: Optional[bool] = None,
         sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true", help="run the checks and record them")
    mode.add_argument("--live", action="store_true", help="run the checks again now")
    parser.add_argument("--instance-id", help="from a laptop: the workshop instance for --live")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION"))
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP_SECONDS,
                        help="seconds the checks may run before they count as failed")
    parser.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS)
    args = parser.parse_args(argv)
    local = local or local_record_path()
    on_box = Path("/etc/pellier").is_dir() if on_box is None else on_box
    logs = logs or (lambda: _client("logs", args.region))

    if args.record or (args.live and on_box):
        record = record_now(run, logs, local, now(), instance(), args.cap)
        print("\n".join(render(record, now(), args.max_age_hours)))
        return 0 if record["ready"] else 1
    if args.live:
        return _live_from_laptop(args, logs, ssm, sleep)
    record = read_local(local) if on_box else latest_from_cloudwatch(
        logs() if callable(logs) else logs)
    if record is None:
        print("No readiness record yet. Run python3 scripts/event_readiness.py --live to "
              "check the box now.")
        return 1
    print("\n".join(render(record, now(), args.max_age_hours)))
    return 0 if record.get("ready") else 1


def _live_from_laptop(args: argparse.Namespace, logs: Any, ssm: Any,
                      sleep: Callable[[float], None]) -> int:
    instance_id = args.instance_id
    if not instance_id:
        latest = latest_from_cloudwatch(logs() if callable(logs) else logs)
        instance_id = (latest or {}).get("instanceId", "")
    if not instance_id.startswith("i-"):
        print("No workshop instance is recorded. Pass --instance-id with the stack's "
              "InstanceId output, or run this on the box.")
        return 1
    code, output = live_via_ssm(ssm or _client("ssm", args.region), instance_id, sleep)
    print(output.rstrip())
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
