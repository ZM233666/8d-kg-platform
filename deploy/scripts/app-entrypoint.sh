#!/bin/sh
# 单容器双进程（可选）；推荐 compose 中拆成 app-api + app-worker
set -eu

cd /app/backend

uvicorn app.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

celery -A app.tasks.celery_app worker -l info &
WORKER_PID=$!

term_handler() {
  kill -TERM "$API_PID" "$WORKER_PID" 2>/dev/null || true
  wait "$API_PID" "$WORKER_PID" 2>/dev/null || true
  exit 0
}

trap term_handler INT TERM

wait -n
EXIT_CODE=$?
term_handler
exit "$EXIT_CODE"
