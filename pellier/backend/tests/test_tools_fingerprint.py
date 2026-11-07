"""The executed Lambda identifies its own files, independently of Runtime."""
from pathlib import Path
import shutil
import sys

DEPLOY = Path(__file__).resolve().parents[3] / "scripts" / "deploy"
sys.path.insert(0, str(DEPLOY))


def test_staged_lambda_matches_its_sources_and_detects_a_stale_search_plan(tmp_path):
    from deploy_lambda import package_files
    from common.fingerprint import compute_fingerprint, deployed_fingerprint

    files = package_files(str(DEPLOY / "pellier_store_tools.py"), "pellier_store_tools.lambda_handler")
    for name, source in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    expected = compute_fingerprint(files)
    assert deployed_fingerprint(tmp_path) == expected
    plan = tmp_path / "services/search_plan.py"
    plan.write_text(plan.read_text() + "\n# changed package\n")
    assert deployed_fingerprint(tmp_path) != expected
    plan.unlink()
    assert deployed_fingerprint(tmp_path) == ""
