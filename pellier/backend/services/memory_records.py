"""Parse managed records without promoting partial episodes to completion."""
import json
from typing import Any
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException


def record_view(record: dict[str, Any], kind: str) -> dict[str, Any]:
    """Preserve AWS record identity and raw text; never infer success from age."""
    raw = str(record.get("content", {}).get("text", ""))
    content = raw
    episode = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            content = str(parsed.get("preference") or parsed.get("fact") or parsed.get("summary") or raw)
            # The live service also serializes consolidated episodes as JSON.
            # Validate the consolidation fields, not a generic "completed" flag.
            if kind == "episodic" and all(
                isinstance(parsed.get(tag), str) and parsed[tag].strip()
                for tag in ("situation", "intent", "assessment", "justification")
            ):
                episode = {tag: parsed[tag].strip() for tag in ("situation", "intent", "assessment", "justification")}
                content = episode["situation"] + " " + episode["justification"]
    except (ValueError, TypeError):
        pass
    if kind == "summary" and raw.lstrip().startswith("<"):
        try:
            content = " ".join(part.strip() for part in ElementTree.fromstring(raw).itertext() if part.strip())
        except (ElementTree.ParseError, DefusedXmlException):
            pass
    if kind == "episodic" and episode is None:
        # The built-in consolidation output is a summary with an assessment.
        # Extraction's <summary_turn> and reflections are NOT completed episodes.
        try:
            root = ElementTree.fromstring(raw)
            if root.tag == "summary" and all(root.findtext(tag, "").strip() for tag in ("situation", "intent", "assessment", "justification")):
                episode = {tag: "".join(root.find(tag).itertext()).strip() for tag in ("situation", "intent", "assessment", "justification")}
                content = episode["situation"] + " " + episode["justification"]
        except (ElementTree.ParseError, DefusedXmlException):
            pass
    return {
        "id": record.get("memoryRecordId", ""),
        "strategyId": record.get("memoryStrategyId", ""),
        "content": content, "raw": raw,
        "createdAt": str(record.get("createdAt", "")),
        "namespaces": record.get("namespaces", []),
        "episode": episode,
    }
