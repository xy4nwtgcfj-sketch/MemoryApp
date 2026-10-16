"""FastAPI-Anwendung: REST-API und Auslieferung der PWA."""

from __future__ import annotations

import hmac
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from . import __version__, db
from .compliance import lesson_text_fuer_pruefung, pruefen
from .config import Settings, load_settings
from .embeddings import EmbeddingFehler, EmbeddingProvider, create_provider, lesson_text
from .models import (
    Bereich,
    BereichUpdate,
    BestaetigungIn,
    DublettenKandidat,
    Einstellungen,
    Entwurf,
    EntwurfAnfrage,
    Lesson,
    LessonImport,
    LessonIn,
    LessonUpdate,
)
from .repository import Invalid, NotFound, Repository
from .search import Filter, Suche
from .structuring import Strukturierer, create_strukturierer

log = logging.getLogger("lessons_vault")
STATIC_DIR = Path(__file__).parent / "static"
TEXTFELDER = {"titel", "situation", "ereignis", "lesson", "massnahme", "tags"}


class LessonAntwort(BaseModel):
    lesson: Lesson
    compliance_hinweise: list[str] = []
    embedding_fehler: str = ""


class CompliancePruefung(BaseModel):
    text: str
    bereich: str = ""


class ImportErgebnis(BaseModel):
    importiert: int
    uebersprungen: int
    fehler: list[str]


def create_app(
    settings: Settings | None = None,
    strukturierer: Strukturierer | None = None,
    provider: EmbeddingProvider | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    conn = db.connect(settings.db_path)
    repo = Repository(conn)
    provider = provider or create_provider(settings.embedding_provider, settings.voyage_api_key, settings.voyage_model)
    strukturierer = strukturierer or create_strukturierer(settings.anthropic_api_key, settings.claude_model, settings.claude_effort)
    suche = Suche(repo, provider)

    app = FastAPI(title="Lessons Vault", version=__version__)
    app.state.repo = repo
    app.state.provider = provider
    app.state.strukturierer = strukturierer

    def auth(request: Request) -> None:
        if not settings.token:
            return
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(supplied.encode(), settings.token.encode()):
            raise HTTPException(status_code=401, detail="Token fehlt oder ist falsch")

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"Nicht gefunden: {exc}"})

    @app.exception_handler(Invalid)
    async def _invalid(_: Request, exc: Invalid) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def embed_lesson(data: Any) -> tuple[Any, str, str]:
        text = lesson_text(data.titel, data.situation, data.ereignis, data.lesson, data.massnahme, data.tags)
        try:
            return provider.embed([text], "document")[0], provider.name, ""
        except EmbeddingFehler as exc:
            log.warning("%s", exc)
            return None, "", "Embedding fehlgeschlagen, Lesson ist nur per Volltext auffindbar. Später 'Neu indexieren'."

    def compliance(data: Any) -> list[str]:
        text = lesson_text_fuer_pruefung(data.titel, data.situation, data.ereignis, data.lesson, data.massnahme, tags=data.tags)
        return pruefen(text, data.bereich, repo.einstellungen().sperrliste)

    deps = [Depends(auth)]

    # Status und Konfiguration -------------------------------------------
    @app.get("/api/status", dependencies=deps)
    def status() -> dict[str, Any]:
        return {
            "version": __version__,
            "ki": strukturierer.verfuegbar,
            "modell": settings.claude_model if strukturierer.verfuegbar else "",
            "embeddings": provider.name,
            "semantisch": provider.semantisch,
        }

    @app.get("/api/bereiche", dependencies=deps)
    def bereiche_liste() -> list[Bereich]:
        return repo.bereiche()

    @app.post("/api/bereiche", dependencies=deps, status_code=201)
    def bereich_anlegen(bereich: Bereich) -> Bereich:
        return repo.bereich_anlegen(bereich)

    @app.patch("/api/bereiche/{name}", dependencies=deps)
    def bereich_aendern(name: str, update: BereichUpdate) -> Bereich:
        return repo.bereich_aendern(name, update.aktiv, update.beispiele)

    @app.get("/api/einstellungen", dependencies=deps)
    def einstellungen() -> Einstellungen:
        return repo.einstellungen()

    @app.put("/api/einstellungen", dependencies=deps)
    def einstellungen_speichern(data: Einstellungen) -> Einstellungen:
        data.sperrliste = sorted({s.strip() for s in data.sperrliste if s.strip()}, key=str.lower)
        return repo.einstellungen_speichern(data)

    # Erfassen ------------------------------------------------------------
    def kandidaten_fuer(text: str) -> list[DublettenKandidat]:
        filt = Filter(ohne_ueberholt=True)
        try:
            ergebnisse = suche.semantisch(text, filt, limit=5)
        except EmbeddingFehler:
            ergebnisse = suche.volltext(text, filt, limit=5)
        kandidaten = []
        for lesson_id, score in ergebnisse:
            l = repo.holen(lesson_id)
            kandidaten.append(
                DublettenKandidat(
                    id=l.id, titel=l.titel, lesson=l.lesson, bereich=l.bereich, status=l.status,
                    bestaetigungen=l.bestaetigungen, aehnlichkeit=round(score, 3),
                )
            )
        return kandidaten

    @app.post("/api/erfassen/entwurf", dependencies=deps)
    def entwurf(anfrage: EntwurfAnfrage) -> Entwurf:
        aktive = repo.bereiche(nur_aktive=True)
        voller_text = anfrage.text if not anfrage.antwort else f"{anfrage.text}\n{anfrage.antwort}"
        kandidaten = kandidaten_fuer(voller_text)
        ergebnis = strukturierer.strukturieren(
            anfrage.text, anfrage.quelle, aktive, kandidaten, anfrage.rueckfrage, anfrage.antwort
        )
        if not ergebnis.ki_verwendet and kandidaten:
            besten = kandidaten[0]
            if besten.aehnlichkeit >= provider.dublettenschwelle:
                ergebnis.dublette = besten
                ergebnis.dublette_begruendung = f"Sehr ähnlicher Text (Ähnlichkeit {besten.aehnlichkeit:.2f})."
        ergebnis.aehnliche = [k for k in kandidaten if not ergebnis.dublette or k.id != ergebnis.dublette.id]
        lokale = pruefen(
            lesson_text_fuer_pruefung(voller_text, ergebnis.titel, ergebnis.situation, ergebnis.ereignis,
                                      ergebnis.lesson, ergebnis.massnahme, tags=ergebnis.tags),
            ergebnis.bereich,
            repo.einstellungen().sperrliste,
        )
        ergebnis.compliance_hinweise = list(dict.fromkeys([*lokale, *ergebnis.compliance_hinweise]))
        return ergebnis

    @app.post("/api/compliance", dependencies=deps)
    def compliance_pruefen(data: CompliancePruefung) -> list[str]:
        return pruefen(data.text, data.bereich, repo.einstellungen().sperrliste)

    # Lessons -------------------------------------------------------------
    @app.get("/api/lessons", dependencies=deps)
    def lessons_liste(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> list[Lesson]:
        return repo.liste(limit=limit, offset=offset)

    @app.post("/api/lessons", dependencies=deps, status_code=201)
    def lesson_anlegen(data: LessonIn) -> LessonAntwort:
        vector, modell, fehler = embed_lesson(data)
        lesson = repo.anlegen(data, vector, modell)
        return LessonAntwort(lesson=lesson, compliance_hinweise=compliance(data), embedding_fehler=fehler)

    @app.get("/api/lessons/{lesson_id}", dependencies=deps)
    def lesson_holen(lesson_id: str) -> dict[str, Any]:
        lesson = repo.holen(lesson_id)
        return {
            "lesson": lesson,
            "protokoll": repo.bestaetigungs_protokoll(lesson_id),
            "compliance_hinweise": compliance(lesson),
        }

    @app.put("/api/lessons/{lesson_id}", dependencies=deps)
    def lesson_aendern(lesson_id: str, update: LessonUpdate) -> LessonAntwort:
        vorher = repo.holen(lesson_id)
        changed = update.model_dump(exclude_unset=True, exclude_none=True)
        vector, modell, fehler = None, None, ""
        if TEXTFELDER & changed.keys():
            merged = vorher.model_copy(update=changed)
            vector, modell, fehler = embed_lesson(merged)
        lesson = repo.aendern(lesson_id, update, vector, modell)
        return LessonAntwort(lesson=lesson, compliance_hinweise=compliance(lesson), embedding_fehler=fehler)

    @app.delete("/api/lessons/{lesson_id}", dependencies=deps, status_code=204)
    def lesson_loeschen(lesson_id: str) -> None:
        repo.loeschen(lesson_id)

    @app.post("/api/lessons/{lesson_id}/bestaetigen", dependencies=deps)
    def lesson_bestaetigen(lesson_id: str, data: BestaetigungIn | None = None) -> Lesson:
        return repo.bestaetigen(lesson_id, data.notiz if data else "")

    # Suche ---------------------------------------------------------------
    @app.get("/api/suche", dependencies=deps)
    def suchen(
        q: str = "",
        modus: str = Query("hybrid", pattern="^(hybrid|volltext|semantisch)$"),
        bereich: str | None = None,
        status: str | None = Query(None, pattern="^(neu|bestätigt|überholt)$"),
        schweregrad_min: int | None = Query(None, ge=1, le=5),
        von: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}"),
        bis: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}"),
        limit: int = Query(30, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        filt = Filter(bereich=bereich or None, status=status or None, schweregrad_min=schweregrad_min, von=von, bis=bis)
        try:
            treffer = suche.suchen(q, modus, filt, limit)  # type: ignore[arg-type]
        except EmbeddingFehler as exc:
            log.warning("%s", exc)
            treffer = suche.suchen(q, "volltext", filt, limit)
        return [{"lesson": t.lesson, "score": t.score, "gefunden_durch": t.gefunden_durch} for t in treffer]

    # Bestand ---------------------------------------------------------------
    @app.get("/api/export", dependencies=deps)
    def export() -> JSONResponse:
        payload = {
            "format": "lessons-vault",
            "version": 1,
            "exportiert_am": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bereiche": [b.model_dump() for b in repo.bereiche()],
            "lessons": [l.model_dump(exclude={"embedding_modell", "erfassung_sekunden"}) for l in repo.alle()],
        }
        stamp = datetime.now().strftime("%Y-%m-%d")
        return JSONResponse(
            payload, headers={"Content-Disposition": f'attachment; filename="lessons-vault-{stamp}.json"'}
        )

    @app.post("/api/import", dependencies=deps)
    def importieren(payload: dict[str, Any] | list[Any]) -> ImportErgebnis:
        if isinstance(payload, dict):
            for b in payload.get("bereiche", []):
                try:
                    bereich = Bereich(**b)
                except ValidationError:
                    continue
                if not repo.bereich_existiert(bereich.name):
                    repo.bereich_anlegen(bereich)
            eintraege = payload.get("lessons", [])
        else:
            eintraege = payload
        importiert, uebersprungen, fehler = 0, 0, []
        gueltige: list[LessonImport] = []
        for i, eintrag in enumerate(eintraege, start=1):
            try:
                item = LessonImport(**eintrag)
            except (ValidationError, TypeError) as exc:
                msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
                fehler.append(f"Eintrag {i}: {msg}")
                continue
            if item.id and repo.existiert(item.id):
                uebersprungen += 1
                continue
            if not repo.bereich_existiert(item.bereich):
                fehler.append(f"Eintrag {i} ({item.titel}): unbekannter Bereich '{item.bereich}'")
                continue
            gueltige.append(item)
        texte = [lesson_text(g.titel, g.situation, g.ereignis, g.lesson, g.massnahme, g.tags) for g in gueltige]
        vektoren: list[Any] = [None] * len(gueltige)
        try:
            for start in range(0, len(texte), 64):
                vektoren[start : start + 64] = provider.embed(texte[start : start + 64], "document")
        except EmbeddingFehler as exc:
            fehler.append(f"Embeddings fehlgeschlagen ({exc}). Lessons ohne Embedding importiert, bitte neu indexieren.")
        for item, vector in zip(gueltige, vektoren):
            try:
                repo.anlegen(item, vector, provider.name if vector is not None else "")
                importiert += 1
            except Invalid as exc:
                fehler.append(f"{item.titel}: {exc}")
        return ImportErgebnis(importiert=importiert, uebersprungen=uebersprungen, fehler=fehler)

    @app.post("/api/reindex", dependencies=deps)
    def reindex() -> dict[str, Any]:
        lessons = repo.alle()
        anzahl = 0
        for start in range(0, len(lessons), 64):
            batch = lessons[start : start + 64]
            texte = [lesson_text(l.titel, l.situation, l.ereignis, l.lesson, l.massnahme, l.tags) for l in batch]
            try:
                vektoren = provider.embed(texte, "document")
            except EmbeddingFehler as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            for lesson, vector in zip(batch, vektoren):
                repo.embedding_setzen(lesson.id, vector, provider.name)
                anzahl += 1
        return {"neu_indexiert": anzahl, "embeddings": provider.name}

    @app.get("/api/statistik", dependencies=deps)
    def statistik() -> dict[str, Any]:
        return repo.statistik()

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def app_factory() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app()
