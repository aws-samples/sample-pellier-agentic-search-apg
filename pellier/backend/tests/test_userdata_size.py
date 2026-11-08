"""The Code Editor instance's user data fits EC2's 16 KB limit for any legal input.

A stack whose rendered user data exceeds the limit fails to create its instance. Every
placeholder gets its worst case; a new placeholder without one raises KeyError here, so
whoever adds it must size it. Workshop Studio runs the same check on its copy.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

TEMPLATE = (Path(__file__).resolve().parents[3]
            / "deploy" / "own-account" / "templates" / "pellier-code-editor.yml")
EC2_USER_DATA_LIMIT = 16 * 1024
SECRET = "arn:aws:secretsmanager:us-east-1:123456789012:secret:"
WORST_CASE = {
    "AWS::StackId": "arn:aws:cloudformation:us-east-1:123456789012:stack/" + "s" * 128 + "/" + "1" * 36,
    "AWS::Region": "us-east-1", "RepoRevision": "a" * 40,
    "RepoUrl": "https://github.com/aws-samples/sample-pellier-agentic-search-apg.git",
    "HomeFolder": "/home/participant/workshop", "CodeEditorUser": "participant",
    "SecretPlaintext.password": "p" * 32, "OriginSecretPlaintext.password": "t" * 48,
    "WorkshopId": "p12345678", "DeploymentSuffix": "z" * 12, "InfrastructureRevision": "a" * 16,
    "CognitoUserPool": "us-east-1_" + "x" * 55, "CognitoUserPoolClient": "c" * 128,
    "DBSecretArn": SECRET + "d" * 512, "StoreToolsSecretArn": SECRET + "t" * 512,
    "OperatorToolsSecretArn": SECRET + "o" * 512,
    "CognitoClientSecret": SECRET + "s" * 512, "CognitoTestCredentialsSecret": SECRET + "s" * 512,
    "DBClusterArn": "arn:aws:rds:us-east-1:123456789012:cluster:" + "d" * 63,
    "DBClusterEndpoint": "d" * 253,
    "RuntimeLogKeyArn": "arn:aws:kms:us-east-1:123456789012:key/mrk-" + "a" * 32,
    "AllowSharedTraceLogChanges": "false",
    # S3's bucket name limit, and a prefix near its 1024-byte key limit.
    "AssetsBucketName": "b" * 63, "AssetsBucketPrefix": "p" * 1000,
}


class _CloudFormation(yaml.SafeLoader):
    """Reads intrinsic tags (!Sub, !Ref, ...) as their plain YAML values."""


def _intrinsic(loader, _suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_mapping(node, deep=True)


_CloudFormation.add_multi_constructor("!", _intrinsic)


def _user_data_script() -> str:
    template = yaml.load(TEMPLATE.read_text(encoding="utf-8"), Loader=_CloudFormation)
    scripts = [resource["Properties"]["UserData"]["Fn::Base64"]
               for resource in template["Resources"].values()
               if "UserData" in resource.get("Properties", {})]
    assert len(scripts) == 1, "expected one instance with user data"
    sub = scripts[0]
    return sub[0] if isinstance(sub, list) else sub


def test_worst_case_user_data_fits_the_ec2_limit():
    rendered = re.sub(r"\$\{([^}]+)\}", lambda match: WORST_CASE[match[1]], _user_data_script())
    assert len(rendered.encode()) <= EC2_USER_DATA_LIMIT, len(rendered.encode())
    result = subprocess.run(["bash", "-n"], input=rendered, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
