"""Tests for `scripts/seed_principal_mappings.py`.

The mapping this script writes is what makes Row-Level Security usable rather
than merely strict. Migration 016 resolves a verified Cognito subject to a
customer scope through `pellier.principal_customers`; an empty table denies
every signed-in shopper, which a participant reads as a broken application
rather than as governance.

Two properties are pinned because both were wrong in the first version:

  1. **Completeness is a property of the table, not the pool.** The first
     `--check` compared *resolvable* subjects against the wanted personas and
     printed "Mapping complete" against an empty table — the precise failure
     the script exists to prevent.
  2. **One subject has one customer scope.** Multiple subjects for one customer
     are legitimate, but one subject mapped to multiple customers would widen
     every RLS policy that calls the shared resolver.

The username -> customer half is imported from `turn_identity`, never
restated, so the application and the database cannot disagree about scope.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from psycopg import DataError


@pytest.fixture(autouse=True)
def _no_external_transports(monkeypatch):
    def unexpected_transport(*_args, **_kwargs):
        pytest.fail("No AWS, database or external CLI call is allowed in this test.")

    monkeypatch.setattr("boto3.client", unexpected_transport)
    monkeypatch.setattr("psycopg.connect", unexpected_transport)
    monkeypatch.setattr("subprocess.run", unexpected_transport)


def _load_seeder():
    module_name = "seed_principal_mappings_for_tests"
    if module_name in sys.modules:
        return sys.modules[module_name]

    script_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "seed_principal_mappings.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


# ---------------------------------------------------------------------------
# One source of truth for scope
# ---------------------------------------------------------------------------


def test_personas_come_from_the_application_mapping():
    """Restating the mapping would let the app and the database diverge.

    The app would believe a turn is scoped to a customer while the database
    refuses every row, with no error explaining why.
    """
    seeder = _load_seeder()
    from services.turn_identity import USERNAME_TO_CUSTOMER_ID

    assert seeder._username_to_customer() == USERNAME_TO_CUSTOMER_ID
    # A copy, so a caller cannot mutate the application's table.
    seeder._username_to_customer()["marco"] = "CUST-INTRUDER"
    assert USERNAME_TO_CUSTOMER_ID["marco"] == "CUST-MARCO"


def test_every_named_persona_is_covered():
    """The obvious question: does each signed-in user get a mapping?"""
    seeder = _load_seeder()

    wanted = seeder._username_to_customer()

    assert set(wanted) == {"marco", "anna", "theo", "jessica"}
    assert set(wanted.values()) == {
        "CUST-MARCO",
        "CUST-ANNA",
        "CUST-THEO",
        "CUST-JESSICA",
    }


# ---------------------------------------------------------------------------
# Upsert shape
# ---------------------------------------------------------------------------


def test_upsert_is_idempotent():
    seeder = _load_seeder()

    sql = seeder.upsert_sql({"marco": ("sub-1", "CUST-MARCO")})

    assert "ON CONFLICT (principal_sub, customer_id) DO NOTHING" in sql
    assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")


def test_upsert_preserves_other_logins_for_the_same_customer():
    """The seeder cannot know which existing login a lifecycle task owns."""
    seeder = _load_seeder()

    sql = seeder.upsert_sql({"marco": ("sub-new", "CUST-MARCO")})

    assert "DELETE FROM pellier.principal_customers" not in sql
    assert "INSERT INTO pellier.principal_customers" in sql


def test_upsert_of_nothing_is_empty_not_a_delete_everything():
    """An empty resolution must never emit a bare DELETE."""
    seeder = _load_seeder()

    assert seeder.upsert_sql({}) == ""


def test_upsert_covers_every_resolved_persona():
    seeder = _load_seeder()

    sql = seeder.upsert_sql(
        {
            "marco": ("sub-m", "CUST-MARCO"),
            "anna": ("sub-a", "CUST-ANNA"),
            "theo": ("sub-t", "CUST-THEO"),
            "jessica": ("sub-j", "CUST-JESSICA"),
        }
    )

    for sub, customer in (
        ("sub-m", "CUST-MARCO"),
        ("sub-a", "CUST-ANNA"),
        ("sub-t", "CUST-THEO"),
        ("sub-j", "CUST-JESSICA"),
    ):
        assert f"('{sub}', '{customer}')" in sql


@pytest.mark.parametrize("field", ["subject", "customer"])
@pytest.mark.parametrize("value,literal", [
    ("O'Reilly", "'O''Reilly'"),
    (r"C:\workshop\end\\", r" E'C:\\workshop\\end\\\\'"),
    (
        "x'); DELETE FROM pellier.principal_customers; --",
        "'x''); DELETE FROM pellier.principal_customers; --'",
    ),
    (
        r"x\'); SELECT current_user; --",
        r" E'x\\''); SELECT current_user; --'",
    ),
    ("first\n\\! do-not-run\nlast", " E'first\n\\\\! do-not-run\nlast'"),
    ("α'客户", "'α''客户'"),
])
def test_upsert_quotes_each_value_as_one_postgresql_literal(field, value, literal):
    """Exercise SQL-looking data without inventing a SQL parser or contacting a DB."""
    seeder = _load_seeder()
    subject, customer = ("sub-normal", "CUST-MARCO")
    if field == "subject":
        subject = value
        expected_values = f"({literal}, 'CUST-MARCO')"
    else:
        customer = value
        expected_values = f"('sub-normal', {literal})"

    statement = seeder.upsert_sql({"marco": (subject, customer)})

    assert statement == (
        "BEGIN;\n"
        "INSERT INTO pellier.principal_customers (principal_sub, customer_id)\n"
        f" VALUES {expected_values}\n"
        " ON CONFLICT (principal_sub, customer_id) DO NOTHING;\n"
        "COMMIT;"
    )


@pytest.mark.parametrize("values", [
    ("subject\x00suffix", "CUST-MARCO"),
    ("subject", "CUST\x00MARCO"),
])
def test_upsert_rejects_nul_before_a_command_can_be_dispatched(values):
    with pytest.raises(DataError, match="NUL"):
        _load_seeder().upsert_sql({"marco": values})


def test_mapping_preflight_rejects_one_existing_subject_with_two_customers():
    seeder = _load_seeder()

    problems = seeder.mapping_problems(
        [("CUST-MARCO", "subject-1"), ("CUST-THEO", "subject-1")],
        {},
    )

    assert problems == [
        "existing subject subject-1 maps to multiple customers: CUST-MARCO, CUST-THEO"
    ]


def test_mapping_preflight_rejects_an_incoming_subject_owned_by_another_customer():
    seeder = _load_seeder()

    problems = seeder.mapping_problems(
        [("CUST-MARCO", "subject-1")],
        {"theo": ("subject-1", "CUST-THEO")},
    )

    assert problems == [
        "theo's subject subject-1 is already mapped to CUST-MARCO, not CUST-THEO"
    ]


def test_mapping_preflight_allows_multiple_principals_for_one_customer():
    seeder = _load_seeder()

    assert seeder.mapping_problems(
        [("CUST-THEO", "subject-1"), ("CUST-THEO", "subject-2")],
        {"theo": ("subject-3", "CUST-THEO")},
    ) == []


def test_cardinality_migration_constrains_the_security_critical_direction():
    migration = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "migrations"
        / "038_principal_customer_cardinality.sql"
    ).read_text()

    assert r"\set ON_ERROR_STOP on" in migration
    assert "GROUP BY principal_sub" in migration
    assert "HAVING count(*) > 1" in migration
    assert "UNIQUE (principal_sub)" in migration
    assert "UNIQUE (customer_id)" not in migration


# ---------------------------------------------------------------------------
# Subject resolution
# ---------------------------------------------------------------------------


class _FakeCognitoExceptions:
    class UserNotFoundException(Exception):
        pass


class _FakeCognito:
    def __init__(self, users):
        self._users = users
        self.exceptions = _FakeCognitoExceptions()

    def admin_get_user(self, UserPoolId, Username):  # noqa: N803 - boto3 casing
        if Username not in self._users:
            raise self.exceptions.UserNotFoundException(Username)
        return {
            "Username": Username,
            "UserAttributes": [
                {"Name": "email", "Value": f"{Username}@example.com"},
                {"Name": "sub", "Value": self._users[Username]},
            ],
        }


def test_resolves_subject_from_user_attributes(monkeypatch):
    seeder = _load_seeder()
    fake = _FakeCognito({"marco": "sub-m", "anna": "sub-a"})
    monkeypatch.setattr("boto3.client", lambda *_a, **_kw: fake)

    resolved, missing = seeder.resolve_subs(
        region="us-east-1", pool_id="pool", usernames=["marco", "anna", "theo"]
    )

    assert resolved == {"marco": "sub-m", "anna": "sub-a"}
    assert missing == ["theo"]


def test_a_user_absent_from_the_pool_is_reported_not_raised(monkeypatch):
    """A deployment may seed a subset; the caller decides if that matters."""
    seeder = _load_seeder()
    monkeypatch.setattr("boto3.client", lambda *_a, **_kw: _FakeCognito({}))

    resolved, missing = seeder.resolve_subs(
        region="us-east-1", pool_id="pool", usernames=["marco"]
    )

    assert resolved == {}
    assert missing == ["marco"]


def test_a_user_without_a_sub_attribute_is_treated_as_missing(monkeypatch):
    """No subject means nothing to key a policy on."""
    seeder = _load_seeder()

    class _NoSub(_FakeCognito):
        def admin_get_user(self, UserPoolId, Username):  # noqa: N803
            return {"Username": Username, "UserAttributes": [{"Name": "email", "Value": "x"}]}

    monkeypatch.setattr("boto3.client", lambda *_a, **_kw: _NoSub({"marco": "x"}))

    resolved, missing = seeder.resolve_subs(
        region="us-east-1", pool_id="pool", usernames=["marco"]
    )

    assert resolved == {}
    assert missing == ["marco"]


# ---------------------------------------------------------------------------
# Credential handling
# ---------------------------------------------------------------------------


def test_env_is_parsed_not_sourced(tmp_path):
    """A password with shell metacharacters must survive intact.

    Sourcing `.env` through a shell word-splits such a value and can echo a
    fragment into a log, which is how a live credential reached a session
    transcript once.
    """
    seeder = _load_seeder()
    env_file = tmp_path / ".env"
    hostile = "~koVh*cCz|sX5$4x8.VRrVs]"
    env_file.write_text(
        "# comment\n"
        "DB_HOST=cluster.example.com\n"
        f'DB_PASSWORD="{hostile}"\n'
        "\n"
        "COGNITO_POOL_ID=us-east-1_ABC\n"
    )

    cfg = seeder._load_env(env_file)

    assert cfg["DB_PASSWORD"] == hostile
    assert cfg["DB_HOST"] == "cluster.example.com"
    assert cfg["COGNITO_POOL_ID"] == "us-east-1_ABC"
    assert "# comment" not in cfg


def test_missing_env_file_is_not_fatal(tmp_path):
    seeder = _load_seeder()

    assert seeder._load_env(tmp_path / "absent.env") == {}


def test_password_is_never_placed_on_a_command_line(monkeypatch):
    """psql must receive credentials through the environment only."""
    seeder = _load_seeder()
    captured = {}

    def _fake_run(args, env=None, capture_output=None, text=None):
        captured["args"] = args
        captured["env"] = env

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr("subprocess.run", _fake_run)

    secret = "s3cr3t-value"
    seeder._psql(
        {
            "DB_HOST": "h",
            "DB_NAME": "d",
            "DB_USER": "u",
            "DB_PASSWORD": secret,
        },
        "SELECT 1",
    )

    assert secret not in " ".join(captured["args"])
    assert captured["env"]["PGPASSWORD"] == secret
    # `-X` keeps a developer's .psqlrc banners out of parsed output.
    assert "-X" in captured["args"]


@pytest.mark.parametrize("check_only", [False, True])
def test_main_preserves_seed_and_check_contract_with_quoted_values(monkeypatch, check_only):
    """Follow the real main -> composer -> psql adapter path with transport stubbed."""
    seeder = _load_seeder()
    for name in list(os.environ):
        if name.startswith(("DB_", "COGNITO_", "AWS_")):
            monkeypatch.delenv(name)
    cfg = {
        "DB_HOST": "database.example",
        "DB_NAME": "test_database",
        "DB_USER": "test_user",
        "DB_PASSWORD": "synthetic-test-password",
        "COGNITO_POOL_ID": "synthetic-pool",
        "COGNITO_REGION": "us-east-1",
    }
    subject, customer = ("subject'quoted", "CUST-O'REILLY")
    monkeypatch.setattr(seeder, "_load_env", lambda _path: cfg)
    monkeypatch.setattr(seeder, "_username_to_customer", lambda: {"marco": customer})
    resolutions = []

    def resolve(**kwargs):
        resolutions.append(kwargs)
        return {"marco": subject}, []

    monkeypatch.setattr(seeder, "resolve_subs", resolve)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        # --check must still compare the table with the resolved current subject.
        output = f"{customer}|{subject}\n" if check_only and len(calls) == 1 else ""
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr("subprocess.run", run)

    assert seeder.main(["--check"] if check_only else []) == 0
    assert resolutions == [{
        "region": "us-east-1", "pool_id": "synthetic-pool", "usernames": ["marco"],
    }]
    assert len(calls) == (1 if check_only else 2)
    assert calls[0][0][-2] == "-c"
    assert calls[0][0][-1].startswith("SELECT customer_id")
    if not check_only:
        command, options = calls[1]
        assert command[-2:] == [
            "-c",
            "BEGIN;\n"
            "INSERT INTO pellier.principal_customers (principal_sub, customer_id)\n"
            " VALUES ('subject''quoted', 'CUST-O''REILLY')\n"
            " ON CONFLICT (principal_sub, customer_id) DO NOTHING;\n"
            "COMMIT;",
        ]
        assert options.get("shell", False) is False
        assert "-X" in command
        assert "ON_ERROR_STOP=1" in command
    for command, options in calls:
        assert cfg["DB_PASSWORD"] not in " ".join(command)
        assert options["env"]["PGPASSWORD"] == cfg["DB_PASSWORD"]
