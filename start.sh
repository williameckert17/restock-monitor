#!/usr/bin/env bash
# One-command setup and launch for restock-monitor.
# Creates a venv on first run, installs deps, then starts the web dashboard.
set -e

VENV=".venv"

if [ ! -d "$VENV" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

echo "Installing / updating dependencies..."
pip install -q -e .

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it to add credentials."
fi

echo ""
echo "  Starting restock-monitor  →  http://localhost:8000"
echo "  Press Ctrl-C to stop."
echo ""
python serve.py
