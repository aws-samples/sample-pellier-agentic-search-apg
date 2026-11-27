"""The root template and its three nested stacks agree on every value they pass.

A required parameter the root does not pass, or an output it reads that the child lacks, fails
the whole account's provisioning, and only a fresh stack shows it. These checks read the
templates as text, so they hold the wiring before any stack is built.
"""
from __future__ import annotations

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "deploy" / "own-account" / "templates"
DEPLOYABLE_REGIONS = ("us-east-1", "us-west-2")


class _Tagged(yaml.SafeLoader):
    """Reads !Tag value as {"Fn::Tag": value} (or {"Ref": value}), so intrinsics stay visible."""


def _intrinsic(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return {"Ref" if suffix == "Ref" else f"Fn::{suffix}": value}


_Tagged.add_multi_constructor("!", _intrinsic)


def _load(name: str) -> dict:
    return yaml.load((TEMPLATES / name).read_text(encoding="utf-8"), Loader=_Tagged)


def _walk(node):
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _nested_stacks() -> dict[str, tuple[dict, dict]]:
    """Each nested stack resource in the root: (its properties, its child template)."""
    root = _load("pellier-governed.yml")
    stacks = {}
    for name, resource in root["Resources"].items():
        if resource["Type"] == "AWS::CloudFormation::Stack":
            url = resource["Properties"]["TemplateURL"]["Fn::Sub"]
            stacks[name] = (resource["Properties"], _load(url.rsplit("}", 1)[-1]))
    return stacks


def test_root_nests_the_three_child_templates() -> None:
    assert sorted(_nested_stacks()) == ["CodeEditorStack", "DatabaseStack", "VpcStack"]


def test_root_passes_every_required_child_parameter_and_no_unknown_one() -> None:
    for name, (properties, child) in _nested_stacks().items():
        passed = set(properties.get("Parameters", {}))
        declared = child.get("Parameters", {})
        required = {key for key, spec in declared.items() if "Default" not in spec}
        assert required <= passed, (name, sorted(required - passed))
        assert passed <= set(declared), (name, sorted(passed - set(declared)))


def test_every_nested_output_the_root_reads_exists_in_that_child() -> None:
    stacks = _nested_stacks()
    root = _load("pellier-governed.yml")
    reads = set()
    for node in _walk(root):
        if isinstance(node, dict) and "Fn::GetAtt" in node:
            target = node["Fn::GetAtt"]
            reads.add(tuple(target.split(".", 2)) if isinstance(target, str)
                      else (target[0], *target[1].split(".", 1)))
        if isinstance(node, dict) and "Fn::Sub" in node:
            text = node["Fn::Sub"][0] if isinstance(node["Fn::Sub"], list) else node["Fn::Sub"]
            found = re.findall(r"\$\{(\w+\.Outputs\.\w+)\}", text)
            reads.update(tuple(match.split(".", 2)) for match in found)
    outputs = {(stack, "Outputs", key) for stack, (_, child) in stacks.items()
               for key in child.get("Outputs", {})}
    nested = {read for read in reads if len(read) == 3 and read[1] == "Outputs"}
    assert nested, "expected the root to read nested outputs"
    assert nested <= outputs, sorted(nested - outputs)


def test_every_mapping_lookup_covers_each_deployable_region() -> None:
    for name in ("pellier-vpc.yml", "pellier-database.yml", "pellier-code-editor.yml",
                 "pellier-governed.yml"):
        template = _load(name)
        mappings = template.get("Mappings", {})
        for node in _walk(template.get("Resources", {})):
            if isinstance(node, dict) and "Fn::FindInMap" in node:
                mapping = node["Fn::FindInMap"][0]
                if node["Fn::FindInMap"][1] == {"Ref": "AWS::Region"}:
                    assert set(DEPLOYABLE_REGIONS) <= set(mappings[mapping]), (name, mapping)


def test_the_lake_reader_role_reaches_the_box_settings() -> None:
    """Database output -> root -> box parameter -> user data -> the .env bootstrap writes."""
    properties, box = _nested_stacks()["CodeEditorStack"]
    assert properties["Parameters"]["LakeReaderRoleArn"] == {
        "Fn::GetAtt": "DatabaseStack.Outputs.LakeReaderRoleArn"}
    user_data = (TEMPLATES / "pellier-code-editor.yml").read_text(encoding="utf-8")
    assert 'export AURORA_ANALYTICS_ROLE_ARN="${LakeReaderRoleArn}"' in user_data
    bootstrap = (ROOT / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    # bootstrap runs under set -u: an unset variable must not stop a stack built before it.
    assert "AURORA_ANALYTICS_ROLE_ARN='${AURORA_ANALYTICS_ROLE_ARN:-}'" in bootstrap
    assert "LakeReaderRoleArn" in box["Parameters"]


def test_the_lake_names_agree_across_the_templates_and_the_script() -> None:
    """The role policy, the box policy and prepare must name the same bucket."""
    database = (TEMPLATES / "pellier-database.yml").read_text(encoding="utf-8")
    box = (TEMPLATES / "pellier-code-editor.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "aurora_analytics.py").read_text(encoding="utf-8")
    assert "DBClusterIdentifier: !Sub pellier-cluster-${WorkshopId}" in database
    for template in (database, box):
        assert "s3:::pellier-lake-${WorkshopId}/lake/*" in template
    assert '"pellier-lake-" + cluster.removeprefix("pellier-cluster-")' in script
    assert "DBClusterParameterGroupName: !Ref ClusterParameterGroup" in database
    assert re.search(r'^\s+aurora_analytics\.enabled: "1"$', database, re.MULTILINE)


def test_conditional_delete_can_check_only_this_workshops_run_files() -> None:
    box = _load("pellier-code-editor.yml")
    statement, = (node for node in _walk(box) if isinstance(node, dict)
                  and node.get("Sid") == "CleanupRecordedLakeFiles")
    assert set(statement["Action"]) == {"s3:GetObject", "s3:DeleteObjectVersion"}
    prefix = "arn:${AWS::Partition}:s3:::pellier-lake-${WorkshopId}/lake/*/"
    assert {resource["Fn::Sub"] for resource in statement["Resource"]} == {
        prefix + "daily_sales/week-?.parquet", prefix + "deliveries/plan.parquet"}
