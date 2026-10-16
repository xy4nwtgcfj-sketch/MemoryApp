#!/usr/bin/env bash
# Konsistente Kopie der SQLite-Datenbank (auch während die App läuft). Für cron/Aufgabenplanung gedacht.
set -euo pipefail
cd "$(dirname "$0")/.."
DB="${LV_DB_PATH:-data/lessons.db}"
mkdir -p backups
python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" \
  "$DB" "backups/lessons-$(date +%Y-%m-%d).db"
ls -1t backups/lessons-*.db | tail -n +31 | xargs -r rm --
