#!/bin/sh
set -eu

# 可选：非交互登录 Codex CLI（需要 OPENAI_API_KEY）
if [ -n "${OPENAI_API_KEY:-}" ]; then
  if command -v codex >/dev/null 2>&1; then
    codex login --api-key "${OPENAI_API_KEY}" 2>/dev/null || true
  fi
fi

if command -v codex >/dev/null 2>&1; then
  echo "codex CLI: $(codex --version 2>/dev/null || codex -V 2>/dev/null || echo 'installed')"
else
  echo "WARNING: codex CLI not found in PATH" >&2
fi

cd /app/backend
exec uvicorn app.codex_service:app --host 0.0.0.0 --port 8787
