"""Performance smoke tests for Pellier storefront (Task 7.1).

Acceptance: ``.kiro/specs/pellier-storefront/requirements.md``
Req 5.1.1-5.1.3.

Runs against a **live** stack seeded with the workshop catalog. The
test module skips cleanly when ``PERF_TEST_BASE_URL`` is unset so the
suite stays CI-safe on machines without a running backend (no Aurora,
no Bedrock). Flip it on in docker-compose or on the workshop Code
Editor box::

    export PERF_TEST_BASE_URL=http://localhost:8000
    .venv/bin/python -m pytest tests/perf/test_perf_smoke.py -v -s

Targets enforced:

* **Req 5.1.1** ``POST /api/search`` end-to-end p95 under 500 ms.
* **Req 5.1.2** ``POST /api/agent/chat`` first-token latency under 2 s.
* **Req 5.1.3** JWT-verified endpoint warm-path *added* latency under
  200 ms (measured as the delta between an authed call and an
  unauthed baseline on the same host, so it isolates JWT verification
  overhead rather than network jitter).

All measurements are printed to stdout so CI surfaces them on every
run, regardless of pass/fail.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from typing import Callable

import pytest
import requests


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #

BASE_URL = os.environ.get("PERF_TEST_BASE_URL", "").rstrip("/")
PERF_JWT = os.environ.get("PERF_TEST_JWT", "").strip()

# Query text used for the search smoke - matches tasks.md 2.1 done-when
# criterion ("linen shirt") so a seeded catalog is guaranteed to answer.
SEARCH_QUERY = os.environ.get("PERF_TEST_SEARCH_QUERY", "linen shirt")

# Number of samples. Keeps CI wall-time bounded while still giving a
# usable p95 (20 samples -> index 18 = 95th percentile).
SEARCH_SAMPLES = int(os.environ.get("PERF_TEST_SEARCH_SAMPLES", "20"))
CHAT_SAMPLES = int(os.environ.get("PERF_TEST_CHAT_SAMPLES", "3"))
JWT_SAMPLES = int(os.environ.get("PERF_TEST_JWT_SAMPLES", "10"))
WARMUP_SAMPLES = int(os.environ.get("PERF_TEST_WARMUP_SAMPLES", "2"))

# Per-Req timeouts used as pytest hard-fail thresholds.
SEARCH_P95_BUDGET_MS = 500.0   # Req 5.1.1
CHAT_FIRST_TOKEN_BUDGET_MS = 2_000.0  # Req 5.1.2
JWT_ADDED_LATENCY_BUDGET_MS = 200.0   # Req 5.1.3

# Per-request timeouts generous enough to survive a cold Aurora ACU
# scale-up on the first call; we discard warmup samples before the
# timing window opens.
REQUEST_TIMEOUT_S = 30.0

skip_without_base = pytest.mark.skipif(
    not BASE_URL,
    reason=(
        "PERF_TEST_BASE_URL is not set - perf smoke skipped. Set it to "
        "the URL of a running backend (for example http://localhost:8000) "
        "to enable."
    ),
)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _percentile(samples: list[float], pct: float) -> float:
    """Nearest-rank percentile (no interpolation).

    Chosen over ``statistics.quantiles`` so a 20-sample p95 maps
    deterministically to the 19th sample (index 18), which matches how
    most workshop attendees reason about "p95".
    """

    if not samples:
        return float("nan")
    ordered = sorted(samples)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[rank - 1]


def _print_summary(label: str, samples_ms: list[float], budget_ms: float) -> None:
    """Emit a one-line summary that CI log viewers will surface."""

    if not samples_ms:
        print(f"[perf] {label}: no samples collected")
        return

    p50 = statistics.median(samples_ms)
    p95 = _percentile(samples_ms, 95)
    mx = max(samples_ms)
    mn = min(samples_ms)
    print(
        f"[perf] {label}: "
        f"n={len(samples_ms)} "
        f"min={mn:.1f}ms "
        f"p50={p50:.1f}ms "
        f"p95={p95:.1f}ms "
        f"max={mx:.1f}ms "
        f"budget={budget_ms:.0f}ms"
    )


def _measure(fn: Callable[[], None], n: int, warmup: int = 0) -> list[float]:
    """Run ``fn`` ``warmup + n`` times, return the last ``n`` wall-times in ms."""

    for _ in range(warmup):
        fn()

    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


# --------------------------------------------------------------------------- #
# Req 5.1.1 - search p95 < 500ms                                              #
# --------------------------------------------------------------------------- #

@skip_without_base
def test_search_p95_under_500ms() -> None:
    """``POST /api/search`` end-to-end p95 SHALL be under 500 ms."""

    url = f"{BASE_URL}/api/search"
    payload = {"query": SEARCH_QUERY, "limit": 10}

    def _one_call() -> None:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_S)
        assert resp.status_code == 200, (
            f"search returned {resp.status_code}: {resp.text[:200]}"
        )

    samples = _measure(_one_call, n=SEARCH_SAMPLES, warmup=WARMUP_SAMPLES)
    _print_summary("search", samples, SEARCH_P95_BUDGET_MS)

    p95 = _percentile(samples, 95)
    assert p95 < SEARCH_P95_BUDGET_MS, (
        f"POST /api/search p95={p95:.1f}ms exceeds "
        f"{SEARCH_P95_BUDGET_MS:.0f}ms (Req 5.1.1)"
    )


# --------------------------------------------------------------------------- #
# Req 5.1.2 - chat first-token < 2s                                           #
# --------------------------------------------------------------------------- #

def _read_first_sse_token(resp: requests.Response) -> None:
    """Consume the SSE stream until the first payload-bearing event lands.

    The chat endpoint emits a ``session_id`` handshake event first
    (Task 3.5); that event is part of the stream but is not a model
    token. We wait for either the first SSE ``data:`` line whose JSON
    payload carries a ``delta``/``text``/``token`` field OR the second
    data line overall, whichever arrives first. This keeps us resilient
    to minor envelope differences without relying on the full response.
    """

    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if not raw.startswith("data:"):
            continue
        body = raw[len("data:"):].strip()
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except ValueError:
            # Non-JSON data line still counts as a token arriving on the wire.
            return
        # Skip the session-handshake frame; wait for the first content frame.
        if isinstance(parsed, dict) and set(parsed.keys()) <= {"session_id", "type"}:
            continue
        return


@skip_without_base
def test_agent_chat_first_token_under_2s() -> None:
    """``POST /api/agent/chat`` first token SHALL arrive under 2 s."""

    url = f"{BASE_URL}/api/agent/chat"
    payload = {"message": "show me a linen shirt", "session_id": None}

    def _measure_one() -> float:
        t0 = time.perf_counter()
        with requests.post(
            url,
            json=payload,
            stream=True,
            timeout=REQUEST_TIMEOUT_S,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            assert resp.status_code == 200, (
                f"chat returned {resp.status_code}: {resp.text[:200]}"
            )
            _read_first_sse_token(resp)
            return (time.perf_counter() - t0) * 1000.0

    # Warm the Bedrock path once so we measure the warm case (Req 5.1.2
    # specifically calls out "typical query", which implies warm).
    for _ in range(max(1, WARMUP_SAMPLES - 1)):
        _measure_one()

    samples = [_measure_one() for _ in range(CHAT_SAMPLES)]
    _print_summary("chat-first-token", samples, CHAT_FIRST_TOKEN_BUDGET_MS)

    worst = max(samples)
    assert worst < CHAT_FIRST_TOKEN_BUDGET_MS, (
        f"POST /api/agent/chat worst first-token={worst:.1f}ms exceeds "
        f"{CHAT_FIRST_TOKEN_BUDGET_MS:.0f}ms (Req 5.1.2)"
    )


# --------------------------------------------------------------------------- #
# Req 5.1.3 - JWT-verified warm-path added latency < 200ms                    #
# --------------------------------------------------------------------------- #

@skip_without_base
def test_jwt_verified_warm_added_latency_under_200ms() -> None:
    """JWT verification SHALL add under 200 ms on the warm path.

    Measured as the delta between authed ``GET /api/user/preferences``
    (which exercises ``require_user`` and thus ``CognitoAuthService``
    with a warm JWKS cache) and unauthed ``GET /api/products`` on the
    same host. Skips cleanly when ``PERF_TEST_JWT`` is not provided -
    the search and chat smokes still run in that case.
    """

    if not PERF_JWT:
        pytest.skip(
            "PERF_TEST_JWT is not set - JWT warm-path check skipped. "
            "Set it to a valid Cognito access token to enable Req 5.1.3."
        )

    authed_url = f"{BASE_URL}/api/user/preferences"
    baseline_url = f"{BASE_URL}/api/products"

    auth_headers = {"Authorization": f"Bearer {PERF_JWT}"}

    def _hit_authed() -> None:
        resp = requests.get(
            authed_url, headers=auth_headers, timeout=REQUEST_TIMEOUT_S
        )
        # Preferences endpoint returns 200 with null body when unset;
        # either 200 or 204 is a valid warm path.
        assert resp.status_code in (200, 204), (
            f"authed preferences returned {resp.status_code}: "
            f"{resp.text[:200]}"
        )

    def _hit_baseline() -> None:
        resp = requests.get(baseline_url, timeout=REQUEST_TIMEOUT_S)
        assert resp.status_code == 200, (
            f"baseline products returned {resp.status_code}: "
            f"{resp.text[:200]}"
        )

    # Warm both paths (populates JWKS cache + DB pool).
    for _ in range(WARMUP_SAMPLES):
        _hit_authed()
        _hit_baseline()

    authed_samples = _measure(_hit_authed, n=JWT_SAMPLES)
    baseline_samples = _measure(_hit_baseline, n=JWT_SAMPLES)

    _print_summary("jwt-authed", authed_samples, JWT_ADDED_LATENCY_BUDGET_MS)
    _print_summary("jwt-baseline", baseline_samples, JWT_ADDED_LATENCY_BUDGET_MS)

    authed_p50 = statistics.median(authed_samples)
    baseline_p50 = statistics.median(baseline_samples)
    added = authed_p50 - baseline_p50
    print(
        f"[perf] jwt-added-latency: "
        f"authed_p50={authed_p50:.1f}ms "
        f"baseline_p50={baseline_p50:.1f}ms "
        f"delta={added:.1f}ms "
        f"budget={JWT_ADDED_LATENCY_BUDGET_MS:.0f}ms"
    )

    assert added < JWT_ADDED_LATENCY_BUDGET_MS, (
        f"JWT-verified warm path added {added:.1f}ms latency "
        f"(authed_p50={authed_p50:.1f}ms, baseline_p50={baseline_p50:.1f}ms), "
        f"exceeds {JWT_ADDED_LATENCY_BUDGET_MS:.0f}ms (Req 5.1.3)"
    )
