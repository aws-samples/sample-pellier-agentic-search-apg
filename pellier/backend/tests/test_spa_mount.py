"""Tests for the SPA_MOUNT_PATH env var in app.py.

The mount path is resolved at module-import time because FastAPI
routes are registered at module scope. We reload the ``app`` module
inside each test with a different ``SPA_MOUNT_PATH`` to exercise
both code paths (root mount and prefixed mount).

These tests use a synthetic ``frontend/dist`` written to a tmp
directory so they don't depend on a real ``npm run build`` having
been run before pytest.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fake_dist(tmp_path: Path) -> Path:
    """A minimal frontend/dist with index.html + one asset."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "fonts").mkdir()
    (dist / "index.html").write_text("<html><body>SPA</body></html>")
    (dist / "assets" / "main.js").write_text("console.log('hi')")
    return dist


@pytest.fixture
def reload_app(fake_dist: Path, monkeypatch: pytest.MonkeyPatch):
    """Reload app.py with a given SPA_MOUNT_PATH and fake dist.

    Returns a factory: ``reload_app(mount_path)`` → fresh ``app`` module.
    """
    def _factory(mount_path: str):
        monkeypatch.setenv("SPA_MOUNT_PATH", mount_path)
        monkeypatch.setenv("FRONTEND_DIST_PATH", str(fake_dist))
        import app as app_module
        app_module = importlib.reload(app_module)

        # Keep SPA-mount tests focused on routing behavior, not external
        # Aurora/Bedrock connectivity during FastAPI lifespan startup.
        async def _noop_connect(self):
            return None

        async def _noop_disconnect(self):
            return None

        async def _ok_query(self, *_args, **_kwargs):
            return [{"?column?": 1}]

        def _ok_embedding(self, *_args, **_kwargs):
            return [0.0, 0.1, 0.2]

        monkeypatch.setattr(app_module.DatabaseService, "connect", _noop_connect, raising=True)
        monkeypatch.setattr(app_module.DatabaseService, "disconnect", _noop_disconnect, raising=True)
        monkeypatch.setattr(app_module.DatabaseService, "execute_query", _ok_query, raising=True)
        monkeypatch.setattr(app_module.EmbeddingService, "generate_embedding", _ok_embedding, raising=True)
        return app_module

    return _factory


# ---------- Default: SPA_MOUNT_PATH = "/" ----------------------------

def test_root_mount_serves_spa_at_slash(reload_app):
    app_module = reload_app("/")
    with TestClient(app_module.app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "SPA" in r.text


def test_root_mount_deep_link_serves_index(reload_app):
    """React Router deep link refresh: /atelier/agents → index.html."""
    app_module = reload_app("/")
    with TestClient(app_module.app) as client:
        r = client.get("/atelier/agents")
        assert r.status_code == 200
        assert "SPA" in r.text


def test_root_mount_api_path_does_not_get_swallowed(reload_app):
    """At root mount, /api/* must NOT be served by the SPA catch-all
    — that would mask real router 404s. Real /api/health works because
    its router is registered above the catch-all."""
    app_module = reload_app("/")
    with TestClient(app_module.app) as client:
        r = client.get("/api/health")
        # Health may be 200 or 503 (depends on DB/Bedrock), but must
        # be JSON, never the SPA HTML.
        assert "SPA" not in r.text
        assert r.headers.get("content-type", "").startswith("application/json")


# ---------- Prefixed: SPA_MOUNT_PATH = "/app" ------------------------

def test_app_mount_serves_spa_at_app_slash(reload_app):
    app_module = reload_app("/app")
    with TestClient(app_module.app) as client:
        r = client.get("/app/")
        assert r.status_code == 200
        assert "SPA" in r.text


def test_app_mount_bare_app_redirects_to_slash(reload_app):
    """GET /app (no trailing slash) → 307 → /app/.

    Without the redirect, the bundle's relative asset URLs
    (``assets/foo.js``) would resolve against ``/`` and 404.
    """
    app_module = reload_app("/app")
    with TestClient(app_module.app, follow_redirects=False) as client:
        r = client.get("/app")
        assert r.status_code == 307
        assert r.headers["location"] == "/app/"


def test_app_mount_deep_link_serves_index(reload_app):
    app_module = reload_app("/app")
    with TestClient(app_module.app) as client:
        r = client.get("/app/atelier/agents")
        assert r.status_code == 200
        assert "SPA" in r.text


def test_app_mount_real_api_still_at_root(reload_app):
    """With SPA at /app, /api/health must still hit the real router."""
    app_module = reload_app("/app")
    with TestClient(app_module.app) as client:
        r = client.get("/api/health")
        assert "SPA" not in r.text
        assert r.headers.get("content-type", "").startswith("application/json")


def test_app_mount_prefixed_api_falls_through_to_spa(reload_app):
    """With SPA at /app, /app/api/health is owned by the SPA catch-all
    (the real API lives at /api/*, not /app/api/*). Proves the prefix
    mount doesn't shadow the real API surface."""
    app_module = reload_app("/app")
    with TestClient(app_module.app) as client:
        r = client.get("/app/api/health")
        assert r.status_code == 200
        assert "SPA" in r.text


def test_app_mount_root_returns_404(reload_app):
    """When SPA is moved to /app, GET / has no handler."""
    app_module = reload_app("/app")
    with TestClient(app_module.app) as client:
        r = client.get("/")
        assert r.status_code == 404


def test_app_mount_assets_served_under_prefix(reload_app):
    app_module = reload_app("/app")
    with TestClient(app_module.app) as client:
        r = client.get("/app/assets/main.js")
        assert r.status_code == 200
        assert "console.log" in r.text
