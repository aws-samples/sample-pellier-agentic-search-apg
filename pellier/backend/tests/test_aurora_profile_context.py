"""Contract tests for the in-process Aurora profile receipt."""

from __future__ import annotations

import inspect

from services.chat import EnhancedChatService


def test_profile_event_matches_its_contract() -> None:
    source = inspect.getsource(EnhancedChatService.chat_stream)

    assert '"type": "aurora_profile_context"' in source
    assert '"profile": {' in source
    assert '"facts_available": persona_fact_count' in source
    assert '"orders_available": persona_order_count' in source
    assert '"available": persona_profile_available' in source


def test_legacy_profile_event_shape_is_absent() -> None:
    source = inspect.getsource(EnhancedChatService.chat_stream)

    assert '"type": "memory_context"' not in source
    assert '"facts_loaded"' not in source
    assert '"orders_loaded"' not in source
