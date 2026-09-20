"""Governed labels must preserve the pinned CLI's existing deployment identity."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from types import ModuleType

import pytest


REPO = Path(__file__).resolve().parents[3]
DEPLOY = REPO / "scripts" / "deploy"
BACKEND = REPO / "pellier" / "backend"

# Verbatim stack construction from the @aws/agentcore 0.29.0 CDK scaffold.
# Keep this independent of the renderer replacement strings so scaffold drift
# cannot be hidden by generating a fixture from the implementation under test.
PINNED_STACK_CONSTRUCTION = """    new AgentCoreStack(app, stackName, {
      spec,
      mcpSpec,
      credentials,
      connectorParametersByFile,
      harnesses: harnessConfigs.length > 0 ? harnessConfigs : undefined,
      paymentSpec,
      env,
      description: `AgentCore stack for ${spec.name} deployed to ${target.name} (${target.region})`,
      tags: {
        'agentcore:project-name': spec.name,
        'agentcore:target-name': target.name,
      },
    });
"""
GOVERNED_TAGS = {
    "Name": "pellier-governed-managed",
    "Project": "pellier",
    "PellierVariant": "governed",
    "PellierComponent": "agentcore",
}


def _load_renderer(monkeypatch, *, suffix: str = "", workshop_format: str = "") -> ModuleType:
    monkeypatch.syspath_prepend(str(DEPLOY))
    monkeypatch.setenv("PELLIER_DEPLOYMENT_SUFFIX", suffix)
    monkeypatch.setenv("WORKSHOP_FORMAT", workshop_format)
    spec = importlib.util.spec_from_file_location(
        "managed_adoption_renderer", DEPLOY / "render_agentcore_project.py"
    )
    assert spec and spec.loader
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    return renderer


def _seed_sources(repo: Path, renderer: ModuleType) -> None:
    for relative in (*renderer.RUNTIME_DEPENDENCY_FILES, *renderer.RUNTIME_SOURCE_FILES):
        target = repo / "pellier" / "backend" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BACKEND / relative, target)


def _scaffold(config_dir: Path, source: str = PINNED_STACK_CONSTRUCTION) -> Path:
    entrypoint = config_dir / "cdk" / "bin" / "cdk.ts"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text(source, encoding="utf-8")
    return entrypoint


def _render(renderer: ModuleType, repo: Path) -> tuple[Path, dict]:
    root = renderer.render_project(
        repo=repo,
        account_id="000000000000",
        region="us-east-1",
        cognito_pool="us-east-1_example",
        cognito_client="example-client",
        lambda_arns={
            surface: f"arn:aws:lambda:us-east-1:000000000000:function:example-{surface}"
            for surface in renderer.TOOL_SCHEMAS
        },
        model_id="example-model",
        workshop_id="dat416-rc",
        include_policies=False,
    )
    return root, json.loads((root / "agentcore" / "agentcore.json").read_text())


def _without_tags(value):
    if isinstance(value, dict):
        return {key: _without_tags(item) for key, item in value.items() if key != "tags"}
    if isinstance(value, list):
        return [_without_tags(item) for item in value]
    return value


@pytest.mark.parametrize("suffix", ["", "rc"])
def test_governed_labels_preserve_resources_target_and_deployed_state(
    tmp_path: Path, monkeypatch, suffix: str
) -> None:
    renderer = _load_renderer(monkeypatch, suffix=suffix, workshop_format="builders")
    repo = tmp_path / "repo"
    _seed_sources(repo, renderer)
    config_dir = renderer.project_root(repo) / "agentcore"
    entrypoint = _scaffold(config_dir)
    state_path = config_dir / ".cli" / "deployed-state.json"
    state_path.parent.mkdir()
    state = b'{"targets":{"default":{"resources":{"runtimeId":"existing-runtime"}}}}\n'
    state_path.write_bytes(state)

    root_before, before = _render(renderer, repo)
    targets_before = (config_dir / "aws-targets.json").read_bytes()
    assert entrypoint.read_text() == PINNED_STACK_CONSTRUCTION

    monkeypatch.setenv("WORKSHOP_FORMAT", "governed")
    root_after, after = _render(renderer, repo)

    assert root_after == root_before
    assert after["name"] == f"pellier{suffix}"
    assert _without_tags(after) == _without_tags(before)
    assert (config_dir / "aws-targets.json").read_bytes() == targets_before
    assert state_path.read_bytes() == state
    for resource in [
        after,
        *after["runtimes"],
        *after["memories"],
        *after["agentCoreGateways"],
        *after["policyEngines"],
    ]:
        assert resource["tags"] == {**before["tags"], **GOVERNED_TAGS}
    assert after["tags"]["PellierWorkshopId"] == "dat416-rc"
    assert after["tags"]["PellierRuntimeExposure"] == "public-workshop-only"
    assert entrypoint.read_text() == PINNED_STACK_CONSTRUCTION.replace(
        "      tags: {\n", "      tags: {\n        ...spec.tags,\n"
    )


@pytest.mark.parametrize("workshop_format", ["", "builders"])
def test_builders_defaults_do_not_gain_governed_tags_or_scaffold_changes(
    tmp_path: Path, monkeypatch, workshop_format: str
) -> None:
    renderer = _load_renderer(monkeypatch, workshop_format=workshop_format)
    repo = tmp_path / "repo"
    _seed_sources(repo, renderer)
    entrypoint = _scaffold(renderer.project_root(repo) / "agentcore")

    root, project = _render(renderer, repo)

    assert root.name == "pellier"
    assert [item["name"] for item in project["runtimes"]] == [
        "pellier_orchestrator", "pellier_operator"
    ]
    assert project["memories"][0]["name"] == "PellierMemory"
    assert project["agentCoreGateways"][0]["name"] == "pellier-gateway"
    assert project["policyEngines"][0]["name"] == "pellier_policy_engine"
    assert project["tags"] == {
        "Project": "pellier",
        "PellierWorkshopId": "dat416-rc",
        "PellierDeploymentClass": "workshop",
        "PellierRuntimeExposure": "public-workshop-only",
    }
    assert entrypoint.read_text() == PINNED_STACK_CONSTRUCTION
    assert json.loads((root / "agentcore" / "aws-targets.json").read_text()) == [
        {"name": "default", "account": "000000000000", "region": "us-east-1"}
    ]


def test_pinned_scaffold_merge_is_idempotent_and_identity_tags_win(
    tmp_path: Path, monkeypatch
) -> None:
    renderer = _load_renderer(monkeypatch, workshop_format="governed")
    assert renderer.AGENTCORE_CLI == "@aws/agentcore@0.29.0"
    entrypoint = _scaffold(tmp_path)
    renderer._customize_governed_cdk_tags(tmp_path)
    first = entrypoint.read_bytes()
    first_mtime = entrypoint.stat().st_mtime_ns

    renderer._customize_governed_cdk_tags(tmp_path)

    assert entrypoint.read_bytes() == first
    assert entrypoint.stat().st_mtime_ns == first_mtime
    source = first.decode()
    assert source.count("...spec.tags,") == 1
    assert source.index("...spec.tags,") < source.index("'agentcore:project-name': spec.name")
    assert source.index("...spec.tags,") < source.index("'agentcore:target-name': target.name")


@pytest.mark.parametrize(
    "source",
    [
        PINNED_STACK_CONSTRUCTION.replace("tags: {", "tags: getTags({"),
        PINNED_STACK_CONSTRUCTION * 2,
        PINNED_STACK_CONSTRUCTION.replace(
            "      tags: {\n", "      tags: {\n        ...customTags,\n"
        ),
    ],
    ids=["changed-shape", "ambiguous-blocks", "unreviewed-customization"],
)
def test_unrecognized_scaffold_stops_before_any_rendered_file_changes(
    tmp_path: Path, monkeypatch, source: str
) -> None:
    renderer = _load_renderer(monkeypatch, suffix="rc", workshop_format="governed")
    repo = tmp_path / "repo"
    config_dir = renderer.project_root(repo) / "agentcore"
    entrypoint = _scaffold(config_dir, source)
    project_path = config_dir / "agentcore.json"
    project_path.write_text('{"name":"pellierrc"}\n')

    with pytest.raises(SystemExit, match="review the pinned scaffold"):
        _render(renderer, repo)

    assert entrypoint.read_text() == source
    assert project_path.read_text() == '{"name":"pellierrc"}\n'
    assert not (renderer.project_root(repo) / "runtime-src").exists()


def test_configuration_only_render_then_scaffold_rerender(tmp_path: Path, monkeypatch) -> None:
    renderer = _load_renderer(monkeypatch, suffix="rc", workshop_format="governed")
    repo = tmp_path / "repo"
    _seed_sources(repo, renderer)
    root, project = _render(renderer, repo)
    assert project["tags"]["Name"] == "pellier-governed-managed"
    assert not (root / "agentcore" / "cdk").exists()

    entrypoint = _scaffold(root / "agentcore")
    _, rerendered = _render(renderer, repo)

    assert rerendered == project
    assert "...spec.tags," in entrypoint.read_text()
