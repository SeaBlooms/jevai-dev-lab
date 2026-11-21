"""CLI: jev serve | jev run <id> | jev smoke | jev compare <id>."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

import httpx
import uvicorn

from jevai.api import create_app
from jevai.cases import Case, get_case, load_cases
from jevai.config import BACKENDS, BackendName, Settings, load_settings
from jevai.gateway import UpstreamError, complete
from jevai.persona import load_persona


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jev", description="Jev AI local sandbox")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the local API + prompt page")
    serve.add_argument("--host", default=None, help="Override JEV_HOST (loopback only)")
    serve.add_argument("--port", type=int, default=None, help="Override JEV_PORT")

    run = sub.add_parser("run", help="Run a saved case once and print JSON")
    run.add_argument("case_id", help="Case id from prompts/cases/")
    run.add_argument("--backend", choices=BACKENDS, default=None, help="Override case / JEV_BACKEND")

    smoke = sub.add_parser("smoke", help="One live ping through a backend")
    smoke.add_argument("--backend", choices=BACKENDS, default=None, help="Override JEV_BACKEND")

    compare = sub.add_parser("compare", help="Run a saved case on every backend and print both replies")
    compare.add_argument("case_id", help="Case id from prompts/cases/")

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.command == "serve":
        host = args.host or settings.host
        port = args.port or settings.port
        # Re-validate host if overridden on CLI
        from jevai.config import ALLOWED_HOSTS

        if host not in ALLOWED_HOSTS:
            print(f"host {host!r} not allowed; use loopback only", file=sys.stderr)
            raise SystemExit(1)
        app = create_app(settings)
        print(f"Jev sandbox → http://{host}:{port}/  (health: /health, default backend: {settings.default_backend})")
        uvicorn.run(app, host=host, port=port, log_level="info")
        return

    if args.command == "run":
        case = _require_case(args.case_id)
        backend = args.backend or case.backend
        try:
            result = asyncio.run(_complete_once(settings, case.prompt, backend, json_mode=case.json_mode))
        except UpstreamError as exc:
            print(f"upstream error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(json.dumps({**result, "case_id": case.id}, indent=2))
        return

    if args.command == "smoke":
        backend = settings.backend(args.backend)
        if not backend.configured:
            print(
                "AI_GATEWAY_API_KEY is missing. Copy it into jevai-dev-lab/.env (see .env.example).",
                file=sys.stderr,
            )
            raise SystemExit(1)
        try:
            result = asyncio.run(_complete_once(settings, "Reply with exactly: OK", backend.name))
        except UpstreamError as exc:
            print(f"upstream error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"smoke ok backend={result['backend']} model={result['model']} persona={result['persona_sha256'][:12]}…")
        print(result["text"])
        return

    if args.command == "compare":
        case = _require_case(args.case_id)
        out = asyncio.run(_compare(settings, case))
        print(json.dumps(out, indent=2))
        if all("error" in r for r in out["results"].values()):
            raise SystemExit(1)
        return

    parser.error(f"unknown command {args.command}")


def _require_case(case_id: str) -> Case:
    case = get_case(case_id)
    if case is None:
        known = ", ".join(c.id for c in load_cases()) or "(none)"
        print(f"unknown case {case_id!r}; known: {known}", file=sys.stderr)
        raise SystemExit(1)
    return case


async def _complete_once(
    settings: Settings,
    prompt: str,
    backend_name: BackendName | None,
    *,
    json_mode: bool = False,
) -> dict[str, str]:
    persona = load_persona()
    backend = settings.backend(backend_name)
    async with httpx.AsyncClient() as client:
        out = await complete(backend, system=persona.text, user=prompt, json_mode=json_mode, client=client)
    return {
        "text": out.text,
        "model": out.model,
        "backend": out.backend,
        "persona_sha256": persona.sha256,
    }


async def _compare(settings: Settings, case: Case) -> dict[str, object]:
    persona = load_persona()

    async def one(name: BackendName, client: httpx.AsyncClient) -> dict[str, str]:
        backend = settings.backend(name)
        try:
            out = await complete(backend, system=persona.text, user=case.prompt, json_mode=case.json_mode, client=client)
        except UpstreamError as exc:
            return {"model": backend.model, "error": str(exc)}
        return {"model": out.model, "text": out.text}

    async with httpx.AsyncClient() as client:
        replies = await asyncio.gather(*(one(name, client) for name in BACKENDS))
    return {
        "case_id": case.id,
        "persona_sha256": persona.sha256,
        "results": dict(zip(BACKENDS, replies, strict=True)),
    }


if __name__ == "__main__":
    main()
