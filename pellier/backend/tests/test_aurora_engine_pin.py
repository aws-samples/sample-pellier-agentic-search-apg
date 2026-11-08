"""The Aurora engine is one pinned version, the same in every place that states it."""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = REPO_ROOT / "deploy" / "own-account" / "templates"
DATABASE = TEMPLATES / "pellier-database.yml"
PARENT = TEMPLATES / "pellier-governed.yml"
OWN_ACCOUNT_PAGE = REPO_ROOT / "docs" / "run-in-your-own-account.md"

# pgvector ships with the engine minor. Source: "Extensions supported for Aurora PostgreSQL 18",
# https://docs.aws.amazon.com/AmazonRDS/latest/AuroraPostgreSQLReleaseNotes/AuroraPostgreSQL.Extensions.html
# (read 2026-11-08). Add the row for a new minor when the pin moves to it.
PGVECTOR_FOR_ENGINE = {"18.3": "0.8.1", "18.4": "0.8.2", "18.6": "0.8.2"}


def _engine_default(template: Path) -> str:
    found = re.findall(r'(?m)^  AuroraEngineVersion:\n    Type: String\n    Default: "([^"]+)"',
                       template.read_text())
    assert len(found) == 1, f"{template.name} must declare one AuroraEngineVersion default"
    return found[0]


def test_both_templates_pin_the_same_full_engine_version():
    database, parent = _engine_default(DATABASE), _engine_default(PARENT)
    assert database == parent, "the parent stack would override the database stack's tested pin"
    assert re.fullmatch(r"\d+\.\d+", database), "pin the major and the minor, never the major alone"


def test_the_pinned_engine_is_stated_the_same_everywhere():
    engine = _engine_default(DATABASE)
    text = DATABASE.read_text()
    assert f"(default {engine})" in text
    assert f"with pgvector {PGVECTOR_FOR_ENGINE[engine]}." in text
    assert f"| Aurora PostgreSQL | engine {engine}," in OWN_ACCOUNT_PAGE.read_text()


def test_a_maintenance_window_cannot_change_the_engine():
    text = DATABASE.read_text()
    instances = re.findall(r"(?m)^    Type: AWS::RDS::DBInstance$", text)
    assert instances, "the database stack defines its cluster instance"
    assert text.count("AutoMinorVersionUpgrade: false") == len(instances)
