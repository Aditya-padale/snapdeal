#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

command -v python3 >/dev/null || { echo "Python 3 is required." >&2; exit 1; }
command -v npm >/dev/null || { echo "Node.js/npm is required." >&2; exit 1; }

cd "$ROOT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Creating backend virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

echo "Installing backend dependencies..."
"$VENV_DIR/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

echo "Installing frontend dependencies..."
npm install --silent

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "Starting backend at http://localhost:8000"
"$VENV_DIR/bin/python" -m uvicorn backend.main:app --reload --port 8000 &
BACKEND_PID=$!

echo "Starting frontend at http://localhost:5173"
npm run dev -- --host 127.0.0.1