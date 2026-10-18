"""Verhindert, dass zwei Instanzen gleichzeitig auf dieselbe Datenbank zugreifen.

Ohne Sperre würde eine zweite Instanz beim Start die laufenden Entwürfe der ersten zurücksetzen und einen
zweiten Worker starten, bevor sie am belegten Port scheitert.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO


class LaeuftBereits(RuntimeError):
    pass


class Instanzsperre:
    def __init__(self, ordner: Path):
        self.pfad = ordner / "app.lock"
        self._datei: IO[str] | None = None

    def erwerben(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        datei = open(self.pfad, "a+")
        try:
            if os.name == "nt":
                import msvcrt

                datei.seek(0)
                msvcrt.locking(datei.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(datei.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            datei.close()
            raise LaeuftBereits(
                f"Lessons Vault läuft bereits mit dieser Datenbank ({self.pfad.parent}). "
                "Erst die laufende Instanz beenden (Stop-ScheduledTask -TaskName 'Lessons Vault')."
            ) from exc
        self._datei = datei

    def freigeben(self) -> None:
        if self._datei is not None:
            self._datei.close()
            self._datei = None
