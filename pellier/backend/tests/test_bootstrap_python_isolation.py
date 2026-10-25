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
    "check_model_access.py",
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


def database_setup_call():
    """Stage 2's database-setup pipeline, from the secrets it pipes in to the setup's output."""
    start = STAGE2.index("printf '%s\\n%s\\n' \"$DB_PASSWORD\" \"$DATABASE_URL\" | sudo")
    end = STAGE2.index("2>&1 | tee /var/log/database-setup.log", start)
    return STAGE2[start:end].rstrip(" \\\n")


def test_database_setup_seeds_on_workshop_python_after_sudo_resets_path(interpreters):
    """Bootstrap names python3.14 and scripts/setup/database-setup.sh runs the seeder with it.

    The interpreter choice and the seeder call now live in two files, so execute both:
    Stage 2's invocation under the clean PATH sudo supplies, then the real setup script
    it calls, with psql stubbed. No database is reached.
    """
    system, _, calls = interpreters
    psql = system / "psql"
    psql.write_text("#!/bin/bash\nexit 0\n")
    psql.chmod(0o755)
    run('sudo() { shift 2; env -i PATH="$OS_PATH" "$@"; }\n' + database_setup_call(),
        OS_PATH=f"{system}:/usr/bin:/bin", REPO_PATH=str(REPO),
        CODE_EDITOR_USER="participant", DB_HOST="db.invalid", DB_PORT="5432",
        DB_NAME="pellier", DB_USER="pellier", DB_PASSWORD="synthetic",
        AWS_REGION="us-east-1", DATABASE_URL="postgresql://synthetic")
    assert calls.read_text().splitlines() == [
        "3.14", "scripts/seed_pellier_catalog.py --from-cache",
    ]


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


def test_operator_secret_write_uses_participant_site_and_keeps_the_password_off_argv(tmp_path):
    """sudo logs its command line to the journal, and any user can list it while it runs, so
    the staff password goes in on stdin, never as an argument (event 13's journal held it)."""
    call = "printf '%s' \"$OPERATOR_PASSWORD\" | sudo -u \"$CODE_EDITOR_USER\" env \\\n"
    command = call + STAGE2.split("        if ! " + call, 1)[1].split("; then", 1)[0]
    # This exact call must select the intended helper, not a nearby sudo command.
    assert "store_operator_credential.py" in command
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture, logged = tmp_path / "received", tmp_path / "sudo-argv"
    executable = fake_bin / "python3.14"
    executable.write_text(
        '#!/bin/bash\n[ "$MOCK_RUN_AS" = participant ] || exit 99\npassword="$(cat)"\n'
        'printf "%s\\n" "$OPERATOR_USERNAME" "$password" "$AWS_REGION" '
        '"$COGNITO_TEST_CREDENTIALS_SECRET_ARN" "${OPERATOR_PASSWORD-unset}" "$*" '
        '> "$MOCK_CAPTURE"\n'
    )
    executable.chmod(0o755)
    password = 'synthetic $(touch SHOULD_NOT_EXIST); `false` $VALUE "quoted"'
    # A shell variable, as in the bootstrap: never exported, so only stdin can carry it.
    result = run(
        f"OPERATOR_PASSWORD={shlex.quote(password)}\n"
        'sudo() { printf "%s\\n" "$*" > "$MOCK_SUDO_ARGV"; [ "$1" = -u ]; '
        'export MOCK_RUN_AS="$2"; shift 2; "$@"; }\n' + command,
        PATH=f"{fake_bin}:/usr/bin:/bin", CODE_EDITOR_USER="participant",
        REPO_PATH=str(tmp_path), OPERATOR_USERNAME="nadia",
        AWS_REGION="us-east-1", COGNITO_TEST_CREDENTIALS_SECRET_ARN="synthetic-secret",
        MOCK_CAPTURE=str(capture), MOCK_SUDO_ARGV=str(logged),
    )
    assert result.stdout == result.stderr == ""
    assert capture.read_text().splitlines() == [
        "nadia", password, "us-east-1", "synthetic-secret", "unset",
        f"{tmp_path}/scripts/store_operator_credential.py",
    ]
    assert password not in logged.read_text() and "OPERATOR_PASSWORD" not in logged.read_text()
    assert not (REPO / "SHOULD_NOT_EXIST").exists()


@pytest.mark.parametrize("setup_exit", [0, 7])
def test_database_setup_keeps_the_master_password_off_sudo_argv(tmp_path, setup_exit):
    """sudo writes its command line, env NAME=value pairs included, to the journal, and its
    --preserve-env records the values too (sudo 1.9.15 on event 14, whose journal held the
    Aurora master password once). The password and the URL that embeds it go in on stdin."""
    stage = STAGE2[STAGE2.index("printf '%s\\n%s\\n' \"$DB_PASSWORD\""):]
    block = stage[:stage.index("\n", stage.index("local setup_rc=")) + 1]
    setup = tmp_path / "scripts/setup/database-setup.sh"
    setup.parent.mkdir(parents=True)
    setup.write_text(
        '#!/bin/bash\nprintf "%s\\n" "$DB_PASSWORD" "$DATABASE_URL" "$DB_HOST" "$PYTHON" '
        '"$(cat)" > "$REPO/received"\n'
        f"exit {setup_exit}\n")
    logged = tmp_path / "sudo-argv"
    # Edge spaces and backslashes survive only IFS= read -r.
    password = ' synthetic $(touch SHOULD_NOT_EXIST); `false` $VALUE "quoted" \\n\\back '
    url = f"postgresql://pellier:{password}@db.invalid:5432/pellier"
    result = run(
        'sudo() { printf "%s\\n" "$*" > "$MOCK_SUDO_ARGV"; [ "$1" = -u ]; shift 2;\n'
        '         env -i PATH=/usr/bin:/bin "$@"; }\n'
        + block.replace("/var/log/database-setup.log", str(tmp_path / "setup.log"))
               .replace("local setup_rc=", "setup_rc=")
        + 'echo "rc=$setup_rc"\n',
        REPO_PATH=str(tmp_path), CODE_EDITOR_USER="participant", DB_HOST="db.invalid",
        DB_PORT="5432", DB_NAME="pellier", DB_USER="pellier", DB_PASSWORD=password,
        DATABASE_URL=url, AWS_REGION="us-east-1", MOCK_SUDO_ARGV=str(logged),
    )
    assert result.stdout.splitlines()[-1] == f"rc={setup_exit}"
    assert (tmp_path / "received").read_text().splitlines() == [
        password, url, "db.invalid", "python3.14", ""]
    argv = logged.read_text()
    assert "synthetic" not in argv and "DB_PASSWORD=" not in argv and "DATABASE_URL=" not in argv
    assert not (REPO / "SHOULD_NOT_EXIST").exists() and not (tmp_path / "SHOULD_NOT_EXIST").exists()


def test_aws_cli_install_reentry_uses_fresh_private_staging_and_owned_cleanup(tmp_path):
    block = STAGE1.split('log "Installing AWS CLI v2..."\n', 1)[1].split(
        "# AL2023 also ships a Python-based AWS CLI", 1
    )[0]
    block = block.replace("/tmp/pellier-aws-cli.XXXXXXXX", str(tmp_path / "attempt.XXXXXXXX"))
    bundle = tmp_path / "installed"
    bundle.mkdir(mode=0o700)
    binary = bundle / "aws"
    binary.write_text("public executable")
    binary.chmod(0o700)
    secret = tmp_path / "credential"
    secret.write_text("synthetic private file")
    secret.chmod(0o600)
    block = block.replace("/usr/local/aws-cli", str(bundle))
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
            ["/bin/bash", "-eu", "-c", "umask 077\n" + stubs + block + "\ntest $(umask) = 0077"], capture_output=True, text=True,
            env={**os.environ, "MOCK_PATHS": str(calls), "MOCK_INSTALL_RC": str(rc)},
        )
        assert result.returncode == rc, result.stderr
    first, second = calls.read_text().splitlines()
    assert first != second
    assert not Path(first).exists() and not Path(second).exists()
    assert sentinel.read_text() == "prior attempt must not be reused or removed"

    assert bundle.stat().st_mode & 0o777 == 0o755
    assert binary.stat().st_mode & 0o777 == 0o755
    assert secret.stat().st_mode & 0o777 == 0o600
