"""First-account CDK bootstrap uses the verified AgentCore scaffold version."""

import json
import os
from pathlib import Path
import subprocess
import sys


def test_bootstrap_and_recovery_use_the_same_exact_cdk_version(tmp_path):
    source = (Path(__file__).resolve().parents[3] / "scripts/bootstrap-environment.sh").read_text()
    block = source.split('log "Bootstrapping CDK', 1)[1].split("\nfi\n", 1)[0]
    block = 'log "Bootstrapping CDK' + block + "\nfi\n"
    binary = tmp_path / "npx"
    captured = tmp_path / "command.json"
    binary.write_text(f'''#!{sys.executable}
import json,os,sys
from pathlib import Path
Path({str(captured)!r}).write_text(json.dumps({{"args":sys.argv[1:],"region":os.environ.get("AWS_REGION"),"default_region":os.environ.get("AWS_DEFAULT_REGION")}}))
''')
    binary.chmod(0o755)
    prelude = 'log() { :; }; warn() { :; }; aws() { printf "123456789012\\n"; };\n'
    result = subprocess.run(["bash", "-eu", "-c", prelude + block], env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "AWS_REGION": "us-east-1"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(captured.read_text()) == {"args": ["-y", "aws-cdk@2.1126.0", "bootstrap", "aws://123456789012/us-east-1"], "region": "us-east-1", "default_region": "us-east-1"}
    assert "'npx aws-cdk@2.1126.0 bootstrap'" in source
