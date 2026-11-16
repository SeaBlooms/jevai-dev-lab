"""Non-streaming chat completion via Vercel AI Gateway OpenAI-compat API."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

GATEWAY_CHAT_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model: str


class GatewayError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def complete(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    client: httpx.AsyncClient | None = None,
    timeout: float = 120.0,
) -> CompletionResult:
    if not api_key:
        raise GatewayError("AI_GATEWAY_API_KEY is not set", status_code=503)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        response = await http.post(GATEWAY_CHAT_URL, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise GatewayError(f"Gateway request failed: {exc}") from exc
    finally:
        if owns_client:
            await http.aclose()

    if response.status_code >= 400:
        detail = _error_detail(response)
        raise GatewayError(detail, status_code=response.status_code)

    data = response.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GatewayError("Gateway response missing choices[0].message.content") from exc

    if not isinstance(text, str):
        raise GatewayError("Gateway returned non-string content")

    used_model = data.get("model") if isinstance(data.get("model"), str) else model
    return CompletionResult(text=text, model=used_model)


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"Gateway HTTP {response.status_code}: {response.text[:500]}"

    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict) and err.get("message"):
        return f"Gateway HTTP {response.status_code}: {err['message']}"
    if isinstance(err, str):
        return f"Gateway HTTP {response.status_code}: {err}"
    return f"Gateway HTTP {response.status_code}: {response.text[:500]}"
