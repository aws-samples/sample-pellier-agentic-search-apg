"""The frontend entrypoint builds only with the workshop's Node 24 runtime."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


REPO = Path(__file__).resolve().parents[3]
START_FRONTEND = REPO / "pellier" / "START_FRONTEND.sh"


def _executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _run_entrypoint(
    tmp_path: Path,
    *,
    initial_version: str | None,
    nvm_version: str | None = None,
    nvm_returncode: int = 0,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """Run the whole entrypoint with isolated Node/npm and no real NVM/build."""
    bash = shutil.which("bash")
    dirname = shutil.which("dirname")
    assert bash and dirname
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "dirname").symlink_to(dirname)
    if initial_version is not None:
        _executable(fake_bin / "node", 'printf "%s\\n" "$INITIAL_NODE_VERSION"\n')
    build_record = tmp_path / "build-record"
    _executable(
        fake_bin / "npm",
        'printf "%s|%s|%s\\n" "$*" "$(node --version)" "$VITE_BASE_PATH" > "$BUILD_RECORD"\n',
    )
    custom_nvm = tmp_path / "custom-nvm"
    custom_nvm.mkdir()
    nvm_record = tmp_path / "nvm-record"
    if nvm_version is not None:
        selected_bin = custom_nvm / "selected-bin"
        selected_bin.mkdir()
        _executable(selected_bin / "node", 'printf "%s\\n" "$SELECTED_NODE_VERSION"\n')
        (custom_nvm / "nvm.sh").write_text(
            'printf "source %s\\n" "$*" >> "$NVM_RECORD"\n'
            # A normal source would activate the default and fail this fixture.
            '[[ "$*" == --no-use ]] || return 91\n'
            'nvm() {\n'
            '    printf "%s\\n" "$*" >> "$NVM_RECORD"\n'
            '    [[ "$*" == "use 24" ]] || return 92\n'
            '    [[ "$NVM_RETURNCODE" == 0 ]] || return "$NVM_RETURNCODE"\n'
            '    export PATH="$NVM_DIR/selected-bin:$PATH"\n'
            '}\n',
            encoding="utf-8",
        )
    environment = {
        "PATH": str(fake_bin),
        "NVM_DIR": str(custom_nvm),
        "INITIAL_NODE_VERSION": initial_version or "",
        "SELECTED_NODE_VERSION": nvm_version or "",
        "NVM_RETURNCODE": str(nvm_returncode),
        "BUILD_RECORD": str(build_record),
        "NVM_RECORD": str(nvm_record),
        "VITE_BASE_PATH": "/synthetic-workshop/",
    }
    result = subprocess.run(
        [bash, "--noprofile", "--norc", str(START_FRONTEND)],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, build_record, nvm_record


@pytest.mark.parametrize("installed_nvm_version", [None, "v22.20.0"])
def test_active_node_24_builds_without_loading_nvm(
    tmp_path: Path, installed_nvm_version: str | None
) -> None:
    result, build_record, nvm_record = _run_entrypoint(
        tmp_path, initial_version="v24.9.0", nvm_version=installed_nvm_version
    )

    assert result.returncode == 0, result.stderr
    assert build_record.read_text() == "run build|v24.9.0|/synthetic-workshop/\n"
    assert not nvm_record.exists()


@pytest.mark.parametrize("initial_version", ["v22.20.0", None])
def test_custom_nvm_selects_installed_node_24_before_building(
    tmp_path: Path, initial_version: str | None
) -> None:
    result, build_record, nvm_record = _run_entrypoint(
        tmp_path, initial_version=initial_version, nvm_version="v24.9.0"
    )

    assert result.returncode == 0, result.stderr
    assert nvm_record.read_text() == "source --no-use\nuse 24\n"
    assert build_record.read_text() == "run build|v24.9.0|/synthetic-workshop/\n"


@pytest.mark.parametrize("initial_version", ["v22.20.0", "v26.5.0", None])
def test_missing_node_24_stops_before_building(
    tmp_path: Path, initial_version: str | None
) -> None:
    result, build_record, nvm_record = _run_entrypoint(
        tmp_path, initial_version=initial_version
    )

    assert result.returncode == 1
    assert "Node.js 24 is required" in result.stderr
    assert not build_record.exists()
    assert not nvm_record.exists()


@pytest.mark.parametrize(
    ("nvm_version", "nvm_returncode"), [("v22.20.0", 0), ("v24.9.0", 3)]
)
def test_failed_or_incorrect_nvm_selection_stops_before_building(
    tmp_path: Path, nvm_version: str, nvm_returncode: int
) -> None:
    result, build_record, nvm_record = _run_entrypoint(
        tmp_path,
        initial_version="v22.20.0",
        nvm_version=nvm_version,
        nvm_returncode=nvm_returncode,
    )

    assert result.returncode == 1
    assert "Node.js 24 is required" in result.stderr
    assert nvm_record.read_text() == "source --no-use\nuse 24\n"
    assert not build_record.exists()
