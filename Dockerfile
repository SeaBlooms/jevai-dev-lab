# Jev: persona + prompt API in front of Vercel AI Gateway and an Ollama server.
# Secrets come from the environment at run time (AI_GATEWAY_API_KEY, JEV_API_TOKEN); none are baked in.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --uid 10001 --create-home jev
WORKDIR /app
COPY --from=build /app /app
COPY prompts ./prompts
COPY static ./static

# config.py refuses 0.0.0.0 unless JEV_CONTAINER=1; publish the port on loopback only (see aidr-hook-observability/deploy).
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    JEV_CONTAINER=1 \
    JEV_HOST=0.0.0.0 \
    JEV_PORT=8790 \
    OLLAMA_BASE_URL=http://host.docker.internal:11434/v1

USER jev
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8790/health', timeout=4)" || exit 1
CMD ["jev", "serve"]
