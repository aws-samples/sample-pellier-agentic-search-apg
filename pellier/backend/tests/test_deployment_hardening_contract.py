"""Deployment-hardening contract for the participant box.

Each assertion here corresponds to a defect that shipped, reached a real
provisioning path, and was not caught by any existing gate:

* the workspace kept a live ``.git`` on the Workshop Studio path, so
  ``git checkout -- .``, ``git stash``, and ``git reset --hard`` could silently
  destroy the exercise a participant was midway through. ``"git.enabled": false``
  hides the Source Control panel; it does nothing to the terminal.
* the Claude Code CLI installed unpinned, re-introducing CLI-behaviour drift on
  a date nobody chose - the same class of failure that made the floating
  ``sonnet`` alias resolve to a model Workshop Studio accounts cannot reach.
* ``CLAUDE_CODE_MODEL`` was set in a sibling workshop. Claude Code does not read
  it, so it advertised control that did not exist.
* editor appearance drifted between the two branches (one lacked
  ``window.zoomLevel`` entirely), so the same room saw two different Code
  Editors.

These are cheap text contracts on purpose: the failures are all "the
provisioning script does not say the thing", which is exactly what a text
contract catches and a unit test of application code never would.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ENVIRONMENT_BOOTSTRAP = REPO / "scripts" / "bootstrap-environment.sh"
LABS_BOOTSTRAP = REPO / "scripts" / "bootstrap-labs.sh"

# Chosen for the release contract and tested against Bedrock mode, the explicit
# Sonnet 5 profile id, a no-auth-prompt start, and the sibling workshop's
# preflight flag set. Bump only as a deliberate release action.
PINNED_CLAUDE_CODE_VERSION = "2.1.233"
EXPLICIT_SONNET_PROFILE = "global.anthropic.claude-sonnet-5"


@pytest.fixture(scope="module")
def labs() -> str:
    return LABS_BOOTSTRAP.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def environment() -> str:
    return ENVIRONMENT_BOOTSTRAP.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The participant workspace must not be a git repository
# ---------------------------------------------------------------------------


def test_git_is_removed_outside_the_fallback_clone_branch(labs: str) -> None:
    """Removal must not live only inside ``if [ ! -d "$REPO_PATH" ]``.

    On a Workshop Studio box CloudFormation UserData has already cloned the
    repo, so that branch never runs. The original code removed ``.git`` only
    there, which left a live checkout in the participant's terminal on every
    real event box.

    The invariant is placement, not count: at least one removal must sit after
    the fallback branch closes, so it runs on both provisioning paths. Whether a
    branch also removes it inside the fallback is an implementation detail -
    ``main`` does, ``governed`` lets the unconditional block cover both.
    """
    guard = 'if [ -d "$REPO_PATH/.git" ]; then'
    assert guard in labs, "no unconditional .git presence check"
    removal = 'rm -rf "$REPO_PATH/.git"'
    assert removal in labs[labs.index(guard) :], (
        "the unconditional block does not remove .git, so the event path keeps "
        "a live repository"
    )


def test_git_removal_is_guarded_by_an_unconditional_presence_check(labs: str) -> None:
    """The event-path removal runs whenever .git exists, not per clone branch."""
    assert 'if [ -d "$REPO_PATH/.git" ]; then' in labs


def test_provenance_is_recorded_before_git_is_destroyed(labs: str) -> None:
    """"Which content is this box running?" must survive losing .git."""
    assert ".workshop-ref.json" in labs
    guard = labs.index('if [ -d "$REPO_PATH/.git" ]; then')
    tail = labs[guard:]
    ref_at = tail.index(".workshop-ref.json")
    rm_at = tail.index('rm -rf "$REPO_PATH/.git"')
    assert ref_at < rm_at, "provenance must be written before .git is removed"


def test_workspace_detachment_is_logged(labs: str) -> None:
    """A silent destructive step is indistinguishable from a skipped one."""
    assert "Workspace detached from git" in labs


# ---------------------------------------------------------------------------
# Claude Code CLI
# ---------------------------------------------------------------------------


def test_claude_code_cli_version_is_pinned(environment: str) -> None:
    assert (
        f'CLAUDE_CODE_VERSION="${{CLAUDE_CODE_VERSION:-{PINNED_CLAUDE_CODE_VERSION}}}"'
        in environment
    )


def test_claude_code_install_uses_the_pin(environment: str) -> None:
    """An unpinned `npm install -g` would silently float past the pin."""
    assert 'npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"' in environment
    assert not re.search(
        r"npm install -g @anthropic-ai/claude-code(?!@)", environment
    ), "an unpinned Claude Code install remains"


def test_no_phantom_claude_code_model_variable(environment: str, labs: str) -> None:
    """`CLAUDE_CODE_MODEL` is not read by Claude Code; `ANTHROPIC_MODEL` is."""
    for name, text in (("bootstrap-environment.sh", environment), ("bootstrap-labs.sh", labs)):
        assert "CLAUDE_CODE_MODEL" not in text, f"{name} sets CLAUDE_CODE_MODEL"


def test_explicit_model_profile_not_a_floating_alias(labs: str) -> None:
    """On Bedrock the bare `sonnet` alias resolves to a different Sonnet."""
    assert f"ANTHROPIC_MODEL=${{ANTHROPIC_MODEL:-{EXPLICIT_SONNET_PROFILE}}}" in labs
    assert "ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-sonnet}" not in labs
    assert "CLAUDE_CODE_USE_BEDROCK=1" in labs


# ---------------------------------------------------------------------------
# Code Editor appearance, shared across both Pellier formats and Mosaic
# ---------------------------------------------------------------------------

APPEARANCE = {
    "editor.fontSize": 16,
    "terminal.integrated.fontSize": 18,
    "window.zoomLevel": 1,
}


def _settings_blocks(text: str) -> list[dict]:
    """Every JSON heredoc in the bootstrap that looks like editor settings."""
    blocks: list[dict] = []
    for match in re.finditer(r"<<\s*'([A-Z_]+)'\n(.*?)\n\1\n", text, re.S):
        body = match.group(2)
        if not body.lstrip().startswith("{"):
            continue
        without_comments = re.sub(r"^\s*//.*$", "", body, flags=re.M)
        try:
            parsed = json.loads(without_comments)
        except json.JSONDecodeError:
            continue
        if "editor.fontSize" in parsed or "workbench.colorTheme" in parsed:
            blocks.append(parsed)
    return blocks


def test_settings_heredocs_are_valid_json(environment: str) -> None:
    assert _settings_blocks(environment), "no editor settings block found"


@pytest.mark.parametrize(("key", "value"), sorted(APPEARANCE.items()))
def test_user_settings_use_the_room_tested_appearance(
    environment: str, key: str, value: int
) -> None:
    """The user-level block is what a participant actually sees."""
    user_block = _settings_blocks(environment)[0]
    assert user_block.get(key) == value, f"{key} is {user_block.get(key)!r}, expected {value!r}"


def test_terminal_foreground_is_forced_high_contrast(environment: str) -> None:
    """Same value the sibling workshop already ships on this AMI."""
    user_block = _settings_blocks(environment)[0]
    customizations = user_block.get("workbench.colorCustomizations", {})
    assert customizations.get("terminal.foreground") == "#FFFFFF"


def test_source_control_ui_stays_hidden(environment: str) -> None:
    """Defence in depth beside the .git removal, not a substitute for it."""
    user_block = _settings_blocks(environment)[0]
    assert user_block.get("git.enabled") is False
