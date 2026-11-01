"""keep_terminal_tabs_off.py: a mis-picked "Show Tabs" flips straight back to the drop-down."""
from __future__ import annotations

import importlib
import json
import os
import stat
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
keep = importlib.import_module("keep_terminal_tabs_off")


def _write(path: Path, settings: dict) -> None:
    path.write_text(json.dumps(settings, indent=4) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def test_show_tabs_deleting_the_setting_puts_it_back_and_keeps_the_rest(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    _write(path, {"window.zoomLevel": 1, "task.reconnection": True})

    assert keep.keep_off(path) is True

    settings = json.loads(path.read_text(encoding="utf-8"))
    assert settings == {"window.zoomLevel": 1, "task.reconnection": True, keep.KEY: False}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_tabs_set_to_true_are_turned_off(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    _write(path, {keep.KEY: True})

    assert keep.keep_off(path) is True
    assert json.loads(path.read_text(encoding="utf-8"))[keep.KEY] is False


def test_a_file_already_off_is_not_rewritten(tmp_path: Path) -> None:
    """Its own write fires the path unit again; that run must change nothing, or it loops."""
    path = tmp_path / "settings.json"
    _write(path, {keep.KEY: False})
    before = path.stat()

    assert keep.keep_off(path) is False
    after = path.stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


def test_a_file_with_comments_or_none_at_all_is_left_alone(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{\n    // a hand-written note\n    "window.zoomLevel": 1\n}\n', encoding="utf-8")
    text = path.read_text(encoding="utf-8")

    assert keep.keep_off(path) is False
    assert path.read_text(encoding="utf-8") == text
    assert keep.keep_off(tmp_path / "missing.json") is False
    assert list(tmp_path.glob(".settings-*")) == []


def test_main_needs_the_settings_path(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    _write(path, {})

    assert keep.main(["keep_terminal_tabs_off.py"]) == 2
    assert keep.main(["keep_terminal_tabs_off.py", str(path)]) == 0
    assert json.loads(path.read_text(encoding="utf-8"))[keep.KEY] is False
