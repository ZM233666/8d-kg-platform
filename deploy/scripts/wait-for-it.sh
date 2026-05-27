#!/usr/bin/env bash
# 用法: wait-for-it.sh host:port [timeout_seconds]
# 示例: ./wait-for-it.sh postgres:5432 60

set -eu

if [ $# -lt 1 ]; then
  echo "usage: $0 host:port [timeout]" >&2
  exit 1
fi

TARGET=$1
TIMEOUT=${2:-60}

HOST=${TARGET%%:*}
PORT=${TARGET##*:}

if [ "$HOST" = "$PORT" ]; then
  echo "invalid target: $TARGET (expected host:port)" >&2
  exit 1
fi

echo "waiting for ${HOST}:${PORT} (timeout ${TIMEOUT}s)..."

START=$(date +%s)
while true; do
  if (echo >/dev/tcp/"$HOST"/"$PORT") >/dev/null 2>&1; then
    echo "${HOST}:${PORT} is up"
    exit 0
  fi
  NOW=$(date +%s)
  if [ $((NOW - START)) -ge "$TIMEOUT" ]; then
    echo "timeout waiting for ${HOST}:${PORT}" >&2
    exit 1
  fi
  sleep 1
done
