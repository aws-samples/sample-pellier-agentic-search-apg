"""An extension install is ready only when the requested ID is installed."""

import hashlib
import os
from pathlib import Path
import re
import subprocess

import pytest


SOURCE = Path(__file__).resolve().parents[3] / "scripts/bootstrap-environment.sh"
CEDAR_RELEASES = "https://github.com/cedar-policy/vscode-cedar/releases/download"


@pytest.mark.parametrize(
    "installed,install_status,list_status,expected",
    [
        ("ms-python.python", 0, 0, 1),  # another install's success is not ours
        ("ms-pyright.pyright-extra", 0, 0, 1),  # exact ID, not a prefix
        ("ms-pyright.pyright", 0, 1, 1),  # failed inventory is not proof
        ("ms-pyright.pyright", 0, 0, 0),
        ("MS-PYRIGHT.PYRIGHT", 1, 0, 0),  # already installed on reentry
    ],
)
def test_install_extension_checks_installed_inventory(
    tmp_path, installed, install_status, list_status, expected
):
    editor = tmp_path / "code-editor-server"
    editor.write_text(
        '#!/bin/bash\n'
        'case "$1" in\n'
        '  --install-extension) echo "successfully installed"; exit "$INSTALL_STATUS" ;;\n'
        '  --list-extensions) printf "%s\\n" "$INSTALLED"; exit "$LIST_STATUS" ;;\n'
        '  *) exit 2 ;;\n'
        'esac\n'
    )
    editor.chmod(0o755)
    function = SOURCE.read_text().split("install_extension() {", 1)[1].split(
        "\n# Install essential extensions", 1
    )[0]
    script = (
        'set -euo pipefail\n'
        'sudo() { shift 2; "$@"; }\n'
        'log() { printf "%s\\n" "$1"; }\n'
        'warn() { printf "%s\\n" "$1"; }\n'
        'install_extension() {' + function + '\n'
        'install_extension ms-pyright.pyright Pyright\n'
    )
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True,
        env={
            **os.environ, "CODE_EDITOR_CMD": str(editor),
            "CODE_EDITOR_USER": "participant", "INSTALLED": installed,
            "INSTALL_STATUS": str(install_status), "LIST_STATUS": str(list_status),
        },
    )
    assert result.returncode == expected, result.stderr
    assert ("✅ Pyright" in result.stdout) == (expected == 0)


def test_cedar_extension_is_one_exact_release_pinned_by_hash():
    text = SOURCE.read_text()
    version = re.search(r'^CEDAR_EXTENSION_VERSION="([^"]*)"$', text, re.M)
    digest = re.search(r'^CEDAR_EXTENSION_SHA256="([^"]*)"$', text, re.M)
    assert version and re.fullmatch(r"\d+\.\d+\.\d+", version.group(1))
    assert digest and re.fullmatch(r"[0-9a-f]{64}", digest.group(1))
    assert f'CEDAR_EXTENSION_RELEASES="{CEDAR_RELEASES}"' in text
    assert "install_cedar_extension || warn" in text


PAYLOAD = "cedar vsix bytes"


@pytest.mark.parametrize(
    "curl_status,pinned_hash,listed,installed",
    [
        (0, hashlib.sha256(PAYLOAD.encode()).hexdigest(), "cedar-policy.vscode-cedar@9.9.9", True),
        (22, hashlib.sha256(PAYLOAD.encode()).hexdigest(), "", False),  # download failed
        (0, "0" * 64, "cedar-policy.vscode-cedar@9.9.9", False),  # wrong bytes never install
        (0, hashlib.sha256(PAYLOAD.encode()).hexdigest(), "", False),  # install not listed
        (0, hashlib.sha256(PAYLOAD.encode()).hexdigest(),
         "cedar-policy.vscode-cedar@9.9.8", False),  # another version is not ours
    ],
)
def test_cedar_extension_is_cosmetic_and_never_stops_setup(
    tmp_path, curl_status, pinned_hash, listed, installed
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "tmp").mkdir()
    calls = tmp_path / "calls.log"
    (bin_dir / "curl").write_text(
        '#!/bin/bash\n'
        'out=""\n'
        'while [ $# -gt 0 ]; do\n'
        '  case "$1" in -o) out="$2"; shift 2 ;; *) echo "curl $1" >> "$CALLS"; shift ;; esac\n'
        'done\n'
        '[ "$CURL_STATUS" = 0 ] || exit "$CURL_STATUS"\n'
        'printf "%s" "$PAYLOAD" > "$out"\n'
    )
    editor = bin_dir / "code-editor-server"
    editor.write_text(
        '#!/bin/bash\n'
        'echo "editor $*" >> "$CALLS"\n'
        'case "$1" in\n'
        '  --install-extension) exit 0 ;;\n'
        '  --list-extensions) printf "%s\\n" "$LISTED" ;;\n'
        'esac\n'
    )
    for tool in (bin_dir / "curl", editor):
        tool.chmod(0o755)
    function = SOURCE.read_text().split("install_cedar_extension() {", 1)[1].split("\n}\n", 1)[0]
    script = (
        'set -euo pipefail\n'
        'sudo() { shift 2; "$@"; }\n'
        'log() { printf "%s\\n" "$1"; }\n'
        'warn() { printf "%s\\n" "$1"; }\n'
        'CEDAR_EXTENSION_VERSION=9.9.9\n'
        f'CEDAR_EXTENSION_SHA256={pinned_hash}\n'
        f'CEDAR_EXTENSION_RELEASES={CEDAR_RELEASES}\n'
        'install_cedar_extension() {' + function + '\n}\n'
        'install_cedar_extension || warn "Cedar step failed"\n'
        'echo "setup continues"\n'
    )
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True,
        env={
            **os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TMPDIR": str(tmp_path / "tmp"), "CALLS": str(calls), "PAYLOAD": PAYLOAD,
            "CURL_STATUS": str(curl_status), "LISTED": listed,
            "CODE_EDITOR_CMD": str(editor), "CODE_EDITOR_USER": "participant",
        },
    )
    log = calls.read_text()
    url = f"{CEDAR_RELEASES}/v9.9.9/vscode-cedar-9.9.9.vsix"
    assert result.returncode == 0, result.stderr
    assert result.stdout.rstrip().endswith("setup continues")
    assert f"curl {url}" in log
    assert ("✅ Cedar 9.9.9" in result.stdout) == installed
    assert ("Plain Text" in result.stdout) != installed
    assert ("--install-extension" in log) == (curl_status == 0 and pinned_hash != "0" * 64)
    assert "Cedar step failed" not in result.stdout
    assert not any((tmp_path / "tmp").iterdir())
