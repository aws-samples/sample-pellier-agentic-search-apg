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

Each Lambda also stamps a tools fingerprint of its own sources (``common/fingerprint.py``).
Task 3A edits one of them, the Gateway's tool schemas, so every participant deploy ships
the checkout's copy into both Lambdas.

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
    "services/store_tools.py": REPO / "solutions" / "lab-1-retrieve" / "retrieval"
    / "store_tools_solution.py",
    "services/search_plan.py": REPO / "solutions" / "lab-1-retrieve" / "retrieval"
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


def test_staff_package_imports_without_loading_models_or_database_pool(tmp_path):
    import os
    import subprocess

    module = _deploy_lambda()
    files = module.package_files(str(DEPLOY / "pellier_operator_tools.py"),
                                 "pellier_operator_tools.lambda_handler")
    for relative, source in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    code = """
import sys
sys.path.insert(0, sys.argv[1])
import pellier_operator_tools
assert len(pellier_operator_tools.TOOLS) == 7
assert 'strands' not in sys.modules
assert 'services.database' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-I", "-c", code, str(tmp_path)], capture_output=True,
                            text=True, env={**os.environ, "AWS_EC2_METADATA_DISABLED": "true",
                                            "AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test"})
    assert result.returncode == 0, result.stderr


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
    """Lab 1 changes Lambda's digest; Runtime and tools must each match their source."""
    sys.path[:0] = [str(REPO / "scripts"), str(DEPLOY)]
    import lab3_check
    import render_agentcore_project
    from common.fingerprint import compute_fingerprint as tools_fingerprint
    from deploy_lambda import package_files

    _, deployed = render_agentcore_project._render_runtime_source(tmp_path / "staged", BACKEND)
    solved = tmp_path / "solved" / "pellier" / "backend"
    shutil.copytree(BACKEND, solved, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
    for name, solution in SOLUTION_COPIES.items():
        shutil.copyfile(solution, solved / name)
    row = {"audit_id": 1, "turn_id": "turn-1", "tool": "get_tickets",
           "deployed_fingerprint": deployed}
    for checkout in (BACKEND, solved):
        local = compute_fingerprint(checkout, skills_root=REPO)
        files = package_files(str(DEPLOY / "pellier_store_tools.py"), "pellier_store_tools.lambda_handler")
        files["services/search_plan.py"] = checkout / "services/search_plan.py"
        tools = tools_fingerprint(files)
        receipt = {**row, "deployed_tools_fingerprint": tools}
        assert lab3_check.judge_build(receipt, local, tools).state == "PASSED", checkout
        assert lab3_check.judge_build(receipt, local, "stale").state == "FAILED"


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


# ---------------------------------------------------------------------------
# A participant deploy keeps both tools Lambdas on this checkout's tool schemas
# ---------------------------------------------------------------------------


class _Lambdas:
    """Deployed packages by function name, read and replaced the way the swaps do it."""

    def __init__(self, packages: dict[str, bytes]) -> None:
        self.packages = packages

    def get_function(self, FunctionName: str) -> dict:  # noqa: N803 - boto3's name
        return {"Code": {"Location": FunctionName}}

    def update_function_code(self, FunctionName: str, ZipFile: bytes) -> dict:  # noqa: N803
        self.packages[FunctionName] = ZipFile
        return {}

    def get_waiter(self, name: str):
        class Waiter:
            def wait(self, FunctionName: str) -> None:  # noqa: N803
                return None

        return Waiter()


def _provisioner():
    spec = importlib.util.spec_from_file_location(
        "provisioner_lambda_package_test", REPO / "scripts" / "provision_agentcore_end_to_end.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _package(deploy_lambda, entry: str, schemas: Path) -> bytes:
    files = deploy_lambda.package_files(str(DEPLOY / f"{entry}.py"), f"{entry}.lambda_handler")
    files["gateway_tool_schemas.py"] = schemas
    return _zip({name: Path(path).read_bytes() for name, path in files.items()})


def _stamped(package: bytes, root: Path, source_paths) -> str:
    """The tools fingerprint the Lambda computes from its own package when it runs."""
    from common.fingerprint import deployed_fingerprint

    zipfile.ZipFile(io.BytesIO(package)).extractall(root)
    return deployed_fingerprint(root, source_paths=source_paths)


def _two_lambdas(provisioner, monkeypatch, schemas: Path) -> tuple[_Lambdas, str, str]:
    """Both tools Lambdas, packaged with ``schemas``, behind a fake Lambda API."""
    targets = provisioner._deployment_targets(provisioner.deployment_identity())
    store, operator = (f"{targets[surface]['server_name']}-function"
                       for surface in ("store", "operator"))
    lambdas = _Lambdas({
        store: _package(provisioner.deploy_lambda, "pellier_store_tools", schemas),
        operator: _package(provisioner.deploy_lambda, "pellier_operator_tools", schemas),
    })
    monkeypatch.setattr(provisioner.boto3, "client", lambda *args, **kwargs: lambdas)
    monkeypatch.setattr(provisioner.deploy_lambda.urllib.request, "urlopen",
                        lambda url, timeout: io.BytesIO(lambdas.packages[url]))
    monkeypatch.setattr(provisioner, "_lab1_checks_failing", lambda repo, env: [])
    return lambdas, store, operator


PROVISIONED_SCHEMAS = (REPO / "solutions" / "lab-3-deploy" / "gateway"
                       / "gateway_tool_schemas_solution.py")


@pytest.mark.parametrize("reset", [False, True], ids=["deploy", "reset"])
def test_a_participant_deploy_keeps_both_lambdas_on_this_checkouts_tool_schemas(
        monkeypatch, tmp_path: Path, reset: bool) -> None:
    """Task 3A edits gateway_tool_schemas.py, which both tools Lambdas import. On the
    2026-11-08 test event the Lab 3 deploy left both Lambdas on the provisioned copy, so the
    staff proof expected a tools fingerprint the operator Lambda never stamped and the deploy
    failed; Task 3B would have read "another build answered" for the store Lambda."""
    monkeypatch.syspath_prepend(str(DEPLOY))
    monkeypatch.syspath_prepend(str(REPO / "scripts"))
    import lab3_check
    from common.fingerprint import OPERATOR_SOURCE_PATHS, SOURCE_PATHS

    provisioner = _provisioner()
    checkout = DEPLOY / "gateway_tool_schemas.py"
    assert PROVISIONED_SCHEMAS.read_bytes() != checkout.read_bytes()
    lambdas, store, operator = _two_lambdas(provisioner, monkeypatch, PROVISIONED_SCHEMAS)

    shipped = provisioner._ship_participant_modules(
        REPO, region="us-east-1", identity=provisioner.deployment_identity(), env={},
        reset_to_starters=reset)

    assert shipped["tool_schemas"] == {"store": True, "operator": True}
    assert ("lab1_search" in shipped) is not reset
    for name in (store, operator):
        archive = zipfile.ZipFile(io.BytesIO(lambdas.packages[name]))
        assert archive.read("gateway_tool_schemas.py") == checkout.read_bytes(), name
    assert (_stamped(lambdas.packages[operator], tmp_path / "operator", OPERATOR_SOURCE_PATHS)
            == provisioner._operator_tools_fingerprint())
    if not reset:
        assert (_stamped(lambdas.packages[store], tmp_path / "store", SOURCE_PATHS)
                == lab3_check.local_tools_fingerprint())


@pytest.mark.parametrize("reset", [False, True], ids=["deploy", "reset"])
def test_a_task_3a_file_edited_outside_its_block_stops_the_deploy_before_anything_ships(
        monkeypatch, tmp_path: Path, reset: bool) -> None:
    """Both Lambdas import the file, and the Gateway is rendered from it, so an edit outside
    the block (a tool dropped from the catalog fails the store Lambda's import) must stop the
    deploy before either package changes."""
    monkeypatch.syspath_prepend(str(DEPLOY))
    provisioner = _provisioner()
    stray = tmp_path / "gateway_tool_schemas.py"
    stray.write_text((DEPLOY / "gateway_tool_schemas.py").read_text() + "\nSTRAY = True\n")
    monkeypatch.setattr(provisioner, "_CHECKOUT_TOOL_SCHEMAS", stray)
    lambdas, store, operator = _two_lambdas(provisioner, monkeypatch, PROVISIONED_SCHEMAS)
    before = dict(lambdas.packages)

    with pytest.raises(RuntimeError, match="changed outside its marked block") as refused:
        provisioner._ship_participant_modules(
            REPO, region="us-east-1", identity=provisioner.deployment_identity(), env={},
            reset_to_starters=reset)
    assert lambdas.packages == before
    message = str(refused.value)
    assert "    +STRAY = True" in message
    assert "uv run scripts/lab_run.py solution --lab 3 --task 3A" in message


def test_blank_lines_and_trailing_spaces_outside_the_block_still_deploy(
        monkeypatch, tmp_path: Path) -> None:
    """A stray Enter or space while reading the file changes nothing the Lambdas import or
    the Gateway publishes, so it must not stop a participant's deploy."""
    monkeypatch.syspath_prepend(str(DEPLOY))
    provisioner = _provisioner()
    lines = (DEPLOY / "gateway_tool_schemas.py").read_text().splitlines()
    edited = tmp_path / "gateway_tool_schemas.py"
    edited.write_text("\n\n".join(f"{line}   " for line in lines) + "\n\n")
    monkeypatch.setattr(provisioner, "_CHECKOUT_TOOL_SCHEMAS", edited)
    lambdas, store, operator = _two_lambdas(provisioner, monkeypatch, PROVISIONED_SCHEMAS)

    shipped = provisioner._ship_participant_modules(
        REPO, region="us-east-1", identity=provisioner.deployment_identity(), env={},
        reset_to_starters=True)

    assert shipped["tool_schemas"] == {"store": True, "operator": True}
    for name in (store, operator):
        archive = zipfile.ZipFile(io.BytesIO(lambdas.packages[name]))
        assert archive.read("gateway_tool_schemas.py") == edited.read_bytes(), name
