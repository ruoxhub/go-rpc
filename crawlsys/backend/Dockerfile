FROM python:3.11-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.30 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.11-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg libodbc2 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --user-group --create-home --shell /usr/sbin/nologin crawlstore
WORKDIR /app
COPY --from=builder --chown=crawlstore:crawlstore /app/.venv ./.venv
COPY --chown=crawlstore:crawlstore app ./app
COPY --chown=crawlstore:crawlstore scripts/migrate_llm_provider_formats.sql /app/scripts/migrate_llm_provider_formats.sql
COPY --chown=crawlstore:crawlstore scripts/migrate_llm_provider_credentials.py /app/scripts/migrate_llm_provider_credentials.py
COPY --chown=crawlstore:crawlstore main.py ./main.py
COPY --chown=crawlstore:crawlstore config.docker.toml ./config.toml
RUN mkdir -p /app/logs && chown crawlstore:crawlstore /app/logs
USER crawlstore
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/docs', timeout=3)"]
CMD ["python", "main.py"]
