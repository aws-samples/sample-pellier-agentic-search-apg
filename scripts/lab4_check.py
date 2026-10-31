#!/usr/bin/env python3
"""Lab 4's checks, one per task.

    uv run scripts/lab4_check.py --task 4A   the $100 credit limit, in Cedar and on the Gateway
    uv run scripts/lab4_check.py --task 4B   the credit-writer role writes only through the function

Each prints its findings and ends with one line, such as ``Lab 4A check passed``.
"""

from __future__ import annotations

import argparse
import importlib
import pathlib
import sys
from typing import Optional, Sequence

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# Each task's check lives in its own sibling module, imported only when that task runs.
TASKS = {"4A": "lab4_policy", "4B": "lab4_credit"}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", choices=sorted(TASKS), required=True)
    args, rest = parser.parse_known_args(argv)
    return importlib.import_module(TASKS[args.task]).main(rest)


if __name__ == "__main__":
    raise SystemExit(main())
