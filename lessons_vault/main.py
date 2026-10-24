"""FastAPI-Anwendung: REST-API und Auslieferung der PWA."""

from __future__ import annotations

from urllib.parse import quote

import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import anthropic
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import __version__, db
from .briefing import BriefingSchreiber, kombinieren, lokale_checkliste, rangliste
from .compliance import lesson_text_fuer_pruefung, pruefen, sperrbegriffe_schwaerzen, sperrliste_treffer
from .config import Settings, load_settings
from .foto import abgleich_inhalt, abgleichen, kandidaten_finden, kandidaten_inhalt
from .images import BildFehler, Bildspeicher, Texterkennung
from .embeddings import (
    EmbeddingFehler,
    EmbeddingProvider,
    create_provider,
    lesson_text,
    modell_installiert,
    ollama_status,
    provider_fuer_bestand,
)
from .models import (
    AntwortIn,
    BildLinks,
    Bereich,
    BereichUpdate,
    BestaetigungIn,
    DublettenKandidat,
    Einstellungen,
    Entwurf,
    EntwurfAnfrage,
    EntwurfEintrag,
    ErfassenAnfrage,
    FotoAnfrage,
    Lesson,
    LessonImport,
    LessonIn,
    LessonUpdate,
    NotizAnfrage,
    RueckmeldungIn,
    StrukturierenAnfrage,
)
from .repository import Invalid, NotFound, Repository
from .search import Filter, Suche, suchbegriffe
from .structuring import BasisStrukturierer, OllamaStrukturierer, Strukturierer, create_strukturierer, manueller_entwurf
from .einzelinstanz import Instanzsperre
from .zugang import SicherheitsMiddleware, zugangstoken
from .praesentation import briefing_pptx, dateiname as pptx_dateiname
from .worker import Hintergrund, ModellNichtBereit

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


class BriefingAnfrage(BaseModel):
    situation: str = Field(default="", max_length=2000)
    bereich: str = ""
    # Entwurf prüfen (Foto): Fotos und ggf. vom Nutzer geprüfter Text
    bild_ids: list[str] = Field(default_factory=list, max_length=5)
    entwurf_text: str = Field(default="", max_length=20000)
    # kombiniert: Claude-Fachwissen + eigene Lessons; eigen: nur Lessons
    modus: Literal["kombiniert", "eigen"] = "kombiniert"


class FeedbackIn(BaseModel):
    lesson_id: str
    bewertung: Literal["hilfreich", "nicht_relevant", ""]


class ImportErgebnis(BaseModel):
    importiert: int
    uebersprungen: int
    fehler: list[str]


def create_app(
    settings: Settings | None = None,
    strukturierer: BasisStrukturierer | None = None,
    provider: EmbeddingProvider | None = None,
    lokal: OllamaStrukturierer | None = None,
    schreiber: BriefingSchreiber | None = None,
    ocr: Texterkennung | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    conn = db.connect(settings.db_path)
    repo = Repository(conn)
    if provider is None and settings.embedding_provider == "auto":
        provider = provider_fuer_bestand(
            repo.haeufigstes_embedding_modell(), settings.voyage_api_key, settings.voyage_model,
            settings.ollama_url, settings.ollama_embed_model,
        )
    provider = provider or create_provider(
        settings.embedding_provider, settings.voyage_api_key, settings.voyage_model,
        settings.ollama_url, settings.ollama_embed_model,
    )
    strukturierer = strukturierer or create_strukturierer(settings.anthropic_api_key, settings.claude_model, settings.claude_effort)
    if lokal is None and settings.ollama_model:
        lokal = OllamaStrukturierer(settings.ollama_url, settings.ollama_model)
    if schreiber is None:
        claude_client = strukturierer.client if isinstance(strukturierer, Strukturierer) else None
        schreiber = BriefingSchreiber(claude_client, settings.claude_model, settings.claude_effort)
    bilder_ordner = Path(settings.bilder_pfad) if settings.bilder_pfad else Path(settings.db_path).parent / "bilder"
    speicher = Bildspeicher(bilder_ordner)
    ocr = ocr or Texterkennung(settings.tesseract_cmd)
    suche = Suche(repo, provider)
    ollama_cache: dict[str, Any] = {"zeit": 0.0, "status": {"erreichbar": False, "modelle": []}}

    def lokal_status(frisch: bool = False) -> dict[str, Any]:
        """Ollama-Status, 30 Sekunden zwischengespeichert."""
        if lokal is None:
            return {"erreichbar": False, "modelle": []}
        if frisch or time.monotonic() - ollama_cache["zeit"] > 30:
            ollama_cache["status"] = ollama_status(lokal.url)
            ollama_cache["zeit"] = time.monotonic()
        return ollama_cache["status"]

    def lokal_bereit(frisch: bool = False) -> bool:
        status = lokal_status(frisch)
        return bool(lokal and status["erreichbar"] and modell_installiert(lokal.model, status["modelle"]))

    def privat_aktiv(einst: Einstellungen) -> bool:
        """Ist irgendetwas auf "lokal" gestellt? Dann darf ohne Bereichswahl nichts an Claude gehen."""
        return einst.strukturierung_standard == "lokal" or "lokal" in einst.strukturierung_bereiche.values()

    def modus_fuer(bereich: str, einst: Einstellungen | None = None) -> str:
        """Wirksamer Strukturierungsmodus: claude, lokal oder manuell."""
        einst = einst or repo.einstellungen()
        if not bereich and privat_aktiv(einst):
            # Ohne Bereich ist unklar, ob der Text zu einem lokalen Bereich gehört: im Zweifel nicht an Claude.
            return "lokal" if lokal is not None else "manuell"
        modus = einst.strukturierung_bereiche.get(bereich, einst.strukturierung_standard) if bereich else einst.strukturierung_standard
        if modus == "auto":
            if strukturierer.verfuegbar:
                return "claude"
            return "lokal" if lokal_bereit() else "manuell"
        if modus == "lokal" and lokal is None:
            return "manuell"
        return modus

    def lokale_bereiche(einst: Einstellungen | None = None) -> set[str]:
        """Bereiche, die nie an Claude gehen dürfen.

        Maßgeblich ist die Einstellung, nicht der wirksame Modus: Auch wenn gerade kein lokales Modell
        läuft und deshalb manuell erfasst wird, bleibt ein auf "lokal" gestellter Bereich privat.
        """
        einst = einst or repo.einstellungen()
        privat = set()
        for b in repo.bereiche():
            eingestellt = einst.strukturierung_bereiche.get(b.name, einst.strukturierung_standard)
            if eingestellt == "lokal" or modus_fuer(b.name, einst) == "lokal":
                privat.add(b.name)
        return privat

    def bild_weg(bereich: str, einst: Einstellungen | None = None) -> str:
        """Wie Fotos ausgewertet werden: "bild" (an Claude), "text" (lokal erkannt, geprüft an Claude), "lokal" (nie an Claude)."""
        einst = einst or repo.einstellungen()
        if bereich and bereich in lokale_bereiche(einst):
            return "lokal"
        if not bereich and privat_aktiv(einst):
            return "lokal"
        if not (isinstance(strukturierer, Strukturierer) and strukturierer.verfuegbar):
            return "lokal"
        if not bereich:
            return "text"  # sicherer Standard ohne Bereichswahl
        beruflich = repo.ist_beruflich(bereich)
        weg = einst.bild_bereiche.get(bereich, "text" if beruflich else "bild")
        # Berufliche Fotos (Kundenfolien) gehen nie als Bild an Claude, unabhängig von der Einstellung.
        return "text" if beruflich else weg

    def vorabpruefung(text: str, bereich: str, freigabe: bool) -> None:
        """Namensprüfung, bevor Text an Claude geht. Sperrliste blockiert immer, andere Treffer brauchen Freigabe."""
        einst = repo.einstellungen()
        gesperrt = sperrliste_treffer(text, einst.sperrliste)
        if gesperrt:
            raise HTTPException(status_code=422, detail={
                "code": "sperrliste",
                "meldung": "Der Text enthält Begriffe aus deiner Sperrliste und wird nicht an Claude geschickt.",
                "hinweise": [f"Sperrliste: \"{b}\"" for b in gesperrt],
            })
        if freigabe:
            return
        hinweise = pruefen(text, bereich, beruflich=repo.ist_beruflich(bereich) if bereich else False)
        if hinweise:
            raise HTTPException(status_code=409, detail={
                "code": "pruefung",
                "meldung": "Bevor das an Claude geht: Diese Angaben sehen nach Namen oder Projektdaten aus.",
                "hinweise": hinweise,
            })

    def verarbeite_entwurf(eintrag: EntwurfEintrag) -> Entwurf:
        """Strukturiert einen gesicherten Entwurf je nach Modus: lokal, Claude oder manuell."""
        einst = repo.einstellungen()
        vorgabe = eintrag.bereich_vorgabe
        modus = eintrag.modus
        # Wurde der Bereich inzwischen auf lokal gestellt, gilt das auch für schon gesicherte Notizen.
        if modus != "lokal" and ((vorgabe and vorgabe in lokale_bereiche(einst)) or (not vorgabe and privat_aktiv(einst))):
            modus = "lokal"
        bereiche = bereiche_fuer(vorgabe)
        voller_text = eintrag.rohtext if not eintrag.antwort else f"{eintrag.rohtext}\n{eintrag.antwort}"
        if modus == "lokal" and lokal is not None:
            kandidaten = kandidaten_fuer(voller_text)
            ergebnis = lokal.strukturieren(eintrag.rohtext, eintrag.quelle, bereiche, kandidaten, eintrag.rueckfrage, eintrag.antwort)
            if lokal.verbindungsfehler:
                raise ModellNichtBereit()
        elif modus == "claude" and strukturierer.verfuegbar:
            try:
                vorabpruefung(voller_text, vorgabe, eintrag.freigabe)
            except HTTPException as exc:
                # Im Hintergrund kann niemand freigeben: nichts senden, der Nutzer entscheidet in der App.
                kandidaten = kandidaten_fuer(voller_text)
                ergebnis = manueller_entwurf(voller_text, eintrag.quelle, bereiche)
                ergebnis.pruefung = exc.detail if isinstance(exc.detail, dict) else {"code": "pruefung", "meldung": str(exc.detail), "hinweise": []}
                return fertigstellen(ergebnis, kandidaten, voller_text, vorgabe)
            kandidaten = kandidaten_fuer(voller_text, ausschliessen=lokale_bereiche(einst))
            ergebnis = strukturierer.strukturieren(eintrag.rohtext, eintrag.quelle, bereiche, kandidaten, eintrag.rueckfrage, eintrag.antwort)  # type: ignore[arg-type]
        else:
            kandidaten = kandidaten_fuer(voller_text)
            ergebnis = manueller_entwurf(voller_text, eintrag.quelle, bereiche)  # type: ignore[arg-type]
        return fertigstellen(ergebnis, kandidaten, voller_text, vorgabe)

    def bilder_aufraeumen() -> int:
        """Nie verknüpfte Fotos nach 2 Tagen löschen, Dateien ohne Datenbankeintrag entfernen."""
        geloescht = 0
        for bild_id in repo.verwaiste_bilder(2):
            speicher.loeschen(bild_id)
            repo.bild_loeschen(bild_id)
            geloescht += 1
        bekannte = repo.alle_bild_ids()
        grenze = time.time() - 3600
        for bild_id in speicher.vorhandene_ids() - bekannte:
            if speicher.pfad(bild_id).stat().st_mtime < grenze:
                speicher.loeschen(bild_id)
                geloescht += 1
        return geloescht

    worker = Hintergrund(
        repo, provider, verarbeite_entwurf, lokal.name if lokal else "",
        pflege=bilder_aufraeumen, bereit=(lambda: lokal_bereit(frisch=True)) if lokal else None,
    )

    sperre = Instanzsperre(Path(settings.db_path).parent)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        sperre.erwerben()  # wirft LaeuftBereits, uvicorn beendet sich dann mit Code 3
        try:
            if settings.worker_aktiv:
                worker.start()
            yield
            worker.stop()
        finally:
            sperre.freigeben()

    token = settings.token or (zugangstoken(Path(settings.db_path).parent) if settings.token_erzwingen else "")
    # Keine öffentliche API-Doku im Betrieb
    app = FastAPI(title="Lessons Vault", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SicherheitsMiddleware)
    # app.js ist rund 90 KB: komprimiert lädt die App über Mobilfunk und Tailscale deutlich schneller.
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.erlaubte_hosts)
    app.state.repo = repo
    app.state.provider = provider
    app.state.strukturierer = strukturierer
    app.state.worker = worker
    app.state.bilder_aufraeumen = bilder_aufraeumen
    app.state.speicher = speicher

    def auth(request: Request) -> None:
        if not token:
            return
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(supplied.encode(), token.encode()):
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
        return pruefen(text, data.bereich, repo.einstellungen().sperrliste, beruflich=repo.ist_beruflich(data.bereich))

    deps = [Depends(auth)]

    # Status und Konfiguration -------------------------------------------
    @app.get("/api/status", dependencies=deps)
    def status() -> dict[str, Any]:
        einst = repo.einstellungen()
        ls = lokal_status()
        return {
            "version": __version__,
            "ki": strukturierer.verfuegbar,
            "modell": settings.claude_model if strukturierer.verfuegbar else "",
            "embeddings": provider.name,
            "semantisch": provider.semantisch,
            "lokal": {
                "konfiguriert": lokal is not None,
                "modell": lokal.model if lokal else "",
                "erreichbar": ls["erreichbar"],
                "modell_installiert": bool(lokal and modell_installiert(lokal.model, ls["modelle"])),
                "embed_modell": settings.ollama_embed_model,
                "embed_modell_installiert": modell_installiert(settings.ollama_embed_model, ls["modelle"]),
            },
            "modi": {b.name: modus_fuer(b.name, einst) for b in repo.bereiche()},
            "texterkennung": {"verfuegbar": ocr.verfuegbar, "hinweis": ocr.status()[1]},
            "bild_wege": {b.name: bild_weg(b.name, einst) for b in repo.bereiche()},
            "modus_standard": modus_fuer("", einst),
            "worker_wartet_auf_modell": worker.wartet_auf_modell,
        }

    @app.get("/api/bereiche", dependencies=deps)
    def bereiche_liste() -> list[Bereich]:
        return repo.bereiche()

    @app.post("/api/bereiche", dependencies=deps, status_code=201)
    def bereich_anlegen(bereich: Bereich) -> Bereich:
        return repo.bereich_anlegen(bereich)

    @app.patch("/api/bereiche/{name}", dependencies=deps)
    def bereich_aendern(name: str, update: BereichUpdate) -> Bereich:
        return repo.bereich_aendern(name, update.aktiv, update.beispiele, update.beruflich)

    @app.get("/api/einstellungen", dependencies=deps)
    def einstellungen() -> Einstellungen:
        return repo.einstellungen()

    @app.put("/api/einstellungen", dependencies=deps)
    def einstellungen_speichern(neu: Einstellungen) -> Einstellungen:
        # Nur mitgeschickte Felder ändern, damit z. B. das Speichern der Sperrliste die KI-Modi nicht zurücksetzt.
        data = repo.einstellungen().model_copy(update=neu.model_dump(exclude_unset=True))
        data.sperrliste = sorted({s.strip() for s in data.sperrliste if s.strip()}, key=str.lower)
        bekannte = {b.name for b in repo.bereiche()}
        data.strukturierung_bereiche = {k: v for k, v in data.strukturierung_bereiche.items() if k in bekannte}
        return repo.einstellungen_speichern(data)

    # Erfassen ------------------------------------------------------------
    def kandidaten_fuer(text: str, ausschliessen: set[str] | None = None) -> list[DublettenKandidat]:
        filt = Filter(ohne_ueberholt=True)
        try:
            ergebnisse = suche.semantisch(text, filt, limit=15)
        except EmbeddingFehler:
            ergebnisse = suche.volltext(text, filt, limit=15)
        kandidaten = []
        for lesson_id, score in ergebnisse:
            l = repo.holen(lesson_id)
            if ausschliessen and l.bereich in ausschliessen:
                continue
            kandidaten.append(
                DublettenKandidat(
                    id=l.id, titel=l.titel, lesson=l.lesson, bereich=l.bereich, status=l.status,
                    bestaetigungen=l.bestaetigungen, aehnlichkeit=round(score, 3),
                )
            )
            if len(kandidaten) == 5:
                break
        return kandidaten

    def bereiche_fuer(vorgabe: str) -> list[Bereich]:
        aktive = repo.bereiche(nur_aktive=True)
        if vorgabe:
            passend = [b for b in repo.bereiche() if b.name == vorgabe]
            if passend:
                return passend
        return aktive

    def fertigstellen(ergebnis: Entwurf, kandidaten: list[DublettenKandidat], voller_text: str, vorgabe: str = "") -> Entwurf:
        if vorgabe and repo.bereich_existiert(vorgabe):
            ergebnis.bereich = vorgabe
            ergebnis.fehlende_felder = [f for f in ergebnis.fehlende_felder if f != "bereich"]
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
            beruflich=repo.ist_beruflich(ergebnis.bereich) if ergebnis.bereich else False,
        )
        ergebnis.compliance_hinweise = list(dict.fromkeys([*lokale, *ergebnis.compliance_hinweise]))
        return ergebnis

    def sofort_entwurf(
        text: str, quelle: str, vorgabe: str, modus: str, rueckfrage: str = "", antwort: str = "", freigabe: bool = False,
    ) -> Entwurf:
        voller_text = text if not antwort else f"{text}\n{antwort}"
        bereiche = bereiche_fuer(vorgabe)
        if modus == "claude":
            vorabpruefung(voller_text, vorgabe, freigabe)
            # Datenschutz: Lessons aus lokal verarbeiteten Bereichen gehen nie an Claude.
            kandidaten = kandidaten_fuer(voller_text, ausschliessen=lokale_bereiche())
            ergebnis = strukturierer.strukturieren(text, quelle, bereiche, kandidaten, rueckfrage, antwort)  # type: ignore[arg-type]
        else:
            kandidaten = kandidaten_fuer(voller_text)
            ergebnis = manueller_entwurf(voller_text, quelle, bereiche)  # type: ignore[arg-type]
        return fertigstellen(ergebnis, kandidaten, voller_text, vorgabe)

    @app.post("/api/erfassen", dependencies=deps)
    def erfassen(anfrage: ErfassenAnfrage) -> dict[str, Any]:
        """Einstieg der Erfassung: sofortiger Entwurf (Claude/manuell) oder Warteschlange (lokal)."""
        vorgabe = anfrage.bereich if anfrage.bereich and repo.bereich_existiert(anfrage.bereich) else ""
        modus = modus_fuer(vorgabe)
        if modus == "lokal":
            eintrag = repo.entwurf_anlegen(anfrage.text, anfrage.quelle, vorgabe, anfrage.erfassung_sekunden, modus="lokal")
            if anfrage.bild_ids:
                repo.bilder_verknuepfen(anfrage.bild_ids, "entwurf", eintrag.id)
            worker.wecken()
            return {"modus": "hintergrund", "eintrag": eintrag, "warteschlange": repo.entwuerfe_zaehlen()["wartet"]}
        return {"modus": "sofort", "entwurf": sofort_entwurf(anfrage.text, anfrage.quelle, vorgabe, modus, freigabe=anfrage.freigabe)}

    @app.post("/api/erfassen/entwurf", dependencies=deps)
    def entwurf(anfrage: EntwurfAnfrage) -> Entwurf:
        vorgabe = anfrage.bereich if anfrage.bereich and repo.bereich_existiert(anfrage.bereich) else ""
        modus = modus_fuer(vorgabe)
        if modus == "lokal":
            # Rückfrage-Runde eines lokalen Bereichs nie über Claude schicken.
            modus = "manuell"
        return sofort_entwurf(anfrage.text, anfrage.quelle, vorgabe, modus, anfrage.rueckfrage, anfrage.antwort, anfrage.freigabe)

    def jetzt_verarbeiten(entwurf_id: str) -> None:
        """Claude- und manuelle Entwürfe sofort strukturieren, ohne hinter einem lokalen Modell zu warten."""
        if repo.entwurf_reservieren(entwurf_id):
            worker.verarbeite(repo.entwurf_holen(entwurf_id))

    def einplanen(eintrag: EntwurfEintrag, hintergrund: BackgroundTasks | None, warten: bool) -> EntwurfEintrag:
        if eintrag.modus == "lokal" and lokal is not None:
            worker.wecken()
            return eintrag
        if warten:
            jetzt_verarbeiten(eintrag.id)
            return repo.entwurf_holen(eintrag.id)
        if hintergrund is not None:
            hintergrund.add_task(jetzt_verarbeiten, eintrag.id)
        else:
            worker.wecken()
        return eintrag

    @app.post("/api/notiz", dependencies=deps, status_code=201)
    def notiz(anfrage: NotizAnfrage, hintergrund: BackgroundTasks, warten: bool = False) -> EntwurfEintrag:
        """Schnellnotiz: Text ist sofort gesichert. Mit warten=true kommt der fertige Entwurf zurück (App),
        sonst wird im Hintergrund strukturiert (iOS-Kurzbefehl)."""
        vorgabe = anfrage.bereich if anfrage.bereich and repo.bereich_existiert(anfrage.bereich) else ""
        einst = repo.einstellungen()
        # Gespeichert wird die Absicht: Ein auf "lokal" gestellter Bereich bleibt lokal, auch wenn gerade kein
        # Modell läuft (dann manuell) und auch wenn die Einstellung später geändert wird.
        privat = (vorgabe and vorgabe in lokale_bereiche(einst)) or (not vorgabe and privat_aktiv(einst))
        modus = "lokal" if privat else modus_fuer(vorgabe, einst)
        if anfrage.entwurf is not None:
            entwurf = anfrage.entwurf
            if vorgabe and not entwurf.bereich:
                entwurf.bereich = vorgabe
            eintrag = repo.entwurf_anlegen(anfrage.text, anfrage.quelle, vorgabe, anfrage.erfassung_sekunden, modus=modus, entwurf=entwurf)
        else:
            eintrag = repo.entwurf_anlegen(anfrage.text, anfrage.quelle, vorgabe, anfrage.erfassung_sekunden, modus=modus)
        if anfrage.bild_ids:
            repo.bilder_verknuepfen(anfrage.bild_ids, "entwurf", eintrag.id)
        if anfrage.entwurf is not None:
            return eintrag
        return einplanen(eintrag, hintergrund, warten)

    @app.post("/api/entwuerfe/{entwurf_id}/strukturieren", dependencies=deps)
    def entwurf_strukturieren(entwurf_id: str, data: StrukturierenAnfrage) -> EntwurfEintrag:
        """Erneut strukturieren, optional mit geändertem Text oder bewusster Freigabe. Wartet auf das Ergebnis."""
        eintrag = repo.entwurf_neu_einreihen(entwurf_id, freigabe=data.freigabe, rohtext=data.text)
        return einplanen(eintrag, None, warten=True)

    # Entwürfe (Hintergrund) ----------------------------------------------
    @app.get("/api/entwuerfe", dependencies=deps)
    def entwuerfe(q: str = "") -> dict[str, Any]:
        eintraege = repo.entwuerfe_suchen(suchbegriffe(q)) if q.strip() else repo.entwuerfe()
        return {"eintraege": eintraege, "zaehler": repo.entwuerfe_zaehlen(), "aktuell": worker.aktueller_entwurf}

    @app.get("/api/entwuerfe/{entwurf_id}", dependencies=deps)
    def entwurf_holen(entwurf_id: str) -> dict[str, Any]:
        eintrag = repo.entwurf_holen(entwurf_id)
        return {**eintrag.model_dump(), "bilder": [bild_info(b) for b in repo.bilder_von("entwurf", entwurf_id)]}

    @app.post("/api/entwuerfe/{entwurf_id}/antwort", dependencies=deps)
    def entwurf_antwort(entwurf_id: str, data: AntwortIn) -> EntwurfEintrag:
        eintrag = repo.entwurf_holen(entwurf_id)
        frage = eintrag.entwurf.rueckfrage if eintrag.entwurf else ""
        eintrag = repo.entwurf_neu_einreihen(entwurf_id, rueckfrage=frage or "Ergänzung", antwort=data.antwort)
        return einplanen(eintrag, None, warten=False)

    @app.post("/api/entwuerfe/{entwurf_id}/neu", dependencies=deps)
    def entwurf_neu(entwurf_id: str, hintergrund: BackgroundTasks) -> EntwurfEintrag:
        eintrag = repo.entwurf_neu_einreihen(entwurf_id)
        return einplanen(eintrag, hintergrund, warten=False)

    @app.delete("/api/entwuerfe/{entwurf_id}", dependencies=deps, status_code=204)
    def entwurf_loeschen(entwurf_id: str) -> None:
        repo.entwurf_loeschen(entwurf_id)

    @app.post("/api/compliance", dependencies=deps)
    def compliance_pruefen(data: CompliancePruefung) -> list[str]:
        beruflich = repo.ist_beruflich(data.bereich) if data.bereich else False
        return pruefen(data.text, data.bereich, repo.einstellungen().sperrliste, beruflich=beruflich)

    # Lessons -------------------------------------------------------------
    @app.get("/api/lessons", dependencies=deps)
    def lessons_liste(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> list[Lesson]:
        return repo.liste(limit=limit, offset=offset)

    @app.post("/api/lessons", dependencies=deps, status_code=201)
    def lesson_anlegen(data: LessonIn) -> LessonAntwort:
        eintrag = None
        if data.entwurf_id:
            eintrag = repo.entwurf_holen(data.entwurf_id)
            # Erfassungsdauer zählt bis zum Absenden des Rohtexts, nicht bis zur späteren Prüfung.
            data = data.model_copy(update={"quelle": eintrag.quelle, "erfassung_sekunden": eintrag.erfassung_sekunden})
        for bild_id in data.bild_ids:
            repo.bild_holen(bild_id)  # 404 vor dem Anlegen, nicht danach
        vector, modell, fehler = embed_lesson(data)
        lesson = repo.anlegen(data, vector, modell)
        if data.bild_ids:
            repo.bilder_verknuepfen(data.bild_ids, "lesson", lesson.id)
        if eintrag:
            repo.links_umhaengen("entwurf", eintrag.id, "lesson", lesson.id)
            repo.entwurf_loeschen(eintrag.id)
        return LessonAntwort(lesson=lesson, compliance_hinweise=compliance(data), embedding_fehler=fehler)

    @app.get("/api/lessons/{lesson_id}", dependencies=deps)
    def lesson_holen(lesson_id: str) -> dict[str, Any]:
        lesson = repo.holen(lesson_id)
        return {
            "lesson": lesson,
            "protokoll": repo.bestaetigungs_protokoll(lesson_id),
            "compliance_hinweise": compliance(lesson),
            "bilder": [bild_info(b) for b in repo.bilder_von("lesson", lesson_id)],
            "hilfreich": repo.hilfreich_zaehlen(lesson_id),
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
        if data and data.entwurf_id:
            repo.entwurf_holen(data.entwurf_id)
        lesson = repo.bestaetigen(lesson_id, data.notiz if data else "")
        if data and data.bild_ids:
            repo.bilder_verknuepfen(data.bild_ids, "lesson", lesson_id)
        if data and data.entwurf_id:
            repo.links_umhaengen("entwurf", data.entwurf_id, "lesson", lesson_id)
            repo.entwurf_loeschen(data.entwurf_id)
        return lesson

    # Suche ---------------------------------------------------------------
    @app.get("/api/suche", dependencies=deps)
    def suchen(
        q: str = "",
        modus: str = Query("hybrid", pattern="^(hybrid|volltext|semantisch)$"),
        bereich: str | None = None,
        status: str | None = Query(None, pattern="^(neu|bestätigt|überholt)$"),
        art: str | None = Query(None, pattern="^(erfahrung|wissen|vorgehen|entscheidung)$"),
        phase: str | None = Query(None, pattern="^(sales|concept|build|test|cutover|hypercare)$"),
        schweregrad_min: int | None = Query(None, ge=1, le=5),
        von: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}"),
        bis: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}"),
        limit: int = Query(30, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        filt = Filter(bereich=bereich or None, status=status or None, schweregrad_min=schweregrad_min, von=von, bis=bis, art=art or None, phase=phase or None)
        try:
            treffer = suche.suchen(q, modus, filt, limit)  # type: ignore[arg-type]
        except EmbeddingFehler as exc:
            log.warning("%s", exc)
            treffer = suche.suchen(q, "volltext", filt, limit)
        return [{"lesson": t.lesson, "score": t.score, "gefunden_durch": t.gefunden_durch} for t in treffer]

    # Fotos -------------------------------------------------------------------
    def bild_info(b: dict[str, Any]) -> dict[str, Any]:
        return {k: b[k] for k in ("id", "breite", "hoehe", "ocr_status", "erstellt_am")}

    @app.post("/api/bilder", dependencies=deps, status_code=201)
    def bilder_hochladen(dateien: list[UploadFile] = File(...)) -> list[dict[str, Any]]:
        if len(dateien) > 5:
            raise HTTPException(status_code=422, detail="Höchstens 5 Fotos auf einmal.")
        ergebnis = []
        for datei in dateien:
            try:
                bild = speicher.speichern(datei.file.read(15 * 1024 * 1024 + 1))
            except BildFehler as exc:
                raise HTTPException(status_code=422, detail=f"{datei.filename}: {exc}") from exc
            repo.bild_anlegen(bild.id, bild.breite, bild.hoehe, bild.groesse)
            # Texterkennung läuft immer lokal, auch wenn das Foto später an Claude geht: Sie speist die Suche.
            if ocr.verfuegbar:
                try:
                    repo.bild_ocr_setzen(bild.id, ocr.erkennen(speicher.pfad(bild.id)), "fertig")
                except Exception as exc:  # Tesseract-Fehler dürfen den Upload nicht verhindern
                    log.warning("Texterkennung fehlgeschlagen: %s", exc)
                    repo.bild_ocr_setzen(bild.id, "", "fehler")
            else:
                repo.bild_ocr_setzen(bild.id, "", "aus")
            ergebnis.append(bild_info(repo.bild_holen(bild.id)))
        return ergebnis

    @app.get("/api/bilder/{bild_id}", dependencies=deps)
    def bild_laden(bild_id: str, variante: str = Query("voll", pattern="^(voll|vorschau)$")) -> FileResponse:
        repo.bild_holen(bild_id)
        try:
            pfad = speicher.pfad(bild_id, variante)
        except BildFehler as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not pfad.exists():
            raise HTTPException(status_code=404, detail="Bilddatei fehlt")
        # no-store: berufliche Fotos sollen nicht im HTTP-Cache des Handys liegen bleiben
        return FileResponse(pfad, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/lessons/{lesson_id}/bilder", dependencies=deps)
    def lesson_bilder_anhaengen(lesson_id: str, data: BildLinks) -> list[dict[str, Any]]:
        repo.holen(lesson_id)
        repo.bilder_verknuepfen(data.bild_ids, "lesson", lesson_id)
        return [bild_info(b) for b in repo.bilder_von("lesson", lesson_id)]

    @app.delete("/api/lessons/{lesson_id}/bilder/{bild_id}", dependencies=deps, status_code=204)
    def lesson_bild_entfernen(lesson_id: str, bild_id: str) -> None:
        repo.bild_loesen(bild_id, "lesson", lesson_id)

    def ocr_texte(bild_ids: list[str]) -> str:
        texte = []
        for i, bild_id in enumerate(bild_ids, start=1):
            b = repo.bild_holen(bild_id)
            # Beim Hochladen war die Texterkennung aus oder fehlgeschlagen: jetzt nachholen, statt dauerhaft leer zu bleiben.
            if not b["ocr_text"] and b.get("ocr_status") in ("aus", "fehler") and ocr.verfuegbar:
                try:
                    repo.bild_ocr_setzen(bild_id, ocr.erkennen(speicher.pfad(bild_id)), "fertig")
                except Exception as exc:  # noqa: BLE001 - Erkennung darf die Auswertung nicht abbrechen
                    log.warning("Texterkennung (nachgeholt) fehlgeschlagen: %s", exc)
                b = repo.bild_holen(bild_id)
            if b["ocr_text"]:
                texte.append(b["ocr_text"] if len(bild_ids) == 1 else f"[Foto {i}]\n{b['ocr_text']}")
        return "\n\n".join(texte)

    @app.post("/api/foto/vorbereiten", dependencies=deps)
    def foto_vorbereiten(anfrage: FotoAnfrage) -> dict[str, Any]:
        """Sagt der Oberfläche, welcher Weg gilt, und liefert den lokal erkannten Text zur Prüfung."""
        vorgabe = anfrage.bereich if anfrage.bereich and repo.bereich_existiert(anfrage.bereich) else ""
        weg = bild_weg(vorgabe)
        sperrliste = repo.einstellungen().sperrliste
        # Sperrbegriffe im erkannten Fototext gleich ersetzen: So bleibt der Ablauf automatisch, ohne dass sie an Claude gehen.
        text, geschwaerzt = sperrbegriffe_schwaerzen(ocr_texte(anfrage.bild_ids), sperrliste)
        return {
            "weg": weg,
            "text": text,
            "geschwaerzt": geschwaerzt,
            # Im Zweifel streng prüfen: ohne Bereich wie "Beruf" (Zahlen und Beträge melden)
            "compliance_hinweise": pruefen(text, vorgabe, sperrliste, beruflich=repo.ist_beruflich(vorgabe) if vorgabe else True) if text else [],
            "texterkennung": {"verfuegbar": ocr.verfuegbar, "hinweis": ocr.status()[1]},
        }

    @app.post("/api/foto/kandidaten", dependencies=deps)
    def foto_kandidaten(anfrage: FotoAnfrage) -> dict[str, Any]:
        vorgabe = anfrage.bereich if anfrage.bereich and repo.bereich_existiert(anfrage.bereich) else ""
        weg = bild_weg(vorgabe)  # nie dem Client glauben
        for bild_id in anfrage.bild_ids:
            repo.bild_holen(bild_id)
        if weg == "lokal":
            raise HTTPException(status_code=409, detail="Für diesen Bereich gehen Fotos nicht an Claude. Nutze den erkannten Text als Notiz.")
        if weg == "text":
            if len(anfrage.text.strip()) < 3:
                raise HTTPException(status_code=422, detail="Kein Text zum Auswerten. Text prüfen oder abtippen.")
            # Fototext: Sperrbegriffe serverseitig ersetzen (nie dem Client glauben). Getippte Notizen blockieren weiter.
            fototext, _ = sperrbegriffe_schwaerzen(anfrage.text, repo.einstellungen().sperrliste)
            vorabpruefung(f"{fototext}\n{anfrage.notiz}", vorgabe, anfrage.freigabe)
            inhalt = kandidaten_inhalt([], fototext, anfrage.notiz)
        else:
            vorabpruefung(anfrage.notiz, vorgabe, anfrage.freigabe)
            inhalt = kandidaten_inhalt([speicher.fuer_claude(b) for b in anfrage.bild_ids], "", anfrage.notiz)
        assert isinstance(strukturierer, Strukturierer)
        try:
            ergebnis = kandidaten_finden(strukturierer.client, settings.claude_model, settings.claude_effort, inhalt)
        except anthropic.APIConnectionError as exc:
            raise HTTPException(status_code=502, detail="Claude nicht erreichbar.") from exc
        except anthropic.RateLimitError as exc:
            raise HTTPException(status_code=502, detail="Claude-Limit erreicht, später erneut versuchen.") from exc
        except anthropic.APIStatusError as exc:
            raise HTTPException(status_code=502, detail=f"Claude-Fehler {exc.status_code}.") from exc
        except (RuntimeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {**ergebnis, "weg": weg}

    # Briefing ----------------------------------------------------------------
    def briefing_antwort(briefing_id: str) -> dict[str, Any]:
        data = repo.briefing_holen(briefing_id)
        treffer = []
        for t in data.pop("treffer"):
            try:
                lesson = repo.holen(t["lesson_id"])
            except NotFound:
                continue  # inzwischen gelöscht
            treffer.append({**t, "lesson": lesson})
        einst = repo.einstellungen()
        lokale = lokale_bereiche(einst)
        data["bilder"] = [bild_info(b) for b in repo.bilder_von("briefing", briefing_id)]
        if data["bereich"] and data["bereich"] in lokale:
            ki_moeglich, ki_hinweis = False, "Der gewählte Bereich wird lokal verarbeitet, daher keine Claude-Zusammenfassung."
        elif not data["bereich"] and einst.strukturierung_standard == "lokal":
            ki_moeglich, ki_hinweis = False, "Standard ist \u201Elokal\u201C: Briefings ohne Bereichswahl gehen nicht an Claude."
        elif data["entwurf_weg"] == "lokal":
            ki_moeglich, ki_hinweis = False, "Fotos dieses Bereichs gehen nicht an Claude. Unten siehst du die passenden Lessons."
        elif data["entwurf_weg"] == "text" and not data["entwurf_text"].strip():
            ki_moeglich, ki_hinweis = False, "Kein geprüfter Text aus dem Foto, daher kein Abgleich durch Claude."
        elif not schreiber.verfuegbar:
            ki_moeglich, ki_hinweis = False, "Claude ist nicht eingerichtet (ANTHROPIC_API_KEY fehlt)."
        else:
            ausgeschlossen = sum(1 for t in treffer if t["lesson"].bereich in lokale)
            kombiniert = data["modus"] == "kombiniert" and not data["entwurf_weg"]
            # Kombiniert geht auch ohne eigene Lessons (dann reines Claude-Wissen, klar gekennzeichnet).
            ki_moeglich = kombiniert or (bool(treffer) and ausgeschlossen < len(treffer))
            ki_hinweis = (f"{ausgeschlossen} Lesson(s) aus lokalen Bereichen sind nicht an Claude gegangen." if ausgeschlossen else "")
        # Transparenz: wie viele Lessons Claude für dieses Briefing gesehen hat (lokale Bereiche nie).
        an_claude = sum(1 for t in treffer if t["lesson"].bereich not in lokale) if ki_moeglich else 0
        return {**data, "treffer": treffer, "ki_moeglich": ki_moeglich, "ki_hinweis": ki_hinweis, "an_claude": an_claude}

    @app.post("/api/briefing", dependencies=deps, status_code=201)
    def briefing_erstellen(anfrage: BriefingAnfrage) -> dict[str, Any]:
        vorgabe = anfrage.bereich if anfrage.bereich and repo.bereich_existiert(anfrage.bereich) else ""
        if not anfrage.bild_ids and len(anfrage.situation.strip()) < 3:
            raise HTTPException(status_code=422, detail="Beschreib kurz, was ansteht, oder füge ein Foto hinzu.")
        weg, entwurf_text = "", ""
        if anfrage.bild_ids:
            for bild_id in anfrage.bild_ids:
                repo.bild_holen(bild_id)
            weg = bild_weg(vorgabe)
            # Für Claude zählt nur geprüfter Text (Weg text); gesucht wird lokal mit allem Erkannten.
            entwurf_text = anfrage.entwurf_text.strip() if weg == "text" else ocr_texte(anfrage.bild_ids)
        suchtext = "\n".join(t for t in (anfrage.situation.strip(), entwurf_text or ocr_texte(anfrage.bild_ids)) if t)[:3000]
        situation = anfrage.situation.strip() or f"Entwurf prüfen ({len(anfrage.bild_ids)} Foto{'s' if len(anfrage.bild_ids) > 1 else ''})"
        try:
            vektor = provider.embed([suchtext], "query")[0]
        except EmbeddingFehler:
            vektor = None
        feedback = [
            (lid, bewertung, vec if modell == provider.name else None)
            for lid, bewertung, vec, modell in repo.feedback_alle()
        ]
        try:
            treffer = rangliste(suche, suchtext, vorgabe, feedback, vektor)
        except EmbeddingFehler:
            treffer = rangliste(suche, suchtext, vorgabe, feedback, vektor, modus="volltext")
        gespeichert = [
            {k: v for k, v in t.as_dict().items() if k != "lesson"} | {"lesson_id": t.lesson.id} for t in treffer
        ]
        briefing_id = repo.briefing_anlegen(
            situation, vorgabe, gespeichert, lokale_checkliste([t.lesson for t in treffer]),
            vektor, provider.name if vektor is not None else "", anfrage.modus,
        )
        if anfrage.bild_ids:
            repo.bilder_verknuepfen(anfrage.bild_ids, "briefing", briefing_id)
            repo.briefing_entwurf_setzen(briefing_id, weg, entwurf_text)
        return briefing_antwort(briefing_id)

    @app.get("/api/briefings", dependencies=deps)
    def briefings_liste(limit: int = Query(20, ge=1, le=100)) -> list[dict[str, Any]]:
        return repo.briefings(limit)

    @app.get("/api/briefing/{briefing_id}", dependencies=deps)
    def briefing_holen(briefing_id: str) -> dict[str, Any]:
        return briefing_antwort(briefing_id)

    @app.get("/api/briefing/{briefing_id}/pptx", dependencies=deps)
    def briefing_pptx_laden(briefing_id: str) -> Response:
        """Plan als PowerPoint, lokal erzeugt (kein weiterer Claude-Aufruf)."""
        data = briefing_antwort(briefing_id)
        if not data.get("plan"):
            raise HTTPException(status_code=409, detail="Erst den Plan mit Claude-Fachwissen erstellen, dann als PowerPoint laden.")
        lessons = {t["lesson"].id: t["lesson"] for t in data["treffer"]}
        inhalt = briefing_pptx(data["situation"], data["plan"], lessons, data.get("erstellt_am", ""))
        name = pptx_dateiname(data["situation"])
        return Response(
            inhalt,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f"attachment; filename=\"briefing.pptx\"; filename*=UTF-8''{quote(name)}"},
        )

    @app.delete("/api/briefing/{briefing_id}", dependencies=deps, status_code=204)
    def briefing_loeschen(briefing_id: str) -> None:
        repo.briefing_loeschen(briefing_id)

    @app.post("/api/briefing/{briefing_id}/zusammenfassung", dependencies=deps)
    def briefing_zusammenfassung(
        briefing_id: str, neu: bool = False, modus: str | None = Query(None, pattern="^(kombiniert|eigen)$"),
        freigabe: bool = False,
    ) -> dict[str, Any]:
        data = briefing_antwort(briefing_id)
        if modus and modus != data["modus"]:
            repo.briefing_modus_setzen(briefing_id, modus)
            data = briefing_antwort(briefing_id)
        if data["zusammenfassung"] and not neu:
            return data
        if not data["ki_moeglich"]:
            raise HTTPException(status_code=409, detail=data["ki_hinweis"] or "Keine Zusammenfassung möglich.")
        situation_text = "" if data["situation"].startswith("Entwurf prüfen (") else data["situation"]
        vorabpruefung(f"{situation_text}\n{data['entwurf_text'] if data['entwurf_weg'] == 'text' else ''}", data["bereich"], freigabe)
        lokale = lokale_bereiche()
        # Datenschutz: Lessons aus lokal verarbeiteten Bereichen gehen nie an Claude.
        lessons = [t["lesson"] for t in data["treffer"] if t["lesson"].bereich not in lokale]
        try:
            if data["entwurf_weg"] in ("text", "bild"):
                bloecke = [speicher.fuer_claude(b["id"]) for b in data["bilder"]] if data["entwurf_weg"] == "bild" else []
                situation = "" if data["situation"].startswith("Entwurf prüfen (") else data["situation"]
                abgleich = abgleichen(
                    schreiber.client, schreiber.model, schreiber.effort,
                    abgleich_inhalt(situation, data["entwurf_text"], bloecke, lessons), lessons,
                )
                repo.briefing_ki_setzen(
                    briefing_id, abgleich["zusammenfassung"], abgleich["fehlt"], f"claude:{schreiber.model}",
                    {"beruecksichtigt": abgleich["beruecksichtigt"]},
                )
                return briefing_antwort(briefing_id)
            if data["modus"] == "kombiniert":
                plan = kombinieren(schreiber, data["situation"], lessons, settings.briefing_effort)
                repo.briefing_plan_setzen(briefing_id, plan, f"claude:{schreiber.model}")
                return briefing_antwort(briefing_id)
            ergebnis = schreiber.schreiben(data["situation"], lessons)
        except anthropic.APIConnectionError as exc:
            raise HTTPException(status_code=502, detail="Claude nicht erreichbar. Die Checkliste unten gilt trotzdem.") from exc
        except anthropic.RateLimitError as exc:
            raise HTTPException(status_code=502, detail="Claude-Limit erreicht, später erneut versuchen.") from exc
        except anthropic.APIStatusError as exc:
            raise HTTPException(status_code=502, detail=f"Claude-Fehler {exc.status_code}.") from exc
        except (RuntimeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        repo.briefing_ki_setzen(
            briefing_id, ergebnis["zusammenfassung"], ergebnis["checkliste"], f"claude:{schreiber.model}", nur_modus="eigen",
        )
        return briefing_antwort(briefing_id)

    @app.post("/api/briefing/{briefing_id}/feedback", dependencies=deps)
    def briefing_feedback(briefing_id: str, data: FeedbackIn) -> dict[str, str]:
        repo.feedback_setzen(briefing_id, data.lesson_id, data.bewertung or None)
        return repo.feedback_fuer_briefing(briefing_id)

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
        return {**repo.statistik(), "bremsen": repo.rueckmeldungen("bremse")}

    @app.get("/api/wiedersehen", dependencies=deps)
    def wiedersehen(tag: str = Query("", max_length=10), ausser: str = Query("", max_length=2000)) -> Lesson | None:
        """Eine ältere Lesson zum Wiedersehen ("Erinnerst du dich?")."""
        tag = tag or datetime.now(timezone.utc).date().isoformat()
        return repo.wiedersehen(tag, [a for a in ausser.split(",") if a][:50])

    @app.post("/api/rueckmeldung", dependencies=deps, status_code=204)
    def rueckmeldung(data: RueckmeldungIn) -> None:
        repo.rueckmeldung_speichern(data.art, data.wert)

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def app_factory() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app()
