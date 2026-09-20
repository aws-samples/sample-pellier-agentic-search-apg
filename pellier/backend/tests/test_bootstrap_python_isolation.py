"""Execute interpreter boundaries without changing host Python or running services."""

import os
from pathlib import Path
import re
import shlex
import subprocess

import pytest


REPO = Path(__file__).resolve().parents[3]
STAGE1 = (REPO / "scripts/bootstrap-environment.sh").read_text()
STAGE2 = (REPO / "scripts/bootstrap-labs.sh").read_text()
RECOVERY_SCRIPTS = (
    "scripts/deploy/deploy_all.sh", "scripts/reset-governed-workshop.sh",
    "scripts/health-gate.sh", "scripts/workshop-start.sh", "scripts/lab3-start.sh",
    "scripts/runtime_hello.sh", "scripts/prove-reset-cycles.sh",
    "scripts/dry-run-builders.sh", "pellier/START_BACKEND.sh",
)


def run(script, **env):
    return subprocess.run(
        ["/bin/bash", "-eu", "-c", script], text=True, capture_output=True,
        env={**os.environ, **env}, check=True,
    )


@pytest.fixture
def interpreters(tmp_path):
    system = tmp_path / "usr/bin"
    system.mkdir(parents=True)
    calls = tmp_path / "calls"
    for version in ("3.9", "3.14"):
        executable = system / f"python{version}"
        executable.write_text(
            "#!/bin/bash\n"
            f"printf '%s\\n' '{version}' >> {shlex.quote(str(calls))}\n"
            f"printf '%s\\n' \"$*\" >> {shlex.quote(str(calls))}\n"
        )
        executable.chmod(0o755)
    (system / "python3").symlink_to("python3.9")
    private = tmp_path / "opt/pellier/bin"
    return system, private, calls


def isolation_block(system, private):
    return STAGE1.split("# BEGIN WORKSHOP PYTHON ISOLATION\n", 1)[1].split(
        "# END WORKSHOP PYTHON ISOLATION", 1
    )[0].replace("/usr/bin/python3.14", str(system / "python3.14")).replace(
        "/opt/pellier/bin", str(private)
    )


def test_bootstrap_preserves_os_interpreter_and_only_installs_private_aliases(interpreters):
    system, private, calls = interpreters
    before = (system / "python3.9").read_bytes()
    block = isolation_block(system, private)
    run(
        'log() { :; }; PY_VER=3.14\n' + block + '\npython3 probe\npython probe\n'
        + shlex.quote(str(system / "python3")) + " os-probe\n",
        PATH=f"{system}:/usr/bin:/bin",
    )
    assert os.readlink(system / "python3") == "python3.9"
    assert (system / "python3.9").read_bytes() == before
    assert (private / "python3").resolve() == system / "python3.14"
    assert (private / "python").resolve() == system / "python3.14"
    assert calls.read_text().splitlines()[::2] == ["3.14", "3.14", "3.14", "3.9"]
    assert "update-alternatives" not in STAGE1
    # No assignment/link operation may target either OS interpreter elsewhere.
    assert not re.search(r"^(?:ln|mv|cp|install|rm)\b.* /usr/bin/python3(?:\.9)?(?:\s|$)", STAGE1, re.M)


def test_privileged_dependency_install_ignores_sudo_default_python(interpreters, tmp_path):
    system, _, calls = interpreters
    command = re.search(r'^    sudo -u .* -m pip install --user --require-hashes .*?\n', STAGE1, re.M)[0]
    command = command.split(" 2>&1", 1)[0]
    run(
        'sudo() { shift 2; env -i PATH="$OS_PATH" "$@"; }\n' + command,
        CODE_EDITOR_USER="participant", REQUIREMENTS=str(tmp_path / "requirements.lock"),
        OS_PATH=f"{system}:/usr/bin:/bin",
    )
    assert calls.read_text().splitlines() == [
        "3.14", f"-m pip install --user --require-hashes -r {tmp_path}/requirements.lock",
    ]


@pytest.mark.parametrize("script", [
    "check_model_access.py", "seed_pellier_catalog.py", "seed_tool_registry.py",
    "provision_agentcore_end_to_end.py", "reset_participant_exercises.py",
])
def test_stage2_commands_select_versioned_python_after_sudo_resets_path(
    script, interpreters, tmp_path,
):
    system, _, calls = interpreters
    # Execute the command actually emitted by Stage 2, under the clean PATH
    # supplied by sudo. No AWS/database/application script is run by the stubs.
    command = next(line.strip() for line in STAGE2.splitlines()
                   if script in line and "python3.14" in line and not line.lstrip().startswith("#"))
    if "bash -c '" in command:
        command = command.split("bash -c '", 1)[1].rsplit("'", 1)[0]
    command = command.rstrip(" \\")
    if command.endswith("'") and command.startswith("python3.14 '"):
        command = command.replace("'$REPO_PATH/", '"$REPO_PATH/').rstrip("'") + '"'
    command = command.replace("'$REPO_PATH/", '"$REPO_PATH/').replace(".env'", '.env"')
    run('sudo() { shift 2; env -i PATH="$OS_PATH" REPO_PATH="$REPO_PATH" bash -eu -c "$1"; }\n'
        + "sudo -u participant " + shlex.quote(command),
        OS_PATH=f"{system}:/usr/bin:/bin", REPO_PATH=str(tmp_path),
    )
    assert calls.read_text().splitlines()[0] == "3.14"
    assert script in calls.read_text()


def test_backend_service_and_editor_select_workshop_python(interpreters, tmp_path):
    system, private, calls = interpreters
    unit = tmp_path / "pellier.service"
    emit = re.search(r"cat > /etc/systemd/system/pellier.service << EOF\n.*?\nEOF\n", STAGE2, re.S)[0]
    run(emit.replace("/etc/systemd/system/pellier.service", str(unit)),
        REPO_PATH=str(tmp_path), CODE_EDITOR_USER="participant", UVICORN_RELOAD_ARGS="--reload")
    text = unit.read_text()
    start = next(line.removeprefix("ExecStart=") for line in text.splitlines() if line.startswith("ExecStart="))
    assert start.startswith("/usr/bin/python3.14 -m uvicorn ")
    run(start.replace("/usr/bin/python3.14", str(system / "python3.14")), PATH=f"{system}:/usr/bin:/bin")
    assert calls.read_text().splitlines()[0] == "3.14"
    assert "Environment=PATH=/opt/pellier/bin:" in text
    assert "Environment=PATH=/opt/pellier/bin:" in STAGE1
    assert STAGE1.count('"python.defaultInterpreterPath": "/usr/bin/python3.14"') == 2


@pytest.mark.parametrize("script", RECOVERY_SCRIPTS)
def test_clean_recovery_shell_prefers_workshop_interpreter(script, interpreters):
    system, private, calls = interpreters
    private.mkdir(parents=True)
    (private / "python3").symlink_to(system / "python3.14")
    source = (REPO / script).read_text()
    path = next(line for line in source.splitlines() if line.startswith('export PATH="/opt/pellier/bin:'))
    run(path.replace("/opt/pellier/bin", str(private)) + "\npython3 recovery\n", PATH=f"{system}:/usr/bin:/bin")
    assert calls.read_text().splitlines() == ["3.14", "recovery"]


def test_stage2_has_no_ambient_python_call_or_system_python_assignment():
    commands = "\n".join(line for line in STAGE2.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"\bpython3\b(?!\.14)", commands)
    assert "update-alternatives" not in STAGE2


def test_operator_secret_write_uses_participant_site_and_literal_environment(tmp_path):
    command = STAGE2.split('        if ! sudo -u "$CODE_EDITOR_USER" env \\\n', 1)[1]
    command = 'sudo -u "$CODE_EDITOR_USER" env \\\n' + command.split("; then", 1)[0]
    # This exact call must select the intended helper, not a nearby sudo command.
    assert "store_operator_credential.py" in command
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "received"
    executable = fake_bin / "python3.14"
    executable.write_text(
        '#!/bin/bash\n[ "$MOCK_RUN_AS" = participant ] || exit 99\n'
        'printf "%s\\n" "$OPERATOR_USERNAME" "$OPERATOR_PASSWORD" "$AWS_REGION" '
        '"$COGNITO_TEST_CREDENTIALS_SECRET_ARN" "$*" > "$MOCK_CAPTURE"\n'
    )
    executable.chmod(0o755)
    password = 'synthetic $(touch SHOULD_NOT_EXIST); `false` $VALUE "quoted"'
    result = run(
        'sudo() { [ "$1" = -u ]; export MOCK_RUN_AS="$2"; shift 2; "$@"; }\n' + command,
        PATH=f"{fake_bin}:/usr/bin:/bin", CODE_EDITOR_USER="participant",
        REPO_PATH=str(tmp_path), OPERATOR_USERNAME="operator", OPERATOR_PASSWORD=password,
        AWS_REGION="us-east-1", COGNITO_TEST_CREDENTIALS_SECRET_ARN="synthetic-secret",
        MOCK_CAPTURE=str(capture),
    )
    assert result.stdout == result.stderr == ""
    assert capture.read_text().splitlines() == [
        "operator", password, "us-east-1", "synthetic-secret",
        f"{tmp_path}/scripts/store_operator_credential.py",
    ]
    assert not (REPO / "SHOULD_NOT_EXIST").exists()


def test_aws_cli_install_reentry_uses_fresh_private_staging_and_owned_cleanup(tmp_path):
    block = STAGE1.split('log "Installing AWS CLI v2..."\n', 1)[1].split(
        "# AL2023 also ships a Python-based AWS CLI", 1
    )[0]
    block = block.replace("/tmp/pellier-aws-cli.XXXXXXXX", str(tmp_path / "attempt.XXXXXXXX"))
    stranded = tmp_path / "attempt.interrupted"
    stranded.mkdir()
    sentinel = stranded / "partial-installer"
    sentinel.write_text("prior attempt must not be reused or removed")
    calls = tmp_path / "staging-paths"
    stubs = '''
curl() { printf archive > awscliv2.zip; }
unzip() {
    [ ! -e aws ] || exit 96
    printf '%s\\n' "$PWD" >> "$MOCK_PATHS"
    mkdir aws
    printf '#!/bin/bash\\nexit "$MOCK_INSTALL_RC"\\n' > aws/install
    chmod +x aws/install
}
'''
    for rc in (9, 0):
        result = subprocess.run(
            ["/bin/bash", "-eu", "-c", stubs + block], capture_output=True, text=True,
            env={**os.environ, "MOCK_PATHS": str(calls), "MOCK_INSTALL_RC": str(rc)},
        )
        assert result.returncode == rc, result.stderr
    first, second = calls.read_text().splitlines()
    assert first != second
    assert not Path(first).exists() and not Path(second).exists()
    assert sentinel.read_text() == "prior attempt must not be reused or removed"
