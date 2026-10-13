"""The Gateway Lambda's zip carries Lab 1's finished search code, and Lab 3B cannot tell.

Bootstrap packages the store-tools Lambda once, from the checkout participants
start with, and Lab 3's participant deploy reuses that function rather than
repackaging it. A zip built from the live files would therefore ship Lab 1's
starters to the Gateway for the whole event, however far a participant got. The
zip instead carries the solution copies of ``services/store_tools.py`` and
``services/search_plan.py``; every other file comes from the checkout.

Lab 3B compares the build fingerprint a Gateway call carries with this
checkout's. The Runtime stamps that fingerprint from its own package
(``RUNTIME_SOURCE_FILES``); the Lambda relays it into ``tool_audit`` and never
digests its zip. These tests keep it that way: no solution copy may be a
fingerprinted runtime source, and laying the zip over the checkout must leave
the fingerprint unchanged. If either fails, 3B would compare a build the
Gateway does not run, or fail for every participant.

The tests build the real zip with ``deploy_lambda.build_package``, without
dependencies or AWS.
"""

from __future__ import annotations

import importlib.util
import io
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from services.build_fingerprint import (
    RUNTIME_DEPENDENCY_FILES,
    RUNTIME_SOURCE_FILES,
    compute_fingerprint,
)

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "pellier" / "backend"
DEPLOY = REPO / "scripts" / "deploy"
SERVER = DEPLOY / "pellier_store_tools.py"
SOLUTION_COPIES = {
    "services/store_tools.py": REPO / "solutions" / "the-quiet-search" / "retrieval"
    / "store_tools_solution.py",
    "services/search_plan.py": REPO / "solutions" / "the-quiet-search" / "retrieval"
    / "search_plan_solution.py",
}
_MARKER_BLOCK = re.compile(
    r"# === WORKSHOP - [^\n]*: START ===.*?# === WORKSHOP - [^\n]*: END ===", re.DOTALL
)


def _deploy_lambda():
    spec = importlib.util.spec_from_file_location("deploy_lambda_package_test",
                                                  DEPLOY / "deploy_lambda.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def package() -> dict[str, object]:
    deploy_lambda = _deploy_lambda()
    files = deploy_lambda.package_files(str(SERVER), "pellier_store_tools.lambda_handler")
    before = compute_fingerprint(BACKEND)
    archive = zipfile.ZipFile(io.BytesIO(deploy_lambda.build_package(files, [])))
    entries = {name: archive.read(name) for name in archive.namelist()}
    return {"module": deploy_lambda, "files": files, "entries": entries,
            "fingerprint_before": before}


def test_the_zip_carries_the_solution_copies_of_lab_1s_search_modules(package) -> None:
    files, entries = package["files"], package["entries"]
    assert set(package["module"].SOLUTION_COPIES) == set(SOLUTION_COPIES)
    for name, solution in SOLUTION_COPIES.items():
        assert Path(files[name]).resolve() == solution.resolve(), name
        assert entries[name] == solution.read_bytes(), name


def test_every_other_file_in_the_zip_is_the_checkouts_own(package) -> None:
    files, entries = package["files"], package["entries"]
    assert set(entries) == set(files)
    assert entries["pellier_store_tools.py"] == SERVER.read_bytes()
    for name, source in files.items():
        if name not in SOLUTION_COPIES:
            parents = Path(source).resolve().parents
            assert REPO in parents and REPO / "solutions" not in parents, name
            assert entries[name] == Path(source).read_bytes(), name


@pytest.mark.parametrize("name", sorted(SOLUTION_COPIES))
def test_each_solution_copy_is_its_live_module_outside_the_marked_regions(name: str) -> None:
    """A copy that drifted would ship last month's store tools to the Gateway."""
    solution = SOLUTION_COPIES[name].read_text(encoding="utf-8")
    live = (BACKEND / name).read_text(encoding="utf-8")
    assert len(_MARKER_BLOCK.findall(solution)) == len(_MARKER_BLOCK.findall(live)), name
    assert _MARKER_BLOCK.sub("<REGION>", solution) == _MARKER_BLOCK.sub("<REGION>", live), (
        f"{SOLUTION_COPIES[name].relative_to(REPO)} drifted from {name} outside its marked "
        "regions; copy the live module and put the answers back inside the markers"
    )


def test_no_solution_copy_is_a_fingerprinted_runtime_source() -> None:
    runtime = {path.as_posix() for path in RUNTIME_SOURCE_FILES}
    assert not runtime & set(SOLUTION_COPIES), (
        "a solution-backed Lambda module is also a Runtime source, so the zip and the "
        "build fingerprint would describe different code"
    )


def test_laying_the_zip_over_the_checkout_leaves_the_build_fingerprint_unchanged(
    package, tmp_path: Path
) -> None:
    """Lab 3B's two sides, the Runtime's digest and this checkout's, cannot see the zip."""
    entries = package["entries"]
    for relative in RUNTIME_SOURCE_FILES + RUNTIME_DEPENDENCY_FILES:
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BACKEND / relative, tmp_path / relative)
    shared = [relative for relative in RUNTIME_SOURCE_FILES if relative.as_posix() in entries]
    assert shared, "no file is in both the zip and the Runtime package; the overlay proves nothing"
    for relative in shared:
        (tmp_path / relative).write_bytes(entries[relative.as_posix()])

    checkout = compute_fingerprint(BACKEND)
    assert checkout == package["fingerprint_before"], "building the zip changed the checkout"
    assert compute_fingerprint(tmp_path, skills_root=REPO) == checkout
