"""An extension install is ready only when the requested ID is installed."""

import os
from pathlib import Path
import subprocess

import pytest


SOURCE = Path(__file__).resolve().parents[3] / "scripts/bootstrap-environment.sh"


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
