"""本地 Codex 抽取服务。

提供一个极薄的 HTTP 适配层:
POST /extract -> codex exec -> 结构化 JSON
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.core.logging import setup_logging
from app.services.codex_exec_runner import (
    CodexExecError,
    CodexExtractorRequest,
    CodexExtractorResponse,
    build_codex_exec_runner,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    app.state.codex_runner = build_codex_exec_runner()
    yield


app = FastAPI(
    title="Local Codex Extractor Service",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract", response_model=CodexExtractorResponse)
async def extract(req: CodexExtractorRequest) -> CodexExtractorResponse:
    runner = app.state.codex_runner
    try:
        return await runner.extract(req)
    except CodexExecError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
