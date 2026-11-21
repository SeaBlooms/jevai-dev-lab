#!/usr/bin/env python3
"""Example: prompt the local Jev sandbox and print the reply.

Requires `jev serve` running on 127.0.0.1:8790 and JEV_API_TOKEN set
(same value as jevai-dev-lab/.env).

  # from jevai-dev-lab/ (loads .env automatically)
  uv run python examples/prompt_once.py
  uv run python examples/prompt_once.py "In one sentence, what do you do?"
  uv run python examples/prompt_once.py --case ping

  # from another repo (export the token, or pass --token)
  export JEV_API_TOKEN=…   # match jevai-dev-lab/.env
  python path/to/jevai-dev-lab/examples/prompt_once.py "Hello"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

DEFAULT_BASE = "http://127.0.0.1:8790"
LAB_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    load_dotenv(LAB_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Call the local Jev sandbox once")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="In one sentence, who are you?",
        help="User prompt (ignored when --case is set)",
    )
    parser.add_argument("--case", metavar="ID", help="Run a saved case instead (e.g. ping)")
    parser.add_argument("--backend", choices=("gateway", "ollama"), help="Override the server default backend")
    parser.add_argument("--base-url", default=os.getenv("JEV_BASE_URL", DEFAULT_BASE))
    parser.add_argument(
        "--token",
        default=os.getenv("JEV_API_TOKEN", ""),
        help="Bearer token (default: JEV_API_TOKEN from env / .env)",
    )
    args = parser.parse_args()

    if not args.token:
        print("JEV_API_TOKEN is not set. Export it or put it in jevai-dev-lab/.env", file=sys.stderr)
        raise SystemExit(1)

    headers = {
        "Authorization": f"Bearer {args.token}",
        "Content-Type": "application/json",
    }
    base = args.base_url.rstrip("/")

    try:
        with httpx.Client(timeout=330.0) as client:
            if args.case:
                params = {"backend": args.backend} if args.backend else None
                response = client.post(f"{base}/v1/prompts/{args.case}/run", headers=headers, params=params)
            else:
                response = client.post(
                    f"{base}/v1/complete",
                    headers=headers,
                    json={"prompt": args.prompt, "backend": args.backend},
                )
    except httpx.ConnectError as exc:
        print(f"Cannot reach {base}. Is `uv run jev serve` running?\n{exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if response.status_code != 200:
        print(f"HTTP {response.status_code}: {response.text}", file=sys.stderr)
        raise SystemExit(1)

    data = response.json()
    # Full JSON on stderr if you want metadata; the model text on stdout for piping.
    meta = {k: data[k] for k in ("backend", "model", "persona_sha256", "case_id") if k in data}
    print(json.dumps(meta, indent=2), file=sys.stderr)
    print(data["text"])


if __name__ == "__main__":
    main()
