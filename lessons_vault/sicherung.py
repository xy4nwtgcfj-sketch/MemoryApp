"""Backups: konsistente Datenbank-Kopie plus Fotos, mit Rotation. Läuft unter Windows und Linux."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def sichern(db_pfad: Path, bilder_ordner: Path, ziel: Path, behalten: int = 30) -> Path:
    """Erzeugt ziel/lessons-<zeit>.db und gleicht ziel/bilder ab. Gibt den Pfad der Datenbank-Sicherung zurück."""
    ziel.mkdir(parents=True, exist_ok=True)
    datei = ziel / f"lessons-{datetime.now():%Y%m%d-%H%M%S}.db"
    quelle = sqlite3.connect(str(db_pfad))
    kopie = sqlite3.connect(str(datei))
    try:
        quelle.backup(kopie)  # konsistent, auch während die App schreibt
    finally:
        kopie.close()
        quelle.close()

    # Fotos inkrementell: nur neue oder geänderte Dateien kopieren
    if bilder_ordner.exists():
        bilder_ziel = ziel / "bilder"
        bilder_ziel.mkdir(exist_ok=True)
        for f in bilder_ordner.glob("*.jpg"):
            z = bilder_ziel / f.name
            if not z.exists() or z.stat().st_size != f.stat().st_size:
                shutil.copy2(f, z)

    for alt in sorted(ziel.glob("lessons-*.db"))[:-behalten]:
        alt.unlink()
    return datei


def pruefen(sicherung: Path) -> dict[str, object]:
    """Prüft eine Sicherung: Integrität, Schemaversion, Anzahl Lessons."""
    conn = sqlite3.connect(f"file:{sicherung}?mode=ro", uri=True)
    try:
        return {
            "integritaet": conn.execute("PRAGMA integrity_check").fetchone()[0],
            "version": conn.execute("PRAGMA user_version").fetchone()[0],
            "lessons": conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0],
        }
    finally:
        conn.close()
