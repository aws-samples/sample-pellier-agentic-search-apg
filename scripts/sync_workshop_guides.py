#!/usr/bin/env python3
"""Bundle the canonical Studio guides for Pellier's read-only in-app guide pages.

Only reads participant Markdown and its referenced static assets. It never reads
exercise solutions, invokes a lab, or changes an account. Use --check in release
validation to reject a stale bundle. Studio remains the authoring source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "introduction": "00-introduction",
    "background": "00-background-and-overview",
    "grounded-inventory": "10-build-a-postgresql-grounded-agent",
    "retrieval-acceptance": "20-build-and-measure-postgresql-hybrid-retrieval",
    "managed-agent-path": "30-deploy-and-operate-the-managed-agent-path",
    "fail-closed-policy": "40-govern-and-prove-agent-actions",
    "summary": "60-summary",
    "reference": "90-appendix",
    "coding-coach": "90-appendix/10-coding-coach",
}
LAB_IDS = tuple(list(PAGES)[2:6])
OUTPUT = Path("pellier/frontend/src/observatory/labs/generated/workshopGuides.json")
ASSET_ROOT = Path("pellier/frontend/public/workshop-guides")
OPEN = re.compile(r'^(:{3,})(alert|expand|tabs|tab)\{(.*)\}\s*$')
ATTR = re.compile(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|([^\s}]+))')
LINK = re.compile(r'(!?\[[^\]]*\]\()([^\s)]+)(\))')


def slug(text: str) -> str:
    text = re.sub(r"[`*]", "", text).lower()
    return re.sub(r"[^\w-]+", "-", text).strip("-")


def parse(markdown: str) -> list[dict]:
    """Parse Studio containers without interpreting HTML or executable content."""
    lines = markdown.splitlines()
    roots: list[dict] = []
    containers: list[tuple[int, list[dict]]] = [(0, roots)]
    pending: list[str] = []
    fence = False
    anchors: dict[str, int] = {}

    def flush() -> None:
        if "\n".join(pending).strip():
            containers[-1][1].append({"kind": "markdown", "text": "\n".join(pending)})
        pending.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            fence = not fence
            pending.append(line)
        elif fence:
            pending.append(line)
        elif match := OPEN.match(line):
            flush()
            width, kind, raw = match.groups()
            attrs = {m[0]: next((v for v in m[1:] if v), "") for m in ATTR.findall(raw)}
            node = {"kind": kind, "title": attrs.get("header", attrs.get("label", "")),
                    "tone": attrs.get("type", "info"), "children": []}
            containers[-1][1].append(node)
            containers.append((len(width), node["children"]))
        elif re.fullmatch(r":{3,}\s*", line):
            flush()
            if len(containers) == 1 or containers[-1][0] != len(line.strip()):
                raise ValueError(f"Unmatched Studio container on line {i + 1}")
            containers.pop()
        elif match := re.match(r"^(#{1,6})\s+(.+)$", line):
            flush()
            title = match[2]
            key = slug(title)
            anchors[key] = anchors.get(key, 0) + 1
            anchor = key if anchors[key] == 1 else f"{key}-{anchors[key]}"
            containers[-1][1].append({"kind": "heading", "level": len(match[1]),
                                       "text": title, "id": anchor})
        elif line.startswith("|") and i + 1 < len(lines) and re.fullmatch(r"[\s|:-]+", lines[i + 1]):
            flush()
            cells = lambda value: [cell.strip() for cell in value.strip().strip("|").split("|")]
            headers = cells(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            containers[-1][1].append({"kind": "table", "headers": headers, "rows": rows})
            continue
        else:
            pending.append(line)
        i += 1
    flush()
    if fence or len(containers) != 1:
        raise ValueError("Unclosed code fence or Studio container")
    return roots


def bundle(studio: Path) -> tuple[dict, dict[str, bytes]]:
    assets: dict[str, bytes] = {}
    pages = {}
    routes = {f"/{path}/": f"/observatory/{'labs' if key in LAB_IDS else 'guide'}/{key}"
              for key, path in PAGES.items()}

    def rewrite(match: re.Match) -> str:
        start, url, end = match.groups()
        if url.startswith("/static/"):
            relative = url.removeprefix("/static/")
            source = (studio / "static" / relative).resolve()
            if not source.is_relative_to((studio / "static").resolve()):
                raise ValueError(f"Asset escapes static root: {url}")
            assets[relative] = source.read_bytes()
            url = f"/workshop-guides/{relative}"
        else:
            path, separator, anchor = url.partition("#")
            url = routes.get(path, path) + (separator + anchor if separator else "")
        return start + url + end

    for key, path in PAGES.items():
        relative = f"content/{path}/index.en.md"
        raw = (studio / relative).read_text()
        title_match = re.search(r'^title:\s*"(.*)"\s*$', raw, re.M)
        if not title_match:
            raise ValueError(f"Missing title: {relative}")
        text = re.sub(r"\A---\n.*?\n---\n", "", raw, count=1, flags=re.S)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        text = LINK.sub(rewrite, text)
        nodes = parse(text)
        pages[key] = {"title": title_match[1], "sourcePage": relative,
                      "sourceSha256": hashlib.sha256(raw.encode()).hexdigest(),
                      "sections": [{"id": n["id"], "text": n["text"]} for n in nodes
                                   if n["kind"] == "heading" and n["level"] == 2],
                      "nodes": nodes}
    return {"version": 1, "source": "Workshop Studio participant guides", "pages": pages}, assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studio-repo", type=Path, required=True)
    parser.add_argument("--source-repo", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data, assets = bundle(args.studio_repo.resolve())
    outputs = {OUTPUT: (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()}
    outputs.update({ASSET_ROOT / name: value for name, value in assets.items()})
    stale = []
    for relative, content in outputs.items():
        target = args.source_repo / relative
        if target.is_file() and target.read_bytes() == content:
            continue
        stale.append(str(relative))
        if not args.check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    if args.check and stale:
        print("In-app guides differ from Studio:\n" + "\n".join(stale), file=sys.stderr)
        return 1
    print(f"{'Verified' if args.check else 'Bundled'} {len(data['pages'])} guide pages and {len(assets)} referenced assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
