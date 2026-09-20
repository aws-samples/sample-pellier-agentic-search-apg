"""Observatory must read every schema in a clean backend interpreter."""
from pathlib import Path
import subprocess
import sys


def test_schema_load_does_not_require_deployment_import_path():
    path = Path(__file__).resolve().parents[3] / "scripts/deploy/gateway_tool_schemas.py"
    process = subprocess.run([sys.executable, "-I", "-c",
        "import runpy,sys; s=runpy.run_path(sys.argv[1]); "
        "assert len(s['TOOL_SCHEMAS'])==4; "
        "assert 'replace_damaged_item' in s['canonical_tool_names']()", str(path)],
        capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
