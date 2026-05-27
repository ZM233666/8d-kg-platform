# 应用镜像：FastAPI + Celery（由 compose 指定不同 command）
# docker build -f deploy/Dockerfile.app -t 8dkg-app:local .

FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY backend ./backend

RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/backend \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app/backend

EXPOSE 8000

# 默认启动 API；worker 在 compose 中覆盖 command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
