#!/usr/bin/env bash
# Startet Lessons Vault auf 127.0.0.1:8765. Zugriff von außen nur über "tailscale serve".
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/uvicorn lessons_vault.main:app_factory --factory --host 127.0.0.1 --port "${LV_PORT:-8765}"
