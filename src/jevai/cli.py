"""CLI: jev serve | jev run <id> | jev smoke."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

import httpx
import uvicorn

from jevai.api import create_app
from jevai.cases import get_case, load_cases
from jevai.config import load_settings
from jevai.gateway import GatewayError, complete
from jevai.persona import load_persona


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jev", description="Jev AI local sandbox")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the local API + prompt page")
    serve.add_argument("--host", default=None, help="Override JEV_HOST (loopback only)")
    serve.add_argument("--port", type=int, default=None, help="Override JEV_PORT")

    run = sub.add_parser("run", help="Run a saved case once and print JSON")
    run.add_argument("case_id", help="Case id from prompts/cases/")

    sub.add_parser("smoke", help="One live ping through the gateway")

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
        print(f"Jev sandbox → http://{host}:{port}/  (health: /health)")
        uvicorn.run(app, host=host, port=port, log_level="info")
        return

    if args.command == "run":
        case = get_case(args.case_id)
        if case is None:
            known = ", ".join(c.id for c in load_cases()) or "(none)"
            print(f"unknown case {args.case_id!r}; known: {known}", file=sys.stderr)
            raise SystemExit(1)
        result = asyncio.run(_complete_once(settings, case.prompt))
        print(
            json.dumps(
                {
                    "text": result["text"],
                    "model": result["model"],
                    "persona_sha256": result["persona_sha256"],
                    "case_id": case.id,
                },
                indent=2,
            )
        )
        return

    if args.command == "smoke":
        if not settings.gateway_configured:
            print(
                "AI_GATEWAY_API_KEY is missing. Copy it into jevai-dev-lab/.env (see .env.example).",
                file=sys.stderr,
            )
            raise SystemExit(1)
        result = asyncio.run(_complete_once(settings, "Reply with exactly: OK"))
        print(f"smoke ok model={result['model']} persona={result['persona_sha256'][:12]}…")
        print(result["text"])
        return

    parser.error(f"unknown command {args.command}")


async def _complete_once(settings, prompt: str) -> dict[str, str]:
    persona = load_persona()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            out = await complete(
                api_key=settings.gateway_api_key,
                model=settings.model,
                system=persona.text,
                user=prompt,
                client=client,
            )
    except GatewayError as exc:
        print(f"gateway error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    return {"text": out.text, "model": out.model, "persona_sha256": persona.sha256}


if __name__ == "__main__":
    main()
