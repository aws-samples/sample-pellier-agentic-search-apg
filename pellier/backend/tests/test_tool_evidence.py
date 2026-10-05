"""The evidence channel keeps each tool use's evidence apart, even for one tool run twice."""

from __future__ import annotations

import contextvars
import threading
from typing import Any, Dict

from services import tool_evidence


def test_two_calls_of_one_tool_in_two_threads_each_take_only_their_own() -> None:
    """Strands runs parallel tool uses in their own contexts; each take is that call's alone."""
    channel = tool_evidence.open_channel()
    try:
        published = threading.Barrier(2)
        taken: Dict[str, Dict[str, Any]] = {}

        def call(call_id: str, order: list) -> None:
            tool_evidence.bind_call(call_id)
            tool_evidence.publish("search_products", {"results": {"product_ids": order}})
            tool_evidence.publish("search_products", {"ranking": {"call": call_id}})
            # Both calls have published before either takes, as when two
            # searches finish together.
            published.wait(timeout=5)
            taken[call_id] = tool_evidence.take("search_products", call_id)

        threads = [
            threading.Thread(target=contextvars.copy_context().run, args=(call, call_id, order))
            for call_id, order in (("use-a", ["31", "36"]), ("use-b", ["90", "28"]))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        assert taken["use-a"] == {
            "results": {"product_ids": ["31", "36"]}, "ranking": {"call": "use-a"},
        }
        assert taken["use-b"] == {
            "results": {"product_ids": ["90", "28"]}, "ranking": {"call": "use-b"},
        }
        assert tool_evidence.take("search_products", "use-a") == {}
    finally:
        tool_evidence.close_channel(channel)


def test_a_take_leaves_other_calls_and_other_tools_in_place() -> None:
    def turn() -> None:
        tool_evidence.bind_call("use-a")
        tool_evidence.publish("search_products", {"receipt_id": 1})
        tool_evidence.publish("check_stock", {"identity": {"binding": "bound"}})
        tool_evidence.bind_call("use-b")
        tool_evidence.publish("search_products", {"receipt_id": 2})

        assert tool_evidence.take("search_products", "use-b") == {"receipt_id": 2}
        assert tool_evidence.take("check_stock", "use-a") == {"identity": {"binding": "bound"}}
        assert tool_evidence.take("search_products", "use-a") == {"receipt_id": 1}

    channel = tool_evidence.open_channel()
    try:
        # A copied context, so the bound call does not leak into other tests.
        contextvars.copy_context().run(turn)
    finally:
        tool_evidence.close_channel(channel)


def test_unbound_evidence_is_taken_without_a_call_id_only() -> None:
    """A tool called directly, with no hook to bind a call, still reports to its caller."""
    channel = tool_evidence.open_channel()
    try:
        context = contextvars.copy_context()
        context.run(tool_evidence.publish, "browse_department", {"results": {"product_ids": ["7"]}})
        assert context.run(tool_evidence.take, "browse_department", "use-a") == {}
        unbound = context.run(tool_evidence.take, "browse_department")
        assert unbound == {"results": {"product_ids": ["7"]}}
    finally:
        tool_evidence.close_channel(channel)


def test_publishing_with_the_channel_closed_is_a_no_op() -> None:
    def outside_a_turn() -> None:
        tool_evidence.bind_call("use-a")
        tool_evidence.publish("search_products", {"receipt_id": 1})
        assert tool_evidence.take("search_products", "use-a") == {}

    contextvars.copy_context().run(outside_a_turn)
