#!/usr/bin/env python3
"""Lab 1's checks, one per task.

    python3 scripts/lab1_check.py --task 1A   the vector branch ranks Anna's products by meaning
    python3 scripts/lab1_check.py --task 1B   Anna's retry kept every limit she asked for

Each prints its findings and ends with one line, such as ``Lab 1A check passed``.
"""

from __future__ import annotations

import argparse
import importlib
import pathlib
import sys
from typing import Optional, Sequence

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# Each task's check lives in its own sibling module, imported only when that task runs.
TASKS = {"1A": "lab1_vector", "1B": "lab1_retry"}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", choices=sorted(TASKS), required=True)
    args, rest = parser.parse_known_args(argv)
    return importlib.import_module(TASKS[args.task]).main(rest)


if __name__ == "__main__":
    raise SystemExit(main())
