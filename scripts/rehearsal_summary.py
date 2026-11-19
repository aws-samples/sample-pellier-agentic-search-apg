#!/usr/bin/env python3
"""Write the one file the AgentCore rehearsal workflow uploads: outcomes, never identifiers.

The managed receipt names the account, the Gateway URL and every ARN, and an Actions artifact
of a public repository can be downloaded by any signed-in user. So the receipt stays on the
runner and this summary carries only an allowlist: the source revision, the overall status,
and each check's name with its pass or fail. Nothing else is copied, not the error text.

    python scripts/rehearsal_summary.py --receipt R.json --revision SHA --output S.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

CHECK_NAME = re.compile(r"[a-z][a-z0-9_]{0,79}")
REVISION = re.compile(r"[0-9a-f]{7,64}")
STATUSES = frozenset({"ready", "failed", "provisioning"})
NO_RECEIPT = "no_receipt"


def summarize(receipt: Optional[Dict[str, Any]], revision: str) -> Dict[str, Any]:
    """The allowlisted summary of a receipt, or of its absence when ``receipt`` is None."""
    if not REVISION.fullmatch(revision):
        raise ValueError("--revision must be a hexadecimal commit SHA")
    verification = (receipt or {}).get("verification")
    checks = {
        name: value
        for name, value in (verification if isinstance(verification, dict) else {}).items()
        if isinstance(value, bool) and CHECK_NAME.fullmatch(str(name))
    }
    status = (receipt or {}).get("status")
    return {
        "source_revision": revision,
        "status": status if status in STATUSES else NO_RECEIPT,
        "checks": dict(sorted(checks.items())),
        "failed_checks": sorted(name for name, passed in checks.items() if not passed),
    }


def _read_receipt(path: Path) -> Optional[Dict[str, Any]]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = summarize(_read_receipt(args.receipt), args.revision)
    except ValueError as exc:
        print(f"rehearsal_summary: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
