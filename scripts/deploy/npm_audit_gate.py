"""Fail on a high or critical npm advisory that is not a listed exception.

npm audit has no ignore list. Pipe `npm audit --json` in and name each accepted
advisory with --ignore, keeping its reason and exit condition beside the call. The gate
also fails when a listed advisory is no longer reported, so a fixed exception is dropped
rather than kept, and when the audit did not run.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

FAILING_SEVERITIES = {"high", "critical"}


def reported_advisories(report: dict[str, Any]) -> dict[str, str]:
    """Map each advisory's GHSA ID in an npm audit report to its severity."""
    found = {}
    for finding in report["vulnerabilities"].values():
        for cause in finding.get("via", []):
            if isinstance(cause, dict):
                found[cause["url"].rsplit("/", 1)[-1]] = cause["severity"]
    return found


def main(argv: list[str] | None = None) -> int:
    """Return 0 when every high or critical advisory is a listed exception."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ignore", action="append", default=[], metavar="GHSA_ID")
    args = parser.parse_args(argv)
    report = json.load(sys.stdin)
    if "vulnerabilities" not in report:
        print(f"npm audit did not run: {report.get('error', 'no vulnerabilities key')}")
        return 2
    found = reported_advisories(report)
    unlisted = sorted(
        ghsa for ghsa, severity in found.items()
        if severity in FAILING_SEVERITIES and ghsa not in args.ignore
    )
    stale = sorted(set(args.ignore) - set(found))
    for ghsa in unlisted:
        print(f"{ghsa} ({found[ghsa]}): fix it, or list it with its reason and exit condition")
    for ghsa in stale:
        print(f"{ghsa} is listed but no longer reported: drop it")
    return 1 if unlisted or stale else 0


if __name__ == "__main__":
    sys.exit(main())
