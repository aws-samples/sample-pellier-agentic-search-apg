"""The step contract of one Ask Pellier turn: labels, findings and layer tags.

This is the one table that maps real stream events to the plain words a
shopper sees. Every finding is computed from the actual tool result by a
fixed template; nothing here is model-written. The Runtime bundle carries
this module too, so the managed rail's tool events describe themselves in
the same words. It imports no settings and no registry: a skill's display
name and path are passed in. Its one import from the backend, the catalog
vocabulary, ships in the bundle beside it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from services.catalog_vocabulary import KNOWN_MATERIALS

STATUS_UNDERSTANDING = "Understanding your request"
STATUS_WRITING = "Writing your answer"
ROUTE_STEP_ID = "route"

# The agent-local skill loader from ``strands.vended_plugins.skills``. It is
# not a store tool: it reads the repository, writes no audit row and is not
# published to the Gateway.
SKILL_LOAD_TOOL = "skills"
SKILL_STEP_ID = "skills"

# How an agent gets its skills: carried in the prompt, or opened on demand.
SKILL_MODE_FIXED = "fixed"
SKILL_MODE_ON_DEMAND = "on_demand"

# The kinds of limit a plan applies, in the order the findings name them.
_LIMIT_KINDS = ("budget", "stock", "exclusions", "department")

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


# A material is a mass noun: "no wool", never "no wools".
_MASS_NOUNS = frozenset(material.lower() for material in KNOWN_MATERIALS)


def plural(word: str) -> str:
    """A shopper's word for more than one: "candles", "watches"; a material stays "wool".

    The one pluralizer for every limit Pellier names: the step findings, the
    page's tags and the ranking panel's chips.
    """
    word = str(word or "").strip()
    if not word or word.lower() in _MASS_NOUNS or word.endswith("s"):
        return word
    if re.search(r"(ch|sh|x|z)$", word):
        return word + "es"
    return word + "s"


def _count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _money(dollars: Any) -> str:
    try:
        amount = float(dollars or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"${amount:g}" if amount == int(amount) else f"${amount:.2f}"


def limit_phrases(plan: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Each hard limit a plan applied, by kind, as the shopper would say it."""
    plan = plan or {}
    hard = plan.get("hard_constraints") or {}
    phrases: Dict[str, str] = {}
    price = hard.get("price_max_usd")
    if price is not None:
        phrases["budget"] = f"under {_money(price)}"
    if hard.get("in_stock_only"):
        phrases["stock"] = "in stock"
    exclusions = [plural(value) for value in (plan.get("exclusions") or []) if value]
    if exclusions:
        phrases["exclusions"] = "no " + " or ".join(exclusions)
    categories = [str(value) for value in (hard.get("categories") or []) if value]
    if categories:
        phrases["department"] = " or ".join(categories) + " only"
    return phrases


def requirement_phrases(
    plan: Optional[Dict[str, Any]], carried: Sequence[str] = ()
) -> Optional[Dict[str, List[str]]]:
    """The Builder view's requirement facts: every limit applied, and those kept from earlier."""
    phrases = limit_phrases(plan)
    if not phrases:
        return None
    return {
        "applied": [phrases[kind] for kind in _LIMIT_KINDS if kind in phrases],
        "carried": [phrases[kind] for kind in _LIMIT_KINDS if kind in phrases and kind in carried],
    }


def _limits_said_now(plan: Dict[str, Any], carried: Sequence[str]) -> tuple[List[str], str]:
    """The limits this message stated, and the exclusions clause, for a finding's head."""
    phrases = limit_phrases(plan)
    stated = [phrases[kind] for kind in ("budget", "stock") if kind in phrases and kind not in carried]
    left_out = ""
    if "exclusions" in phrases and "exclusions" not in carried:
        exclusions = [plural(value) for value in (plan.get("exclusions") or []) if value]
        left_out = ", " + " and ".join(exclusions) + " left out"
    return stated, left_out


def _carried_suffix(plan: Dict[str, Any], carried: Sequence[str]) -> str:
    phrases = limit_phrases(plan)
    kept = [phrases[kind] for kind in _LIMIT_KINDS if kind in phrases and kind in carried]
    return ". Kept your limits from earlier: " + ", ".join(kept) if kept else ""


def _search_finding(
    parsed: Dict[str, Any], *, kept: Optional[int] = None, carried: Sequence[str] = ()
) -> str:
    """What a search found: how many it returned, how many fit, which limits applied."""
    count = _count(parsed.get("count"))
    plan = parsed.get("search_plan") or {}
    stated, left_out = _limits_said_now(plan, carried)
    if count == 0:
        head = "Nothing matched"
    else:
        head = f"{count} found"
        if kept is not None:
            head += f" from {kept} that fit"
    if stated:
        head += " " + " and ".join(stated)
    return head + left_out + _carried_suffix(plan, carried)


def _browse_finding(parsed: Dict[str, Any], *, carried: Sequence[str] = ()) -> str:
    department = str(parsed.get("department") or "that department")
    count = _count(parsed.get("count"))
    plan = parsed.get("search_plan") or {}
    stated, left_out = _limits_said_now(plan, carried)
    if count == 0:
        head = f"Nothing in {department}" + (" " + " and ".join(stated) if stated else "")
    else:
        head = f"{count} in {department}, by rating" + (", " + " and ".join(stated) if stated else "")
    return head + left_out + _carried_suffix(plan, carried)


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
    # warehouse_name is the plain city ("Brooklyn"); city carries the state too.
    named = [(str(row.get("warehouse_name") or row.get("city")), _count(row.get("quantity")))
             for row in warehouses]
    by_city = dict(named)
    if all(city in by_city for city in _CITY_ORDER):
        ordered = [(city, by_city[city]) for city in _CITY_ORDER]
    else:
        ordered = named
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


def _handoff_finding(parsed: Dict[str, Any]) -> str:
    credit = parsed.get("credit_request_status")
    if credit == "request_opened":
        return "A store credit request is waiting for a person"
    if credit == "already_requested":
        return "A store credit request was already waiting for a person"
    if credit == "sign_in_required":
        return "Sign in before a credit can be requested"
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


def finding_for(
    tool: str,
    parsed: Dict[str, Any],
    *,
    kept: Optional[int] = None,
    carried: Sequence[str] = (),
) -> str:
    """One plain line computed from the actual result of ``tool``.

    Args:
        tool: The store tool that ran.
        parsed: Its result, as ``parse_result`` read it.
        kept: For a search, how many catalog rows fit the hard limits, when
            the filter counts were taken.
        carried: The limit kinds kept from earlier in the conversation.
    """
    if result_failed(tool, parsed):
        return ERROR_FINDINGS.get(tool, _GENERIC_ERROR_FINDING)
    if tool == "search_products":
        return _search_finding(parsed, kept=kept, carried=carried)
    if tool == "browse_department":
        return _browse_finding(parsed, carried=carried)
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
        return _handoff_finding(parsed)
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
    """The layers that applied to this step, for the Builder view.

    A shopper's credit ask is a request, never an approval: it names no
    amount, and nobody approves it. A person answers it by investigating.
    """
    tags = list(LAYER_TAGS.get(tool, ()))
    credit = parsed.get("credit_request_status")
    if tool == "ask_a_person" and credit in ("request_opened", "already_requested"):
        tags.append("Request")
    return tags


@dataclass
class TurnSteps:
    """Allocate one step id per tool use.

    Each tool use gets its own step, keyed by its tool-use id, so a Shopping
    turn that searches twice, even two at once, shows two search steps, each
    with its own finding, ranking and result. A call with no id keys by its
    tool. Skill loads share one step. There is no cap on the number of steps,
    so no call's evidence is ever merged into another's: keeping the list
    short is the browser's job, which shows the latest few and collapses the
    earlier ones. Each step travels as its own small event, so nothing about
    the stream needs a cap either.

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

    def step_id(self, tool: str, call_id: Optional[str] = None) -> str:
        """An opaque id per tool use. The tool name lives only under ``builder``."""
        key = SKILL_STEP_ID if tool == SKILL_LOAD_TOOL else (call_id or tool)
        if key in self.ids:
            return self.ids[key]
        step_id = f"step-{len(self.order)}"
        self.ids[key] = step_id
        self.order.append(step_id)
        return step_id

    def running(
        self,
        tool: str,
        tool_input: Optional[Dict[str, Any]] = None,
        *,
        call_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The ``step`` event for a tool start; ``call_id`` is its tool-use id."""
        tool_input = dict(tool_input or {})
        if tool == SKILL_LOAD_TOOL:
            name = str(tool_input.get("skill_name") or "")
            tool_input["skill_name"] = self.skill_names.get(name, name)
        step_id = self.step_id(tool, call_id)
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
        call_id: Optional[str] = None,
        tool_input: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        audit_id: Optional[int] = None,
        evidence: Optional[Dict[str, Any]] = None,
        rail: str = "in-process",
    ) -> Dict[str, Any]:
        """The ``step`` event for a tool end, with its finding and Builder data.

        ``evidence`` is what this one tool use published, taken by its id.
        """
        tool_input = tool_input or {}
        evidence = evidence or {}
        step_id = self.step_id(tool, call_id)
        parsed = parse_result(result_text)
        carried = [str(kind) for kind in (evidence.get("requirements") or {}).get("carried") or []]
        if tool == SKILL_LOAD_TOOL:
            refused = skill_load_refused(result_text)
            name = str(tool_input.get("skill_name") or "")
            # A skill opened twice was loaded once.
            if refused is None and all(skill["name"] != name for skill in self.loaded_skills):
                self.loaded_skills.append({
                    "name": name,
                    "display_name": self.skill_names.get(name, name),
                    "path": self.skill_paths.get(name, f"skills/{name}/SKILL.md"),
                })
            finding = skill_finding(self.loaded_skills, refused)
            failed = refused is not None
        else:
            kept = ((evidence.get("ranking") or {}).get("filters") or {}).get("kept")
            finding = finding_for(tool, parsed, kept=kept, carried=carried)
            failed = result_failed(tool, parsed)
        builder: Dict[str, Any] = {
            "tool": tool,
            "rail": rail,
            "duration_ms": duration_ms,
            "audit_id": audit_id,
            "receipt_id": evidence.get("receipt_id"),
            "identity": evidence.get("identity"),
            "ranking": evidence.get("ranking"),
            "requirements": requirement_phrases(parsed.get("search_plan"), carried),
        }
        if tool == SKILL_LOAD_TOOL:
            builder["skills"] = list(self.loaded_skills)
        event: Dict[str, Any] = {
            "type": "step",
            "id": step_id,
            "label": self.labels.get(step_id) or step_label(tool, tool_input),
            "status": "failed" if failed else "done",
            "finding": finding,
            "tags": layer_tags(tool, parsed),
            "builder": builder,
        }
        return _with_results(event, evidence.get("results"))

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
        stop_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The Router's step, done the moment the intent is known.

        The Skills tag names what the agent starts with. On demand it starts
        with the names only, and the tag says so before any load.

        ``stop_reason`` is how the agent's turn ended, once it has: the same
        step is sent again with it, so the Builder view can say when an
        answer was cut short at ``max_tokens``.
        """
        tags = list(LAYER_TAGS[ROUTE_STEP_ID])
        if memory:
            tags.append("Memory")
        if skills:
            tags.append("Skills")
        elif skill_mode == SKILL_MODE_ON_DEMAND:
            tags.append("Skills (on demand)")
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
                "stop_reason": stop_reason,
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
        step_id = self.step_id(tool, str(tool_call.get("id") or "") or None)
        label = step_label(tool, tool_call.get("input") or {})
        self.labels[step_id] = label
        return _with_results({
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
                "requirements": None,
            },
        }, tool_call.get("results"))


def _with_results(event: Dict[str, Any], results: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach the page grid's result to a catalog step, when the tool reported one.

    It travels beside ``builder`` because the shopper's page shows it with the
    Builder view off too. Like ``builder``, it never reaches the model.
    """
    if results is not None and event["status"] != "failed":
        event["results"] = results
    return event


def status_event(label: str) -> Dict[str, Any]:
    """The status line event; the pulse follows the stream, not a timer."""
    return {"type": "status", "label": label}
