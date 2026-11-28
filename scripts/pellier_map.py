"""The workshop's mental model in the terminal: the arc and the system built so far.

The welcome banner shows ``Retrieve -> Ground -> Deploy -> Govern``. Each check that passes
shows where the participant stands on that arc, and the last check of each lab also shows the
system as it stands, with the components that lab added. One definition of the components
serves all four maps and the Wrap-up, so they cannot drift apart.

A component is shown only when the running system has it: the AgentCore ones are read from
the backend's settings, and the Wrap-up shows only the components whose records it found.
"""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass
from itertools import zip_longest
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import workshop_check as check

LABS = {1: "Retrieve", 2: "Ground", 3: "Deploy", 4: "Govern"}
MAP_AFTER_TASK = {"3B": 3, "4B": 4}
# Labs 1 and 2 end with the grid of what the participant has proved (proved_grid), not the arc
# or the component map; Labs 3 and 4 keep the arc and the map until their output is redone.
FIRST_MAPPED_LAB = 3
GRID_HEADER = ("Lab", "What you added", "What you proved")
NOT_PROVED = "Not proved yet: its checks do not pass now"
DONE, NOW, LATER = "✓", "●", "·"
JOIN = " ─ "

# What each lab adds, in the order a request meets it. ``needs`` names the settings fact that
# must hold for the component to be on the map; an empty ``needs`` means the lab's own check
# proves it.
@dataclass(frozen=True)
class Component:
    name: str
    needs: str = ""


ADDS: Dict[int, Sequence[Component]] = {
    1: (Component("Router"), Component("Catalog agent"),
        Component("Aurora: full text + pgvector + RRF + Cohere Rerank")),
    2: (Component("Stock agent"), Component("check_stock"),
        Component("Aurora: warehouse rows")),
    3: (Component("AgentCore Runtime", "runtime"), Component("Memory", "memory"),
        Component("Gateway", "gateway"), Component("Policy (Cedar)", "gateway"),
        Component("Lambda", "gateway"), Component("Aurora row rules")),
    4: (Component("Operator (Nadia)"), Component("Cedar credit cap"),
        Component("credit-writer role"), Component("one row per key")),
}


def facts(env: Optional[Mapping[str, str]] = None) -> Dict[str, bool]:
    """What the running Pellier has, from the backend's settings and the environment."""
    values = dict(check.parse_dotenv(check.DEFAULT_ENV))
    values.update(os.environ if env is None else env)
    return {
        "runtime": str(values.get("USE_AGENTCORE_RUNTIME", "")).lower() in ("true", "1", "yes"),
        "memory": bool(values.get("AGENTCORE_MEMORY_ID")),
        "gateway": bool(values.get("AGENTCORE_GATEWAY_URL")),
    }


def arc(task: str) -> str:
    """``Retrieve ✓  Ground ✓  Deploy ●  Govern ·`` for the lab ``task`` belongs to; empty in
    Lab 1, whose last check prints its completion row instead.

    The guide reaches each lab through the earlier ones. Task 3B finishes Lab 3. In Lab 4,
    the 4B and 4A checks leave Jessica's payment proof to the separate SQL step.
    """
    lab = int(task[0])
    if lab < FIRST_MAPPED_LAB:
        return ""
    finished = lab if task == "3B" else lab - 1
    marks = [DONE if number <= finished else NOW if number == lab else LATER for number in LABS]
    return "  ".join(f"{name} {mark}" for name, mark in zip(LABS.values(), marks))


def _line(lab: int, have: Mapping[str, bool], current: int,
          seen: Optional[Sequence[str]] = None) -> str:
    parts = [component.name for component in ADDS[lab]
             if (not component.needs or have.get(component.needs))
             and (seen is None or component.name in seen)]
    mark = NOW if lab == current else DONE
    return check.wrapped(f"  {mark} Lab {lab}  ", f"{'' if lab == 1 else '+ '}{JOIN.join(parts)}")


def system_map(lab: int, have: Optional[Mapping[str, bool]] = None) -> str:
    """The system built through ``lab``, the lab's additions marked ``●``."""
    have = facts() if have is None else have
    lines = ["Pellier so far", *(_line(number, have, lab) for number in range(1, lab + 1))]
    return "\n".join(lines)


def finale(have: Mapping[str, bool], seen: Sequence[str]) -> str:
    """The whole system for the Wrap-up: every lab lit, Lab 3 and 4 limited to the components
    whose records the trace found (``seen``, by component name)."""
    lines = ["Pellier, all four labs"]
    for number in range(1, 5):
        lines.append(_line(number, have, 0, seen if number >= 3 else None))
    return "\n".join(lines)


def proved_grid(rows: Sequence[Tuple[str, str, Optional[str]]],
                width: Optional[int] = None) -> List[str]:
    """``What you’ve proved · N of 4 labs`` and one row per lab finished so far.

    Each row is ``(lab, what it added, what the participant proved)``; a lab whose checks do
    not pass now has no proof and says so. The last two columns wrap to the terminal.
    """
    proved = sum(1 for _lab, _added, proof in rows if proof)
    cells = [GRID_HEADER] + [(lab, added, proof or NOT_PROVED) for lab, added, proof in rows]
    first = max(len(lab) for lab, _added, _proof in cells) + 2
    room = (width or check.terminal_width()) - first - 2
    longest_added = max(len(added) for _lab, added, _proof in cells)
    longest_proof = max(len(proof) for _lab, _added, proof in cells)
    added_width = min(longest_added, room - min(longest_proof, room // 2))
    proof_width = room - added_width
    lines = [check.paint(f"What you\u2019ve proved \u00b7 {proved} of 4 labs", check.PASSED)]
    for lab, added, proof in cells:
        for left, right in zip_longest(textwrap.wrap(added, added_width),
                                       textwrap.wrap(proof, proof_width), fillvalue=""):
            lines.append(f"{lab:<{first}}{left:<{added_width}}  {right}".rstrip())
            lab = ""
    return lines


def passed_extras(task: str) -> List[str]:
    """Show the architecture overview after the build checks in Labs 3 and 4."""
    if task not in MAP_AFTER_TASK:
        return []
    return [system_map(MAP_AFTER_TASK[task]), ""]
