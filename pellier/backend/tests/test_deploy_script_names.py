"""Every name a deploy script's functions read is bound somewhere.

A dev-account deploy (2026-10-05) stopped on ``operator_log_group``, read in the
provisioner's ``main`` after the operator Runtime was removed. The NameError
sits outside the provisioner's handled errors and on a line only a live deploy
reaches, so no other test saw it. This reads each script's symbol table: a name
a function reads but never binds must be bound at module level or be a builtin.
"""

from __future__ import annotations

import builtins
import symtable
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = (
    REPO / "scripts" / "provision_agentcore_end_to_end.py",
    *sorted((REPO / "scripts" / "deploy").glob("*.py")),
)
MODULE_ATTRIBUTES = frozenset({"__file__", "__name__", "__doc__", "__spec__"})


def _module_bindings(module: symtable.SymbolTable) -> set[str]:
    return MODULE_ATTRIBUTES | {
        symbol.get_name()
        for symbol in module.get_symbols()
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
    }


def _unbound_reads(table: symtable.SymbolTable, bound: set[str]) -> list[str]:
    unbound = [
        f"{table.get_name()}:{symbol.get_name()}"
        for symbol in table.get_symbols()
        if symbol.is_referenced()
        and symbol.is_global()
        and symbol.get_name() not in bound
        and not hasattr(builtins, symbol.get_name())
    ]
    for child in table.get_children():
        unbound.extend(_unbound_reads(child, bound))
    return unbound


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.name)
def test_every_name_a_deploy_function_reads_is_bound(script: Path) -> None:
    module = symtable.symtable(script.read_text(encoding="utf-8"), str(script), "exec")
    bound = _module_bindings(module)
    unbound = [
        name for child in module.get_children() for name in _unbound_reads(child, bound)
    ]
    assert unbound == [], f"{script.name} reads names nothing binds: {unbound}"
