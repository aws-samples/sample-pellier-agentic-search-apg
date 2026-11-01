"""Chat payloads are bounded: an anonymous caller cannot send a megabyte prompt."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from models.search import ChatMessage, ChatRequest
from routes.agent import ChatRequest as AgentChatRequest


def test_message_at_the_limit_is_accepted() -> None:
    assert ChatRequest(message="x" * 4000).message
    assert AgentChatRequest(message="x" * 4000).message


def test_message_over_the_limit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 4001)
    with pytest.raises(ValidationError):
        AgentChatRequest(message="x" * 4001)


def test_history_content_over_the_limit_is_rejected() -> None:
    ChatMessage(role="user", content="x" * 8000)
    with pytest.raises(ValidationError):
        ChatMessage(role="user", content="x" * 8001)


def test_history_over_fifty_entries_is_rejected() -> None:
    turn = {"role": "user", "content": "hi"}
    assert len(ChatRequest(message="hi", conversation_history=[turn] * 50).conversation_history) == 50
    with pytest.raises(ValidationError):
        ChatRequest(message="hi", conversation_history=[turn] * 51)


def test_oversized_message_is_a_422_over_http() -> None:
    app = FastAPI()

    @app.post("/chat")
    def chat(request: ChatRequest) -> dict:
        return {"ok": True}

    client = TestClient(app)
    assert client.post("/chat", json={"message": "x" * 4001}).status_code == 422
    assert client.post("/chat", json={"message": "hello"}).status_code == 200
