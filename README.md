# jevai-dev-lab

Local sandbox for the **Jev** persona: a pinned-persona second-opinion service for reviewing guardrail verdicts, with a checked-in system prompt in front of two OpenAI-compatible backends ([Vercel AI Gateway](https://vercel.com/docs/ai-gateway/openai-compat) and a homelab Ollama box), a small REST API, and a page for saved test prompts.

Public GitHub: [SeaBlooms/jevai-dev-lab](https://github.com/SeaBlooms/jevai-dev-lab).

Callers never send the system prompt and never see the gateway key. Bind is loopback-only (`127.0.0.1:8790`); only the upstream model call leaves the machine.

## Setup

```bash
cd jevai-dev-lab
uv sync --group dev
cp .env.example .env
# set AI_GATEWAY_API_KEY (Vercel AI Gateway; this process does not read other projects' env files)
# set JEV_API_TOKEN to any local secret
```

## Commands

```bash
uv run jev serve                       # http://127.0.0.1:8790/  — prompt page + API
uv run jev run ping                    # one saved case → JSON on stdout
uv run jev run ping --backend ollama   # same case on the homelab box
uv run jev smoke                       # one live call on the default backend
uv run jev smoke --backend ollama      # no AI_GATEWAY_API_KEY needed
uv run jev compare verdict-review      # one case on both backends, replies side by side

uv run pytest
uv run ruff check src tests
```

## API

Bearer `JEV_API_TOKEN` on every route except `GET /health`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Up, default backend + model, per-backend `configured`, persona sha256 |
| `GET` | `/prompts` | Saved cases (id, title, prompt, pinned backend) |
| `POST` | `/v1/complete` | `{ "prompt": "…", "case_id": null, "backend": null }` → `{ text, model, backend, persona_sha256, case_id }` |
| `POST` | `/v1/prompts/{id}/run?backend=` | Run a case from `prompts/cases/` (`backend` optional) |
| `GET` | `/` | Prompt page (backend dropdown) |

### Backends

| Name | Upstream | Model |
| --- | --- | --- |
| `gateway` | Vercel AI Gateway (`AI_GATEWAY_API_KEY`) | `JEV_MODEL`, default `anthropic/claude-sonnet-5` |
| `ollama` | Ollama, `OLLAMA_BASE_URL` (default `http://localhost:11434/v1`; set your LAN box in `.env`, no key) | `OLLAMA_MODEL`, default `qwen3:8b` |

Each request uses the first of: the request's `backend` (body field or `?backend=` query), the case's `backend:` key, then `JEV_BACKEND` (default `gateway`). There is no automatic fallback: if the homelab box is down, the call fails with 502 `Homelab Ollama unreachable …` so replies from different models never get mixed up.

Notes for `qwen3:8b`:

- Jev sends `reasoning_effort: "none"`. qwen3 thinks by default, and the thinking trace counts toward the token budget and can leave the reply empty.
- Cases with `json_mode: true` (such as `verdict-review`) get `response_format: {"type": "json_object"}` on Ollama only. The Gateway path relies on the prompt alone.
- The first call after the model unloads is a cold load, so `OLLAMA_TIMEOUT` defaults to 300 s.
- An 8B Q4 model on an RTX 2070 is weaker than Claude on nuanced verdicts. Use `jev compare verdict-review` to check before routing real traffic to it.

### From another local repo

First sibling caller: **aidr-hook-observability**. Export `JEV_API_TOKEN` (same value
as this `.env`) on the `aidr-obs serve` process, keep this sandbox running, then use
**Ask Jev** in the event drawer. That posts a redacted hook capture to
`POST /v1/complete` with `case_id: "verdict-review"` and caches the reply. It doesn't send
`backend` yet, so it gets `JEV_BACKEND`. See
[aidr-hook-observability](https://github.com/SeaBlooms/aidr-hook-observability).

```bash
curl -s http://127.0.0.1:8790/v1/complete \
  -H "Authorization: Bearer $JEV_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"In one sentence, who are you?"}'
```

Python example (needs `jev serve` running):

```bash
uv run python examples/prompt_once.py
uv run python examples/prompt_once.py "In one sentence, what do you do?"
uv run python examples/prompt_once.py --case ping
uv run python examples/prompt_once.py --case verdict-review
uv run python examples/prompt_once.py --case verdict-review --backend ollama
```

See [`examples/prompt_once.py`](examples/prompt_once.py) for the `httpx` call you can copy into a sibling repo (`JEV_API_TOKEN` + `POST /v1/complete`).

## Persona and cases

- [`prompts/system.md`](prompts/system.md) — replace this file to change who Jev is; the server reloads it when the file changes.
- [`prompts/cases/*.yaml`](prompts/cases/) — each file needs `id`, `title`, `prompt`. Optional: `backend` (`gateway` | `ollama`) pins the case, `json_mode: true` asks backends that support it for a JSON object.
  - `ping` — identity check
  - `summarize` — short structured summary
  - `verdict-review` — sample guardrail second-opinion prompt (JSON `stance` + `note`). The dashboard builds a live prompt in the same shape and tags the request with `case_id: "verdict-review"`.

## Env

See [`.env.example`](.env.example): `AI_GATEWAY_API_KEY`, `JEV_MODEL` (default `anthropic/claude-sonnet-5`), `JEV_API_TOKEN`, `JEV_HOST=127.0.0.1`, `JEV_PORT=8790`, `JEV_BACKEND=gateway`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL=qwen3:8b`, `OLLAMA_TIMEOUT=300`.

`OLLAMA_BASE_URL` and `OLLAMA_MODEL` use the same names as `local-llm-workspace`, so values exported in your shell for that repo also apply here (shell env wins over `.env`).

## License

MIT, see [LICENSE](LICENSE).

Out of scope for this pass: tools, streaming, OpenAI-compatible alias, deploy.
