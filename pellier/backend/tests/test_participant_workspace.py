"""Participant navigation opens live files and survives source ZIP extraction."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "participant_workspace", ROOT / "scripts/configure_participant_workspace.py"
)
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repository with spaces"
    (root / "workshop").mkdir(parents=True)
    for name in ["Pellier.code-workspace", "workshop/participant-files.json"]:
        (root / name).write_bytes((ROOT / name).read_bytes())
    for item in json.loads((root / "workshop/participant-files.json").read_text()):
        for name in ("source", "solution"):
            p = root / item[name]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("fixture " + name)
    return root


def test_numbered_groups_and_every_link_reach_existing_repository_files():
    config = json.loads((ROOT / "Pellier.code-workspace").read_text())
    assert [f["name"] for f in config["folders"]] == [
        "01 - Retrieve", "02 - Ground", "03 - Deploy", "04 - Govern", "05 - Explore Pellier source"]
    for folder in config["folders"][:4]:
        assert (ROOT / folder["path"] / "README.md").is_file()
        assert (ROOT / folder["path"] / "solution/README.md").is_file()
    for item in json.loads((ROOT / "workshop/participant-files.json").read_text()):
        alias = ROOT / item["alias"]
        assert alias.samefile(ROOT / item["source"])
        assert (alias.parent / "solution" / alias.name).samefile(ROOT / item["solution"])


def test_editing_numbered_file_edits_the_live_source_and_rerun_preserves_it(repo):
    workspace.configure(repo)
    alias = repo / "labs/01-retrieve/1A-rrf.sql"
    alias.write_text("participant's edit")
    workspace.configure(repo)
    assert (repo / "workshop/lab-1-rrf.sql").read_text() == "participant's edit"
    settings = json.loads((repo / ".vscode/settings.json").read_text())
    assert settings["terminal.integrated.cwd"] == "${workspaceFolder}"
    # Solution aliases link to the answers recovery copies; the editor must not change them.
    assert settings["files.readonlyInclude"] == {"labs/*/solution/**": True, "solution/**": True}
    tasks = json.loads((repo / ".vscode/tasks.json").read_text())["tasks"]
    assert len(tasks) == 1 and tasks[0]["options"]["cwd"] == "${workspaceFolder}"


def test_zip_materialized_link_is_repaired_but_an_edited_file_is_not_overwritten(repo):
    alias = repo / "labs/01-retrieve/1A-rrf.sql"
    alias.parent.mkdir(parents=True)
    alias.write_text(os.path.relpath(repo / "workshop/lab-1-rrf.sql", alias.parent))
    workspace.configure(repo)
    assert alias.is_symlink()
    alias.unlink()
    alias.write_text("do not lose my work")
    with pytest.raises(ValueError, match="Preserving existing participant file"):
        workspace.configure(repo)
    assert alias.read_text() == "do not lose my work"


@pytest.mark.parametrize("first_exit", ["0", "1"])
def test_terminal_starts_at_root_and_retries_the_start_page(repo, first_exit):
    scripts = repo / "scripts"
    scripts.mkdir(exist_ok=True)
    launcher = scripts / "open-workshop-terminal.sh"
    launcher.write_bytes((ROOT / "scripts/open-workshop-terminal.sh").read_bytes())
    binary = repo / "bin"
    binary.mkdir()
    (binary / "code").write_text(
        '#!/bin/sh\nprintf "%s\\n" "$PWD" "$@" >> "$PROBE_CODE"\nexit "$PROBE_EXIT"\n'
    )
    (binary / "bash").write_text('#!/bin/sh\nprintf "%s\\n" "$PWD" "$@" > "$PROBE_SHELL"\n')
    for file in binary.iterdir():
        file.chmod(0o755)
    env = {**os.environ, "PATH": str(binary) + ":" + os.environ["PATH"],
           "PROBE_CODE": str(repo / "code.log"), "PROBE_SHELL": str(repo / "shell.log"),
           "PROBE_EXIT": first_exit}
    for attempt in range(2):
        subprocess.run(["/bin/bash", str(launcher)], cwd=repo / "workshop", env=env,
                       check=True, capture_output=True)
        assert (repo / "shell.log").read_text().splitlines() == [str(repo), "-l"]
        started = (repo / ".local/code-editor-started").exists()
        assert started == (attempt == 1 or first_exit == "0")
        env["PROBE_EXIT"] = "0"


def test_bootstrap_opens_workspace_and_revalidates_after_source_extraction():
    env = (ROOT / "scripts/bootstrap-environment.sh").read_text()
    assert '--default-workspace $HOME_FOLDER/$REPO_NAME/Pellier.code-workspace' in env
    configure = env.index("scripts/configure_participant_workspace.py")
    assert configure < env.index("ExecStart=$CODE_EDITOR_CMD")
    assert env.count("scripts/configure_participant_workspace.py") == 1
    # Folder settings land first so the configurator merges into them, not under them.
    assert env.index("<< 'WORKSPACE_SETTINGS'") < configure
    # The configurator owns the only terminal task; no heredoc may overwrite it.
    assert "tasks.json" not in env.replace("configure_participant_workspace.py", "")
    assert "configure_participant_workspace.py" in (ROOT / "scripts/bootstrap-labs.sh").read_text()
