"""The Gateway Lambda's zip carries a working Lab 1 search, and Lab 3B cannot tell.

Bootstrap packages the store-tools Lambda once, from the checkout participants
start with, so a zip of the live files would ship Lab 1's starters. It carries
the solution copies of ``services/store_tools.py`` and ``services/search_plan.py``
instead; every other file comes from the checkout. A participant deploy later
swaps in the participant's own search plan, once both Lab 1 checks pass and
nothing outside its marked region was edited, without rebuilding the package
(``deploy_lambda.replace_package_modules``).

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
import sys
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


def test_lab_3b_proves_the_build_whatever_state_lab_1_is_in(tmp_path: Path) -> None:
    """A participant's Lab 1 edits change the zip's twins, never the digest 3B compares."""
    sys.path[:0] = [str(REPO / "scripts"), str(DEPLOY)]
    import lab3_check
    import render_agentcore_project

    _, deployed = render_agentcore_project._render_runtime_source(tmp_path / "staged", BACKEND)
    solved = tmp_path / "solved" / "pellier" / "backend"
    shutil.copytree(BACKEND, solved, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
    for name, solution in SOLUTION_COPIES.items():
        shutil.copyfile(solution, solved / name)
    row = {"audit_id": 1, "turn_id": "turn-1", "tool": "get_tickets",
           "deployed_fingerprint": deployed}
    for checkout in (BACKEND, solved):
        local = compute_fingerprint(checkout, skills_root=REPO)
        assert lab3_check.judge_build(row, local).state == "PROVED", checkout


# ---------------------------------------------------------------------------
# A participant deploy ships the participant's own Lab 1 search once it passes
# ---------------------------------------------------------------------------


def _zip(entries: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name, (2026, 10, 26, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return out.getvalue()


class _Lambda:
    """The Lambda API as the swap uses it: read the code, upload a zip, wait for it."""

    def __init__(self, deployed: bytes) -> None:
        self.deployed, self.uploaded, self.waited = deployed, None, []

    def get_function(self, FunctionName: str) -> dict:  # noqa: N803 - boto3's name
        return {"Code": {"Location": f"https://code.example.test/{FunctionName}.zip"}}

    def update_function_code(self, FunctionName: str, ZipFile: bytes) -> dict:  # noqa: N803
        self.uploaded = ZipFile
        return {"CodeSha256": "new"}

    def get_waiter(self, name: str):
        client = self

        class Waiter:
            def wait(self, FunctionName: str) -> None:  # noqa: N803
                client.waited.append((name, FunctionName))

        return Waiter()


@pytest.fixture
def deployed(monkeypatch) -> _Lambda:
    deploy_lambda = _deploy_lambda()
    client = _Lambda(_zip({"services/store_tools.py": b"supplied search",
                           "services/search_plan.py": b"supplied plan",
                           "httpx/__init__.py": b"a dependency"}))
    monkeypatch.setattr(deploy_lambda.urllib.request, "urlopen",
                        lambda url, timeout: io.BytesIO(client.deployed))
    client.module = deploy_lambda
    return client


def test_the_swap_changes_only_the_named_modules(deployed, tmp_path: Path) -> None:
    (tmp_path / "store_tools.py").write_bytes(b"your search")
    (tmp_path / "search_plan.py").write_bytes(b"your plan")
    changed = deployed.module.replace_package_modules(
        deployed, "pellier-store-tools-server-function",
        {"services/store_tools.py": tmp_path / "store_tools.py",
         "services/search_plan.py": tmp_path / "search_plan.py"})
    assert changed
    archive = zipfile.ZipFile(io.BytesIO(deployed.uploaded))
    assert archive.read("services/store_tools.py") == b"your search"
    assert archive.read("services/search_plan.py") == b"your plan"
    assert archive.read("httpx/__init__.py") == b"a dependency"
    assert sorted(archive.namelist()) == sorted(
        ["services/store_tools.py", "services/search_plan.py", "httpx/__init__.py"])
    for name in archive.namelist():  # the Lambda runtime's user must be able to read them
        assert (archive.getinfo(name).external_attr >> 16) & 0o444 == 0o444, name
    assert deployed.waited == [("function_updated_v2", "pellier-store-tools-server-function")]


def test_a_package_that_already_carries_the_files_is_not_uploaded(deployed,
                                                                   tmp_path: Path) -> None:
    (tmp_path / "store_tools.py").write_bytes(b"supplied search")
    changed = deployed.module.replace_package_modules(
        deployed, "pellier-store-tools-server-function",
        {"services/store_tools.py": tmp_path / "store_tools.py"})
    assert not changed and deployed.uploaded is None and deployed.waited == []
