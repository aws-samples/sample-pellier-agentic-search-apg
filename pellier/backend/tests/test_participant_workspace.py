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



def test_each_lab_lists_its_exercise_files_before_its_solution_folder():
    """Folders sort first by default, which put solution/ above 1A and 1B."""
    settings = json.loads((ROOT / "Pellier.code-workspace").read_text())["settings"]
    assert settings["explorer.sortOrder"] == "filesFirst"


def test_task_3a_files_sort_in_the_order_the_guide_edits_them():
    """Task 3A has two files and Task 3B one; the Explorer sorts by name, so the
    numbers keep "publish the tool" above "bind the caller", as the guide edits them."""
    lab3 = [e for e in json.loads((ROOT / "workshop/participant-files.json").read_text())
            if e["alias"].startswith("labs/03-deploy/")]
    names = sorted(Path(e["alias"]).name for e in lab3)
    assert names == ["3A-1-publish-tool.py", "3A-2-bind-caller.py", "3B-row-ownership.sql"]
    by_name = {Path(e["alias"]).name: e["source"] for e in lab3}
    assert by_name["3A-1-publish-tool.py"] == "scripts/deploy/gateway_tool_schemas.py"
    assert by_name["3A-2-bind-caller.py"] == "pellier/backend/services/agentcore_gateway.py"

def test_lab_1s_go_deeper_worksheet_sorts_after_its_tasks():
    """The Explorer's collator puts a leading "1-" before "1A", so the optional file
    carries no task number and sorts after 1A and 1B."""
    lab1 = [e for e in json.loads((ROOT / "workshop/participant-files.json").read_text())
            if e["alias"].startswith("labs/01-retrieve/")]
    assert [Path(e["alias"]).name for e in lab1] == [
        "1A-vector-branch.py", "1B-search-plan.py", "go-deeper-fusion.sql"]
    assert [bool(e.get("optional")) for e in lab1] == [False, False, True]

def test_deployment_bookkeeping_stays_out_of_the_explorer():
    """Provisioning writes these beside the source; scripts read them, participants do not."""
    excludes = json.loads((ROOT / "Pellier.code-workspace").read_text())["settings"]["files.exclude"]
    for name in ("**/.provision.env", ".workshop-ref.json", "package.zip"):
        assert excludes.get(name) is True, f"{name} should be hidden from the Explorer"

def test_editing_numbered_file_edits_the_live_source_and_rerun_preserves_it(repo):
    workspace.configure(repo)
    alias = repo / "labs/01-retrieve/1A-vector-branch.py"
    alias.write_text("participant's edit")
    workspace.configure(repo)
    assert (repo / "pellier/backend/services/store_tools.py").read_text() == "participant's edit"
    settings = json.loads((repo / ".vscode/settings.json").read_text())
    assert settings["terminal.integrated.cwd"] == "${workspaceFolder}"
    # Solution aliases link to the answers recovery copies; the editor must not change them.
    assert settings["files.readonlyInclude"] == {"labs/*/solution/**": True, "solution/**": True}
    tasks = json.loads((repo / ".vscode/tasks.json").read_text())["tasks"]
    assert len(tasks) == 1 and tasks[0]["options"]["cwd"] == "${workspaceFolder}"


def test_zip_materialized_link_is_repaired_but_an_edited_file_is_not_overwritten(repo):
    alias = repo / "labs/01-retrieve/go-deeper-fusion.sql"
    alias.parent.mkdir(parents=True)
    alias.write_text(os.path.relpath(repo / "workshop/lab-1-fusion.sql", alias.parent))
    workspace.configure(repo)
    assert alias.is_symlink()
    alias.unlink()
    alias.write_text("do not lose my work")
    with pytest.raises(ValueError, match="Preserving existing participant file"):
        workspace.configure(repo)
    assert alias.read_text() == "do not lose my work"


def test_a_reload_reconnects_the_one_workshop_terminal_instead_of_opening_another(repo):
    """Seen on event 20: the task had no problem matcher, which Code Editor needs to reconnect
    a task, so every reload opened another terminal and left 22 shells, and whatever ran in
    them, out of sight."""
    workspace.configure(repo)
    [task] = json.loads((repo / ".vscode/tasks.json").read_text())["tasks"]
    assert task["runOptions"] == {"runOn": "folderOpen", "instanceLimit": 1}
    assert task["isBackground"] is True
    matcher = task["problemMatcher"]
    assert set(matcher["background"]) == {"activesBegin", "beginsPattern", "endsPattern"}
    assert task["command"] == "bash" and "args" not in task
    assert task["options"]["env"] == {"PELLIER_WORKSHOP_TERMINAL": "1"}


def test_the_welcome_prints_and_opens_nothing_in_the_editor(tmp_path):
    """The old launcher also opened a start page through the editor's CLI, which could take
    focus from the terminal, or open late in a second terminal when the CLI was not ready."""
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "code").write_text(f'#!/bin/sh\ntouch "{tmp_path}/code-called"\n')
    (binary / "code").chmod(0o755)
    env = {**os.environ, "PATH": f"{binary}:{os.environ['PATH']}"}
    shown = subprocess.run(["bash", str(ROOT / "scripts/workshop-banner.sh")], cwd=tmp_path,
                           env=env, capture_output=True, text=True, check=True).stdout
    assert shown.startswith("Pellier: Retrieve → Ground → Deploy → Govern")
    assert "This terminal starts at the repository root." in shown
    assert not (tmp_path / "code-called").exists()


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
