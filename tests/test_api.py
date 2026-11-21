"""API tests with a fake AI Gateway transport (no live model calls)."""

from __future__ import annotations

from dataclasses import replace

from jevai.config import Settings, load_settings


def test_health_ok_no_secrets(client, persona_sha, settings: Settings) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["model"] == settings.model
    assert data["persona_sha256"] == persona_sha
    assert data["gateway_configured"] is True
    dumped = res.text.lower()
    assert "test-gateway-key" not in dumped
    assert "test-token" not in dumped
    assert "you are jev" not in dumped


def test_prompts_requires_token(client) -> None:
    assert client.get("/prompts").status_code == 401
    assert client.get("/prompts", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_list_prompts(client) -> None:
    res = client.get("/prompts", headers={"Authorization": "Bearer test-token"})
    assert res.status_code == 200
    ids = {c["id"] for c in res.json()}
    assert ids == {"ping", "summarize", "verdict-review", "local-only"}


def test_complete_attaches_persona(client, persona_text: str) -> None:
    res = client.post(
        "/v1/complete",
        headers={"Authorization": "Bearer test-token"},
        json={"prompt": "hello"},
    )
    assert res.status_code == 200
    data = res.json()
    assert persona_text in data["text"]
    assert "user='hello'" in data["text"]
    assert data["case_id"] is None
    assert data["model"] == "anthropic/claude-sonnet-5"
    assert data["backend"] == "gateway"
    assert "via=gateway" in data["text"]


def test_run_unknown_case_404(client) -> None:
    res = client.post(
        "/v1/prompts/nope/run",
        headers={"Authorization": "Bearer test-token"},
    )
    assert res.status_code == 404


def test_run_saved_case(client) -> None:
    res = client.post(
        "/v1/prompts/ping/run",
        headers={"Authorization": "Bearer test-token"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == "ping"
    assert "In one sentence, who are you?" in data["text"]


def test_complete_bad_token(client) -> None:
    res = client.post(
        "/v1/complete",
        headers={"Authorization": "Bearer nope"},
        json={"prompt": "x"},
    )
    assert res.status_code == 401


def test_host_lock(monkeypatch, tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "AI_GATEWAY_API_KEY=k\nJEV_API_TOKEN=t\nJEV_HOST=0.0.0.0\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("JEV_HOST", raising=False)
    monkeypatch.delenv("JEV_API_TOKEN", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    try:
        load_settings(dotenv_path=env)
        raise AssertionError("expected ValueError for non-loopback host")
    except ValueError as exc:
        assert "not allowed" in str(exc)


AUTH = {"Authorization": "Bearer test-token"}


def test_health_lists_backends(client) -> None:
    data = client.get("/health").json()
    assert data["default_backend"] == "gateway"
    assert data["backends"]["gateway"] == {"model": "anthropic/claude-sonnet-5", "configured": True}
    assert data["backends"]["ollama"] == {"model": "qwen3:8b", "configured": True}
    assert "ollama.test" not in client.get("/health").text


def test_complete_request_backend_override(client) -> None:
    res = client.post("/v1/complete", headers=AUTH, json={"prompt": "hi", "backend": "ollama"})
    assert res.status_code == 200
    data = res.json()
    assert data["backend"] == "ollama"
    assert data["model"] == "qwen3:8b"
    assert "via=ollama" in data["text"]


def test_complete_unknown_backend_422(client) -> None:
    res = client.post("/v1/complete", headers=AUTH, json={"prompt": "hi", "backend": "nope"})
    assert res.status_code == 422


def test_case_backend_pin(client) -> None:
    res = client.post("/v1/prompts/local-only/run", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["backend"] == "ollama"


def test_query_backend_beats_case_pin(client) -> None:
    res = client.post("/v1/prompts/local-only/run?backend=gateway", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["backend"] == "gateway"


def test_env_default_backend(client_with, settings: Settings) -> None:
    c = client_with(replace(settings, default_backend="ollama"))
    res = c.post("/v1/complete", headers=AUTH, json={"prompt": "hi"})
    assert res.status_code == 200
    assert res.json()["backend"] == "ollama"


def test_json_mode_only_sent_to_ollama(client) -> None:
    local = client.post("/v1/prompts/verdict-review/run?backend=ollama", headers=AUTH).json()
    assert "json=True" in local["text"]
    remote = client.post("/v1/prompts/verdict-review/run?backend=gateway", headers=AUTH).json()
    assert "json=False" in remote["text"]


def test_complete_case_tag_applies_json_mode(client) -> None:
    res = client.post(
        "/v1/complete",
        headers=AUTH,
        json={"prompt": "live capture", "case_id": "verdict-review", "backend": "ollama"},
    )
    assert res.status_code == 200
    assert "json=True" in res.json()["text"]


def test_ollama_unreachable_502(ollama_down_client) -> None:
    res = ollama_down_client.post("/v1/complete", headers=AUTH, json={"prompt": "hi", "backend": "ollama"})
    assert res.status_code == 502
    assert "Homelab Ollama unreachable" in res.json()["detail"]
    ok = ollama_down_client.post("/v1/complete", headers=AUTH, json={"prompt": "hi"})
    assert ok.status_code == 200
    assert ok.json()["backend"] == "gateway"


def test_gateway_without_key_503(client_with, settings: Settings) -> None:
    c = client_with(replace(settings, gateway_api_key=""))
    assert c.post("/v1/complete", headers=AUTH, json={"prompt": "hi"}).status_code == 503
    assert c.post("/v1/complete", headers=AUTH, json={"prompt": "hi", "backend": "ollama"}).status_code == 200


def test_bad_jev_backend_env(monkeypatch, tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("JEV_API_TOKEN=t\nJEV_BACKEND=cloud\n", encoding="utf-8")
    monkeypatch.delenv("JEV_BACKEND", raising=False)
    monkeypatch.delenv("JEV_API_TOKEN", raising=False)
    monkeypatch.delenv("JEV_HOST", raising=False)
    try:
        load_settings(dotenv_path=env)
        raise AssertionError("expected ValueError for unknown JEV_BACKEND")
    except ValueError as exc:
        assert "JEV_BACKEND" in str(exc)


def test_index_served(client) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "jev" in res.text.lower()
