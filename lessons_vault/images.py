"""Lokaler Bildspeicher und Texterkennung.

Bilder werden neu kodiert (JPEG, ohne EXIF/Standort), in drei Größen abgelegt:
- voll:    max. 2400 px, für die Anzeige und die Texterkennung
- vorschau: max. 400 px, für Listen
Für Claude wird bei Bedarf eine Version mit max. 1568 px erzeugt (größere Bilder verkleinert die API ohnehin).
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import shutil
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger(__name__)

MAX_BYTES = 15 * 1024 * 1024
MAX_PIXEL = 30_000_000  # Schutz vor "Dekompressionsbomben"
# Nur Formate, die Kamera und Browser liefern. Andere (z. B. EPS) würden externe Programme aufrufen.
FORMATE = ["JPEG", "PNG", "WEBP"]  # JPEG umfasst auch MPO (Mehrbild-JPEG mancher Handys)
GROESSEN = {"voll": 2400, "vorschau": 400}
CLAUDE_KANTE = 1568
Image.MAX_IMAGE_PIXELS = MAX_PIXEL


class BildFehler(Exception):
    pass


@dataclass
class GespeichertesBild:
    id: str
    breite: int
    hoehe: int
    groesse: int


def _verkleinern(img: Image.Image, kante: int) -> Image.Image:
    if max(img.size) <= kante:
        return img.copy()
    kopie = img.copy()
    kopie.thumbnail((kante, kante), Image.LANCZOS)
    return kopie


def _jpeg(img: Image.Image, qualitaet: int = 85) -> bytes:
    puffer = io.BytesIO()
    # Ohne exif=... schreibt Pillow keine Metadaten: Standort, Kamera, Zeitstempel sind weg.
    img.save(puffer, "JPEG", quality=qualitaet, optimize=True)
    return puffer.getvalue()


class Bildspeicher:
    def __init__(self, ordner: Path):
        self.ordner = ordner
        self.ordner.mkdir(parents=True, exist_ok=True)

    def pfad(self, bild_id: str, variante: str = "voll") -> Path:
        if variante not in GROESSEN or not re.fullmatch(r"[0-9a-f-]{36}", bild_id):
            raise BildFehler("Ungültige Bildangabe")
        return self.ordner / f"{bild_id}_{variante}.jpg"

    def speichern(self, daten: bytes) -> GespeichertesBild:
        if len(daten) > MAX_BYTES:
            raise BildFehler("Bild ist größer als 15 MB.")
        try:
            with warnings.catch_warnings():
                # Pillow warnt zwischen MAX_PIXEL und 2 x MAX_PIXEL nur; hier ist das schon ein Fehler.
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(daten), formats=FORMATE) as roh:
                    if roh.width * roh.height > MAX_PIXEL:
                        raise BildFehler("Bild hat zu viele Pixel.")
                    roh.load()
                    # Ausrichtung aus EXIF anwenden, bevor die Metadaten wegfallen
                    img = ImageOps.exif_transpose(roh).convert("RGB")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise BildFehler("Datei ist kein lesbares Bild (JPEG, PNG, WebP).") from exc
        bild_id = str(uuid.uuid4())
        voll = _verkleinern(img, GROESSEN["voll"])
        groesse = 0
        for variante, kante in GROESSEN.items():
            inhalt = _jpeg(voll if variante == "voll" else _verkleinern(img, kante), 85 if variante == "voll" else 75)
            self.pfad(bild_id, variante).write_bytes(inhalt)
            groesse += len(inhalt)
        return GespeichertesBild(bild_id, voll.width, voll.height, groesse)

    def fuer_claude(self, bild_id: str) -> dict:
        """Content-Block für die Claude API (base64, max. 1568 px)."""
        with Image.open(self.pfad(bild_id)) as img:
            daten = _jpeg(_verkleinern(img.convert("RGB"), CLAUDE_KANTE), 85)
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(daten).decode()},
        }

    def loeschen(self, bild_id: str) -> None:
        for variante in GROESSEN:
            try:
                self.pfad(bild_id, variante).unlink(missing_ok=True)
            except BildFehler:
                pass

    def vorhandene_ids(self) -> set[str]:
        # Nur Dateien im eigenen Namensschema; fremde Dateien im Ordner lassen den Aufräumjob sonst abbrechen.
        return {i for p in self.ordner.glob("*_voll.jpg") if re.fullmatch(r"[0-9a-f-]{36}", i := p.name.split("_")[0])}


# ------------------------------------------------------------------ Texterkennung
WINDOWS_STANDARD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


class Texterkennung:
    """Lokale Texterkennung mit Tesseract (Deutsch + Englisch)."""

    def __init__(self, befehl: str = "", sprachen: str = "deu+eng"):
        self.sprachen = sprachen
        self.befehl = befehl or (WINDOWS_STANDARD if os.name == "nt" and Path(WINDOWS_STANDARD).exists() else "") or shutil.which("tesseract") or ""
        self._status: tuple[bool, str] | None = None

    def status(self) -> tuple[bool, str]:
        """(verfügbar, Hinweis). Wird einmal ermittelt."""
        if self._status is None:
            self._status = self._pruefen()
        return self._status

    def _pruefen(self) -> tuple[bool, str]:
        try:
            import pytesseract
        except ImportError:
            return False, "Python-Paket pytesseract fehlt (pip install -r requirements.txt)."
        if not self.befehl:
            return False, "Tesseract ist nicht installiert. Siehe README, Abschnitt Fotos."
        pytesseract.pytesseract.tesseract_cmd = self.befehl
        try:
            sprachen = set(pytesseract.get_languages(config=""))
        except Exception as exc:  # pytesseract wirft je nach Fehler unterschiedliche Typen
            return False, f"Tesseract lässt sich nicht starten ({exc.__class__.__name__})."
        fehlend = [s for s in self.sprachen.split("+") if s not in sprachen]
        if fehlend:
            return False, f"Tesseract-Sprachpaket fehlt: {', '.join(fehlend)}. Beim Installieren 'German' auswählen."
        return True, ""

    @property
    def verfuegbar(self) -> bool:
        return self.status()[0]

    def erkennen(self, pfad: Path) -> str:
        if not self.verfuegbar:
            raise BildFehler(self.status()[1])
        import pytesseract

        with Image.open(pfad) as img:
            grau = ImageOps.grayscale(img)
            if grau.width < 1600:
                # Kleine Fotos hochskalieren: Tesseract erkennt Schrift ab etwa 20 px Zeilenhöhe zuverlässig.
                faktor = 1600 / grau.width
                grau = grau.resize((1600, int(grau.height * faktor)), Image.LANCZOS)
            text = pytesseract.image_to_string(grau, lang=self.sprachen, config="--psm 3")
        return text_bereinigen(text)


def text_bereinigen(text: str) -> str:
    zeilen = [re.sub(r"[ \t]+", " ", z).strip() for z in text.splitlines()]
    # Einzelne Zeichen-Fragmente (Aufzählungszeichen, Rauschen) entfernen
    zeilen = [z for z in zeilen if len(z) > 1 or z == ""]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(zeilen)).strip()
