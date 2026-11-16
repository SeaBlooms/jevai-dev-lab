"""Env and path config. Host is locked to loopback."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT / "prompts"
CASES_DIR = PROMPTS_DIR / "cases"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system.md"
STATIC_DIR = ROOT / "static"

ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class Settings:
    gateway_api_key: str
    model: str
    api_token: str
    host: str
    port: int

    @property
    def gateway_configured(self) -> bool:
        return bool(self.gateway_api_key.strip())


def load_settings(*, dotenv_path: Path | None = None) -> Settings:
    load_dotenv(dotenv_path or (ROOT / ".env"), override=False)

    host = os.getenv("JEV_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"JEV_HOST={host!r} is not allowed. Bind only to loopback: {sorted(ALLOWED_HOSTS)}")

    port_raw = os.getenv("JEV_PORT", "8790").strip() or "8790"
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"JEV_PORT must be an integer, got {port_raw!r}") from exc
    if not (1 <= port <= 65535):
        raise ValueError(f"JEV_PORT out of range: {port}")

    token = os.getenv("JEV_API_TOKEN", "").strip()
    if not token:
        raise ValueError("JEV_API_TOKEN is required (set it in .env; see .env.example)")

    return Settings(
        gateway_api_key=os.getenv("AI_GATEWAY_API_KEY", "").strip(),
        model=os.getenv("JEV_MODEL", "anthropic/claude-sonnet-5").strip() or "anthropic/claude-sonnet-5",
        api_token=token,
        host=host,
        port=port,
    )
