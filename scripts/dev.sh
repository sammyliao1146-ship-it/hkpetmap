#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo '請先建立 .venv 並安裝依賴：python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"'
  exit 1
fi
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001 &
pet_backend_pid=$!
npm --prefix frontend run dev &
pet_frontend_pid=$!
pet_sync_pid=''
if [[ "${PET_START_SYNC_WORKER:-0}" == '1' ]]; then
  .venv/bin/python -m scripts.sync_worker --lock "${PET_SYNC_LOCK_MODE:-redis}" &
  pet_sync_pid=$!
fi
cleanup() {
  kill "$pet_backend_pid" "$pet_frontend_pid" 2>/dev/null || true
  if [[ -n "$pet_sync_pid" ]]; then kill "$pet_sync_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
wait
