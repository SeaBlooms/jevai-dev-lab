"""Env and path config. Host is locked to loopback."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT / "prompts"
CASES_DIR = PROMPTS_DIR / "cases"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system.md"
STATIC_DIR = ROOT / "static"

ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
CONTAINER_BIND = "0.0.0.0"

BackendName = Literal["gateway", "ollama"]
BACKENDS: tuple[BackendName, ...] = get_args(BackendName)

GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_GATEWAY_MODEL = "anthropic/claude-sonnet-5"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"


@dataclass(frozen=True)
class BackendConfig:
    name: BackendName
    label: str
    base_url: str
    api_key: str
    model: str
    timeout: float
    requires_key: bool
    supports_json_mode: bool
    extra_body: tuple[tuple[str, str], ...] = ()

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    @property
    def configured(self) -> bool:
        if self.requires_key:
            return bool(self.api_key.strip())
        return bool(self.base_url.strip())


@dataclass(frozen=True)
class Settings:
    gateway_api_key: str
    model: str
    api_token: str
    host: str
    port: int
    default_backend: BackendName = "gateway"
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    ollama_timeout: float = 300.0

    @property
    def gateway_configured(self) -> bool:
        return bool(self.gateway_api_key.strip())

    def backend(self, name: BackendName | None = None) -> BackendConfig:
        name = name or self.default_backend
        if name == "gateway":
            return BackendConfig(
                name="gateway",
                label="AI Gateway",
                base_url=GATEWAY_BASE_URL,
                api_key=self.gateway_api_key,
                model=self.model,
                timeout=120.0,
                requires_key=True,
                supports_json_mode=False,
            )
        if name == "ollama":
            return BackendConfig(
                name="ollama",
                label="Homelab Ollama",
                base_url=self.ollama_base_url,
                api_key="",
                model=self.ollama_model,
                timeout=self.ollama_timeout,
                requires_key=False,
                supports_json_mode=True,
                # qwen3 thinks by default; the trace counts toward max_tokens and can leave content empty.
                extra_body=(("reasoning_effort", "none"),),
            )
        raise ValueError(f"Unknown backend {name!r}; expected one of {list(BACKENDS)}")


def host_allowed(host: str) -> bool:
    """Loopback always; 0.0.0.0 only inside a container (JEV_CONTAINER=1), where Docker publishes the port."""
    if host in ALLOWED_HOSTS:
        return True
    return host == CONTAINER_BIND and os.getenv("JEV_CONTAINER", "").strip() == "1"


def parse_backend(value: str | None) -> BackendName | None:
    if value is None or not value.strip():
        return None
    name = value.strip().lower()
    if name not in BACKENDS:
        raise ValueError(f"Unknown backend {value!r}; expected one of {list(BACKENDS)}")
    return name  # type: ignore[return-value]


def load_settings(*, dotenv_path: Path | None = None) -> Settings:
    load_dotenv(dotenv_path or (ROOT / ".env"), override=False)

    host = os.getenv("JEV_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if not host_allowed(host):
        raise ValueError(
            f"JEV_HOST={host!r} is not allowed. Bind only to loopback: {sorted(ALLOWED_HOSTS)} "
            f"({CONTAINER_BIND} needs JEV_CONTAINER=1)"
        )

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

    try:
        default_backend = parse_backend(os.getenv("JEV_BACKEND")) or "gateway"
    except ValueError as exc:
        raise ValueError(f"JEV_BACKEND: {exc}") from exc

    timeout_raw = os.getenv("OLLAMA_TIMEOUT", "300").strip() or "300"
    try:
        ollama_timeout = float(timeout_raw)
    except ValueError as exc:
        raise ValueError(f"OLLAMA_TIMEOUT must be a number, got {timeout_raw!r}") from exc
    if ollama_timeout <= 0:
        raise ValueError(f"OLLAMA_TIMEOUT must be positive, got {ollama_timeout}")

    return Settings(
        gateway_api_key=os.getenv("AI_GATEWAY_API_KEY", "").strip(),
        model=os.getenv("JEV_MODEL", DEFAULT_GATEWAY_MODEL).strip() or DEFAULT_GATEWAY_MODEL,
        api_token=token,
        host=host,
        port=port,
        default_backend=default_backend,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).strip() or DEFAULT_OLLAMA_BASE_URL,
        ollama_model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL,
        ollama_timeout=ollama_timeout,
    )
