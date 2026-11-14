"""Refuse to mutate governance under an AWS SDK that cannot see the fields.

The defect this prevents
-----------------------

botocore parses and serializes strictly against its bundled service model, and it drops
fields it does not know **in both directions, silently**. Measured on a workshop box:

    botocore 1.43.28   UpdatePolicy input: definition, description, policyEngineId,
                       policyId, validationMode
    botocore 1.43.51   ... the same, plus enforcementMode

Under 1.43.28, `scripts/policy_mode.py --restore-shipped` would send `update_policy` with
no `enforcementMode` at all. The service applies its own default, the API returns 200, the
diff shows nothing, and Cedar enforcement is off for the rest of the workshop. Every DENY
the labs teach becomes a line in a log.

That is why this is a hard stop and not a warning, and why it checks the SERVICE MODEL
rather than a version string: a version comparison encodes today's cut line, while the
model answers the only question that matters, which is whether the field exists.

Why an interpreter can be wrong at all
--------------------------------------

The validated dependency set is `pellier/backend/requirements.lock`, which pins
botocore 1.43.51. WHERE that set lives differs by host, and assuming either answer is how
this goes wrong:

    workshop box    installed into the participant's ~/.local by
                    bootstrap-environment.sh. `python3` IS the validated interpreter and
                    there is no venv at all.
    developer box   a `pellier/backend/.venv`, and the ambient `python3` is whatever the
                    machine happens to have. Measured here: 1.43.28.

So the guard checks the SDK the running interpreter actually has, rather than checking
which path it was launched from. Shell entry points resolve `$PYTHON` (venv if present,
else `python3`) for the same reason, but any of these scripts can also be run by hand,
which is why the check belongs in the script and not only in the caller.
"""

from __future__ import annotations

import sys
from typing import Iterable, List, Tuple

# Two different services, and conflating them is its own bug class. The CONTROL plane
# owns Gateway, policy engine and policy mutation; the DATA plane owns Memory actors,
# sessions, events and records. `DeleteMemoryRecord` exists only on the data plane, so a
# requirement block pointed at the control plane reports OperationNotFoundError for a
# capability the SDK has.
CONTROL_SERVICE = "bedrock-agentcore-control"
DATA_SERVICE = "bedrock-agentcore"


def _members(service: str, operation: str, direction: str) -> set:
    import botocore.session

    model = botocore.session.get_session().get_service_model(service)
    op = model.operation_model(operation)
    shape = op.input_shape if direction == "input" else op.output_shape
    return set(shape.members) if shape is not None else set()


def missing_members(
    service: str, requirements: Iterable[Tuple[str, str, Iterable[str]]]
) -> List[str]:
    """Requirement tuples this SDK's service model cannot satisfy.

    Each requirement is ``(operation, "input"|"output", members)``. Returns a flat list
    of ``Operation.direction.member`` strings so the caller can name every gap at once
    rather than failing on the first.
    """
    gaps: List[str] = []
    for operation, direction, wanted in requirements:
        try:
            present = _members(service, operation, direction)
        except Exception as exc:  # noqa: BLE001 - an unknown operation is itself a gap
            gaps.append(f"{operation}.{direction}: unavailable ({type(exc).__name__})")
            continue
        for member in wanted:
            if member not in present:
                gaps.append(f"{operation}.{direction}.{member}")
    return gaps


def require(
    what: str,
    requirements: Iterable[Tuple[str, str, Iterable[str]]],
    *,
    service: str = CONTROL_SERVICE,
) -> None:
    """Hard-stop unless the SDK model carries every member ``what`` depends on."""
    try:
        import botocore
    except ImportError:  # pragma: no cover - boto3 is a hard dependency of the callers
        raise SystemExit("botocore is not installed for this interpreter")

    gaps = missing_members(service, requirements)
    if not gaps:
        return
    raise SystemExit(
        f"Refusing to {what}: this interpreter's AWS SDK cannot see the required "
        f"fields.\n\n"
        f"  interpreter : {sys.executable}\n"
        f"  botocore    : {botocore.__version__}\n"
        f"  service     : {service}\n"
        f"  missing     : {', '.join(gaps)}\n\n"
        "botocore drops unknown fields silently in both directions, so proceeding would "
        "send an incomplete request, receive a success, and leave the governance state "
        "different from the one reported.\n\n"
        "Re-run with the interpreter that carries pellier/backend/requirements.lock:\n"
        "  workshop box : python3          (the lock is installed into ~/.local; there\n"
        "                                   is no venv on a workshop box)\n"
        "  developer box: ./pellier/backend/.venv/bin/python\n"
    )


# The mutation `policy_mode.py` performs. `enforcementMode` is the field an older model
# drops, and it is the one that decides whether a policy enforces or merely logs.
POLICY_MODE_REQUIREMENTS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("UpdatePolicy", "input", ("policyId", "policyEngineId", "enforcementMode")),
    ("GetPolicy", "output", ("enforcementMode",)),
    ("UpdateGateway", "input", ("gatewayIdentifier",)),
)

# The narrow per-item deletes `reset_memory_runtime.py` uses. If the model lacks them the
# script would fall back to nothing at all, and a reset that silently cleans no memory
# hands the next participant someone else's preferences.
MEMORY_RUNTIME_REQUIREMENTS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("DeleteEvent", "input", ("memoryId", "actorId", "sessionId", "eventId")),
    ("DeleteMemoryRecord", "input", ("memoryId", "memoryRecordId")),
    ("ListMemoryRecords", "input", ("memoryId", "namespace", "namespacePath")),
    ("ListActors", "input", ("memoryId",)),
)


def require_policy_mode_support() -> None:
    require("change Cedar enforcement mode", POLICY_MODE_REQUIREMENTS)


def require_memory_runtime_support() -> None:
    require(
        "delete AgentCore Memory runtime data",
        MEMORY_RUNTIME_REQUIREMENTS,
        service=DATA_SERVICE,
    )


def report() -> int:
    """Print what this interpreter can and cannot do. For diagnosing a box."""
    import botocore

    print(f"interpreter : {sys.executable}")
    print(f"botocore    : {botocore.__version__}")
    for label, service, requirements in (
        ("policy mode mutation", CONTROL_SERVICE, POLICY_MODE_REQUIREMENTS),
        ("memory runtime delete", DATA_SERVICE, MEMORY_RUNTIME_REQUIREMENTS),
    ):
        gaps = missing_members(service, requirements)
        verdict = "OK" if not gaps else f"MISSING {', '.join(gaps)}"
        print(f"{label:22}: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(report())
