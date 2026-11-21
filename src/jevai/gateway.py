"""Non-streaming chat completion against an OpenAI-compatible upstream (AI Gateway or Ollama)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from jevai.config import GATEWAY_BASE_URL, BackendConfig

GATEWAY_CHAT_URL = f"{GATEWAY_BASE_URL}/chat/completions"


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model: str
    backend: str


class UpstreamError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


GatewayError = UpstreamError


async def complete(
    backend: BackendConfig,
    *,
    system: str,
    user: str,
    json_mode: bool = False,
    client: httpx.AsyncClient | None = None,
) -> CompletionResult:
    if not backend.configured:
        if backend.name == "gateway":
            raise UpstreamError("AI_GATEWAY_API_KEY is not set", status_code=503)
        raise UpstreamError(f"{backend.label} is not configured", status_code=503)

    headers = {"Content-Type": "application/json"}
    if backend.api_key:
        headers["Authorization"] = f"Bearer {backend.api_key}"

    payload: dict[str, Any] = {
        "model": backend.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }
    payload.update(dict(backend.extra_body))
    if json_mode and backend.supports_json_mode:
        payload["response_format"] = {"type": "json_object"}

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=backend.timeout)
    try:
        response = await http.post(backend.chat_url, headers=headers, json=payload, timeout=backend.timeout)
    except httpx.TimeoutException as exc:
        raise UpstreamError(f"{backend.label} timed out after {backend.timeout:g}s") from exc
    except httpx.ConnectError as exc:
        raise UpstreamError(f"{backend.label} unreachable at {backend.base_url}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise UpstreamError(f"{backend.label} request failed: {exc}") from exc
    finally:
        if owns_client:
            await http.aclose()

    if response.status_code >= 400:
        detail = _error_detail(backend.label, response)
        raise UpstreamError(detail, status_code=response.status_code)

    data = response.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise UpstreamError(f"{backend.label} response missing choices[0].message.content") from exc

    if not isinstance(text, str):
        raise UpstreamError(f"{backend.label} returned non-string content")
    if not text.strip():
        raise UpstreamError(f"{backend.label} returned empty content")

    used_model = data.get("model") if isinstance(data.get("model"), str) else backend.model
    return CompletionResult(text=text, model=used_model, backend=backend.name)


def _error_detail(label: str, response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"{label} HTTP {response.status_code}: {response.text[:500]}"

    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict) and err.get("message"):
        return f"{label} HTTP {response.status_code}: {err['message']}"
    if isinstance(err, str):
        return f"{label} HTTP {response.status_code}: {err}"
    return f"{label} HTTP {response.status_code}: {response.text[:500]}"
