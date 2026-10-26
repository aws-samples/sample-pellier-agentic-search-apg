"""Tests for collectorless span export to the CloudWatch X-Ray OTLP endpoint.

The contract that matters is the degradation contract. Export is best-effort
evidence plumbing: it must never fail startup, and — just as importantly — it
must never *claim* to be attached when it is not. A readiness surface that
reports healthy export while spans are being dropped is worse than one that
reports the failure, because the workshop's "here is the evidence" step then
fails with no explanation.

So every test below pins one of two things: that a failure path returns a
reasoned, unattached state, or that the success path attaches exactly one
processor to the provider that already exists.
"""

from __future__ import annotations

import pathlib

import pytest

from services import otel_cloudwatch_export as export_module
from services.otel_cloudwatch_export import (
    SigV4RequestSigner,
    SpanExportState,
    build_signing_exporter,
    init_cloudwatch_span_export,
    traces_endpoint_for_region,
)


# ---------------------------------------------------------------------------
# Endpoint construction
# ---------------------------------------------------------------------------


def test_endpoint_follows_the_documented_xray_pattern():
    """The traces endpoint is `https://xray.<region>.amazonaws.com/v1/traces`."""
    assert (
        traces_endpoint_for_region("us-east-1")
        == "https://xray.us-east-1.amazonaws.com/v1/traces"
    )
    assert (
        traces_endpoint_for_region("eu-west-2")
        == "https://xray.eu-west-2.amazonaws.com/v1/traces"
    )


# ---------------------------------------------------------------------------
# Degraded paths — each returns a reason, none raise
# ---------------------------------------------------------------------------


def test_disabled_by_configuration_attaches_nothing():
    state = init_cloudwatch_span_export(enabled=False, region="us-east-1")

    assert state.attached is False
    assert "OTEL_CLOUDWATCH_TRACES_ENABLED" in state.reason
    # An unattached state must not advertise a destination.
    assert state.as_dict()["spans_log_group"] is None


def test_missing_sdk_provider_is_reported_not_raised(monkeypatch):
    """A non-SDK provider drops spans, so attaching to it would be a lie."""
    monkeypatch.setattr(export_module, "_sdk_provider", lambda: None)

    state = init_cloudwatch_span_export(enabled=True, region="us-east-1")

    assert state.attached is False
    assert "No SDK TracerProvider" in state.reason
    assert state.endpoint == "https://xray.us-east-1.amazonaws.com/v1/traces"


def test_unresolvable_credentials_are_reported_before_attaching(monkeypatch):
    """No credentials must be a reported state, not a silent retry loop.

    The processor would otherwise attach cleanly and fail every export on a
    background thread, which reads to an operator as working export.
    """
    attached: list = []

    class _Provider:
        sampler = None

        def add_span_processor(self, processor):  # pragma: no cover - must not run
            attached.append(processor)

    class _NoCredsSession:
        def get_credentials(self):
            return None

    monkeypatch.setattr(export_module, "_sdk_provider", lambda: _Provider())
    monkeypatch.setattr("botocore.session.Session", _NoCredsSession)

    state = init_cloudwatch_span_export(enabled=True, region="us-east-1")

    assert state.attached is False
    assert "credentials" in state.reason.lower()
    assert attached == [], "must not attach a processor it cannot sign with"


def test_exporter_construction_failure_is_reported(monkeypatch):
    class _Provider:
        sampler = None

        def add_span_processor(self, processor):
            raise RuntimeError("provider is shut down")

    class _Session:
        def get_credentials(self):
            return object()

    monkeypatch.setattr(export_module, "_sdk_provider", lambda: _Provider())
    monkeypatch.setattr("botocore.session.Session", _Session)

    state = init_cloudwatch_span_export(enabled=True, region="us-east-1")

    assert state.attached is False
    assert "provider is shut down" in state.reason


# ---------------------------------------------------------------------------
# Attached path
# ---------------------------------------------------------------------------


def test_attaches_one_processor_and_reports_the_destination(
    monkeypatch, caplog
):
    """Success attaches exactly one processor and names where spans go."""
    processors: list = []

    class _Sampler:
        def get_description(self):
            return "ParentBased{root=AlwaysOnSampler}"

    class _Provider:
        sampler = _Sampler()

        def add_span_processor(self, processor):
            processors.append(processor)

    class _Session:
        def get_credentials(self):
            return object()

    monkeypatch.setattr(export_module, "_sdk_provider", lambda: _Provider())
    monkeypatch.setattr("botocore.session.Session", _Session)

    with caplog.at_level("WARNING"):
        state = init_cloudwatch_span_export(
            enabled=True,
            region="eu-central-1",
            endpoint="https://example.invalid/v1/traces",
        )

    assert state.attached is True
    assert state.reason == ""
    assert state.endpoint == "https://example.invalid/v1/traces"
    assert state.region == "eu-central-1"
    assert "AlwaysOn" in (state.sampler or "")
    assert len(processors) == 1, "exactly one processor per init call"

    payload = state.as_dict()
    assert payload["spans_log_group"] == "aws/spans"
    assert payload["attached"] is True
    assert not any("not 100%" in record.message for record in caplog.records)


def test_export_state_is_readable_after_init(monkeypatch):
    """`export_state()` mirrors the last init so readiness can read it later."""
    monkeypatch.setattr(export_module, "_sdk_provider", lambda: None)

    returned = init_cloudwatch_span_export(enabled=True, region="us-east-1")

    assert export_module.export_state() == returned


def test_ratio_sampler_is_warned_about_but_still_attaches(monkeypatch, caplog):
    """A sampled turn cannot be found by turn_id, so say so — but do not override.

    Sampling is the operator's call. Silently forcing it back to 100% would
    override a deliberate cost decision; saying nothing would let the
    reconstruction exercise fail mysteriously.
    """
    class _Sampler:
        def get_description(self):
            return (
                "ParentBased{root=TraceIdRatioBased{0.050000},"
                "remoteParentSampled=AlwaysOnSampler,"
                "remoteParentNotSampled=AlwaysOffSampler}"
            )

    class _Provider:
        sampler = _Sampler()

        def add_span_processor(self, processor):
            pass

    class _Session:
        def get_credentials(self):
            return object()

    monkeypatch.setattr(export_module, "_sdk_provider", lambda: _Provider())
    monkeypatch.setattr("botocore.session.Session", _Session)

    with caplog.at_level("WARNING"):
        state = init_cloudwatch_span_export(enabled=True, region="us-east-1")

    assert state.attached is True
    assert any("not 100%" in record.message for record in caplog.records)


def test_agent_observability_flag_is_warned_about(monkeypatch, caplog):
    """ADOT's content extraction would put payloads on spans; warn loudly."""
    class _Provider:
        sampler = None

        def add_span_processor(self, processor):
            pass

    class _Session:
        def get_credentials(self):
            return object()

    monkeypatch.setattr(export_module, "_sdk_provider", lambda: _Provider())
    monkeypatch.setattr("botocore.session.Session", _Session)
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "true")

    with caplog.at_level("WARNING"):
        init_cloudwatch_span_export(enabled=True, region="us-east-1")

    assert any(
        "AGENT_OBSERVABILITY_ENABLED" in record.message for record in caplog.records
    )


# ---------------------------------------------------------------------------
# SigV4 signing
#
# The endpoint rejects an unsigned or mis-signed POST with a 403 that the
# BatchSpanProcessor swallows on a background thread, so a signing mistake is
# invisible at runtime: startup logs success and no span ever arrives. These
# assertions are the only place the signature is checked before an operator is
# depending on it.
# ---------------------------------------------------------------------------


class _FakeCredentials:
    """Credentials shaped like botocore's, with no session token."""

    access_key = "AKIAEXAMPLE"
    secret_key = "wJalrXUtnFEMI/K7MDENG/EXAMPLEKEY"
    token = None


class _FakeCredentialsWithToken(_FakeCredentials):
    token = "FQoGZXIvYXdzEExampleSessionToken"


class _PreparedRequest:
    """Minimal stand-in for `requests.PreparedRequest`."""

    def __init__(self, body: bytes = b"span-payload", **headers: str) -> None:
        self.method = "POST"
        self.url = "https://xray.us-east-1.amazonaws.com/v1/traces"
        self.body = body
        self.headers = {"Content-Type": "application/x-protobuf", **headers}


def _sign(request: _PreparedRequest, region: str = "us-east-1", creds=None) -> dict:
    signer = SigV4RequestSigner(creds or _FakeCredentials(), region)
    return dict(signer(request).headers)


def test_signature_names_the_xray_service_and_region():
    """A signature scoped to the wrong service is rejected with a 403."""
    headers = _sign(_PreparedRequest(), region="eu-west-2")

    authorization = headers["Authorization"]
    assert authorization.startswith("AWS4-HMAC-SHA256 ")
    assert "/eu-west-2/xray/aws4_request" in authorization
    assert "X-Amz-Date" in headers


def test_the_body_actually_sent_is_the_body_signed():
    """Signing must happen after preparation, or compression breaks it.

    Two payloads differing only in bytes must produce different signatures. If
    they match, the payload hash is not part of the canonical request and every
    export fails once a body is present.
    """
    first = _sign(_PreparedRequest(body=b"payload-one"))["Authorization"]
    second = _sign(_PreparedRequest(body=b"payload-two"))["Authorization"]

    assert first != second


def test_only_headers_the_transport_will_not_rewrite_are_signed():
    """`User-Agent` and `Accept-Encoding` are urllib3's to change."""
    headers = _sign(
        _PreparedRequest(**{"User-Agent": "python-requests/2.32", "Accept-Encoding": "gzip"})
    )

    signed = headers["Authorization"].split("SignedHeaders=")[1].split(",")[0]
    assert "content-type" in signed
    assert "host" in signed
    assert "user-agent" not in signed
    assert "accept-encoding" not in signed


def test_a_session_token_is_forwarded():
    """An instance role or assumed role signs with a session token."""
    headers = _sign(_PreparedRequest(), creds=_FakeCredentialsWithToken())

    assert headers["X-Amz-Security-Token"] == _FakeCredentialsWithToken.token


def test_credentials_are_read_per_request_not_captured_once():
    """A rotating instance role must not freeze the process on stale keys."""
    reads: list[str] = []

    class _Rotating:
        secret_key = "secret"
        token = None

        @property
        def access_key(self) -> str:
            reads.append("read")
            return f"AKIAROTATED{len(reads)}"

    signer = SigV4RequestSigner(_Rotating(), "us-east-1")
    first = dict(signer(_PreparedRequest()).headers)["Authorization"]
    second = dict(signer(_PreparedRequest()).headers)["Authorization"]

    assert len(reads) >= 2, "credentials were captured once instead of per request"
    assert first != second


def test_the_prepared_request_is_returned_for_requests_to_send():
    """A `requests` auth hook that returns None sends an unsigned request."""
    request = _PreparedRequest()
    signer = SigV4RequestSigner(_FakeCredentials(), "us-east-1")

    assert signer(request) is request


def test_the_exporter_posts_to_the_given_endpoint_with_the_signing_hook(monkeypatch):
    """A real span through the real exporter, with only the HTTP send intercepted: the
    request reaches the endpoint signed. Checked by behaviour because the exporter's
    internals move between OTLP releases (1.45 replaced its `_session` with a transport)."""
    import requests
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    sent = []

    def send(self, request, **kwargs):
        sent.append(request)
        response = requests.Response()
        response.status_code, response._content, response.request = 200, b"", request
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    exporter = build_signing_exporter(
        endpoint="https://xray.ap-south-1.amazonaws.com/v1/traces",
        region="ap-south-1",
        credentials=_FakeCredentials(),
    )
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer("signing-test").start_as_current_span("routing"):
        pass
    provider.shutdown()

    (request,) = sent
    assert request.url == "https://xray.ap-south-1.amazonaws.com/v1/traces"
    assert request.headers["Authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE/")
    assert "/ap-south-1/xray/aws4_request" in request.headers["Authorization"]


def test_the_exporter_needs_no_aws_distro_package():
    """The distro is a 58-package dependency absent from the participant lock.

    Importing it here is what made Stage 1 export inert on every box while
    startup still reported a reason nobody read.
    """
    source = (
        pathlib.Path(export_module.__file__).read_text()
    )
    assert "amazon.opentelemetry" not in source.split('"""', 2)[2]


# ---------------------------------------------------------------------------
# State shape
# ---------------------------------------------------------------------------


def test_state_is_frozen():
    """The state is a report, not a mutable handle callers can edit."""
    state = SpanExportState(attached=False, reason="nope")
    with pytest.raises(Exception):
        state.attached = True  # type: ignore[misc]
