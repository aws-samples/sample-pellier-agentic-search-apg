"""Fingerprint the Lambda's application sources at execution, not its caller's build."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

SOURCE_PATHS = (
    "pellier_store_tools.py", "gateway_tool_schemas.py",
    "common/types.py", "common/dataapi.py", "common/handler.py", "common/fingerprint.py",
    "services/__init__.py", "services/store_tools.py", "services/search_plan.py",
    "services/retrieval_receipt.py", "services/catalog_vocabulary.py",
)
OPERATOR_SOURCE_PATHS = (
    *(name for name in SOURCE_PATHS if name != "pellier_store_tools.py"),
    "pellier_operator_tools.py", "services/operator_graph.py", "services/operator_review.py",
)


def compute_fingerprint(files: Mapping[str, str | Path], *, source_paths=SOURCE_PATHS) -> str:
    digest = hashlib.sha256()
    for name in sorted(source_paths):
        digest.update(name.encode() + b"\0" + Path(files[name]).read_bytes() + b"\0")
    return digest.hexdigest()


def deployed_fingerprint(root: Path, *, source_paths=SOURCE_PATHS) -> str:
    try:
        return compute_fingerprint({name: root / name for name in source_paths}, source_paths=source_paths)
    except OSError:
        return ""
