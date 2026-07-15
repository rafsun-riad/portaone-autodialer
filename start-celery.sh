#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

cd "$BACKEND_DIR"

uv run celery -A core worker -l info &
worker_pid=$!

uv run celery -A core beat -l info &
beat_pid=$!

cleanup() {
  kill "$worker_pid" "$beat_pid" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

wait "$worker_pid" "$beat_pid"