"""A rerun of the Lambda deployer must not rewrite which deployment an IAM role belongs to.

The own-account teardown deletes a role only when its PellierWorkshopId tag is that
deployment's id. In the owner's account, a deployment made on 2026-10-06 had its store-tools
role created with the right id and later retagged `dat416`, the deployer's fallback when
WORKSHOP_ID is unset, because a rerun on an existing role overwrote the tag.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[3]


def _deployer() -> Any:
    spec = importlib.util.spec_from_file_location(
        "role_tags_deploy_lambda", REPO / "scripts" / "deploy" / "deploy_lambda.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.time = SimpleNamespace(sleep=lambda _seconds: None)
    return module


class _Exists(Exception):
    pass


def _iam(existing_tags: List[Dict[str, str]] | None) -> SimpleNamespace:
    calls: List[tuple[str, Dict[str, Any]]] = []

    def create_role(**kwargs: Any) -> Dict[str, Any]:
        calls.append(("create_role", kwargs))
        if existing_tags is not None:
            raise _Exists()
        return {"Role": {"Arn": "arn:aws:iam::123456789012:role/r"}}

    def get_role(**kwargs: Any) -> Dict[str, Any]:
        calls.append(("get_role", kwargs))
        return {"Role": {"Arn": "arn:aws:iam::123456789012:role/r", "Tags": existing_tags}}

    def record(name: str) -> Any:
        return lambda **kwargs: calls.append((name, kwargs))

    return SimpleNamespace(
        calls=calls,
        exceptions=SimpleNamespace(EntityAlreadyExistsException=_Exists),
        create_role=create_role,
        get_role=get_role,
        tag_role=record("tag_role"),
        put_role_policy=record("put_role_policy"),
    )


RERUN_TAGS = {"Project": "pellier", "PellierWorkshopId": "dat416"}


def _tagged(iam: SimpleNamespace) -> List[Dict[str, str]]:
    return [tag for name, kw in iam.calls if name == "tag_role" for tag in kw["Tags"]]


def test_a_rerun_keeps_the_deployment_id_the_role_was_created_with() -> None:
    deployer = _deployer()
    deployer.iam_client = _iam([{"Key": "PellierWorkshopId", "Value": "p1cf5ad10"}])
    deployer.create_iam_role("r", {}, {}, RERUN_TAGS)
    assert _tagged(deployer.iam_client) == [{"Key": "Project", "Value": "pellier"}]


def test_a_rerun_adds_the_tags_an_untagged_role_lacks() -> None:
    deployer = _deployer()
    deployer.iam_client = _iam([])
    deployer.create_iam_role("r", {}, {}, RERUN_TAGS)
    assert sorted(t["Key"] for t in _tagged(deployer.iam_client)) == [
        "PellierWorkshopId", "Project"]


def test_a_rerun_on_a_fully_tagged_role_writes_no_tags() -> None:
    deployer = _deployer()
    deployer.iam_client = _iam([{"Key": "Project", "Value": "pellier"},
                                {"Key": "PellierWorkshopId", "Value": "p1cf5ad10"}])
    deployer.create_iam_role("r", {}, {}, RERUN_TAGS)
    assert [name for name, _ in deployer.iam_client.calls] == [
        "create_role", "get_role", "put_role_policy"]


def test_a_new_role_is_created_with_every_tag() -> None:
    deployer = _deployer()
    deployer.iam_client = _iam(None)
    deployer.create_iam_role("r", {}, {}, RERUN_TAGS)
    (_, created), = [c for c in deployer.iam_client.calls if c[0] == "create_role"]
    assert {t["Key"]: t["Value"] for t in created["Tags"]} == RERUN_TAGS
