"""The step contract of one Ask Pellier turn: labels, findings and layer tags.

This is the one table that maps real stream events to the plain words a
shopper sees. Every finding is computed from the actual tool result by a
fixed template; nothing here is model-written. The Runtime bundle carries
this module too, so the managed rail's tool events describe themselves in
the same words. It imports no settings and no registry: a skill's display
name and path are passed in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

STATUS_UNDERSTANDING = "Understanding your request"
STATUS_WRITING = "Writing your answer"
ROUTE_STEP_ID = "route"

# The agent-local skill loader from ``strands.vended_plugins.skills``. It is
# not a store tool: it reads the repository, writes no audit row and is not
# published to the Gateway.
SKILL_LOAD_TOOL = "skills"
SKILL_STEP_ID = "skills"

# One Router step plus three tool steps; anything beyond folds into the last.
MAX_STEPS = 4

STEP_LABELS: Dict[str, str] = {
    "search_products": "Searching the catalog in Aurora",
    "browse_department": "Browsing a department in Aurora",
    "compare_products": "Comparing two pieces",
    "check_stock": "Checking stock in three warehouses",
    "get_orders": "Reading your orders",
    "get_return_policy": "Reading the return policy",
    "get_tickets": "Reading your tickets",
    "ask_a_person": "Asking a person at Pellier",
}

LAYER_TAGS: Dict[str, tuple[str, ...]] = {
    ROUTE_STEP_ID: ("Router",),
    "search_products": ("Aurora",),
    "browse_department": ("Aurora",),
    "compare_products": ("Aurora",),
    "check_stock": ("Aurora",),
    "get_orders": ("Aurora", "Identity"),
    "get_return_policy": ("Aurora",),
    "get_tickets": ("Aurora", "Identity"),
    "ask_a_person": ("Identity",),
    SKILL_LOAD_TOOL: ("Skills",),
}

ERROR_FINDINGS: Dict[str, str] = {
    "search_products": "The catalog search did not complete",
    "browse_department": "The department could not be read",
    "compare_products": "The comparison did not complete",
    "check_stock": "The stock check did not complete",
    "get_orders": "Your orders could not be read",
    "get_return_policy": "The return policy could not be read",
    "get_tickets": "Your tickets could not be read",
    "ask_a_person": "The handoff did not go through",
    SKILL_LOAD_TOOL: "The skill could not be opened",
}
_GENERIC_ERROR_FINDING = "This check did not complete"

# Warehouse reading order when all three cities report.
_CITY_ORDER = ("Brooklyn", "Austin", "Portland")

_SCOPE_FINDINGS = {
    "customer_scope_required": "Sign in before account records can be read",
    "customer_scope_mismatch": "Only the signed-in account can be read",
}


def step_label(tool: str, tool_input: Optional[Dict[str, Any]] = None) -> str:
    """The plain-words label for a tool start."""
    if tool == SKILL_LOAD_TOOL:
        name = str((tool_input or {}).get("skill_name") or "").strip()
        return f"Opening {name}" if name else "Opening a skill"
    return STEP_LABELS.get(tool, "Checking something")


def parse_result(result_text: Any) -> Dict[str, Any]:
    """The JSON a tool returned, or ``{"_text": ...}`` when it returned prose."""
    if isinstance(result_text, dict):
        return result_text
    text = str(result_text or "")
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            pass
    return {"_text": text}


def result_failed(tool: str, parsed: Dict[str, Any]) -> bool:
    """True when the tool reported an error rather than an answer."""
    if "error" in parsed and tool != "compare_products":
        return True
    if tool == "compare_products" and parsed.get("status") not in ("success", "not_found"):
        return True
    if parsed.get("status") == "error":
        return True
    if tool == SKILL_LOAD_TOOL and "_text" not in parsed:
        return True
    return False


def _plural(word: str) -> str:
    word = str(word or "").strip()
    if not word:
        return ""
    if word.endswith("s"):
        return word
    return word + "s"


def _count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _money(cents_or_dollars: Any, *, cents: bool = False) -> str:
    try:
        amount = float(cents_or_dollars or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if cents:
        amount = amount / 100.0
    return f"${amount:g}" if amount == int(amount) else f"${amount:.2f}"


def _search_finding(parsed: Dict[str, Any]) -> str:
    count = _count(parsed.get("count"))
    plan = parsed.get("search_plan") or {}
    hard = plan.get("hard_constraints") or {}
    limits: List[str] = []
    price = hard.get("price_max_usd")
    if price is not None:
        limits.append(f"under {_money(price)}")
    if hard.get("in_stock_only"):
        limits.append("in stock")
    exclusions = [_plural(value) for value in (plan.get("exclusions") or []) if value]
    if count == 0:
        head = "Nothing matched" + (" " + " and ".join(limits) if limits else "")
    elif limits:
        head = f"{count} " + " and ".join(limits)
    else:
        head = f"{count} found"
    if exclusions:
        head += ", " + " and ".join(exclusions) + " left out"
    return head


def _browse_finding(parsed: Dict[str, Any]) -> str:
    department = str(parsed.get("department") or "that department")
    count = _count(parsed.get("count"))
    if count == 0:
        return f"Nothing in {department}"
    return f"{count} in {department}, by rating"


def _compare_finding(parsed: Dict[str, Any]) -> str:
    if parsed.get("status") == "not_found":
        return "One of the pieces was not found"
    first = parsed.get("product_1") or {}
    second = parsed.get("product_2") or {}
    return (
        f"{first.get('name', 'First piece')} {_money(first.get('price'))} vs "
        f"{second.get('name', 'second piece')} {_money(second.get('price'))}"
    )


def _stock_finding(parsed: Dict[str, Any]) -> str:
    status = parsed.get("status")
    if status == "not_found":
        return "Not a piece Pellier carries"
    if status == "ambiguous":
        return f"{len(parsed.get('candidates') or [])} pieces match that name"
    warehouses = [row for row in parsed.get("warehouses") or [] if isinstance(row, dict)]
    if _count(parsed.get("total_units")) == 0 or not warehouses:
        return "Sold out in all three warehouses"
    by_city = {str(row.get("city")): _count(row.get("quantity")) for row in warehouses}
    if all(city in by_city for city in _CITY_ORDER):
        ordered = [(city, by_city[city]) for city in _CITY_ORDER]
    else:
        ordered = [(str(row.get("city")), _count(row.get("quantity"))) for row in warehouses]
    return ", ".join(f"{city} {quantity}" for city, quantity in ordered)


def _orders_finding(parsed: Dict[str, Any]) -> str:
    scoped = _SCOPE_FINDINGS.get(str(parsed.get("status")))
    if scoped:
        return scoped
    count = _count(parsed.get("count"))
    if count == 0:
        return "No orders on your account"
    return f"{count} order{'' if count == 1 else 's'} on your account"


def _policy_finding(parsed: Dict[str, Any]) -> str:
    if parsed.get("status") == "not_found":
        return "No return policy found"
    days = _count(parsed.get("return_window_days"))
    department = str(parsed.get("department") or "default")
    if department == "default":
        return f"{days}-day returns, store-wide"
    return f"{days}-day returns for {department}"


def _tickets_finding(parsed: Dict[str, Any]) -> str:
    scoped = _SCOPE_FINDINGS.get(str(parsed.get("status")))
    if scoped:
        return scoped
    count = _count(parsed.get("count"))
    if count == 0:
        return "No tickets on your account"
    open_count = _count(parsed.get("open_count"))
    closed = count - open_count
    finding = f"{open_count} open ticket{'' if open_count == 1 else 's'}"
    if closed > 0:
        finding += f", {closed} closed"
    return finding


def _handoff_finding(parsed: Dict[str, Any], tool_input: Dict[str, Any]) -> str:
    credit = parsed.get("credit_request")
    amount = _money(tool_input.get("store_credit_cents"), cents=True)
    if credit == "review_opened":
        return f"A {amount} credit request is waiting for a person"
    if credit == "sign_in_required":
        return "Sign in before a credit can be requested"
    if credit == "over_ceiling":
        return "That credit is above what a person can approve here"
    if credit == "not_recorded":
        return "Handed to a person; the credit request was not recorded"
    return "Handed to a person at Pellier"


def skill_finding(loaded: Sequence[Dict[str, str]], refused: Optional[str] = None) -> str:
    """The finding for the folded skills step.

    Args:
        loaded: Every skill opened so far this turn, each as
            ``{"display_name", "path"}`` in load order.
        refused: A name the loader refused, when the latest call was refused.
    """
    if refused:
        return f"No skill named {refused} for this agent"
    if not loaded:
        return "No skill was opened"
    if len(loaded) == 1:
        return f"Loaded {loaded[0]['display_name']} from {loaded[0]['path']}"
    names = [skill["display_name"] for skill in loaded]
    return f"Loaded {', '.join(names[:-1])} and {names[-1]} from skills/"


def finding_for(tool: str, parsed: Dict[str, Any], tool_input: Optional[Dict[str, Any]] = None) -> str:
    """One plain line computed from the actual result of ``tool``."""
    tool_input = tool_input or {}
    if result_failed(tool, parsed):
        return ERROR_FINDINGS.get(tool, _GENERIC_ERROR_FINDING)
    if tool == "search_products":
        return _search_finding(parsed)
    if tool == "browse_department":
        return _browse_finding(parsed)
    if tool == "compare_products":
        return _compare_finding(parsed)
    if tool == "check_stock":
        return _stock_finding(parsed)
    if tool == "get_orders":
        return _orders_finding(parsed)
    if tool == "get_return_policy":
        return _policy_finding(parsed)
    if tool == "get_tickets":
        return _tickets_finding(parsed)
    if tool == "ask_a_person":
        return _handoff_finding(parsed, tool_input)
    return "Done"


def skill_load_refused(result_text: Any) -> Optional[str]:
    """The refused name when the loader answered a load with a refusal."""
    text = str(result_text or "").strip()
    if text.startswith("Skill '") and "' not found" in text:
        return text[len("Skill '"):text.index("' not found")]
    if text.startswith("Error:"):
        return "that"
    return None


def layer_tags(tool: str, parsed: Dict[str, Any]) -> List[str]:
    """The layers that applied to this step, for the Builder view."""
    tags = list(LAYER_TAGS.get(tool, ()))
    if tool == "ask_a_person" and parsed.get("credit_request") == "review_opened":
        tags.append("Approval")
    return tags


@dataclass
class TurnSteps:
    """Allocate step ids inside the budget and fold repeated or extra work.

    A repeated call of the same tool reuses its step, so a Shopping turn that
    searches twice shows one search step with the latest finding. Skill loads
    share one step. A fourth distinct tool folds into the last step rather
    than growing the list.

    Args:
        skill_names: Skill name to display name, for the loader's labels.
        skill_paths: Skill name to repository path, for the loader's findings.
    """

    skill_names: Dict[str, str] = field(default_factory=dict)
    skill_paths: Dict[str, str] = field(default_factory=dict)
    order: List[str] = field(default_factory=lambda: [ROUTE_STEP_ID])
    ids: Dict[str, str] = field(default_factory=dict)
    loaded_skills: List[Dict[str, str]] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)

    def step_id(self, tool: str) -> str:
        """An opaque id per step. The tool name lives only under ``builder``."""
        key = SKILL_STEP_ID if tool == SKILL_LOAD_TOOL else tool
        if key in self.ids:
            return self.ids[key]
        if len(self.order) >= MAX_STEPS:
            return self.order[-1]
        step_id = f"step-{len(self.order)}"
        self.ids[key] = step_id
        self.order.append(step_id)
        return step_id

    def running(self, tool: str, tool_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """The ``step`` event for a tool start."""
        tool_input = dict(tool_input or {})
        if tool == SKILL_LOAD_TOOL:
            name = str(tool_input.get("skill_name") or "")
            tool_input["skill_name"] = self.skill_names.get(name, name)
        step_id = self.step_id(tool)
        label = step_label(tool, tool_input)
        self.labels[step_id] = label
        return {
            "type": "step",
            "id": step_id,
            "label": label,
            "status": "running",
            "tags": list(LAYER_TAGS.get(tool, ())),
            "builder": {"tool": tool},
        }

    def finished(
        self,
        tool: str,
        result_text: Any,
        *,
        tool_input: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        audit_id: Optional[int] = None,
        evidence: Optional[Dict[str, Any]] = None,
        rail: str = "in-process",
    ) -> Dict[str, Any]:
        """The ``step`` event for a tool end, with its finding and Builder data."""
        tool_input = tool_input or {}
        evidence = evidence or {}
        step_id = self.step_id(tool)
        parsed = parse_result(result_text)
        if tool == SKILL_LOAD_TOOL:
            refused = skill_load_refused(result_text)
            if refused is None:
                name = str(tool_input.get("skill_name") or "")
                self.loaded_skills.append({
                    "name": name,
                    "display_name": self.skill_names.get(name, name),
                    "path": self.skill_paths.get(name, f"skills/{name}/SKILL.md"),
                })
            finding = skill_finding(self.loaded_skills, refused)
            failed = refused is not None
        else:
            finding = finding_for(tool, parsed, tool_input)
            failed = result_failed(tool, parsed)
        builder: Dict[str, Any] = {
            "tool": tool,
            "rail": rail,
            "duration_ms": duration_ms,
            "audit_id": audit_id,
            "receipt_id": evidence.get("receipt_id"),
            "identity": evidence.get("identity"),
            "ranking": evidence.get("ranking"),
        }
        if tool == SKILL_LOAD_TOOL:
            builder["skills"] = list(self.loaded_skills)
        return {
            "type": "step",
            "id": step_id,
            "label": self.labels.get(step_id) or step_label(tool, tool_input),
            "status": "failed" if failed else "done",
            "finding": finding,
            "tags": layer_tags(tool, parsed),
            "builder": builder,
        }

    def route(
        self,
        *,
        agent: str,
        intent: str,
        finding: str,
        model_id: str,
        skills: Sequence[Dict[str, Any]],
        skill_mode: str,
        memory: Optional[Dict[str, Any]] = None,
        rail: str = "in-process",
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The Router's step, done the moment the intent is known."""
        tags = list(LAYER_TAGS[ROUTE_STEP_ID])
        if memory:
            tags.append("Memory")
        if skills:
            tags.append("Skills")
        self.labels[ROUTE_STEP_ID] = STATUS_UNDERSTANDING
        return {
            "type": "step",
            "id": ROUTE_STEP_ID,
            "label": STATUS_UNDERSTANDING,
            "status": "done",
            "finding": finding,
            "tags": tags,
            "builder": {
                "tool": None,
                "rail": rail,
                "intent": intent,
                "agent": agent,
                "model_id": model_id,
                "skills": list(skills),
                "skill_mode": skill_mode,
                "memory": memory,
                "note": note,
            },
        }


    def managed(self, tool_call: Dict[str, Any], *, rail: str = "gateway-mcp") -> Dict[str, Any]:
        """A done ``step`` for one tool call the managed Runtime reported.

        The Runtime computes ``finding`` beside the Gateway with the same
        templates, so it arrives on the call. Identity fields arrive the same
        way; the ranking is attached by the route when the receipt is readable.
        """
        tool = str(tool_call.get("tool") or "")
        status = str(tool_call.get("status") or "success")
        failed = status not in ("success", "completed")
        identity = None
        if tool_call.get("binding"):
            identity = {
                "binding": tool_call.get("binding"),
                "requested_customer": tool_call.get("requested_customer"),
                "bound_customer": tool_call.get("bound_customer"),
                "authorized_customer": tool_call.get("bound_customer"),
            }
        finding = tool_call.get("finding")
        if not finding:
            finding = ERROR_FINDINGS.get(tool, _GENERIC_ERROR_FINDING) if failed else "Done"
        step_id = self.step_id(tool)
        label = step_label(tool, tool_call.get("input") or {})
        self.labels[step_id] = label
        return {
            "type": "step",
            "id": step_id,
            "label": label,
            "status": "failed" if failed else "done",
            "finding": finding,
            "tags": list(LAYER_TAGS.get(tool, ())),
            "builder": {
                "tool": tool,
                "rail": rail,
                "duration_ms": tool_call.get("duration_ms"),
                "audit_id": None,
                "receipt_id": None,
                "identity": identity,
                "ranking": tool_call.get("ranking"),
            },
        }


def status_event(label: str) -> Dict[str, Any]:
    """The status line event; the pulse follows the stream, not a timer."""
    return {"type": "status", "label": label}
