"""Isolated rehearsals use the renderer identity across bootstrap and recovery."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[3]
RESOLVER = REPO / "scripts/deploy/resolve_agentcore_identity.py"
FLAG = "PELLIER_DEPLOYMENT_SUFFIX"


@pytest.mark.parametrize("requested", [None, "", "rc", "rehearsal"])
def test_bootstrap_carries_suffix_through_all_environment_boundaries(tmp_path, requested):
    expected = requested or ""
    env = {"PATH": os.environ["PATH"], "AWS_REGION": "us-east-1"}
    if requested is not None:
        env[FLAG] = requested
    source = (REPO / "scripts/bootstrap-environment.sh").read_text()
    function = "write_stage2_manifest() {" + source.split("write_stage2_manifest() {", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
    env["STAGE2_ENV_MANIFEST"] = str(tmp_path / "stage2.env")
    subprocess.run(["bash", "-eu", "-c", "chown() { :; }\n" + function + "write_stage2_manifest"], env=env, check=True)
    stages = [tmp_path / "stage2.env"]

    source = (REPO / "scripts/bootstrap-labs.sh").read_text()
    recovery = source.split('cat > "$PROVISION_ENV" << EOF\n', 1)[1].split("\nEOF", 1)[0]
    env["PROVISION_ENV"] = str(tmp_path / "provision.env")
    subprocess.run(["bash", "-eu", "-c", 'cat > "$PROVISION_ENV" << EOF\n' + recovery + "\nEOF\n"], env=env, check=True)
    stages.append(tmp_path / "provision.env")
    dotenv_line = next(line for line in source.splitlines() if line.startswith(f"{FLAG}="))
    env["PROVISION_ENV"] = str(tmp_path / "backend.env")
    subprocess.run(["bash", "-eu", "-c", 'cat > "$PROVISION_ENV" << EOF\n' + dotenv_line + "\nEOF\n"], env=env, check=True)
    stages.append(tmp_path / "backend.env")
    for path in stages:
        result = subprocess.run(["bash", "-eu", "-c", f'source "$1"; printf "%s" "${{{FLAG}}}"', "bash", str(path)], env={"PATH": env["PATH"]}, check=True, capture_output=True, text=True)
        assert result.stdout == expected

    sudo = source.split('sudo -u "$CODE_EDITOR_USER" bash -c "', 1)[1]
    export_line = next(line.strip() for line in sudo.splitlines() if f"export {FLAG}=" in line)
    result = subprocess.run(["bash", "-eu", "-c", f'child="{export_line}"; unset {FLAG}; bash -eu -c "$child; printenv {FLAG}"'], env=env, check=True, capture_output=True, text=True)
    assert result.stdout.strip() == expected


@pytest.mark.parametrize("suffix", ["", "rc", "rehearsal"])
def test_identity_resolver_uses_renderer_names_and_saved_configuration(tmp_path, suffix):
    (tmp_path / ".env").write_text(f"{FLAG}='{suffix}'\n")
    env = os.environ.copy()
    env.pop(FLAG, None)
    names = {
        "project-root": str(tmp_path / ".agentcore-project" / f"pellier{suffix}"),
        "runtime-name": f"pellier{'_' + suffix if suffix else ''}_orchestrator",
        "policy-engine-name": f"pellier{'_' + suffix if suffix else ''}_policy_engine",
    }
    for field, expected in names.items():
        result = subprocess.run([sys.executable, str(RESOLVER), "--repo", str(tmp_path), "--field", field], env=env, check=True, capture_output=True, text=True)
        assert result.stdout.strip() == expected


def test_explicit_empty_suffix_wins_over_saved_isolation_label(tmp_path):
    (tmp_path / ".env").write_text(f"{FLAG}='rehearsal'\n")
    result = subprocess.run([sys.executable, str(RESOLVER), "--repo", str(tmp_path), "--field", "runtime-name"], env={**os.environ, FLAG: ""}, check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "pellier_orchestrator"


def test_invalid_suffix_fails_without_a_resolved_project(tmp_path):
    result = subprocess.run([sys.executable, str(RESOLVER), "--repo", str(tmp_path), "--field", "project-root"], env={**os.environ, FLAG: "../other"}, capture_output=True, text=True)
    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.parametrize("script", ["policy_mode.py", "prove_governance_windows.py"])
def test_policy_helpers_preserve_suffix_from_dotenv_and_explicit_environment(tmp_path, monkeypatch, script):
    spec = importlib.util.spec_from_file_location(f"suffix_{script}", REPO / "scripts" / script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / ".env").write_text(f"{FLAG}='rehearsal'\n")
    monkeypatch.setattr(module, "_BACKEND", tmp_path)
    monkeypatch.delenv(FLAG, raising=False)
    assert module._load_env()[FLAG] == "rehearsal"
    monkeypatch.setenv(FLAG, "rc")
    cfg = module._load_env()
    assert cfg[FLAG] == "rc"
    if script == "policy_mode.py":
        assert module._project_for_config(cfg) == REPO / ".agentcore-project/pellierrc"


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
@pytest.mark.parametrize("suffix,override", [("", None), ("rehearsal", None), ("rehearsal", "chosen_runtime")])
def test_runtime_hello_invokes_only_the_resolved_deployment(tmp_path, suffix, override):
    project = tmp_path / ".agentcore-project" / f"pellier{suffix}"
    project.mkdir(parents=True)
    (tmp_path / ".env").write_text(f"{FLAG}='{suffix}'\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npx = bin_dir / "npx"
    calls = tmp_path / "invoke.json"
    npx.write_text(f'''#!{sys.executable}
import json,os,sys
from pathlib import Path
Path({str(calls)!r}).write_text(json.dumps({{"cwd":os.getcwd(),"args":sys.argv[1:],"endpoint":os.environ.get("AGENTCORE_RUNTIME_ENDPOINT")}}))
print(json.dumps({{"success":True,"response":{{"rail":"gateway-mcp","response":"Recorded fixture response","tool_calls":[],"gateway_tools":[]}}}}))
''')
    npx.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PELLIER_REPO": str(tmp_path), "PELLIER_TOKEN": "fixture-token", "PELLIER_EVIDENCE_DIR": str(tmp_path / "evidence"), "AGENTCORE_RUNTIME_ENDPOINT": "arn:fixture:runtime"}
    env.pop(FLAG, None)
    command = ["bash", str(REPO / "scripts/runtime_hello.sh")]
    if override:
        command.extend(["--runtime", override])
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    invoked = json.loads(calls.read_text())
    assert invoked["cwd"] == str(project)
    runtime = invoked["args"][invoked["args"].index("--runtime") + 1]
    assert runtime == (override or f"pellier{'_' + suffix if suffix else ''}_orchestrator")
    assert invoked["endpoint"] == "DEFAULT"


@pytest.mark.parametrize("suffix", ["", "rehearsal"])
def test_interactive_agentcore_wrapper_uses_saved_deployment(tmp_path, suffix):
    project = tmp_path / ".agentcore-project" / f"pellier{suffix}"
    project.mkdir(parents=True)
    (tmp_path / ".env").write_text(f"{FLAG}='{suffix}'\n")
    (tmp_path / "scripts").symlink_to(REPO / "scripts", target_is_directory=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "wrapper.json"
    binary = bin_dir / "agentcore"
    binary.write_text(f'''#!{sys.executable}
import json,os,sys
from pathlib import Path
if sys.argv[1:] == ["--version"]:
    print("0.29.0")
else:
    Path({str(calls)!r}).write_text(json.dumps({{"cwd":os.getcwd(),"args":sys.argv[1:],"endpoint":os.environ.get("AGENTCORE_RUNTIME_ENDPOINT")}}))
''')
    binary.chmod(0o755)
    source = (REPO / "scripts/bootstrap-labs.sh").read_text()
    wrapper = source.split('AGENTCORE_CLI_PINNED_VERSION="0.29.0"', 1)[1].split("# Pellier service shortcuts", 1)[0]
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PELLIER_REPO": str(tmp_path), "AGENTCORE_RUNTIME_ENDPOINT": "arn:fixture:runtime"}
    env.pop(FLAG, None)
    result = subprocess.run(["bash", "-eu", "-c", 'log() { :; }\nAGENTCORE_CLI_PINNED_VERSION="0.29.0"\n' + wrapper + "\nagentcore status\n"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(calls.read_text()) == {"cwd": str(project), "args": ["status"], "endpoint": "DEFAULT"}


@pytest.mark.parametrize("explicit,expected", [(None, "rctest"), ("", ""), ("rc", "rc")])
def test_direct_provisioner_resolves_dotenv_identity_before_first_deploy(tmp_path, monkeypatch, explicit, expected):
    # Import before loading the saved suffix, as the direct Python entry does.
    monkeypatch.setattr(os, "environ", dict(os.environ))
    os.environ.pop(FLAG, None)
    spec = importlib.util.spec_from_file_location("suffix_direct_provisioner", REPO / "scripts/provision_agentcore_end_to_end.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inputs = {
        FLAG: "rctest", "AWS_REGION": "us-east-1", "DB_CLUSTER_ARN": "arn:aws:rds:us-east-1:123456789012:cluster:fixture",
        "DB_SECRET_ARN": "fixture", "COGNITO_POOL": "fixture", "COGNITO_CLIENT": "fixture",
        "COGNITO_TEST_CREDENTIALS_SECRET_ARN": "fixture", "AGENT_MODEL_ID": "fixture",
        "BEDROCK_FAST_MODEL": "fixture", "AGENTCORE_RUNTIME_LOG_RETENTION_DAYS": "30",
        "AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN": "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-1234567890ab",
    }
    for key in inputs:
        os.environ.pop(key, None)
    (tmp_path / ".env").write_text("".join(f"{key}='{value}'\n" for key, value in inputs.items()))
    if explicit is not None:
        os.environ[FLAG] = explicit
    monkeypatch.setattr(sys, "argv", ["provision", "--repo-path", str(tmp_path), "--output-json", str(tmp_path / "receipt.json")])
    monkeypatch.setattr(module.boto3, "client", lambda service, **_: SimpleNamespace(get_caller_identity=lambda: {"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:role/fixture"}) if service == "sts" else pytest.fail("unexpected provider access"))
    monkeypatch.setattr(module, "_verify_log_kms_key", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "_ensure_data_api_enabled", lambda *_args: None)
    monkeypatch.setattr(module, "_verify_local_schema", lambda: {})
    captured = []

    def stop_at_deployment(**kwargs):
        captured.append(kwargs["identity"])
        raise RuntimeError("fixture stops before any AWS deployment")

    monkeypatch.setattr(module, "_deploy_lambdas", stop_at_deployment)
    assert module.main() == 1
    identity, = captured
    assert identity.suffix == expected
    assert identity.project_name == f"pellier{expected}"
    assert all(config["server_name"].startswith(f"pellier{'-' + expected if expected else ''}-") for config in module._deployment_targets(identity).values())

    # The captured identity remains authoritative even if ambient state changes.
    os.environ[FLAG] = "unrelated"
    commands = []
    monkeypatch.setattr(module, "_run", lambda command, **_: commands.append(command))
    root = module._scaffold_cli_project(repo=tmp_path, env={}, identity=identity)
    assert root.name == identity.project_name
    assert commands[0][commands[0].index("--project-name") + 1] == identity.project_name
    invokes = []
    monkeypatch.setattr(module, "_agentcore", lambda _root, *args, **_: invokes.append(args))
    monkeypatch.setattr(module, "_decode_runtime_invoke", lambda _: {"response": "fixture", "rail": "gateway-mcp"})
    module._authenticated_runtime_smoke(root=root, access_token="fixture", username="marco", env={}, identity=identity)
    assert invokes[0][invokes[0].index("--runtime") + 1] == identity.runtime_name
    state = {"targets": {"default": {"resources": {
        "mcp": {"gateways": {identity.gateway_name: {"gatewayArn": "arn:fixture:gateway"}}},
        "policyEngines": {identity.policy_engine_name: {"policyEngineId": "fixture"}},
    }}}}
    rendered = []
    monkeypatch.setattr(module, "_read_deployed_state", lambda _: state)
    monkeypatch.setattr(module, "render_project", lambda **kwargs: rendered.append(kwargs["identity"]))
    deployed_root, deployed_state = module._deploy_cli_project(
        repo=tmp_path, account_id="123456789012", region="us-east-1",
        cognito_pool="fixture", cognito_client="fixture", lambda_arns={},
        model_id="fixture", workshop_id="fixture", env={}, identity=identity,
    )
    assert deployed_root == root and deployed_state is state
    assert rendered == [identity, identity]


@pytest.mark.parametrize("explicit,expected", [(None, "rctest"), ("", "")])
def test_direct_renderer_cli_reads_saved_suffix_and_writes_consistent_names(tmp_path, monkeypatch, explicit, expected):
    monkeypatch.syspath_prepend(str(REPO / "scripts/deploy"))
    import render_agentcore_project as renderer

    monkeypatch.delenv(FLAG, raising=False)
    (tmp_path / ".env").write_text(f"{FLAG}='rctest'\n")
    if explicit is not None:
        monkeypatch.setenv(FLAG, explicit)
    arns = {surface: f"arn:aws:lambda:us-east-1:123456789012:function:fixture-{surface}" for surface in renderer.TOOL_SCHEMAS}
    arns_path = tmp_path / "lambda-arns.json"
    arns_path.write_text(json.dumps(arns))
    monkeypatch.setattr(renderer, "_render_runtime_source", lambda root, _: (root / "runtime-src", "fixture-fingerprint"))
    monkeypatch.setattr(sys, "argv", ["render", "--repo", str(tmp_path), "--account-id", "123456789012", "--region", "us-east-1", "--cognito-pool", "pool", "--cognito-client", "client", "--model-id", "fixture", "--workshop-id", "fixture", "--lambda-arns", str(arns_path)])
    assert renderer.main() == 0
    identity = renderer.deployment_identity(expected)
    config = json.loads((tmp_path / ".agentcore-project" / identity.project_name / "agentcore/agentcore.json").read_text())
    assert config["name"] == identity.project_name
    assert [runtime["name"] for runtime in config["runtimes"]] == [identity.runtime_name, identity.operator_runtime_name]
    assert config["memories"][0]["name"] == identity.memory_name
    assert config["agentCoreGateways"][0]["name"] == identity.gateway_name
    assert config["policyEngines"][0]["name"] == identity.policy_engine_name
