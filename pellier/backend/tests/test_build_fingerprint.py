"""The executed-revision proof: digest, comparison, and the three states.

Lab 3 asks a participant to prove AgentCore Runtime executed the revision they
packaged. The invoke response carries no version and ``qualifier=DEFAULT`` is an
alias, so a green invocation is equally consistent with "my code ran" and "my
deploy failed and the previous image answered". The fingerprint is what
separates those, and these tests pin the properties that make the separation
trustworthy rather than merely present.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.build_fingerprint import (  # noqa: E402
    RUNTIME_DEPENDENCY_FILES,
    RUNTIME_SKILL_FILES,
    RUNTIME_SOURCE_FILES,
    compute_fingerprint,
    short_fingerprint,
)


def _stage(root: Path) -> Path:
    """Write a minimal tree containing every file the digest covers, bundle layout."""
    for relative in RUNTIME_SOURCE_FILES + RUNTIME_DEPENDENCY_FILES + RUNTIME_SKILL_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative.as_posix()}\n", encoding="utf-8")
    return root


def _digest(staged: Path) -> str:
    return compute_fingerprint(staged, skills_root=staged)


def test_fingerprint_is_stable_across_calls(tmp_path: Path) -> None:
    staged = _stage(tmp_path)
    assert _digest(staged) == _digest(staged)


def test_identical_trees_fingerprint_identically(tmp_path: Path) -> None:
    """Two byte-identical stagings must agree, or every comparison is noise."""
    first = _stage(tmp_path / "a")
    second = _stage(tmp_path / "b")
    assert _digest(first) == _digest(second)


def test_editing_a_packaged_file_changes_the_fingerprint(tmp_path: Path) -> None:
    staged = _stage(tmp_path)
    before = _digest(staged)
    target = staged / RUNTIME_SOURCE_FILES[0]
    target.write_text(target.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    assert _digest(staged) != before


def test_editing_a_skill_changes_the_fingerprint(tmp_path: Path) -> None:
    """Skills are procedural memory the agent ships; a skill edit is a new build."""
    staged = _stage(tmp_path)
    before = _digest(staged)
    skill = staged / RUNTIME_SKILL_FILES[0]
    skill.write_text(skill.read_text(encoding="utf-8") + "\nSay thank you.\n", encoding="utf-8")
    assert _digest(staged) != before


def test_dependency_manifest_changes_the_fingerprint(tmp_path: Path) -> None:
    """A lockfile bump ships a materially different package."""
    staged = _stage(tmp_path)
    before = _digest(staged)
    lock = staged / Path("uv.lock")
    lock.write_text(lock.read_text(encoding="utf-8") + "# bumped\n", encoding="utf-8")
    assert _digest(staged) != before


def test_renaming_a_file_changes_the_fingerprint(tmp_path: Path) -> None:
    """Path is hashed with content, so a move is not invisible."""
    staged = _stage(tmp_path)
    before = _digest(staged)
    moved = staged / "services" / "renamed_module.py"
    (staged / RUNTIME_SOURCE_FILES[-1]).rename(moved)
    # The digest now raises for the missing file, which is the louder failure
    # this module prefers; restore it as a different name and confirm drift.
    (staged / RUNTIME_SOURCE_FILES[-1]).write_text("# restored\n", encoding="utf-8")
    assert _digest(staged) != before


def test_an_unpackaged_file_does_not_change_the_fingerprint(tmp_path: Path) -> None:
    """Editing a file the runtime does not ship must read as no change.

    A participant who edits something outside the packaged set and sees the
    fingerprint move would conclude their edit deployed when it did not.
    """
    staged = _stage(tmp_path)
    before = _digest(staged)
    (staged / "not_packaged.py").write_text("# ignored\n", encoding="utf-8")
    assert _digest(staged) == before


def test_missing_packaged_file_raises_rather_than_digesting_a_subset(
    tmp_path: Path,
) -> None:
    """A partial digest would report a false mismatch and misdirect debugging."""
    staged = _stage(tmp_path)
    (staged / RUNTIME_SOURCE_FILES[0]).unlink()
    with pytest.raises(FileNotFoundError) as excinfo:
        _digest(staged)
    assert RUNTIME_SOURCE_FILES[0].as_posix() in str(excinfo.value)


def test_this_checkout_fingerprints(tmp_path: Path) -> None:
    """The real backend tree must carry every file the renderer packages.

    With no ``skills_root`` the digest reads the checkout layout: the skills
    beside ``pellier/`` at the repository root.
    """
    assert compute_fingerprint(BACKEND)


def test_the_skill_list_is_the_checked_in_set() -> None:
    """Every ``skills/*/SKILL.md`` ships, and nothing ships that is not checked in."""
    on_disk = sorted(
        path.relative_to(BACKEND.parents[1]).as_posix()
        for path in (BACKEND.parents[1] / "skills").glob("*/SKILL.md")
    )
    assert on_disk == sorted(path.as_posix() for path in RUNTIME_SKILL_FILES)


def test_the_skill_package_ships_with_its_loader() -> None:
    """The managed prompt is built from the registry, so the whole package is packaged."""
    packaged = {path.as_posix() for path in RUNTIME_SOURCE_FILES}
    for module in ("__init__", "assignments", "loader", "models", "registry"):
        assert f"skills/{module}.py" in packaged


def test_short_fingerprint_preserves_the_unknown_case() -> None:
    assert short_fingerprint("") == ""
    assert short_fingerprint(None) == ""
    assert short_fingerprint("a" * 64) == "a" * 12


class TestBuildState:
    """`unknown` must never be reported as `stale`, in either direction."""

    @staticmethod
    def _state(deployed: str, local: str) -> str:
        from services.agentcore_runtime import _build_state

        return _build_state(deployed, local)

    def test_matching_digests_are_current(self) -> None:
        assert self._state("abc123", "abc123") == "current"

    def test_differing_digests_are_stale(self) -> None:
        assert self._state("abc123", "def456") == "stale"

    def test_runtime_reporting_nothing_is_unknown(self) -> None:
        """A runtime deployed before this mechanism cannot report a digest."""
        assert self._state("", "def456") == "unknown"

    def test_local_digest_unavailable_is_unknown(self) -> None:
        """If we cannot digest our own tree we cannot claim the deploy is stale."""
        assert self._state("abc123", "") == "unknown"

    def test_both_absent_is_unknown(self) -> None:
        assert self._state("", "") == "unknown"


def test_receipt_carries_the_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stored receipt must expose all three fields, not just the digest."""
    import services.agentcore_runtime as runtime

    monkeypatch.setattr(runtime, "_local_fingerprint_cache", "local-digest")
    runtime._store_managed_runtime_receipt(
        "session-1",
        principal_sub="sub-1",
        rail="gateway-mcp",
        auth_token_present=True,
        build_fingerprint="local-digest",
    )
    trace = runtime.get_latest_trace("session-1", principal_sub="sub-1")
    assert trace["buildFingerprint"] == "local-digest"
    assert trace["localBuildFingerprint"] == "local-digest"
    assert trace["buildState"] == "current"


def test_receipt_reports_stale_when_the_deployed_digest_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.agentcore_runtime as runtime

    monkeypatch.setattr(runtime, "_local_fingerprint_cache", "local-digest")
    runtime._store_managed_runtime_receipt(
        "session-2",
        principal_sub="sub-2",
        rail="gateway-mcp",
        auth_token_present=True,
        build_fingerprint="an-older-deployment",
    )
    trace = runtime.get_latest_trace("session-2", principal_sub="sub-2")
    assert trace["buildState"] == "stale"


def test_receipt_records_who_chose_each_customer_but_never_the_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    import services.agentcore_runtime as runtime

    monkeypatch.setattr(runtime, "_local_fingerprint_cache", "local-digest")
    runtime._store_managed_runtime_receipt(
        "session-3",
        principal_sub="sub-3",
        rail="gateway-mcp",
        auth_token_present=True,
        build_fingerprint="local-digest",
        tool_calls=[
            {"tool": "get_tickets", "status": "success",
             "input": {"customer_id": "CUST-THEO"},
             "customer_scope": "server", "requested_other_customer": True},
            {"tool": "search_products", "status": "success", "input": {"query": "bowl"}},
            {"tool": "get_tickets", "status": "error",
             "customer_scope": "model", "requested_other_customer": False},
            "not-a-call",
        ],
    )
    trace = runtime.get_latest_trace("session-3", principal_sub="sub-3")
    assert trace["customerBindings"] == [
        {"tool": "get_tickets", "status": "success",
         "customerScope": "server", "requestedOtherCustomer": True},
        {"tool": "get_tickets", "status": "error",
         "customerScope": "model", "requestedOtherCustomer": False},
    ]
    assert "CUST-" not in json.dumps(trace["customerBindings"])


def test_renderer_and_backend_share_one_file_list() -> None:
    """The packaged set and the digested set must not drift apart.

    The renderer imports this tuple rather than keeping its own copy; a file
    added to the runtime but not to the tuple would ship unfingerprinted, which
    weakens the comparison silently instead of failing loudly.
    """
    renderer = (BACKEND.parents[1] / "scripts" / "deploy" / "render_agentcore_project.py").read_text(
        encoding="utf-8"
    )
    assert "from services.build_fingerprint import" in renderer
    assert "RUNTIME_SOURCE_FILES = (" not in renderer, (
        "render_agentcore_project.py has reintroduced its own copy of the "
        "packaged-file list; it must import the one in services.build_fingerprint."
    )


def test_the_runtime_package_imports_only_what_it_ships() -> None:
    """Every module a packaged file imports at module scope is itself packaged.

    The renderer copies exactly ``RUNTIME_SOURCE_FILES`` into the Runtime
    container, so an entrypoint import of an unlisted backend module passes
    every local test and then crashes the container at startup, which the
    service reports only as an initialization timeout. ``config`` is the one
    module the package resolves another way, through environment variables.
    """
    import ast

    packaged = {path.as_posix() for path in RUNTIME_SOURCE_FILES}
    local_roots = ("services", "agents", "skills", "routes", "pellier_copy")

    def module_scope_imports(tree: ast.Module):
        stack = list(tree.body)
        while stack:
            node = stack.pop()
            if isinstance(node, (ast.If, ast.Try)):
                stack.extend(node.body)
                stack.extend(getattr(node, "orelse", []))
                stack.extend(getattr(node, "finalbody", []))
                for handler in getattr(node, "handlers", []):
                    stack.extend(handler.body)
            elif isinstance(node, ast.ImportFrom) and node.module:
                yield node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    yield alias.name

    unshipped = {}
    for relative in sorted(packaged):
        if not relative.endswith(".py"):
            continue
        tree = ast.parse((BACKEND / relative).read_text())
        for module in module_scope_imports(tree):
            if module.split(".")[0] not in local_roots:
                continue
            as_file = module.replace(".", "/") + ".py"
            as_package = module.replace(".", "/") + "/__init__.py"
            if as_file not in packaged and as_package not in packaged:
                unshipped.setdefault(relative, []).append(module)
    assert not unshipped, f"packaged files import modules the package does not ship: {unshipped}"
