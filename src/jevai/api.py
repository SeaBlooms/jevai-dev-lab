"""FastAPI app: health, prompts, complete, and static prompt page."""

from __future__ import annotations

import logging
import secrets
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from jevai.cases import Case, get_case, load_cases
from jevai.config import STATIC_DIR, Settings, load_settings
from jevai.gateway import GatewayError, complete
from jevai.persona import PersonaCache

logger = logging.getLogger("jevai")

bearer_scheme = HTTPBearer(auto_error=False)


class CompleteRequest(BaseModel):
    prompt: str = Field(min_length=1)
    case_id: str | None = None


class CompleteResponse(BaseModel):
    text: str
    model: str
    persona_sha256: str
    case_id: str | None = None


class CaseOut(BaseModel):
    id: str
    title: str
    prompt: str


class HealthResponse(BaseModel):
    status: str
    model: str
    persona_sha256: str
    gateway_configured: bool


def create_app(
    settings: Settings | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    cfg = settings or load_settings()
    persona_cache = PersonaCache()
    app = FastAPI(title="Jev AI sandbox", version="0.1.0")
    app.state.settings = cfg
    app.state.persona_cache = persona_cache
    app.state.http_client = http_client

    def require_token(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    ) -> None:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Missing bearer token")
        if not secrets.compare_digest(credentials.credentials, cfg.api_token):
            raise HTTPException(status_code=401, detail="Invalid token")

    async def run_completion(prompt: str, case_id: str | None) -> CompleteResponse:
        persona = persona_cache.get()
        try:
            result = await complete(
                api_key=cfg.gateway_api_key,
                model=cfg.model,
                system=persona.text,
                user=prompt,
                client=app.state.http_client,
            )
        except GatewayError as exc:
            status = 503 if exc.status_code == 503 else 502
            logger.warning("gateway failure case_id=%s status=%s", case_id, exc.status_code)
            raise HTTPException(status_code=status, detail=str(exc)) from exc

        logger.info("complete ok case_id=%s model=%s", case_id, result.model)
        logger.debug("prompt=%s", prompt)
        return CompleteResponse(
            text=result.text,
            model=result.model,
            persona_sha256=persona.sha256,
            case_id=case_id,
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        persona = persona_cache.get()
        return HealthResponse(
            status="ok",
            model=cfg.model,
            persona_sha256=persona.sha256,
            gateway_configured=cfg.gateway_configured,
        )

    @app.get("/prompts", response_model=list[CaseOut], dependencies=[Depends(require_token)])
    async def list_prompts() -> list[CaseOut]:
        return [_case_out(c) for c in load_cases()]

    @app.post("/v1/complete", response_model=CompleteResponse, dependencies=[Depends(require_token)])
    async def complete_route(body: CompleteRequest) -> CompleteResponse:
        return await run_completion(body.prompt.strip(), body.case_id)

    @app.post(
        "/v1/prompts/{case_id}/run",
        response_model=CompleteResponse,
        dependencies=[Depends(require_token)],
    )
    async def run_prompt(case_id: str) -> CompleteResponse:
        case = get_case(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"Unknown case: {case_id}")
        return await run_completion(case.prompt, case.id)

    @app.get("/")
    async def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=404, detail="static/index.html missing")
        return FileResponse(index_path)

    return app


def _case_out(case: Case) -> CaseOut:
    return CaseOut(id=case.id, title=case.title, prompt=case.prompt)


# Default app for uvicorn `jevai.api:app` when settings are available at import time.
# CLI uses create_app() explicitly so missing .env fails in the CLI, not at import.
app = None
