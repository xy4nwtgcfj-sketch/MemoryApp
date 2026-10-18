#!/usr/bin/env bash
# Sicherung von Datenbank und Fotos (Linux/macOS). Ziel über LV_BACKUP_ZIEL, sonst ./backups.
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python scripts/backup.py "$@"
