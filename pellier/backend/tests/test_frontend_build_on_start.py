"""The pellier unit builds the frontend before a start only when the bundle is not current.

A Vite build takes about 13 s and no lab edits the frontend, so a restart for a lab edit must not
wait for one. A bundle that is missing, built for another base path, rebuilt by another command,
or older than any file the build reads is built again.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "build-frontend-if-changed.sh"
BOOTSTRAP = REPO / "scripts" / "bootstrap-labs.sh"
BASE = "/ports/8000/"
FAKE_NPM = """#!/bin/bash
echo "$*" >> "$NPM_LOG"
[ -n "${NPM_FAIL:-}" ] && exit 3
mkdir -p dist && echo built > dist/index.html
"""


class Frontend:
    """A frontend folder whose npm records each build instead of running Vite."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "frontend"
        (self.root / "src").mkdir(parents=True)
        (self.root / "src" / "main.tsx").write_text("app\n")
        (self.root / "package.json").write_text("{}\n")
        (self.root / "node_modules").mkdir()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        (self.bin / "npm").write_text(FAKE_NPM)
        (self.bin / "npm").chmod(0o755)
        self.log = tmp_path / "npm.log"

    def start(self, base: str = BASE,
              fail: bool = False) -> tuple[subprocess.CompletedProcess, int]:
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
               "NPM_LOG": str(self.log), "VITE_BASE_PATH": base}
        env.pop("NPM_FAIL", None)
        if fail:
            env["NPM_FAIL"] = "1"
        result = subprocess.run(["bash", str(SCRIPT), str(self.root)], env=env,
                                capture_output=True, text=True, check=False)
        builds = self.log.read_text().count("run build") if self.log.exists() else 0
        return result, builds

    def later(self, relative: str) -> None:
        """Move a file's time past the recorded build, as an edit or another build would."""
        stamp = (self.root / "node_modules" / ".pellier-frontend-build").stat().st_mtime
        os.utime(self.root / relative, (stamp + 10, stamp + 10))


@pytest.fixture
def frontend(tmp_path: Path) -> Frontend:
    return Frontend(tmp_path)


def test_the_first_start_builds_and_the_next_one_reuses_the_bundle(frontend: Frontend) -> None:
    first, builds = frontend.start()
    assert first.returncode == 0 and builds == 1
    assert "no build recorded" in first.stdout
    second, builds = frontend.start()
    assert second.returncode == 0 and builds == 1
    assert "build skipped" in second.stdout


@pytest.mark.parametrize("changed", ["src/main.tsx", "package.json"])
def test_an_edited_input_builds_again(frontend: Frontend, changed: str) -> None:
    frontend.start()
    frontend.later(changed)
    result, builds = frontend.start()
    assert builds == 2
    assert f"{changed} changed" in result.stdout


def test_a_bundle_built_by_another_command_is_built_again(frontend: Frontend) -> None:
    """npm run build by hand may use another base path, whose asset URLs 404 behind the proxy."""
    frontend.start()
    frontend.later("dist/index.html")
    result, builds = frontend.start()
    assert builds == 2
    assert "rebuilt by another command" in result.stdout


def test_another_base_path_builds_again(frontend: Frontend) -> None:
    frontend.start()
    result, builds = frontend.start(base="/")
    assert builds == 2
    assert "the base path is now /" in result.stdout


def test_a_missing_bundle_is_built(frontend: Frontend) -> None:
    frontend.start()
    (frontend.root / "dist" / "index.html").unlink()
    result, builds = frontend.start()
    assert builds == 2
    assert "dist/index.html is missing" in result.stdout


def test_a_failed_build_records_nothing_so_the_next_start_tries_again(frontend: Frontend) -> None:
    frontend.start()
    frontend.later("src/main.tsx")
    failed, builds = frontend.start(fail=True)
    assert failed.returncode == 3 and builds == 2
    assert not (frontend.root / "node_modules" / ".pellier-frontend-build").exists()
    retried, builds = frontend.start()
    assert retried.returncode == 0 and builds == 3


def test_the_unit_builds_through_the_script_and_never_blocks_the_backend() -> None:
    unit_lines = [line for line in BOOTSTRAP.read_text().splitlines()
                  if line.startswith("ExecStartPre=")]
    frontend_lines = [line for line in unit_lines if "frontend" in line]
    assert frontend_lines == [(
        "ExecStartPre=-/bin/bash -c 'bash $REPO_PATH/scripts/build-frontend-if-changed.sh "
        "$REPO_PATH/pellier/frontend || true'")]
    assert not any("npm run build" in line for line in unit_lines)
