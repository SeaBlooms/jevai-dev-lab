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
    (cases / "verdict-review.yaml").write_text(
        "id: verdict-review\ntitle: Second opinion\njson_mode: true\nprompt: Return JSON stance and note.\n",
        encoding="utf-8",
    )
    (cases / "local-only.yaml").write_text(
        "id: local-only\ntitle: Pinned to ollama\nbackend: ollama\nprompt: Stay on the LAN.\n",
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


OLLAMA_TEST_BASE = "http://ollama.test:11434/v1"
OLLAMA_TEST_CHAT_URL = f"{OLLAMA_TEST_BASE}/chat/completions"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gateway_api_key="test-gateway-key",
        model="anthropic/claude-sonnet-5",
        api_token="test-token",
        host="127.0.0.1",
        port=8790,
        ollama_base_url=OLLAMA_TEST_BASE,
        ollama_model="qwen3:8b",
    )


@pytest.fixture
def persona_sha(persona_text: str) -> str:
    return hashlib.sha256(persona_text.encode("utf-8")).hexdigest()


def _fake_upstream_handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content.decode("utf-8"))
    if request.url == GATEWAY_CHAT_URL:
        backend = "gateway"
        assert request.headers.get("Authorization") == "Bearer test-gateway-key"
        assert "reasoning_effort" not in body
        assert "response_format" not in body
    elif request.url == OLLAMA_TEST_CHAT_URL:
        backend = "ollama"
        assert "Authorization" not in request.headers
        assert body["reasoning_effort"] == "none"
    else:
        raise AssertionError(f"unexpected upstream URL {request.url}")
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["role"] == "user"
    system = body["messages"][0]["content"]
    user = body["messages"][1]["content"]
    json_mode = body.get("response_format") == {"type": "json_object"}
    return httpx.Response(
        200,
        json={
            "model": body["model"],
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"ECHO via={backend} json={json_mode} system={system!r} user={user!r}",
                    }
                }
            ],
        },
    )


def _make_client(settings: Settings, handler) -> TestClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TestClient(create_app(settings, http_client=http))


@pytest.fixture
def client(prompts_tree: Path, settings: Settings) -> TestClient:
    with _make_client(settings, _fake_upstream_handler) as test_client:
        yield test_client


@pytest.fixture
def client_with(prompts_tree: Path):
    opened: list[TestClient] = []

    def factory(custom: Settings) -> TestClient:
        test_client = _make_client(custom, _fake_upstream_handler)
        test_client.__enter__()
        opened.append(test_client)
        return test_client

    yield factory
    for test_client in opened:
        test_client.__exit__(None, None, None)


@pytest.fixture
def ollama_down_client(prompts_tree: Path, settings: Settings) -> TestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == OLLAMA_TEST_CHAT_URL:
            raise httpx.ConnectError("connection refused", request=request)
        return _fake_upstream_handler(request)

    with _make_client(settings, handler) as test_client:
        yield test_client
