#!/usr/bin/env python3
"""Validate participant file links and install Code Editor defaults.

Run after source extraction and before the editor starts. A ZIP extractor may
materialize a Git symlink as its target-path text; repair only that exact form.
Never replace a participant's edited regular file with a link.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def configure(repo: Path) -> None:
    repo = repo.resolve()
    entries = json.loads((repo / "workshop/participant-files.json").read_text())
    links = []
    for item in entries:
        alias = Path(item["alias"])
        links.extend(((alias, item["source"]),
                      (alias.parent / "solution" / alias.name, item["solution"])))
    # Validate everything before changing anything.
    for relative, source in links:
        link, target = repo / relative, repo / source
        if not target.is_file() or not target.resolve().is_relative_to(repo):
            raise ValueError(f"Missing or external participant target: {source}")
        expected = os.path.relpath(target, link.parent)
        if link.is_symlink():
            if link.resolve() != target.resolve():
                raise ValueError(f"Unexpected participant link: {relative}")
        elif link.exists() and link.read_text() != expected:
            raise ValueError(f"Preserving existing participant file: {relative}")
    for relative, source in links:
        link = repo / relative
        if not link.is_symlink():
            link.parent.mkdir(parents=True, exist_ok=True)
            link.unlink(missing_ok=True)
            link.symlink_to(os.path.relpath(repo / source, link.parent))

    workspace = json.loads((repo / "Pellier.code-workspace").read_text())
    for folder in workspace["folders"]:
        if not (repo / folder["path"]).is_dir():
            raise ValueError(f"Workspace folder missing: {folder['path']}")
    vscode = repo / ".vscode"
    vscode.mkdir(exist_ok=True)
    settings = dict(workspace["settings"])
    settings["terminal.integrated.cwd"] = "${workspaceFolder}"
    path = vscode / "settings.json"
    # Bootstrap-owned defaults; retain unrelated preferences across reruns.
    existing = json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps({**existing, **settings}, indent=2) + "\n")
    tasks = {
        "version": "2.0.0",
        "tasks": [{
            "label": "Pellier workshop terminal", "type": "shell", "command": "bash",
            "args": ["-l", "${workspaceFolder}/scripts/open-workshop-terminal.sh"],
            "options": {"cwd": "${workspaceFolder}"},
            "runOptions": {"runOn": "folderOpen"}, "isBackground": True,
            "presentation": {"echo": False, "reveal": "always", "focus": True,
                             "panel": "dedicated", "showReuseMessage": False},
            "problemMatcher": [],
        }],
    }
    (vscode / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    configure(parser.parse_args().repo)
    print("Pellier workspace ready: four labs, linked exercise files, "
          "solution paths and root terminal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
