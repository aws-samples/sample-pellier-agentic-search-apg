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

# The CLI lane runs on this explicit profile, and Claude Code on a pinned release no older
# than the first one that runs Sonnet 5.5.
EXPLICIT_SONNET_PROFILE = "global.anthropic.claude-sonnet-5-5"
SONNET_5_5_FIRST_CLAUDE_CODE = (2, 1, 280)


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
    removal = 'mv "$REPO_PATH/.git" "$LAB_SOURCE_GIT"'
    assert removal in labs[labs.index(guard) :], (
        "the unconditional block does not move .git out, so the event path keeps "
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
    rm_at = tail.index('mv "$REPO_PATH/.git" "$LAB_SOURCE_GIT"')
    assert ref_at < rm_at, "provenance must be written before .git leaves the workspace"


def test_workspace_detachment_is_logged(labs: str) -> None:
    """A silent destructive step is indistinguishable from a skipped one."""
    assert "Workspace detached from git" in labs


# ---------------------------------------------------------------------------
# Claude Code CLI
# ---------------------------------------------------------------------------


def _pin(text: str, name: str) -> str:
    match = re.search(rf'^{name}="([^"]+)"$', text, re.MULTILINE)
    assert match, f'{name}="..." is missing from bootstrap-environment.sh'
    return match.group(1)


def _stable_release(version: str) -> tuple[int, ...]:
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"{version} is not a stable release"
    return tuple(int(part) for part in version.split("."))


def test_claude_code_installs_its_pinned_release(environment: str) -> None:
    """Unpinned, the CLI changed on a date nobody chose; pinned too old, it refused
    the model (Claude Code 2.1.233 does not run Sonnet 5.5)."""
    version = _stable_release(_pin(environment, "CLAUDE_CODE_VERSION"))
    assert version >= SONNET_5_5_FIRST_CLAUDE_CODE
    assert 'npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"' in environment
    assert not re.search(r"@anthropic-ai/claude-code@(?!\$\{CLAUDE_CODE_VERSION\})", environment)


def test_typescript_installs_its_pinned_release(environment: str) -> None:
    """The AgentCore CLI's deploy build runs tsc; `typescript@5` moved with each 5.x."""
    _stable_release(_pin(environment, "TYPESCRIPT_VERSION"))
    assert 'npm install -g "typescript@${TYPESCRIPT_VERSION}"' in environment
    assert not re.search(r"typescript@(?!\$\{TYPESCRIPT_VERSION\})", environment)


def test_node_installs_its_pinned_build_and_logs_a_fallback(environment: str) -> None:
    """`dnf install nodejs` took whatever NodeSource published last. The pinned build
    installs first; the newest 24.x only keeps an event running, and the log says so."""
    assert _stable_release(_pin(environment, "NODE_RPM_VERSION"))[0] == 24
    assert _pin(environment, "NODE_RPM") == "nodejs-2:${NODE_RPM_VERSION}-1nodesource"
    assert re.fullmatch(r"[0-9a-f]{64}", _pin(environment, "NODESOURCE_SETUP_SHA256"))
    assert 'dnf install -y -q --allowerasing "$NODE_RPM"' in environment
    assert "setup_24.x | bash" not in environment, "the setup script runs unchecked"
    assert "not the pinned v${NODE_RPM_VERSION}" in environment


def test_ci_runs_the_node_release_the_box_runs(environment: str) -> None:
    """`node-version: "24"` took each new 24.x in CI before any event ran it."""
    pinned = _pin(environment, "NODE_RPM_VERSION")
    found = [
        (path.name, value)
        for path in sorted((REPO / ".github" / "workflows").glob("*.yml"))
        for value in re.findall(r"node-version:\s*\"?([^\"\s]+)", path.read_text("utf-8"))
    ]
    assert found, "no workflow sets up Node"
    assert all(value == pinned for _, value in found), f"expected {pinned}: {found}"


def test_ci_runs_on_a_pinned_runner_image() -> None:
    """`runs-on: ubuntu-latest` moved to Ubuntu 26.04 on 2026-11-05, where the pinned Playwright
    has no Chromium build, so the browser job failed on a change that touched no browser code."""
    found = [
        (path.name, value)
        for path in sorted((REPO / ".github" / "workflows").glob("*.yml"))
        for value in re.findall(r"runs-on:\s*(\S+)", path.read_text("utf-8"))
    ]
    assert found, "no workflow names a runner"
    assert all(value == "ubuntu-24.04" for _, value in found), f"expected ubuntu-24.04: {found}"


def test_ci_runs_each_pipx_tool_at_an_exact_release() -> None:
    """`pipx run cfn-lint` took each new cfn-lint, so a new rule could fail CI unasked."""
    runs = [
        (path.name, match.group(1))
        for path in sorted((REPO / ".github" / "workflows").glob("*.yml"))
        for match in re.finditer(r"pipx run (?:--spec )?(\S+)", path.read_text("utf-8"))
    ]
    assert runs, "no workflow runs a pipx tool"
    loose = [run for run in runs if not re.fullmatch(r"[\w.-]+==\d+\.\d+\.\d+", run[1])]
    assert not loose, f"pin each tool exactly: {loose}"


def test_the_cli_link_points_at_npms_binary_not_at_itself(environment: str) -> None:
    """`command -v claude` can answer /usr/bin/claude, the link, and loop it onto itself."""
    assert '_claude_bin="$(npm prefix -g 2>/dev/null)/bin/claude"' in environment
    assert '_claude_bin="$(command -v claude' not in environment


def test_global_npm_installs_are_readable_by_the_participant(
    environment: str, labs: str
) -> None:
    """The worker runs under umask 077; a bare `npm install -g` there leaves
    /usr/lib/node_modules/<pkg> root-only, and the participant cannot run the CLI
    (found on a live event: `claude` absent from the coaching track)."""
    for name, text in (("bootstrap-environment.sh", environment), ("bootstrap-labs.sh", labs)):
        for line in text.splitlines():
            code = line.split("#", 1)[0]
            if "npm install -g" not in code or "Recover:" in code or "warn " in code:
                continue
            assert "umask 022" in code, f"{name}: global install without umask 022: {line.strip()}"


def test_claude_code_is_checked_as_the_participant(environment: str) -> None:
    assert 'runuser -u "$CODE_EDITOR_USER" -- claude --version' in environment


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


def _user_settings_block(text: str) -> dict:
    """The user-level settings heredoc, found by its tag rather than its position."""
    match = re.search(r"<<\s*'VSCODE_SETTINGS'\n(.*?)\nVSCODE_SETTINGS\n", text, re.S)
    assert match, "user settings heredoc not found"
    return json.loads(re.sub(r"^\s*//.*$", "", match.group(1), flags=re.M))


def test_settings_heredocs_are_valid_json(environment: str) -> None:
    assert _settings_blocks(environment), "no editor settings block found"


@pytest.mark.parametrize(("key", "value"), sorted(APPEARANCE.items()))
def test_user_settings_use_the_room_tested_appearance(
    environment: str, key: str, value: int
) -> None:
    """The user-level block is what a participant actually sees."""
    user_block = _user_settings_block(environment)
    assert user_block.get(key) == value, f"{key} is {user_block.get(key)!r}, expected {value!r}"


def test_terminal_foreground_is_forced_high_contrast(environment: str) -> None:
    """Same value the sibling workshop already ships on this AMI.

    Scoped to the default dark theme. Unscoped, it also applies after a
    participant picks a light theme, where the terminal's minimum contrast
    ratio turns it into pale grey instead of the theme's own dark text.
    """
    user_block = _user_settings_block(environment)
    customizations = user_block.get("workbench.colorCustomizations", {})
    assert customizations.get("[Default Dark Modern]", {}).get("terminal.foreground") == "#FFFFFF"
    assert "terminal.foreground" not in customizations


def test_source_control_ui_stays_hidden(environment: str) -> None:
    """Defence in depth beside the .git removal, not a substitute for it."""
    user_block = _user_settings_block(environment)
    assert user_block.get("git.enabled") is False
