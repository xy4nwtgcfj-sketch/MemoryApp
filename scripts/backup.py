"""Sicherung von Datenbank und Fotos. Ziel: LV_BACKUP_ZIEL (z. B. ein OneDrive- oder NAS-Ordner), sonst ./backups.

Aufruf: .venv\\Scripts\\python scripts\\backup.py          (Windows)
        .venv/bin/python scripts/backup.py              (Linux)
        ... scripts/backup.py --pruefen <datei.db>      (Sicherung prüfen)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from lessons_vault.config import load_settings  # noqa: E402
from lessons_vault.sicherung import pruefen, sichern  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--pruefen":
        print(pruefen(Path(argv[1])))
        return 0
    settings = load_settings()
    db_pfad = Path(settings.db_path)
    bilder = Path(settings.bilder_pfad) if settings.bilder_pfad else db_pfad.parent / "bilder"
    ziel = Path(os.environ.get("LV_BACKUP_ZIEL", "backups"))
    datei = sichern(db_pfad, bilder, ziel)
    ergebnis = pruefen(datei)
    print(f"Sicherung: {datei} {ergebnis}")
    return 0 if ergebnis["integritaet"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
