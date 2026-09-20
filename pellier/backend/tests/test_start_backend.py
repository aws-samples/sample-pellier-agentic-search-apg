"""Exercise the launcher with inert executables; never start an app or server."""

from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize(
    "backend_exists,config_exit",
    [(False, 0), (True, 0), (True, 9)],
)
def test_launcher_enters_its_backend_or_stops_before_running_commands(
    tmp_path, backend_exists, config_exit
):
    project = tmp_path / "project with spaces"
    project.mkdir()
    launcher = project / "START_BACKEND.sh"
    source = Path(__file__).resolve().parents[2] / "START_BACKEND.sh"
    launcher.write_bytes(source.read_bytes())
    backend = project / "backend"
    if backend_exists:
        backend.mkdir()

    unrelated = tmp_path / "unrelated working directory"
    unrelated.mkdir()
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    calls = tmp_path / "calls.txt"
    executable = stubs / "python3"
    executable.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "python3|$PWD|$*" >> "$PELLIER_LAUNCHER_TEST_LOG"\n'
        f'if [ "$1" = "generate_mcp_config.py" ]; then exit {config_exit}; fi\nexit 0\n'
    )
    executable.chmod(0o700)

    result = subprocess.run(
        ["/bin/bash", str(launcher)],
        cwd=unrelated,
        env={
            "PATH": f"{stubs}:/usr/bin:/bin",
            "PELLIER_LAUNCHER_TEST_LOG": str(calls),
        },
        capture_output=True,
        text=True,
        timeout=5,
    )

    if not backend_exists:
        assert result.returncode != 0
        assert not calls.exists(), "a failed cd must execute neither command"
    else:
        assert result.returncode == 0
        assert calls.read_text().splitlines() == [
            f"python3|{backend}|generate_mcp_config.py",
            f"python3|{backend}|-m uvicorn app:app --reload --host 0.0.0.0 --port 8000",
        ]
        if config_exit:
            assert "MCP config generation skipped" in result.stdout
