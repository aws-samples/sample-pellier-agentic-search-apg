#!/usr/bin/env python3
"""Turn Code Editor's terminal tabs back off after "Show Tabs" turns them on.

The workshop picks terminals from a drop-down, not a tab list (see bootstrap-environment.sh):
hovering the workshop terminal's tab covers its name with Rerun Task, and rerunning it stopped a
running deploy. The drop-down's last entry, "Show Tabs", deletes the setting from the user
settings file and turns the tab list on for the rest of the event. A systemd path unit runs
this script whenever that file changes; it puts the setting back, and Code Editor reloads the
file, so a mis-pick flips straight back to the drop-down.

usage: keep_terminal_tabs_off.py SETTINGS_JSON
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

KEY = "terminal.integrated.tabs.enabled"


def keep_off(path: Path) -> bool:
    """Set the tabs setting to false in a user settings file.

    Args:
        path: Code Editor's user settings.json.

    Returns:
        True when the file was rewritten; False when it already held false, is missing, or is
        not plain JSON (a hand-edited file with comments is left alone).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    try:
        settings = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"{path}: not plain JSON ({exc}); left unchanged", file=sys.stderr)
        return False
    if not isinstance(settings, dict) or settings.get(KEY) is False:
        return False
    settings[KEY] = False
    mode = path.stat().st_mode & 0o777
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".json")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(json.dumps(settings, indent=4) + "\n")
    os.chmod(temporary, mode)
    os.replace(temporary, path)
    return True


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    if keep_off(Path(argv[1])):
        print(f"{KEY} set back to false in {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
