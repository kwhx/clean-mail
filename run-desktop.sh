#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

mkdir -p "$DIR/data/tmp"
export TMPDIR="$DIR/data/tmp"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install fastapi uvicorn python-multipart jinja2 google-genai mcp pywebview
fi

# Ensure pywebview is available in virtualenv
if ! .venv/bin/python -c "import webview" 2>/dev/null; then
    echo "Installing pywebview..."
    .venv/bin/pip install pywebview
fi

echo "Launching CleanMail Native Desktop Window..."
exec .venv/bin/python desktop.py
