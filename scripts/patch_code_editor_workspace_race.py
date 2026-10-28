#!/usr/bin/env python3
"""Close a start-up race in Code Editor that can leave the Explorer empty and no terminal.

VS Code's WorkspaceService (src/vs/workbench/services/configuration/browser/
configurationService.ts) completes a multi-root workspace once its workspace file has loaded.
For a remote workspace that load can finish before `this.workspace` exists. The update handler
then throws "Cannot set properties of undefined (setting 'initialized')", and initialize()
keeps the workspace's stale `initialized = false`, so the workspace never completes: the
Explorer keeps its loading clock, the panel and the workshop terminal never open, and only a
reload recovers. It stalled 4 of 14 fresh loads on a test event box (Code Editor 1.101.2).

The patch guards the handler and, in initialize(), re-reads the workspace file's state before
the completion check. It matches the bundle's shape, not the minifier's names, and leaves a
build it does not recognise unchanged.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

MARK = "/*pellier-workspace-race*/"
ID = r"[\w$]+"
HANDLER = re.compile(
    rf"onDidUpdateConfiguration\((?P<e>{ID})=>\{{this\.{ID}\((?P=e)\)\.then\(\(\)=>\{{"
    rf"(?P<body>this\.(?P<ws>{ID})\.initialized=this\.(?P<cfg>{ID})\.initialized,"
    rf"this\.(?P<complete>{ID})\((?P=e)\))\}}\)")
INITIALIZE = re.compile(
    rf"await this\.{ID}\({ID},{ID}\),(?P<check>this\.(?P<complete>{ID})\(!1\),"
    rf"{ID}\(\"code/didInitWorkspaceService\"\))")


def patch(bundle: str) -> tuple[str, str]:
    """Return the bundle and what happened to it: patched, already patched or unrecognised."""
    if MARK in bundle:
        return bundle, "already patched"
    handlers, inits = list(HANDLER.finditer(bundle)), list(INITIALIZE.finditer(bundle))
    if len(handlers) != 1 or len(inits) != 1:
        return bundle, f"unrecognised ({len(handlers)} handlers, {len(inits)} initialize sites)"
    handler, init = handlers[0], inits[0]
    if handler["complete"] != init["complete"]:
        return bundle, "unrecognised (the two sites name different completion checks)"
    ws, cfg = handler["ws"], handler["cfg"]
    guarded = f"this.{ws}&&({handler['body']})"
    resync = f"this.{ws}.initialized=this.{ws}.initialized||this.{cfg}.initialized{MARK},"
    edits = sorted([(handler.span("body"), guarded),
                    (init.span("check"), resync + init["check"])], reverse=True)
    for (start, end), text in edits:
        bundle = bundle[:start] + text + bundle[end:]
    return bundle, "patched"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workbench", nargs="+", type=Path,
                        help="Code Editor's out/vs/code/browser/workbench/workbench.js")
    for path in parser.parse_args().workbench:
        bundle, outcome = patch(path.read_text(encoding="utf-8"))
        if outcome == "patched":
            path.write_text(bundle, encoding="utf-8")
        print(f"{path}: {outcome}")


if __name__ == "__main__":
    main()
