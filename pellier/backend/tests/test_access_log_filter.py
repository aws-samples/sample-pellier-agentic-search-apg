"""The access-log filter drops scanner probes and never the app's own API calls."""

from __future__ import annotations

import logging

from app import SecurityScanFilter


def _access(method: str, path: str) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 0,
                             '%s - "%s %s HTTP/%s" %d',
                             ("127.0.0.1:5000", method, path, "1.1", 200), None)


def test_the_operator_execute_call_is_logged() -> None:
    assert SecurityScanFilter().filter(_access("POST", "/api/operator/reviews/7/execute"))


def test_scanner_probes_are_dropped() -> None:
    for path in ("/.env", "/wp-admin/setup.php", "/cgi-bin/exec", "/vendor/phpunit/x"):
        assert not SecurityScanFilter().filter(_access("GET", path)), path


def test_ordinary_pages_are_logged() -> None:
    assert SecurityScanFilter().filter(_access("GET", "/operator"))
