"""Model IDs must agree across config, the example env file, and the preflight.

`.env.example` is what a local participant copies to `.env`, and environment
variables override the `Settings` defaults. So a value that drifts in that file
does not merely document the wrong model -- it *selects* the wrong model, and it
does so past the model-access preflight, which probes the ladder named in
`config.py`. The failure that motivated this test looked like every model
reachable, green, while the runtime invoked identifiers nobody had validated.

The exact model ladder is a release decision. These tests assert that the
runtime defaults, example environment, preflight, CLI, and frontend catalogue
agree, so a model refresh cannot bypass the account's access checks.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
ENV_EXAMPLE = BACKEND / ".env.example"
CONFIG = BACKEND / "config.py"
PREFLIGHT = REPO / "scripts" / "check_model_access.py"

# Every model setting a participant can override from .env. BEDROCK_FAST_MODEL
# is included because the preflight treats it as hard-required and it backs a
# participant-facing control; it was absent from .env.example entirely.
MODEL_SETTINGS = (
    "BEDROCK_OPUS_MODEL",
    "BEDROCK_SONNET_MODEL",
    "BEDROCK_ROUTER_MODEL",
    "BEDROCK_REPORTING_MODEL",
    "BEDROCK_FAST_MODEL",
    "BEDROCK_CHAT_MODEL",
)


def _config_defaults() -> dict[str, str]:
    text = CONFIG.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for name in MODEL_SETTINGS:
        match = re.search(rf'^\s*{name}:\s*str\s*=\s*"([^"]+)"', text, re.M)
        if match:
            found[name] = match.group(1)
    return found


def _env_example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() in MODEL_SETTINGS:
            values[key.strip()] = value.strip()
    return values


def test_config_declares_every_model_setting() -> None:
    defaults = _config_defaults()
    missing = [name for name in MODEL_SETTINGS if name not in defaults]
    assert not missing, (
        f"config.py no longer declares {missing}. Either the setting was renamed "
        "(update MODEL_SETTINGS here) or it was dropped and .env.example still "
        "offers it."
    )


def test_env_example_offers_every_model_setting() -> None:
    values = _env_example_values()
    missing = [name for name in MODEL_SETTINGS if name not in values]
    assert not missing, (
        f".env.example does not set {missing}. A participant copying this file "
        "gets the config default for those, which is fine -- but the preflight "
        "and the reference tables describe a complete ladder, so an omitted "
        "setting reads as 'this model is not used'."
    )


def test_env_example_matches_config_defaults() -> None:
    defaults = _config_defaults()
    values = _env_example_values()
    disagreements = {
        name: (defaults[name], values[name])
        for name in MODEL_SETTINGS
        if name in defaults and name in values and defaults[name] != values[name]
    }
    assert not disagreements, (
        "config.py and .env.example name different models: "
        + "; ".join(
            f"{name}: config={config_value!r} env={env_value!r}"
            for name, (config_value, env_value) in sorted(disagreements.items())
        )
        + ". Environment wins at runtime, so .env.example is the file that "
        "decides. Move config, example environment, and preflight together."
    )


def test_preflight_probes_the_models_config_actually_resolves() -> None:
    """The preflight must probe the pinned ladder, not a list of its own.

    A preflight that validates models the runtime never calls reports green and
    proves nothing.
    """
    defaults = _config_defaults()
    preflight = PREFLIGHT.read_text(encoding="utf-8")
    # Probe both ends of the editorial ladder and the required fast profile.
    for name in ("BEDROCK_OPUS_MODEL", "BEDROCK_SONNET_MODEL", "BEDROCK_FAST_MODEL"):
        model_id = defaults.get(name)
        assert model_id, f"config.py does not declare {name}"
        assert model_id in preflight, (
            f"{PREFLIGHT.name} never probes {model_id}, which config.py resolves "
            f"for {name}. The preflight can report the account ready for models "
            "the runtime does not use, while the model it does use was never "
            "checked."
        )


def test_claude_profiles_are_global_and_visible_in_the_frontend() -> None:
    defaults = _config_defaults()
    catalogue = (REPO / "pellier/frontend/src/observatory/constants/bedrockModels.ts").read_text()
    for setting, model_id in defaults.items():
        assert model_id.startswith("global.anthropic."), setting
        assert model_id in catalogue, f"Frontend catalogue is missing {setting}: {model_id}"


def test_cli_bootstrap_and_rehearsal_match_the_preflight_profile() -> None:
    model_id = _config_defaults()["BEDROCK_SONNET_MODEL"]
    pin = "${ANTHROPIC_MODEL:-" + model_id + "}"
    for relative in ("scripts/bootstrap-labs.sh", "scripts/dry-run-builders.sh"):
        assert pin in (REPO / relative).read_text(), relative
