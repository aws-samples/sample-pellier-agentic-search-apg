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


import pytest


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
    """Provide the completed clone only while testing surrounding starter scaffolding.

    Participant implementations run unchanged. The untouched starter's refusal
    and the recovery's real contract are tested separately by marker/guide tests.
    This fixture does not establish that the shipping exercise is completed.
    """
    import inspect
    from dataclasses import replace
    from services.search_plan import SearchPlan

    if "Complete Task 1B before relaxing a preference" in inspect.getsource(SearchPlan._with_relaxations):
        monkeypatch.setattr(SearchPlan, "_with_relaxations",
                            lambda self, relaxations: replace(self, relaxations=list(relaxations)))
