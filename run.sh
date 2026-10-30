#!/usr/bin/env bash
# Start the Pre-Underwriting Agent (Mac/Linux).
# First run: creates a private Python environment (.venv) and installs dependencies (1-3 minutes).
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install it from https://www.python.org/downloads/ and run ./run.sh again."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Setting up for the first time. This takes 1-3 minutes..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

PORT="${PORT:-8000}"
echo
echo "Starting the app. Open http://localhost:${PORT} in your browser."
echo "Keep this window open while you use the app. Press Ctrl+C to stop."
echo
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload
