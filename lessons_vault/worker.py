"""Hintergrund-Worker: strukturiert wartende Entwürfe mit dem lokalen Modell und holt Embeddings nach.

Ein einziger Thread, weil ein lokales Modell auf 4 CPU-Kernen ohnehin nur eine Anfrage sinnvoll
abarbeiten kann.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .embeddings import EmbeddingFehler, EmbeddingProvider, lesson_text
from .models import Entwurf, EntwurfEintrag
from .repository import Repository

log = logging.getLogger(__name__)

Verarbeiter = Callable[[EntwurfEintrag], Entwurf]


class ModellNichtBereit(Exception):
    """Das lokale Modell ist (gerade) nicht erreichbar. Der Entwurf wartet, statt als Fehler zu enden."""


class Hintergrund:
    def __init__(
        self,
        repo: Repository,
        provider: EmbeddingProvider,
        verarbeiter: Verarbeiter,
        modell_name: str,
        leerlauf_sekunden: float = 30.0,
        backoff_sekunden: float = 60.0,
        pflege: Callable[[], object] | None = None,
        pflege_intervall: float = 3600.0,
        bereit: Callable[[], bool] | None = None,
    ):
        self.repo = repo
        self.provider = provider
        self.verarbeiter = verarbeiter
        self.modell_name = modell_name
        self.leerlauf_sekunden = leerlauf_sekunden
        self.backoff_sekunden = backoff_sekunden
        self._event = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.aktueller_entwurf: str | None = None
        self.bereit = bereit
        self.wartet_auf_modell = False
        self.pflege = pflege
        self.pflege_intervall = pflege_intervall
        self._letzte_pflege = float("-inf")

    # Einzelschritte (direkt testbar) ------------------------------------
    def verarbeite_naechsten(self) -> bool:
        if self.bereit is not None and self.repo.entwuerfe_zaehlen()["wartet"]:
            self.wartet_auf_modell = not self.bereit()
            if self.wartet_auf_modell:
                return False
        eintrag = self.repo.naechsten_entwurf_reservieren()
        if eintrag is None:
            return False
        self.aktueller_entwurf = eintrag.id
        start = time.monotonic()
        try:
            entwurf = self.verarbeiter(eintrag)
            fehlgeschlagen = not entwurf.ki_verwendet and bool(entwurf.ki_fehler)
            self.repo.entwurf_ergebnis(
                eintrag.id, entwurf, "fehler" if fehlgeschlagen else "fertig",
                entwurf.ki_fehler if fehlgeschlagen else "", entwurf.ki_modell or self.modell_name,
                time.monotonic() - start,
            )
        except ModellNichtBereit:
            log.info("Lokales Modell nicht erreichbar, Entwurf %s wartet", eintrag.id)
            self.repo.entwurf_zuruecklegen(eintrag.id)
            self.wartet_auf_modell = True
            return False
        except Exception as exc:  # Worker darf nie sterben; Rohtext bleibt erhalten.
            log.exception("Entwurf %s fehlgeschlagen", eintrag.id)
            self.repo.entwurf_ergebnis(eintrag.id, None, "fehler", str(exc) or exc.__class__.__name__, self.modell_name, time.monotonic() - start)
        finally:
            self.aktueller_entwurf = None
        return True

    def nachindexieren(self, batch: int = 16) -> int:
        # Ein nicht-semantischer Ersatz überschreibt nie vorhandene (bessere) Embeddings.
        lessons = self.repo.lessons_ohne_embedding(self.provider.name, batch, nur_fehlende=not self.provider.semantisch)
        if not lessons:
            return 0
        texte = [lesson_text(l.titel, l.situation, l.ereignis, l.lesson, l.massnahme, l.tags) for l in lessons]
        vektoren = self.provider.embed(texte, "document")
        for lesson, vector in zip(lessons, vektoren):
            self.repo.embedding_setzen(lesson.id, vector, self.provider.name)
        log.info("%d Lessons mit %s nachindexiert", len(lessons), self.provider.name)
        return len(lessons)

    # Thread ----------------------------------------------------------------
    def wecken(self) -> None:
        self._event.set()

    def start(self) -> None:
        zurueckgesetzt = self.repo.entwuerfe_zuruecksetzen()
        if zurueckgesetzt:
            log.info("%d unterbrochene Entwürfe wieder eingereiht", zurueckgesetzt)
        self._thread = threading.Thread(target=self._loop, name="lessons-vault-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._event.set()
        if self._thread:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.verarbeite_naechsten():
                    continue
                if self.nachindexieren():
                    continue
                if self.pflege and time.monotonic() - self._letzte_pflege > self.pflege_intervall:
                    self._letzte_pflege = time.monotonic()
                    self.pflege()
                wartezeit = self.leerlauf_sekunden
            except EmbeddingFehler as exc:
                log.warning("Nachindexieren pausiert: %s", exc)
                wartezeit = self.backoff_sekunden
            except Exception:  # Worker darf nicht sterben
                log.exception("Unerwarteter Fehler im Worker")
                wartezeit = self.backoff_sekunden
            self._event.wait(wartezeit)
            self._event.clear()
