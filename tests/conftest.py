"""Shared fixtures: temp prompts, settings, fake gateway transport."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from jevai.api import create_app
from jevai.config import Settings
from jevai.gateway import GATEWAY_CHAT_URL


@pytest.fixture
def persona_text() -> str:
    return "You are Jev, a test persona."


@pytest.fixture
def prompts_tree(tmp_path: Path, persona_text: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    prompts = tmp_path / "prompts"
    cases = prompts / "cases"
    cases.mkdir(parents=True)
    system = prompts / "system.md"
    system.write_text(persona_text + "\n", encoding="utf-8")
    (cases / "ping.yaml").write_text(
        "id: ping\ntitle: Who are you?\nprompt: In one sentence, who are you?\n",
        encoding="utf-8",
    )
    (cases / "summarize.yaml").write_text(
        "id: summarize\ntitle: Summarize\nprompt: Summarize this.\n",
        encoding="utf-8",
    )

    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html><body>jev</body></html>", encoding="utf-8")

    monkeypatch.setattr("jevai.config.PROMPTS_DIR", prompts)
    monkeypatch.setattr("jevai.config.CASES_DIR", cases)
    monkeypatch.setattr("jevai.config.SYSTEM_PROMPT_PATH", system)
    monkeypatch.setattr("jevai.config.STATIC_DIR", static)
    monkeypatch.setattr("jevai.persona.SYSTEM_PROMPT_PATH", system)
    monkeypatch.setattr("jevai.cases.CASES_DIR", cases)
    monkeypatch.setattr("jevai.api.STATIC_DIR", static)
    return prompts


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gateway_api_key="test-gateway-key",
        model="anthropic/claude-sonnet-5",
        api_token="test-token",
        host="127.0.0.1",
        port=8790,
    )


@pytest.fixture
def persona_sha(persona_text: str) -> str:
    return hashlib.sha256(persona_text.encode("utf-8")).hexdigest()


def _fake_gateway_handler(request: httpx.Request) -> httpx.Response:
    assert request.url == GATEWAY_CHAT_URL
    assert request.headers.get("Authorization") == "Bearer test-gateway-key"
    body = json.loads(request.content.decode("utf-8"))
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["role"] == "user"
    system = body["messages"][0]["content"]
    user = body["messages"][1]["content"]
    return httpx.Response(
        200,
        json={
            "model": body["model"],
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"ECHO system={system!r} user={user!r}",
                    }
                }
            ],
        },
    )


@pytest.fixture
def client(prompts_tree: Path, settings: Settings) -> TestClient:
    transport = httpx.MockTransport(_fake_gateway_handler)
    http = httpx.AsyncClient(transport=transport)
    app = create_app(settings, http_client=http)
    with TestClient(app) as test_client:
        yield test_client
