#!/usr/bin/env python3
"""Print one renderer-owned deployment name without reading or changing AWS."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--field", choices=("project-root", "runtime-name", "policy-engine-name"), required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    from render_agentcore_project import deployment_identity_from_repo, project_root

    identity = deployment_identity_from_repo(repo)
    print({
        "project-root": str(project_root(repo, identity.suffix)),
        "runtime-name": identity.runtime_name,
        "policy-engine-name": identity.policy_engine_name,
    }[args.field])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
