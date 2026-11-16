"""API tests with a fake AI Gateway transport (no live model calls)."""

from __future__ import annotations

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
    assert ids == {"ping", "summarize"}


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


def test_index_served(client) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "jev" in res.text.lower()
