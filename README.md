# jevai-dev-lab

Local sandbox for the **Jev** persona: a checked-in system prompt in front of [Vercel AI Gateway](https://vercel.com/docs/ai-gateway/openai-compat), with a small REST API and a page for saved test prompts.

Callers never send the system prompt and never see the gateway key. Bind is loopback-only (`127.0.0.1:8790`).

## Setup

```bash
cd jevai-dev-lab
uv sync --group dev
cp .env.example .env
# set AI_GATEWAY_API_KEY (copy by hand from vanishaudio-ops/.env.local — this process does not read it)
# set JEV_API_TOKEN to any local secret
```

## Commands

```bash
uv run jev serve          # http://127.0.0.1:8790/  — prompt page + API
uv run jev run ping       # one saved case → JSON on stdout
uv run jev smoke          # one live gateway call (needs AI_GATEWAY_API_KEY)

uv run pytest
uv run ruff check src tests
```

## API

Bearer `JEV_API_TOKEN` on every route except `GET /health`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Up, model id, persona sha256 |
| `GET` | `/prompts` | Saved cases (id, title, prompt) |
| `POST` | `/v1/complete` | `{ "prompt": "…", "case_id": null }` → `{ text, model, persona_sha256, case_id }` |
| `POST` | `/v1/prompts/{id}/run` | Run a case from `prompts/cases/` |
| `GET` | `/` | Prompt page |

### From another local repo

First sibling caller: **aidr-hook-observability**. Export `JEV_API_TOKEN` (same value
as this `.env`) on the `aidr-obs serve` process, keep this sandbox running, then use
**Ask Jev** in the event drawer. That posts a redacted hook capture to
`POST /v1/complete` with `case_id: "verdict-review"` and caches the reply. See
[aidr-hook-observability/README.md](../aidr-hook-observability/README.md).

```bash
curl -s http://127.0.0.1:8790/v1/complete \
  -H "Authorization: Bearer $JEV_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"In one sentence, who are you?"}'
```

Python example (needs `jev serve` running):

```bash
uv run python examples/prompt_once.py
uv run python examples/prompt_once.py "What is vanishaudio-site?"
uv run python examples/prompt_once.py --case ping
```

See [`examples/prompt_once.py`](examples/prompt_once.py) for the `httpx` call you can copy into a sibling repo (`JEV_API_TOKEN` + `POST /v1/complete`).

## Persona and cases

- [`prompts/system.md`](prompts/system.md) — replace this file to change who Jev is; the server reloads it when the file changes.
- [`prompts/cases/*.yaml`](prompts/cases/) — each file needs `id`, `title`, `prompt`.

## Env

See [`.env.example`](.env.example): `AI_GATEWAY_API_KEY`, `JEV_MODEL` (default `anthropic/claude-sonnet-5`), `JEV_API_TOKEN`, `JEV_HOST=127.0.0.1`, `JEV_PORT=8790`.

Out of scope for this pass: tools, streaming, OpenAI-compatible alias, deploy.
