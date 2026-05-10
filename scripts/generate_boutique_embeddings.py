#!/usr/bin/env python3
"""Generate Cohere Embed v4 embeddings for the boutique catalog.

Reads ``data/pellier_catalog.csv``, generates a 1024-dim embedding per row
using ``us.cohere.embed-v4:0`` on Amazon Bedrock (``search_document``
input type), and writes the same CSV in place with the ``embedding``
column populated as a JSON array string.

Offline developer tool. Runs once per catalog revision; the output CSV
is committed to git and loaded by sub-step 4 (``scripts/load_catalog.py``)
without touching Bedrock.

Exit codes
----------
    0   success, all rows embedded
    1   pre-flight failed (missing CSV, invalid columns, etc.)
    2   Bedrock access or authentication failed
    3   embedding generation failed after retries
    4   CSV write failed
    10  unexpected error

Usage
-----
    python scripts/generate_boutique_embeddings.py
    python scripts/generate_boutique_embeddings.py --dry-run
    python scripts/generate_boutique_embeddings.py --no-resume
    python scripts/generate_boutique_embeddings.py --csv-path data/other.csv

Environment
-----------
    AWS credentials in the standard chain (env, shared config, IAM role).
    AWS_REGION: defaults to us-west-2 (matches legacy catalog pipeline).

Dependencies
------------
    boto3, standard library only.

Runtime
-------
    ~1-2 min for 92 rows at 5-way concurrency.
    Cost: < $0.01 in Bedrock charges (Cohere Embed v4 is ~$0.0001/1K tokens).
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import logging
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "pellier_catalog.csv"
CHECKPOINT_PATH = PROJECT_ROOT / "data" / ".pellier_catalog_embeddings.checkpoint"

SCRIPT_VERSION = "1.0.0"
DEFAULT_MODEL = "us.cohere.embed-v4:0"
EMBEDDING_DIM = 1024
MAX_WORKERS = 5
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0
EXPECTED_ROW_COUNT = 92

# Errors we retry on (transient). Anything else fails fast.
TRANSIENT_ERRORS = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "InternalServerError",
    "InternalServerException",
    "RequestTimeout",
    "RequestTimeoutException",
    "ModelTimeoutException",
}

logger = logging.getLogger("generate_boutique_embeddings")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EmbeddingResult:
    embedded_product_ids: List[int] = field(default_factory=list)
    skipped_product_ids: List[int] = field(default_factory=list)
    failed_product_ids: List[int] = field(default_factory=list)
    duration_seconds: float = 0.0
    total_api_calls: int = 0
    total_retries: int = 0


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        pid = getattr(record, "productId", None)
        if pid is not None:
            payload["productId"] = pid
        return json.dumps(payload)


def _configure_logging(quiet: bool, json_output: bool) -> None:
    level = logging.WARNING if quiet else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    if json_output or not sys.stdout.isatty():
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False


def _log(level: int, msg: str, product_id: Optional[int] = None) -> None:
    extra = {"productId": product_id} if product_id is not None else {}
    logger.log(level, msg, extra=extra)


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


def _read_checkpoint(total_rows: int, model_id: str) -> List[int]:
    if not CHECKPOINT_PATH.exists():
        return []
    try:
        data = json.loads(CHECKPOINT_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        _log(logging.WARNING, f"Checkpoint unreadable, ignoring: {exc}")
        return []
    if data.get("total_rows") != total_rows:
        _log(logging.WARNING, "Checkpoint total_rows mismatch, ignoring")
        return []
    if data.get("model_id") != model_id:
        _log(logging.WARNING, "Checkpoint model_id mismatch, ignoring")
        return []
    ids = [int(x) for x in data.get("completed_product_ids", [])]
    _log(logging.INFO, f"Resuming from checkpoint: {len(ids)} rows already embedded")
    return ids


def _write_checkpoint(
    completed_ids: List[int],
    total_rows: int,
    model_id: str,
    started_at: str,
) -> None:
    payload = {
        "started_at": started_at,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "completed_product_ids": sorted(completed_ids),
        "total_rows": total_rows,
        "script_version": SCRIPT_VERSION,
        "model_id": model_id,
    }
    tmp = CHECKPOINT_PATH.with_suffix(CHECKPOINT_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, CHECKPOINT_PATH)


def _delete_checkpoint() -> None:
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def _parse_tags(raw: str) -> List[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        try:
            value = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return []
    if isinstance(value, list):
        return [str(t).strip() for t in value if t]
    return []


def _build_input_text(description: str, tags: List[str]) -> str:
    if tags:
        return f"{description}. Tags: {', '.join(tags)}"
    return description


def _read_csv(csv_path: Path) -> tuple[List[str], List[dict]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return fieldnames, rows


def _preflight(csv_path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    required = {"productId", "description", "tags", "embedding"}
    missing = required - set(fieldnames)
    if missing:
        raise SystemExit(f"pre-flight failed: CSV missing columns {missing}")
    if len(rows) < EXPECTED_ROW_COUNT:
        raise SystemExit(
            f"pre-flight failed: expected >= {EXPECTED_ROW_COUNT} rows, got {len(rows)}"
        )
    for row in rows:
        if not row.get("description", "").strip():
            raise SystemExit(
                f"pre-flight failed: empty description for productId {row.get('productId')}"
            )
    _log(logging.INFO, f"Pre-flight OK: {len(rows)} rows, schema valid")


# ---------------------------------------------------------------------------
# Bedrock invocation
# ---------------------------------------------------------------------------


def _make_bedrock_client(model_id: str):
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    region = os.environ.get("AWS_REGION", "us-west-2")
    try:
        client = boto3.client("bedrock-runtime", region_name=region)
    except NoCredentialsError as exc:
        _log(logging.ERROR, f"AWS credentials not found: {exc}")
        raise SystemExit(2)

    # Reachability: embed "test" to confirm model access.
    try:
        body = json.dumps(
            {
                "texts": ["test"],
                "input_type": "search_document",
                "embedding_types": ["float"],
                "output_dimension": EMBEDDING_DIM,
            }
        )
        client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="*/*",
            body=body,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        _log(logging.ERROR, f"Bedrock reachability check failed ({code}): {exc}")
        raise SystemExit(2)
    except Exception as exc:
        _log(logging.ERROR, f"Bedrock reachability check failed: {exc}")
        raise SystemExit(2)
    _log(logging.INFO, f"Bedrock reachability OK: {model_id}")
    return client


def _invoke_embedding(
    client,
    model_id: str,
    text: str,
    product_id: int,
    retry_counter: List[int],
) -> List[float]:
    """Call Bedrock once, retrying up to MAX_RETRIES on transient errors."""
    from botocore.exceptions import ClientError

    body = json.dumps(
        {
            "texts": [text],
            "input_type": "search_document",
            "embedding_types": ["float"],
            "output_dimension": EMBEDDING_DIM,
        }
    )
    last_err: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.invoke_model(
                modelId=model_id,
                contentType="application/json",
                accept="*/*",
                body=body,
            )
            payload = json.loads(response["body"].read())
            emb = payload["embeddings"]["float"][0]
            if len(emb) != EMBEDDING_DIM:
                raise ValueError(f"expected {EMBEDDING_DIM} dims, got {len(emb)}")
            return emb
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            last_err = exc
            if code not in TRANSIENT_ERRORS:
                _log(logging.ERROR, f"Non-retriable error ({code}): {exc}", product_id)
                raise
            if attempt == MAX_RETRIES:
                break
            sleep_s = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            retry_counter[0] += 1
            _log(
                logging.WARNING,
                f"Transient error ({code}) attempt {attempt}/{MAX_RETRIES}, "
                f"sleeping {sleep_s:.1f}s",
                product_id,
            )
            time.sleep(sleep_s)
        except Exception as exc:  # noqa: BLE001 — rethrow with context
            last_err = exc
            if attempt == MAX_RETRIES:
                break
            sleep_s = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            retry_counter[0] += 1
            _log(
                logging.WARNING,
                f"Error attempt {attempt}/{MAX_RETRIES}: {exc}; sleeping {sleep_s:.1f}s",
                product_id,
            )
            time.sleep(sleep_s)
    assert last_err is not None
    raise last_err


def _fake_embedding(product_id: int) -> List[float]:
    rng = random.Random(product_id)
    return [rng.gauss(0, 0.05) for _ in range(EMBEDDING_DIM)]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _serialize_embedding(vec: List[float]) -> str:
    return json.dumps(vec, separators=(",", ":"))


def _atomic_write_csv(csv_path: Path, fieldnames: List[str], rows: List[dict]) -> None:
    tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    # Verify tmp file before committing.
    with tmp.open(newline="", encoding="utf-8") as f:
        verify = list(csv.DictReader(f))
    if len(verify) != len(rows):
        tmp.unlink(missing_ok=True)
        raise SystemExit(4)
    missing_embed = [r["productId"] for r in verify if not r["embedding"]]
    if missing_embed:
        tmp.unlink(missing_ok=True)
        _log(
            logging.ERROR,
            f"temp CSV has {len(missing_embed)} rows missing embeddings; aborting",
        )
        raise SystemExit(4)
    os.replace(tmp, csv_path)


def generate_embeddings(
    csv_path: Path = DEFAULT_CSV,
    model_id: str = DEFAULT_MODEL,
    resume: bool = True,
    dry_run: bool = False,
) -> EmbeddingResult:
    start_time = time.time()
    started_at = datetime.now(timezone.utc).isoformat()

    if not csv_path.exists():
        _log(logging.ERROR, f"pre-flight failed: CSV not found at {csv_path}")
        raise SystemExit(1)

    fieldnames, rows = _read_csv(csv_path)
    _preflight(csv_path, rows, fieldnames)

    if dry_run:
        _log(
            logging.WARNING,
            "DRY RUN: using synthetic embeddings, not suitable for production",
        )

    # Checkpoint: identify already-done productIds.
    completed_ids: List[int] = []
    if resume and not dry_run:
        completed_ids = _read_checkpoint(len(rows), model_id)
    elif not resume:
        _delete_checkpoint()

    completed_set = set(completed_ids)

    # Index existing embeddings from the CSV itself — if the file already
    # has a valid-looking JSON array for a row and the checkpoint agrees,
    # we skip that row. This handles the case where the checkpoint was
    # lost but embeddings from an earlier run survived in the CSV.
    existing_embeddings: dict[str, str] = {}
    for row in rows:
        if row.get("embedding"):
            existing_embeddings[row["productId"]] = row["embedding"]

    result = EmbeddingResult()
    retry_counter = [0]

    # Cost estimate
    input_texts: List[tuple[int, str]] = []
    for row in rows:
        pid = int(row["productId"])
        if pid in completed_set and existing_embeddings.get(row["productId"]):
            result.skipped_product_ids.append(pid)
            continue
        tags = _parse_tags(row.get("tags", ""))
        if not tags:
            _log(
                logging.WARNING,
                "tags could not be parsed; embedding on description alone",
                pid,
            )
        text = _build_input_text(row["description"], tags)
        input_texts.append((pid, text))

    if input_texts:
        approx_tokens = sum(max(1, len(t) // 4) for _, t in input_texts)
        approx_cost = (approx_tokens / 1000) * 0.0001
        _log(
            logging.INFO,
            f"Planning to embed {len(input_texts)} rows "
            f"(~{approx_tokens} tokens, est. ${approx_cost:.4f})",
        )
    else:
        _log(logging.INFO, "Nothing to embed; CSV already complete")

    # Bedrock client (skip in dry run).
    client = None
    if not dry_run and input_texts:
        client = _make_bedrock_client(model_id)

    # Thread-safe state for checkpointing during concurrent execution.
    lock = threading.Lock()

    def _embed_one(pid: int, text: str) -> tuple[int, Optional[List[float]], Optional[Exception]]:
        try:
            if dry_run:
                vec = _fake_embedding(pid)
            else:
                vec = _invoke_embedding(client, model_id, text, pid, retry_counter)
            return pid, vec, None
        except Exception as exc:  # noqa: BLE001
            return pid, None, exc

    # Mutate rows in place; track order via productId lookup.
    row_by_pid = {int(r["productId"]): r for r in rows}
    completed_since_checkpoint = 0
    total_to_embed = len(input_texts)

    if total_to_embed:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_pid = {
                executor.submit(_embed_one, pid, text): pid for pid, text in input_texts
            }
            for future in as_completed(future_to_pid):
                pid, vec, err = future.result()
                result.total_api_calls += 1
                if err is not None or vec is None:
                    result.failed_product_ids.append(pid)
                    _log(logging.ERROR, f"embedding failed: {err}", pid)
                    continue
                row_by_pid[pid]["embedding"] = _serialize_embedding(vec)
                with lock:
                    result.embedded_product_ids.append(pid)
                    completed_ids.append(pid)
                    completed_since_checkpoint += 1
                    done = len(result.embedded_product_ids) + len(result.skipped_product_ids)
                    if done % 10 == 0 or done == len(rows):
                        pct = 100.0 * done / len(rows)
                        _log(logging.INFO, f"Processed {done}/{len(rows)} ({pct:.1f}%)")
                    if (
                        not dry_run
                        and completed_since_checkpoint >= 10
                    ):
                        _write_checkpoint(completed_ids, len(rows), model_id, started_at)
                        completed_since_checkpoint = 0

    result.total_retries = retry_counter[0]

    if result.failed_product_ids:
        _log(
            logging.ERROR,
            f"{len(result.failed_product_ids)} rows failed: "
            f"{sorted(result.failed_product_ids)}",
        )
        # Persist what we have so resume works.
        if not dry_run:
            _write_checkpoint(completed_ids, len(rows), model_id, started_at)
        raise SystemExit(3)

    try:
        _atomic_write_csv(csv_path, fieldnames, rows)
    except SystemExit:
        raise
    except Exception as exc:
        _log(logging.ERROR, f"CSV write failed: {exc}")
        raise SystemExit(4)

    if not dry_run:
        _delete_checkpoint()

    result.duration_seconds = time.time() - start_time
    _log(
        logging.INFO,
        f"Done: embedded={len(result.embedded_product_ids)} "
        f"skipped={len(result.skipped_product_ids)} "
        f"failed={len(result.failed_product_ids)} "
        f"retries={result.total_retries} "
        f"duration={result.duration_seconds:.1f}s",
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate Cohere Embed v4 embeddings for the boutique catalog.",
    )
    p.add_argument("--csv-path", type=Path, default=DEFAULT_CSV)
    p.add_argument("--model-id", default=DEFAULT_MODEL)
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    _configure_logging(quiet=args.quiet, json_output=args.json_output)
    try:
        generate_embeddings(
            csv_path=args.csv_path,
            model_id=args.model_id,
            resume=not args.no_resume,
            dry_run=args.dry_run,
        )
        return 0
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 10
        return code
    except Exception as exc:  # noqa: BLE001
        _log(logging.ERROR, f"unexpected error: {exc}")
        return 10


if __name__ == "__main__":
    sys.exit(main())
