"""Readiness requires successful calls and the same embedding ID in both rails."""

import importlib.util
import io
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import boto3
from botocore.response import StreamingBody
from botocore.stub import Stubber
import pytest


REPO = Path(__file__).resolve().parents[3]


def _load(relative, monkeypatch):
    # Model preflight's CLI dotenv loader must not read a developer's account
    # configuration merely because this isolated test imports the script.
    spec = importlib.util.spec_from_file_location(f"model_proof_{Path(relative).stem}", REPO / relative)
    module = importlib.util.module_from_spec(spec)
    original = Path.is_file
    with monkeypatch.context() as context:
        context.setattr(Path, "is_file", lambda path: False if path.name == ".env" else original(path))
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("operation", ["invoke", "rerank"])
@pytest.mark.parametrize("outcome", ["success", "denied", "invalid_model", "invalid_payload"])
def test_only_actual_successful_provider_calls_pass(monkeypatch, operation, outcome):
    module = _load("scripts/check_model_access.py", monkeypatch)
    client = boto3.client(
        "bedrock-runtime" if operation == "invoke" else "bedrock-agent-runtime",
        region_name="us-east-1", aws_access_key_id="fixture", aws_secret_access_key="fixture",
    )
    model = {"model_id": "fixture-model", "name": "Fixture", "body": {"prompt": "test"}}
    if operation == "rerank":
        model.update(api="bedrock-agent-runtime.rerank", body={"query": "test", "documents": ["one", "two"], "top_n": 1})
    with Stubber(client) as stub:
        api = "invoke_model" if operation == "invoke" else "rerank"
        if outcome == "success":
            response = {"body": StreamingBody(io.BytesIO(b'{}'), 2), "contentType": "application/json"} if operation == "invoke" else {"results": [{"index": 0, "relevanceScore": 0.9}]}
            stub.add_response(api, response)
        else:
            code = "AccessDeniedException" if outcome == "denied" else "ValidationException"
            detail = {"denied": "Access denied", "invalid_model": "The provided model identifier is invalid", "invalid_payload": "Malformed input request: required field missing"}[outcome]
            stub.add_client_error(api, service_error_code=code, service_message=detail)
        assert module.check_model(client, client, model) is (outcome == "success")
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("profile_ok,bare_ok,expected", [(True, True, "us.cohere.embed-v4:0"), (False, True, "cohere.embed-v4:0"), (False, False, None)])
def test_ready_persists_the_proved_embedding_for_backend_and_mcp(tmp_path, monkeypatch, profile_ok, bare_ok, expected):
    module = _load("scripts/check_model_access.py", monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text("BEDROCK_EMBEDDING_MODEL=stale-backend\nBEDROCK_EMBED_MODEL_ID=stale-mcp\nBEDROCK_MODEL_ACCESS_READY=true\n")
    calls = []

    def invoke(_client, model_id, _body):
        calls.append(model_id)
        if model_id == "us.cohere.embed-v4:0" and not profile_ok:
            return "denied", "fixture denial"
        if model_id == "cohere.embed-v4:0" and not bare_ok:
            return "denied", "fixture denial"
        return "ok", ""

    monkeypatch.setattr(module, "_invoke_one", invoke)
    monkeypatch.setattr(module, "_rerank_one", lambda *_args: ("ok", ""))
    monkeypatch.setattr(module.boto3, "client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(sys, "argv", ["check", "--write-env", str(env_path)])
    if expected is None:
        with pytest.raises(SystemExit) as failure:
            module.main()
        assert failure.value.code == 1
    else:
        module.main()
    values = dict(line.split("=", 1) for line in env_path.read_text().splitlines())
    assert values["BEDROCK_MODEL_ACCESS_READY"] == ("true" if expected else "false")
    if expected:
        assert values["BEDROCK_EMBEDDING_MODEL"] == values["BEDROCK_EMBED_MODEL_ID"] == expected
    else:
        assert values["BEDROCK_EMBEDDING_MODEL"] == "stale-backend"
        assert values["BEDROCK_EMBED_MODEL_ID"] == "stale-mcp"
    assert ("cohere.embed-v4:0" in calls) is (not profile_ok)

    if expected is None:
        return
    # Exercise the existing sudo recovery path: dotenv fills the provisioner's
    # process, and the Lambda deployment consumes its MCP-specific variable.
    monkeypatch.setattr(os, "environ", dict(os.environ))
    os.environ.pop("BEDROCK_EMBEDDING_MODEL", None)
    os.environ.pop("BEDROCK_EMBED_MODEL_ID", None)
    provisioner = _load("scripts/provision_agentcore_end_to_end.py", monkeypatch)
    provisioner._load_env_fallback(tmp_path)
    from config import Settings

    assert Settings().BEDROCK_EMBEDDING_MODEL == expected
    deployer = _load("scripts/deploy/deploy_lambda.py", monkeypatch)
    fake = SimpleNamespace(get_caller_identity=lambda: {"Account": "123456789012"})
    monkeypatch.setattr(deployer.boto3, "Session", lambda **_: SimpleNamespace(client=lambda _: fake))
    monkeypatch.setattr(deployer, "create_iam_role", lambda *_args, **_kwargs: "arn:aws:iam::123456789012:role/fixture")
    deployed = []
    monkeypatch.setattr(deployer, "create_or_update_lambda_function", lambda **kwargs: deployed.append(kwargs) or "arn:aws:lambda:us-east-1:123456789012:function:fixture")
    monkeypatch.setattr(sys, "argv", ["deploy", "--region", "us-east-1", "--server-name", "fixture", "--mcp-server-path", str(REPO / "scripts/deploy/pellier_search_server.py")])
    deployer.main()
    assert deployed[0]["env"]["BEDROCK_EMBED_MODEL_ID"] == expected


def test_a_rejected_model_never_sets_ready(monkeypatch, tmp_path):
    module = _load("scripts/check_model_access.py", monkeypatch)
    monkeypatch.setattr(module.boto3, "client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(module, "_invoke_one", lambda *_args: ("error", "ValidationException: invalid model or payload"))
    monkeypatch.setattr(module, "_rerank_one", lambda *_args: ("error", "ValidationException: invalid model or payload"))
    env_path = tmp_path / ".env"
    env_path.write_text("BEDROCK_MODEL_ACCESS_READY=true\n")
    monkeypatch.setattr(sys, "argv", ["check", "--write-env", str(env_path)])
    with pytest.raises(SystemExit) as failure:
        module.main()
    assert failure.value.code == 1
    assert env_path.read_text() == "BEDROCK_MODEL_ACCESS_READY=false\n"
