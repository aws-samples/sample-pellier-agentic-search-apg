"""The anonymous AgentCore status routes: cached probe, no resource identifiers."""

from __future__ import annotations

import asyncio

import pytest

import app as app_module
import services.agentcore_memory as memory_module
from config import settings


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    app_module._memory_status_cache[:] = [0.0, None]


def test_memory_status_probes_once_inside_the_cache_window(monkeypatch) -> None:
    calls: list[int] = []

    def probe() -> dict:
        calls.append(1)
        return {"live": True, "source": "agentcore-sdk", "memory_id": "mem-secret-id"}

    monkeypatch.setattr(memory_module, "probe_memory_backend_status", probe)

    first = asyncio.run(app_module.memory_status())
    second = asyncio.run(app_module.memory_status())

    assert len(calls) == 1
    assert first == second == {"live": True, "source": "agentcore-sdk"}


def test_gateway_status_omits_the_gateway_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", "https://gw.example/mcp")

    body = asyncio.run(app_module.gateway_status())

    assert body["configured"] is True
    assert "gateway_url" not in body and "gw.example" not in str(body)
