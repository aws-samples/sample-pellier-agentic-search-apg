"""Internal telemetry exceptions must stay out of browser and SSE payloads."""

import json

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from services import otel_trace_extractor as extractor


_READERS = (
    "extract_trace",
    "extract_agent_execution_from_otel",
    "get_waterfall_data",
)
_PRIVATE_DETAIL = "private shopper context at /srv/internal/telemetry.py:42"


class _BrokenExporter:
    def get_finished_spans(self):
        raise RuntimeError(_PRIVATE_DETAIL)


@pytest.mark.parametrize("reader", _READERS)
def test_exporter_failure_logs_details_without_returning_them(
    monkeypatch, caplog, reader
):
    monkeypatch.setattr(extractor, "OTEL_WORKING", True)
    monkeypatch.setattr(extractor, "_span_exporter", _BrokenExporter())

    payload = getattr(extractor, reader)()

    assert payload["otel_enabled"] is False
    assert payload["spans"] == []
    assert payload["reason"]
    assert _PRIVATE_DETAIL not in json.dumps(payload)
    assert _PRIVATE_DETAIL in caplog.text


@pytest.mark.parametrize("reader", _READERS)
def test_initialization_failure_is_safe_for_all_trace_readers(
    monkeypatch, caplog, reader
):
    provider = TracerProvider()

    def fail_attach(_processor):
        raise RuntimeError(_PRIVATE_DETAIL)

    monkeypatch.setattr(provider, "add_span_processor", fail_attach)
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
    monkeypatch.setattr(extractor, "OTEL_WORKING", True)
    monkeypatch.setattr(extractor, "OTEL_FAILURE_REASON", "")
    monkeypatch.setattr(extractor, "_span_exporter", None)
    try:
        extractor.init_span_capture()
        payload = getattr(extractor, reader)()
    finally:
        provider.shutdown()

    assert payload["otel_enabled"] is False
    assert payload["spans"] == []
    assert "failed to initialize span capture" in payload["reason"]
    assert _PRIVATE_DETAIL not in json.dumps(payload)
    assert _PRIVATE_DETAIL in caplog.text
