"""Tests for ``generate_boutique_embeddings``.

Mocks boto3's Bedrock client — never hits the real API. Each test builds
a temporary CSV with the minimum columns the module needs.
"""

from __future__ import annotations

import csv
import importlib
import io
import json
import sys
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


CSV_FIELDS = [
    "productId", "name", "brand", "color", "price", "description",
    "category", "tags", "rating", "reviews", "imgUrl",
    "reasoning_lead", "reasoning_body", "reasoning_urgent",
    "match_reason", "badge", "tier", "image_verified", "embedding",
]


def _minimal_row(pid: int, description: str = "A nice linen shirt") -> dict:
    return {
        "productId": pid,
        "name": f"Product {pid}",
        "brand": "Pellier Editions",
        "color": "Oatmeal",
        "price": 100.0,
        "description": description,
        "category": "Linen",
        "tags": json.dumps(["minimal", "linen", "everyday"]),
        "rating": 4.7,
        "reviews": 100,
        "imgUrl": "https://example.com/img.jpg",
        "reasoning_lead": "",
        "reasoning_body": "",
        "reasoning_urgent": "",
        "match_reason": "",
        "badge": "",
        "tier": 1,
        "image_verified": "true",
        "embedding": "",
    }


def _write_csv(path: Path, row_count: int = 92) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for i in range(1, row_count + 1):
            writer.writerow(_minimal_row(i))


@pytest.fixture
def module(tmp_path, monkeypatch):
    """Fresh module import per-test so CHECKPOINT_PATH can be patched."""
    # Ensure a clean import so patched constants stick for the test body.
    if "generate_boutique_embeddings" in sys.modules:
        del sys.modules["generate_boutique_embeddings"]
    mod = importlib.import_module("generate_boutique_embeddings")
    monkeypatch.setattr(mod, "CHECKPOINT_PATH", tmp_path / ".chkpt")
    monkeypatch.setattr(mod, "EXPECTED_ROW_COUNT", 1)  # tests use tiny CSVs
    # Silence logs during tests.
    mod._configure_logging(quiet=True, json_output=False)
    return mod


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "catalog.csv"
    _write_csv(p, row_count=2)
    return p


def _fake_bedrock_response(vec: List[float]) -> dict:
    # Return a fresh BytesIO each call so repeated .read() works under mocking.
    return {"body": io.BytesIO(json.dumps({"embeddings": {"float": [vec]}}).encode())}


def _always_fresh(vec: List[float]):
    """Side-effect function that returns a new response dict per call."""
    def _inner(*args, **kwargs):
        return _fake_bedrock_response(vec)
    return _inner


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def test_preflight_fails_on_missing_csv(module, tmp_path):
    with pytest.raises(SystemExit) as exc:
        module.generate_embeddings(csv_path=tmp_path / "does-not-exist.csv")
    assert exc.value.code == 1


def test_preflight_fails_on_invalid_model(module, csv_path):
    from botocore.exceptions import ClientError

    err = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "no access"}},
        "InvokeModel",
    )
    fake_client = MagicMock()
    fake_client.invoke_model.side_effect = err
    with patch("boto3.client", return_value=fake_client):
        with pytest.raises(SystemExit) as exc:
            module.generate_embeddings(csv_path=csv_path, model_id="bogus")
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Happy path + retries
# ---------------------------------------------------------------------------


def test_successful_embedding_of_one_row(module, csv_path):
    vec = [0.01] * module.EMBEDDING_DIM
    fake_client = MagicMock()
    # first call is reachability check, subsequent are per-row
    fake_client.invoke_model.side_effect = _always_fresh(vec)
    with patch("boto3.client", return_value=fake_client):
        result = module.generate_embeddings(csv_path=csv_path, resume=False)
    assert sorted(result.embedded_product_ids) == [1, 2]
    assert result.failed_product_ids == []
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        emb = json.loads(r["embedding"])
        assert len(emb) == module.EMBEDDING_DIM


def test_retry_on_throttling_exception(module, csv_path):
    from botocore.exceptions import ClientError

    throttle = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
        "InvokeModel",
    )
    vec = [0.02] * module.EMBEDDING_DIM
    fake_client = MagicMock()
    # reachability, then for row 1: throttle, throttle, success; row 2: success
    fake_client.invoke_model.side_effect = [
        _fake_bedrock_response(vec),  # reachability
        throttle,
        throttle,
        _fake_bedrock_response(vec),
        _fake_bedrock_response(vec),
    ]
    with patch("boto3.client", return_value=fake_client), \
         patch.object(module.time, "sleep", return_value=None):
        result = module.generate_embeddings(csv_path=csv_path, resume=False)
    assert result.total_retries >= 2
    assert result.failed_product_ids == []


def test_retry_exhausted_raises(module, csv_path):
    from botocore.exceptions import ClientError

    throttle = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
        "InvokeModel",
    )
    vec = [0.03] * module.EMBEDDING_DIM
    fake_client = MagicMock()
    fake_client.invoke_model.side_effect = [
        _fake_bedrock_response(vec),  # reachability
        throttle, throttle, throttle,  # row A fails
        throttle, throttle, throttle,  # row B fails
    ]
    with patch("boto3.client", return_value=fake_client), \
         patch.object(module.time, "sleep", return_value=None):
        with pytest.raises(SystemExit) as exc:
            module.generate_embeddings(csv_path=csv_path, resume=False)
    assert exc.value.code == 3


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


def test_checkpoint_skips_completed_product_ids(module, csv_path, tmp_path):
    # Pre-populate row 1's embedding + checkpoint so it should be skipped.
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows[0]["embedding"] = json.dumps([0.5] * module.EMBEDDING_DIM, separators=(",", ":"))
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    module.CHECKPOINT_PATH.write_text(
        json.dumps(
            {
                "completed_product_ids": [1],
                "total_rows": 2,
                "model_id": module.DEFAULT_MODEL,
                "started_at": "x",
                "last_updated": "x",
                "script_version": "1.0.0",
            }
        )
    )

    vec = [0.04] * module.EMBEDDING_DIM
    fake_client = MagicMock()
    fake_client.invoke_model.side_effect = _always_fresh(vec)
    with patch("boto3.client", return_value=fake_client):
        result = module.generate_embeddings(csv_path=csv_path, resume=True)
    assert 1 in result.skipped_product_ids
    assert 2 in result.embedded_product_ids


def test_checkpoint_invalid_for_different_model_ignored(module, csv_path):
    module.CHECKPOINT_PATH.write_text(
        json.dumps(
            {
                "completed_product_ids": [1, 2],
                "total_rows": 2,
                "model_id": "some-other-model",
                "started_at": "x",
                "last_updated": "x",
                "script_version": "1.0.0",
            }
        )
    )
    vec = [0.05] * module.EMBEDDING_DIM
    fake_client = MagicMock()
    fake_client.invoke_model.side_effect = _always_fresh(vec)
    with patch("boto3.client", return_value=fake_client):
        result = module.generate_embeddings(csv_path=csv_path, resume=True)
    # Checkpoint should be ignored; both rows re-embedded.
    assert sorted(result.embedded_product_ids) == [1, 2]
    assert result.skipped_product_ids == []


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_atomic_write_preserves_original_on_failure(module, csv_path):
    """If the Bedrock call fails for all rows, the original CSV is untouched."""
    from botocore.exceptions import ClientError

    throttle = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
        "InvokeModel",
    )
    vec = [0.06] * module.EMBEDDING_DIM
    fake_client = MagicMock()
    fake_client.invoke_model.side_effect = [
        _fake_bedrock_response(vec),  # reachability
    ] + [throttle] * 6

    original_bytes = csv_path.read_bytes()
    with patch("boto3.client", return_value=fake_client), \
         patch.object(module.time, "sleep", return_value=None):
        with pytest.raises(SystemExit):
            module.generate_embeddings(csv_path=csv_path, resume=False)
    # Original CSV content unchanged.
    assert csv_path.read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_generates_fake_vectors_no_bedrock_call(module, csv_path):
    with patch("boto3.client") as boto_mock:
        result = module.generate_embeddings(csv_path=csv_path, dry_run=True)
    boto_mock.assert_not_called()
    assert sorted(result.embedded_product_ids) == [1, 2]
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        emb = json.loads(r["embedding"])
        assert len(emb) == module.EMBEDDING_DIM
    # Deterministic: same seed -> same vector for same productId
    row1_again = module._fake_embedding(1)
    assert json.loads(rows[0]["embedding"])[:5] == row1_again[:5]
