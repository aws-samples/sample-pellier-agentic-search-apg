"""Pytest configuration for backend tests.

Ensures the backend package directory is importable so test modules can
`from models import ...`, `from services.X import ...`, etc., and pins the
settings environment so a run is hermetic.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_backend_str = str(_BACKEND_ROOT)
if _backend_str not in sys.path:
    sys.path.insert(0, _backend_str)

# Hermetic settings. These lines must run before anything imports `config`,
# because config.py builds `Settings` at module scope.
#
# 1. Ignore any real .env. Otherwise `Settings` loads the developer's
#    pellier/backend/.env and tests asserting a variable is *absent* read a
#    live value, failing only on boxes that have been through bootstrap.
# 2. Supply DB placeholders. DB_HOST/NAME/USER/PASSWORD are required fields,
#    so without them importing config raises ValidationError and `pytest -q`
#    reports a collection error for every module that touches settings
#    instead of running the suite. This replaces the DB_HOST=... prefix the
#    backend CLAUDE.md used to prescribe.
os.environ["PELLIER_DISABLE_DOTENV"] = "1"
for _var, _placeholder in (
    ("DB_HOST", "localhost"),
    ("DB_NAME", "pellier_test"),
    ("DB_USER", "pellier_test"),
    ("DB_PASSWORD", "pellier_test"),
):
    os.environ.setdefault(_var, _placeholder)

# 3. Pin a fake AWS identity and turn off instance metadata. boto3 resolves
#    credentials when a client is built (Strands' BedrockModel, the AgentCore
#    clients). With no credentials, botocore asks the EC2 metadata service,
#    which `_no_aws_network` refuses, so CI failed; with a developer's profile,
#    the same tests passed locally. One fake identity makes both runs the same.
for _var in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
    os.environ.pop(_var, None)
os.environ.update({
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "AWS_EC2_METADATA_DISABLED": "true",
})
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


import pytest

# The four sign-in names scripts/migrations/002_seed.sql writes to
# pellier.customers.cognito_username. The app loads them from Aurora at startup;
# tests start from the same map (test_fresh_setup_postgres.py checks the seed).
SEED_CUSTOMER_USERNAMES = {
    "anna": "CUST-ANNA",
    "marco": "CUST-MARCO",
    "theo": "CUST-THEO",
    "jessica": "CUST-JESSICA",
}


@pytest.fixture(autouse=True)
def _seeded_customer_usernames():
    """Start every test with the seeded username-to-customer map loaded."""
    from services.turn_identity import set_customer_usernames

    set_customer_usernames(SEED_CUSTOMER_USERNAMES)
    yield
    set_customer_usernames(SEED_CUSTOMER_USERNAMES)


class TestReachedAws(AssertionError):
    """A test tried to call AWS. Patch the boundary instead."""


@pytest.fixture(autouse=True)
def _no_aws_network(monkeypatch):
    """Make any unpatched AWS call fail loudly.

    Every boto3 service, including Bedrock and AgentCore, sends through
    botocore's HTTP session; the managed Runtime data plane is invoked with
    ``urllib`` against ``amazonaws.com``. Both are refused here so a future
    test that drives an agent without a stand-in cannot quietly reach Bedrock
    wherever credentials happen to exist.
    """
    import urllib.request

    import botocore.httpsession

    def _refuse_boto(self, request, *args, **kwargs):
        raise TestReachedAws(
            f"test reached AWS through botocore: {request.method} {request.url}"
        )

    real_urlopen = urllib.request.urlopen

    def _refuse_aws_urlopen(url, *args, **kwargs):
        target = getattr(url, "full_url", url)
        if "amazonaws.com" in str(target):
            raise TestReachedAws(f"test reached AWS through urllib: {target}")
        return real_urlopen(url, *args, **kwargs)

    monkeypatch.setattr(botocore.httpsession.URLLib3Session, "send", _refuse_boto)
    monkeypatch.setattr(urllib.request, "urlopen", _refuse_aws_urlopen)


@pytest.fixture(autouse=True)
def _hermetic_structured_extractor(monkeypatch):
    """Keep the shopper search planner's live Sonnet call out of every test.

    Extraction always runs on the local rail; ``get_structured_extractor`` is
    the boundary where Bedrock is reached. This stand-in reads no requirements
    from the query, so a test that needs a reading installs its own extractor
    on the same attribute.
    """
    import services.structured_extract as structured_extract

    class _NoRequirements:
        def extract(self, query: str) -> dict:
            return structured_extract.StructuredExtractor._empty(query, status="parsed")

    monkeypatch.setattr(
        structured_extract, "get_structured_extractor", lambda: _NoRequirements()
    )


@pytest.fixture
def completed_search_plan(monkeypatch):
    """Run the Task 1B solution's fallback, whatever the live file holds.

    Tests of the surrounding search code need a fallback that keeps the hard
    limits. The starter's own failure, and the solution's fix, are asserted by
    ``tests/test_lab1_starter_failure.py``.
    """
    from services.search_plan import SearchPlan
    from tests.lab_variants import SOLUTION, plan_fallback

    monkeypatch.setattr(SearchPlan, "_with_relaxations", plan_fallback(SOLUTION))
