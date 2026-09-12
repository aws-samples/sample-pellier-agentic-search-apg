"""Content fingerprint for the code AgentCore Runtime actually executes.

The problem this solves
-----------------------

A participant packages their edited source, deploys it to AgentCore Runtime,
invokes it, and gets an answer. Nothing in that loop proves the answer came
from *their* revision. The Runtime invoke response carries no version: the
request pins ``qualifier=DEFAULT``, which is an endpoint alias, so the ARN in
the response path is identical for yesterday's baseline and today's package.
A successful invocation is therefore compatible with "my code ran" and with
"my deploy silently failed and the previous image answered" — and those are
the two cases the lab exists to distinguish.

The mechanism
-------------

Since the deployed revision cannot be read back out of the service, it is
carried in: the renderer digests the staged runtime sources at package time
and injects the digest as ``PELLIER_BUILD_FINGERPRINT``. The entrypoint echoes
it on every response. The backend computes the same digest over its own copy
of the same files and compares.

Matching fingerprints prove the deployed package was built from byte-identical
sources. Differing fingerprints prove the participant is looking at an older
deployment, which is the more useful finding and the one a green invocation
otherwise hides.

What it does and does not prove
-------------------------------

It proves the *content* of the deployed package. It is not a signature and not
an attestation: it says which bytes were staged, not who staged them or that
the service did not modify them afterwards. A participant who edits a file the
runtime does not ship sees no change, correctly — the digest covers exactly the
files that are packaged, and nothing else.

One source of truth
-------------------

``RUNTIME_SOURCE_FILES`` lives here rather than in the renderer so the list
that is packaged and the list that is digested cannot drift apart. A file
added to the runtime but not to this tuple would ship unfingerprinted, which
would make the comparison quietly weaker rather than loudly wrong.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

__all__ = [
    "RUNTIME_SOURCE_FILES",
    "FINGERPRINT_ENV_VAR",
    "compute_fingerprint",
    "deployed_fingerprint",
    "short_fingerprint",
]

# The source files staged into the managed runtime package, relative to
# `pellier/backend`. The renderer copies exactly these (plus the dependency
# manifests below) and the digest covers exactly these.
RUNTIME_SOURCE_FILES: tuple[Path, ...] = (
    Path("agentcore_runtime.py"),
    Path("operator_agentcore_runtime.py"),
    Path("services/__init__.py"),
    Path("services/agentcore_gateway.py"),
    Path("services/conversation_context.py"),
    Path("services/intent_router.py"),
    Path("services/otel_content_redaction.py"),
    Path("services/operator_graph.py"),
    Path("services/product_envelope.py"),
    Path("services/response_mode.py"),
    Path("services/runtime_env.py"),
)

# Dependency manifests are staged alongside the sources and change what the
# runtime resolves at build time, so they belong in the digest: a lockfile bump
# produces a materially different package from identical application code.
RUNTIME_DEPENDENCY_FILES: tuple[Path, ...] = (
    Path("pyproject.toml"),
    Path("uv.lock"),
)

FINGERPRINT_ENV_VAR = "PELLIER_BUILD_FINGERPRINT"

# Long enough that a collision is not a practical concern, short enough to read
# aloud from a screen and compare by eye in a workshop room.
_DISPLAY_LENGTH = 12


def compute_fingerprint(backend_dir: Path | str) -> str:
    """Digest the runtime sources under ``backend_dir``.

    Returns a full hex SHA-256. Raises ``FileNotFoundError`` naming the first
    missing file rather than digesting a partial set: a fingerprint computed
    over fewer files than were packaged would compare unequal for the wrong
    reason and send a participant hunting a deployment fault that is really a
    missing file here.
    """
    root = Path(backend_dir)
    digest = hashlib.sha256()

    # Sorted by POSIX relative path so the digest is independent of filesystem
    # iteration order, and the path is hashed alongside the bytes so that
    # renaming a file changes the fingerprint even when its content does not.
    for relative in sorted(
        RUNTIME_SOURCE_FILES + RUNTIME_DEPENDENCY_FILES,
        key=lambda item: item.as_posix(),
    ):
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(
                f"Runtime source {relative.as_posix()} is missing under {root}. "
                "The fingerprint must cover every packaged file; digesting a "
                "partial set would report a false mismatch."
            )
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")

    return digest.hexdigest()


def deployed_fingerprint() -> str:
    """Return the fingerprint baked into this process's package, if any.

    Empty string when unset, which is the honest answer for a runtime deployed
    before this mechanism existed. Callers must render that as unknown rather
    than as a mismatch: absence of the variable is not evidence of stale code.
    """
    return os.environ.get(FINGERPRINT_ENV_VAR, "").strip()


def short_fingerprint(value: str | None) -> str:
    """Shorten a fingerprint for display, preserving the unknown case."""
    if not value:
        return ""
    return value[:_DISPLAY_LENGTH]
