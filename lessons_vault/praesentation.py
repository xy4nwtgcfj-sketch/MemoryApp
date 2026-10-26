"""PowerPoint aus einem Briefing-Plan im Beratungsstil (lokal erzeugt, kein weiterer Claude-Aufruf).

Aufbau: Titel, Agenda, Executive Summary (drei Kernbotschaften + Storyline), "Where to focus" (Balkendiagramm
der Gewichte je Abschnitt), je Planabschnitt eine Kapitelfolie und eine Inhaltsfolie in der vom Plan gewählten
Darstellung (40 Bausteine in BAUSTEINE: Kacheln, Chevrons, Risikomatrix, Diagramme, Wasserfall, Eisberg, Fischgräte,
Waage, Waben, Zahnräder, Roadmap ...), Watch-outs, weitere Themen, nächste Schritte als Zeitstrahl. Der
zusammenhängende Text steht in den Notizen. `darstellung_waehlen` vermeidet Wiederholungen im Deck (ERSATZ) und
fällt auf eine einfachere Darstellung zurück, wenn die Daten nicht reichen (RUECKFALL).

Die Folien nennen weder eine KI noch die Wissensdatenbank des Nutzers; sie sind zum Weitergeben gedacht.
Die Marke des Bereichs bestimmt das Erscheinungsbild:
- Stil "dunkel": Titel- und Kapitelfolien in der Hauptfarbe, Farbbalken oben, Logo oben rechts (z. B. Deloitte).
- Stil "hell": Titel- und Kapitelfolien auf hellem Grund, Wortmarke statt Balken, Serifen-Überschriften
  (z. B. van Newboert).
Piktogramme sind Freiformen (Linienzeichnungen), damit sie ohne Schrift- oder Bildabhängigkeit überall gleich
aussehen. Diagramme sind native PowerPoint-Diagramme.
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Emu, Inches, Pt

from .models import Marke

TEXT = RGBColor(0x1A, 0x1D, 0x21)
GRAU = RGBColor(0x5F, 0x65, 0x6E)
HELLGRAU = RGBColor(0x9A, 0xA0, 0xA8)
LINIE = RGBColor(0xE1, 0xE4, 0xE8)
KARTE = RGBColor(0xF4, 0xF5, 0xF7)
WEISS = RGBColor(0xFF, 0xFF, 0xFF)
RISIKO = {  # Zellfarben der Risikomatrix nach Summe aus Eintritt und Auswirkung
    "niedrig": RGBColor(0xE4, 0xF1, 0xE2), "mittel": RGBColor(0xFB, 0xEE, 0xD0), "hoch": RGBColor(0xF8, 0xDE, 0xDA),
}

BREITE, HOEHE = Inches(13.333), Inches(7.5)
RAND = Inches(0.6)
INHALT_OBEN = Inches(1.85)
INHALT_HOEHE = Inches(4.9)
STANDARD_ICONS = ("flag", "target", "gear", "users", "check", "chart", "clock", "document")

MARKE = re.compile(r"\s?\[\[E:([\w-]+)\]\]")


def text_ohne_marken(text: str) -> str:
    """Interne Erfahrungsmarken verschwinden ersatzlos; die Folien weisen keine Quellen aus."""
    return MARKE.sub("", text or "").strip()


def _rgb(hexwert: str) -> RGBColor:
    h = hexwert.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _hell(farbe: RGBColor) -> bool:
    """Wahrgenommene Helligkeit; entscheidet über weiße oder dunkle Schrift."""
    r, g, b = farbe[0], farbe[1], farbe[2]
    return (0.299 * r + 0.587 * g + 0.114 * b) > 160


def _abdunkeln(farbe: RGBColor, faktor: float = 0.7) -> RGBColor:
    return RGBColor(int(farbe[0] * faktor), int(farbe[1] * faktor), int(farbe[2] * faktor))


def _mischen(a: RGBColor, b: RGBColor, anteil: float) -> RGBColor:
    """anteil 0 = a, 1 = b."""
    anteil = min(1.0, max(0.0, anteil))
    return RGBColor(*(int(round(a[i] * (1 - anteil) + b[i] * anteil)) for i in range(3)))


@dataclass
class Thema:
    name: str
    untertitel: str
    primaer: RGBColor
    akzent: RGBColor
    schrift: str
    schrift_titel: str
    hell: bool
    hintergrund: RGBColor
    logo: bytes | None

    @classmethod
    def aus(cls, marke: Marke | None, logo: bytes | None) -> "Thema":
        if marke is None:
            return cls("", "", RGBColor(0x1F, 0x3A, 0x5F), RGBColor(0xD9, 0xA4, 0x41), "Calibri", "Calibri", False,
                       RGBColor(0xF4, 0xF1, 0xE9), logo)
        schrift = marke.schrift or "Calibri"
        return cls(marke.name, marke.untertitel, _rgb(marke.farbe), _rgb(marke.akzent), schrift, marke.schrift_titel or schrift,
                   marke.stil == "hell", _rgb(marke.hintergrund), logo)

    @property
    def titel_grund(self) -> RGBColor:
        return self.hintergrund if self.hell else self.primaer

    @property
    def titel_schrift(self) -> RGBColor:
        return self.primaer if self.hell else (TEXT if _hell(self.primaer) else WEISS)

    @property
    def titel_nebenschrift(self) -> RGBColor:
        if self.hell:
            return GRAU
        return GRAU if _hell(self.primaer) else RGBColor(0xC8, 0xCE, 0xD6)

    @property
    def akzent_text(self) -> RGBColor:
        """Akzentfarbe als Textfarbe auf Weiß: helle Akzente (z. B. Deloitte-Grün) etwas abdunkeln."""
        return _abdunkeln(self.akzent) if _hell(self.akzent) else self.akzent

    @property
    def akzent_auf_grund(self) -> RGBColor:
        """Akzent auf der Titel-/Kapitelfläche: hell -> abgedunkelt, auf dunklem Grund die reine Farbe."""
        return self.akzent_text if self.hell else self.akzent

    @property
    def karte(self) -> RGBColor:
        return self.hintergrund if self.hell else KARTE

    @property
    def primaer_hell(self) -> RGBColor:
        """Zarter Ton der Hauptfarbe für Piktogramm-Kreise."""
        return _mischen(self.primaer, WEISS, 0.88)


# ------------------------------------------------------------------ Schriftmaße (für passende Schriftgrößen)
_FONT_DATEIEN = {
    "calibri": ("calibri.ttf", "calibrib.ttf"),
    "georgia": ("georgia.ttf", "georgiab.ttf"),
    "open sans": ("segoeui.ttf", "segoeuib.ttf"),  # ähnliche Laufweite
    "arial": ("arial.ttf", "arialbd.ttf"),
    "segoe ui": ("segoeui.ttf", "segoeuib.ttf"),
}
_FONT_ORDNER = (Path(r"C:\Windows\Fonts"), Path.home() / "AppData/Local/Microsoft/Windows/Fonts", Path("/usr/share/fonts"))


@lru_cache(maxsize=64)
def _font(schrift: str, fett: bool, px: int):
    try:
        from PIL import ImageFont
    except ImportError:  # pragma: no cover
        return None
    normal, dick = _FONT_DATEIEN.get(schrift.lower(), _FONT_DATEIEN["calibri"])
    for ordner in _FONT_ORDNER:
        pfad = ordner / (dick if fett else normal)
        if pfad.exists():
            try:
                return ImageFont.truetype(str(pfad), px)
            except OSError:  # pragma: no cover
                return None
    return None


def _textbreite(text: str, schrift: str, pt: float, fett: bool) -> float:
    """Breite in Zoll."""
    font = _font(schrift, fett, 64)
    if font is None:
        return len(text) * pt * (0.56 if fett else 0.52) / 72
    return font.getlength(text) / 64 * pt / 72


def _zeilen(text: str, schrift: str, pt: float, fett: bool, breite: float) -> list[str]:
    zeilen: list[str] = []
    for absatz in text.split("\n"):
        aktuell = ""
        for wort in absatz.split():
            probe = f"{aktuell} {wort}".strip()
            if aktuell and _textbreite(probe, schrift, pt, fett) > breite:
                zeilen.append(aktuell)
                aktuell = wort
            else:
                aktuell = probe
        zeilen.append(aktuell)
    return zeilen


def _texthoehe(text: str, schrift: str, pt: float, fett: bool, breite: float, abstand: float = 1.2) -> float:
    return len(_zeilen(text, schrift, pt, fett, breite)) * pt * abstand / 72


def _passend(text: str, schrift: str, breite: float, hoehe: float, von: int, bis: int, fett: bool = False, abstand: float = 1.2) -> int:
    """Größte Schriftgröße zwischen `von` und `bis`, bei der der Text in die Fläche (Zoll) passt."""
    for pt in range(von, bis - 1, -1):
        # 6 % Reserve: PowerPoint setzt die Schrift je nach Hinting etwas breiter als die Messung
        if _texthoehe(text, schrift, pt, fett, (breite - 0.16) * 0.94, abstand) <= hoehe - 0.08:
            return pt
    return bis


# ------------------------------------------------------------------ Grundbausteine
def _textfeld(folie, links, oben, breite, hoehe, *, anker=MSO_ANCHOR.TOP):
    feld = folie.shapes.add_textbox(links, oben, breite, hoehe)
    rahmen = feld.text_frame
    rahmen.word_wrap = True
    rahmen.margin_left = rahmen.margin_right = Inches(0.08)
    rahmen.margin_top = rahmen.margin_bottom = Inches(0.04)
    rahmen.vertical_anchor = anker
    return rahmen


def _absatz(rahmen, text, *, groesse=18, farbe=TEXT, fett=False, erster=False, abstand=6, schrift="Calibri",
            rechts=False, mitte=False, sperrung=0, zeilenabstand=None):
    absatz = rahmen.paragraphs[0] if erster else rahmen.add_paragraph()
    absatz.space_after = Pt(abstand)
    if rechts:
        absatz.alignment = PP_ALIGN.RIGHT
    elif mitte:
        absatz.alignment = PP_ALIGN.CENTER
    if zeilenabstand:
        absatz.line_spacing = zeilenabstand
    lauf = absatz.add_run()
    lauf.text = text
    lauf.font.size = Pt(groesse)
    lauf.font.color.rgb = farbe
    lauf.font.bold = fett
    lauf.font.name = schrift
    if sperrung:
        lauf._r.get_or_add_rPr().set("spc", str(int(sperrung * 100)))  # Laufweite in 1/100 pt
    return absatz


def _flaeche(folie, links, oben, breite, hoehe, farbe: RGBColor, form=MSO_SHAPE.RECTANGLE, *, rundung=None):
    shape = folie.shapes.add_shape(form, links, oben, breite, hoehe)
    shape.fill.solid()
    shape.fill.fore_color.rgb = farbe
    shape.line.fill.background()
    shape.shadow.inherit = False
    if rundung is not None and shape.adjustments:
        shape.adjustments[0] = rundung
    return shape


def _karte(folie, links, oben, breite, hoehe, farbe: RGBColor):
    return _flaeche(folie, links, oben, breite, hoehe, farbe, MSO_SHAPE.ROUNDED_RECTANGLE, rundung=0.06)


def _form_text(shape, text, *, groesse, farbe, schrift, fett=True, sperrung=0, rand=Inches(0.06)):
    """Text mittig in einer Form (Kreis, Chevron)."""
    rahmen = shape.text_frame
    rahmen.word_wrap = True
    rahmen.margin_left = rahmen.margin_right = rand
    rahmen.margin_top = rahmen.margin_bottom = 0
    rahmen.vertical_anchor = MSO_ANCHOR.MIDDLE
    _absatz(rahmen, text, groesse=groesse, farbe=farbe, fett=fett, erster=True, abstand=0, schrift=schrift, mitte=True, sperrung=sperrung)
    return rahmen


def _nummernkreis(folie, thema: Thema, links, oben, groesse, text, *, fuellung=None, schriftfarbe=None, pt=11):
    kreis = _flaeche(folie, links, oben, groesse, groesse, fuellung or thema.primaer, MSO_SHAPE.OVAL)
    _form_text(kreis, text, groesse=pt, farbe=schriftfarbe or (TEXT if _hell(fuellung or thema.primaer) else WEISS), schrift=thema.schrift)
    return kreis


def _linie(folie, x1, y1, x2, y2, farbe: RGBColor, breite_pt: float = 1.0):
    verbinder = folie.shapes.add_connector(1, x1, y1, x2, y2)  # MSO_CONNECTOR.STRAIGHT
    verbinder.line.color.rgb = farbe
    verbinder.line.width = Pt(breite_pt)
    return verbinder


def _bild(praes, folie, daten: bytes | None, *, hoehe, links=None, oben=None, rechts_oben=False, unten_links=False):
    if not daten:
        return None
    try:
        bild = folie.shapes.add_picture(io.BytesIO(daten), 0, 0, height=hoehe)
    except Exception:  # noqa: BLE001  defektes Logo darf die Präsentation nicht verhindern
        return None
    if rechts_oben:
        bild.left, bild.top = praes.slide_width - bild.width - Inches(0.5), Inches(0.3)
    elif unten_links:
        bild.left, bild.top = Inches(0.9), praes.slide_height - bild.height - Inches(0.7)
    else:
        bild.left, bild.top = links, oben
    return bild


def _wortmarke(rahmen, thema: Thema, *, groesse=12, farbe=None, erster=True, rechts=False):
    _absatz(rahmen, thema.name, groesse=groesse, farbe=farbe or thema.primaer, fett=True, erster=erster, abstand=0,
            schrift=thema.schrift_titel, rechts=rechts, sperrung=1.5)


# ------------------------------------------------------------------ Piktogramme (Linienzeichnungen auf 0..1000)
def _kreis_punkte(cx: float, cy: float, r: float, n: int = 32) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _zahnrad() -> list[tuple[float, float]]:
    punkte = []
    for i in range(16):
        winkel = 2 * math.pi * i / 16
        r = 400 if i % 2 == 0 else 300
        punkte.append((500 + r * math.cos(winkel), 500 + r * math.sin(winkel)))
    return punkte


def _bogen(cx: float, cy: float, r: float, von: float, bis: float, n: int = 12) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(math.radians(von + (bis - von) * i / n)), cy + r * math.sin(math.radians(von + (bis - von) * i / n)))
            for i in range(n + 1)]


# Je Piktogramm eine Liste von Pfaden (Punkte, geschlossen?)
PIKTOGRAMME: dict[str, list[tuple[list[tuple[float, float]], bool]]] = {
    "check": [([(180, 520), (420, 760), (820, 280)], False)],
    "warning": [([(500, 120), (900, 840), (100, 840)], True), ([(500, 380), (500, 600)], False), ([(500, 700), (500, 720)], False)],
    "gear": [(_zahnrad(), True), (_kreis_punkte(500, 500, 130), True)],
    "flag": [([(220, 900), (220, 120)], False), ([(220, 160), (780, 160), (660, 360), (780, 560), (220, 560)], False)],
    "target": [(_kreis_punkte(500, 500, 380), True), (_kreis_punkte(500, 500, 230), True), (_kreis_punkte(500, 500, 70), True)],
    "clock": [(_kreis_punkte(500, 500, 380), True), ([(500, 260), (500, 520), (680, 620)], False)],
    "users": [(_kreis_punkte(380, 330, 120), True), ([(160, 820), (160, 700), (260, 580), (500, 580), (600, 700), (600, 820)], False),
              (_kreis_punkte(690, 300, 100), True), ([(700, 560), (790, 580), (860, 680), (860, 820)], False)],
    "chart": [([(140, 860), (860, 860)], False), ([(230, 860), (230, 560), (350, 560), (350, 860)], False),
              ([(440, 860), (440, 360), (560, 360), (560, 860)], False), ([(650, 860), (650, 180), (770, 180), (770, 860)], False)],
    "lock": [([(220, 460), (780, 460), (780, 880), (220, 880)], True), (_bogen(500, 460, 170, 180, 360), False), ([(500, 620), (500, 720)], False)],
    "idea": [(_bogen(500, 400, 240, 150, 390), False), ([(380, 580), (380, 700), (620, 700), (620, 580)], False),
             ([(400, 800), (600, 800)], False), ([(500, 60), (500, 140)], False), ([(800, 180), (740, 240)], False), ([(200, 180), (260, 240)], False)],
    "document": [([(260, 100), (600, 100), (760, 260), (760, 900), (260, 900)], True), ([(600, 100), (600, 260), (760, 260)], False),
                 ([(380, 500), (640, 500)], False), ([(380, 640), (640, 640)], False)],
    "shield": [([(500, 100), (840, 220), (840, 500), (500, 900), (160, 500), (160, 220)], True), ([(360, 500), (460, 600), (650, 400)], False)],
    "search": [(_kreis_punkte(420, 420, 260), True), ([(610, 610), (860, 860)], False)],
    "link": [(_kreis_punkte(330, 500, 170), True), (_kreis_punkte(670, 500, 170), True), ([(400, 500), (600, 500)], False)],
    "money": [(_kreis_punkte(500, 500, 380), True), ([(500, 240), (500, 760)], False),
              ([(620, 380), (570, 330), (430, 330), (380, 390), (430, 460), (570, 540), (620, 610), (570, 670), (430, 670), (380, 620)], False)],
    "calendar": [([(160, 220), (840, 220), (840, 880), (160, 880)], True), ([(160, 400), (840, 400)], False),
                 ([(340, 120), (340, 300)], False), ([(660, 120), (660, 300)], False)],
    "chat": [([(160, 200), (840, 200), (840, 640), (440, 640), (280, 800), (280, 640), (160, 640)], True)],
    "tool": [([(220, 780), (560, 440)], False), (_kreis_punkte(660, 340, 150), True), ([(660, 340), (780, 220)], False)],
    "list": [([(340, 300), (840, 300)], False), ([(340, 500), (840, 500)], False), ([(340, 700), (840, 700)], False),
             (_kreis_punkte(200, 300, 40), True), (_kreis_punkte(200, 500, 40), True), (_kreis_punkte(200, 700, 40), True)],
    "arrow": [([(160, 500), (820, 500)], False), ([(580, 260), (820, 500), (580, 740)], False)],
}


def _piktogramm(folie, thema: Thema, name: str, links, oben, groesse, *, farbe: RGBColor | None = None, grund: RGBColor | None = None):
    """Liniensymbol in einem farbigen Kreis. Unbekannte Namen zeichnen den Zielkreis."""
    pfade = PIKTOGRAMME.get(name) or PIKTOGRAMME["target"]
    if grund is not None:
        _flaeche(folie, links, oben, groesse, groesse, grund, MSO_SHAPE.OVAL)
    innen = int(groesse * 0.54)
    versatz = int((groesse - innen) / 2)
    skala = innen / 1000
    builder = folie.shapes.build_freeform(pfade[0][0][0][0], pfade[0][0][0][1], scale=skala)
    for i, (punkte, geschlossen) in enumerate(pfade):
        if i:
            builder.move_to(*punkte[0])
        builder.add_line_segments(punkte[1:], close=geschlossen)
    form = builder.convert_to_shape(links + versatz, oben + versatz)
    form.fill.background()
    form.shadow.inherit = False
    form.line.color.rgb = farbe or thema.primaer
    form.line.width = Pt(max(1.25, groesse / Inches(1) * 3.0))
    ln = form.line._get_or_add_ln()
    ln.set("cap", "rnd")
    ln.append(OxmlElement("a:round"))
    return form


# ------------------------------------------------------------------ Folienrahmen
def _kopf(praes, thema: Thema, titel: str, kicker: str = ""):
    folie = praes.slides.add_slide(praes.slide_layouts[6])  # leer
    breite = praes.slide_width
    if thema.hell:
        # Wortmarke oben rechts in Akzentfarbe, keine Balken (van-Newboert-Master)
        if thema.name:
            rahmen = _textfeld(folie, breite - Inches(4.6), Inches(0.42), Inches(4.0), Inches(0.4))
            _wortmarke(rahmen, thema, groesse=12, farbe=thema.akzent_text, rechts=True)
        titelbreite = breite - Inches(1.2) - (Inches(4.2) if thema.name else 0)
    else:
        _flaeche(folie, 0, 0, breite, Inches(0.12), thema.primaer)
        _flaeche(folie, RAND, Inches(0.12), Inches(0.6), Inches(0.06), thema.akzent)
        titelbreite = breite - Inches(1.2) - (Inches(2.2) if thema.logo else 0)
        _bild(praes, folie, thema.logo, hoehe=Inches(0.55), rechts_oben=True)
    rahmen = _textfeld(folie, RAND, Inches(0.38), titelbreite, Inches(1.4))
    groesse = _passend(titel, thema.schrift_titel, titelbreite / Inches(1), 0.95, 26, 18, fett=True, abstand=1.15)
    if kicker:
        _absatz(rahmen, kicker.upper(), groesse=11, farbe=thema.akzent_text if thema.hell else GRAU, fett=True, erster=True, abstand=3,
                schrift=thema.schrift, sperrung=1)
        _absatz(rahmen, titel, groesse=groesse, farbe=thema.primaer, fett=True, schrift=thema.schrift_titel, zeilenabstand=1.05)
    else:
        _absatz(rahmen, titel, groesse=groesse, farbe=thema.primaer, fett=True, erster=True, schrift=thema.schrift_titel, zeilenabstand=1.05)
    return folie


def _fuss(praes, folie, thema: Thema, text: str):
    _flaeche(folie, RAND, praes.slide_height - Inches(0.62), praes.slide_width - 2 * RAND, Emu(9525), LINIE)
    rahmen = _textfeld(folie, RAND - Inches(0.08), praes.slide_height - Inches(0.55), praes.slide_width - Inches(2.0), Inches(0.35))
    links = text if thema.hell or not thema.name else f"{thema.name}  ·  {text}"
    _absatz(rahmen, links, groesse=9, farbe=HELLGRAU, erster=True, schrift=thema.schrift)
    nummer = _textfeld(folie, praes.slide_width - Inches(1.2), praes.slide_height - Inches(0.55), Inches(0.68), Inches(0.35))
    _absatz(nummer, str(len(praes.slides)), groesse=9, farbe=thema.akzent_text if thema.hell else GRAU, fett=True, erster=True,
            schrift=thema.schrift, rechts=True)


def _kurz(text: str, laenge: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= laenge else text[: laenge - 1].rstrip() + "…"


# ------------------------------------------------------------------ Titel, Agenda, Kapitel
def _titelfolie(praes, thema: Thema, titel: str, untertitel: str, datum: str):
    """Decktitel und Untertitel aus dem Plan; die Aufgabenbeschreibung selbst steht nicht auf der Folie."""
    folie = praes.slides.add_slide(praes.slide_layouts[6])
    _flaeche(folie, 0, 0, praes.slide_width, praes.slide_height, thema.titel_grund)
    s = thema.schrift
    unterzeile = "  ·  ".join(t for t in (thema.untertitel, datum) if t)
    if thema.hell:
        # Wortmarke oben links, Titel in Serifen, Illustration rechts (van-Newboert-Master)
        if thema.name:
            kopf = _textfeld(folie, Inches(0.9), Inches(0.55), Inches(6), Inches(0.5))
            _wortmarke(kopf, thema, groesse=13)
            if thema.untertitel:
                _absatz(kopf, thema.untertitel, groesse=8, farbe=GRAU, abstand=0, schrift=s, sperrung=3)
        textbreite = Inches(6.6) if thema.logo else praes.slide_width - Inches(1.8)
        rahmen = _textfeld(folie, Inches(0.9), Inches(2.3), textbreite, Inches(3.8))
        groesse = _passend(titel, thema.schrift_titel, textbreite / Inches(1), 2.0, 34, 22, fett=True, abstand=1.1)
        _flaeche(folie, Inches(0.9), Inches(2.1), Inches(1.0), Inches(0.06), thema.akzent_text)
        _absatz(rahmen, titel, groesse=groesse, farbe=thema.titel_schrift, fett=True, erster=True, abstand=12, schrift=thema.schrift_titel, zeilenabstand=1.05)
        if untertitel:
            _absatz(rahmen, untertitel, groesse=16, farbe=thema.titel_schrift, abstand=14, schrift=s, zeilenabstand=1.15)
        _absatz(rahmen, datum, groesse=13, farbe=thema.titel_nebenschrift, schrift=s)
        bild = _bild(praes, folie, thema.logo, hoehe=Inches(5.0), links=0, oben=0)
        if bild is not None:
            if bild.width > Inches(5.2):  # breite Illustrationen kleiner setzen
                bild.height = int(bild.height * Inches(5.2) / bild.width)
                bild.width = Inches(5.2)
            bild.left = praes.slide_width - bild.width - Inches(0.9)
            bild.top = int((praes.slide_height - bild.height) / 2)
        return folie
    _flaeche(folie, Inches(0.9), Inches(2.2), Inches(1.2), Inches(0.08), thema.akzent)
    if thema.name:
        kopfzeile = _textfeld(folie, Inches(0.9), Inches(0.5), praes.slide_width - Inches(1.8), Inches(0.6))
        _absatz(kopfzeile, thema.name, groesse=20, farbe=thema.titel_schrift, fett=True, erster=True, schrift=s)
    textbreite = praes.slide_width - Inches(1.8)
    rahmen = _textfeld(folie, Inches(0.9), Inches(2.4), textbreite, Inches(3.6))
    groesse = _passend(titel, thema.schrift_titel, textbreite / Inches(1), 1.9, 40, 24, fett=True, abstand=1.1)
    _absatz(rahmen, titel, groesse=groesse, farbe=thema.titel_schrift, fett=True, erster=True, abstand=12, schrift=thema.schrift_titel, zeilenabstand=1.05)
    if untertitel:
        _absatz(rahmen, untertitel, groesse=18, farbe=thema.titel_schrift, abstand=16, schrift=s, zeilenabstand=1.15)
    if unterzeile:
        _absatz(rahmen, unterzeile, groesse=14, farbe=thema.titel_nebenschrift, schrift=s)
    _bild(praes, folie, thema.logo, hoehe=Inches(0.9), unten_links=True)
    return folie


def _agenda(praes, thema: Thema, kapitel: list[dict[str, str]], fuss: str):
    folie = _kopf(praes, thema, "Agenda")
    n = len(kapitel)
    spalten = 2 if n > 6 else 1
    je_spalte = math.ceil(n / spalten)
    zeilenhoehe = min(Inches(0.82), int(INHALT_HOEHE / je_spalte))
    luecke = Inches(0.5)
    spaltenbreite = int((praes.slide_width - 2 * RAND - luecke * (spalten - 1)) / spalten)
    for i, k in enumerate(kapitel):
        spalte, zeile = divmod(i, je_spalte)
        x = RAND + spalte * (spaltenbreite + luecke)
        y = INHALT_OBEN + zeile * zeilenhoehe
        _nummernkreis(folie, thema, x, y + Inches(0.06), Inches(0.42), f"{i + 1:02d}")
        rahmen = _textfeld(folie, x + Inches(0.58), y, spaltenbreite - Inches(0.58), zeilenhoehe - Inches(0.06))
        _absatz(rahmen, k["titel"], groesse=16, farbe=thema.primaer, fett=True, erster=True, abstand=1, schrift=thema.schrift_titel)
        if k.get("sub") and zeilenhoehe >= Inches(0.7):
            _absatz(rahmen, _kurz(k["sub"], 180 if spalten == 1 else 110), groesse=11, farbe=GRAU, abstand=0, schrift=thema.schrift, zeilenabstand=1.1)
        if zeile < je_spalte - 1 and i < n - 1:
            _flaeche(folie, x + Inches(0.58), y + zeilenhoehe - Emu(9525), spaltenbreite - Inches(0.58), Emu(9525), LINIE)
    _fuss(praes, folie, thema, fuss)
    return folie


def _kapitelfolie(praes, thema: Thema, nr: int, titel: str, kernaussage: str, kapitel: list[dict[str, str]]):
    folie = praes.slides.add_slide(praes.slide_layouts[6])
    _flaeche(folie, 0, 0, praes.slide_width, praes.slide_height, thema.titel_grund)
    if thema.hell:
        if thema.name:
            rahmen = _textfeld(folie, praes.slide_width - Inches(4.6), Inches(0.42), Inches(4.0), Inches(0.4))
            _wortmarke(rahmen, thema, groesse=12, farbe=thema.akzent_text, rechts=True)
    else:
        _bild(praes, folie, thema.logo, hoehe=Inches(0.55), rechts_oben=True)
    nummer = _textfeld(folie, Inches(0.85), Inches(1.5), Inches(4), Inches(1.4))
    _absatz(nummer, f"{nr:02d}", groesse=72, farbe=thema.akzent_auf_grund, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
    _flaeche(folie, Inches(0.9), Inches(3.05), Inches(1.2), Inches(0.06), thema.akzent_auf_grund)
    textbreite = praes.slide_width - Inches(2.4)
    rahmen = _textfeld(folie, Inches(0.9), Inches(3.3), textbreite, Inches(2.8))
    groesse = _passend(titel, thema.schrift_titel, textbreite / Inches(1), 1.3, 36, 24, fett=True, abstand=1.1)
    _absatz(rahmen, titel, groesse=groesse, farbe=thema.titel_schrift, fett=True, erster=True, abstand=12, schrift=thema.schrift_titel, zeilenabstand=1.05)
    if kernaussage:
        _absatz(rahmen, kernaussage, groesse=18, farbe=thema.titel_nebenschrift, abstand=0, schrift=thema.schrift, zeilenabstand=1.15)
    # Kapitelleiste unten: wo stehen wir
    n = len(kapitel)
    luecke = Inches(0.08)
    breite = min(Inches(2.0), int((praes.slide_width - 2 * RAND - luecke * (n - 1)) / n))
    gesamt = breite * n + luecke * (n - 1)
    x = int((praes.slide_width - gesamt) / 2)
    y = praes.slide_height - Inches(0.85)
    for i, k in enumerate(kapitel):
        aktiv = i + 1 == nr
        if aktiv:
            pille = _flaeche(folie, x, y, breite, Inches(0.38), thema.akzent_auf_grund, MSO_SHAPE.ROUNDED_RECTANGLE, rundung=0.5)
            farbe = TEXT if _hell(thema.akzent_auf_grund) else WEISS
        else:
            pille = _flaeche(folie, x, y, breite, Inches(0.38), _mischen(thema.titel_grund, thema.titel_schrift, 0.1), MSO_SHAPE.ROUNDED_RECTANGLE, rundung=0.5)
            farbe = thema.titel_nebenschrift
        beschriftung = f"{i + 1:02d}" if n > 10 else _kurz(f"{i + 1:02d}  {k['titel']}", 26)
        _form_text(pille, beschriftung, groesse=9, farbe=farbe, schrift=thema.schrift, fett=aktiv)
        x += breite + luecke
    return folie


# ------------------------------------------------------------------ Inhaltsbausteine
def _icon_von(p: dict[str, Any], i: int) -> str:
    return p.get("icon") or STANDARD_ICONS[i % len(STANDARD_ICONS)]


def _gewichtspunkte(folie, thema: Thema, rechts, oben, gewicht: int):
    """Fünf Punkte, davon `gewicht` gefüllt, rechtsbündig an `rechts`."""
    d = Inches(0.1)
    for i in range(5):
        x = rechts - (5 - i) * (d + Inches(0.05))
        _flaeche(folie, x, oben, d, d, thema.primaer if i < gewicht else LINIE, MSO_SHAPE.OVAL)


def _kacheln(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    n = len(punkte)
    spalten = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 3}.get(n, 3)
    zeilen = math.ceil(n / spalten)
    luecke = Inches(0.25)
    kb = int((breite - luecke * (spalten - 1)) / spalten)
    kh = int((hoehe - luecke * (zeilen - 1)) / zeilen)
    if zeilen == 1:  # wenige Karten: nicht die ganze Höhe füllen
        laengste = max(len(p["punkt"]) + len(p.get("kurz", "")) for p in punkte)
        kh = min(kh, Inches(2.3) if laengste < 160 else Inches(3.2))
    for i, p in enumerate(punkte):
        zeile, spalte = divmod(i, spalten)
        kx = x + spalte * (kb + luecke)
        ky = y + zeile * (kh + luecke)
        _karte(folie, kx, ky, kb, kh, thema.karte)
        icon = Inches(0.56)
        _piktogramm(folie, thema, _icon_von(p, i), kx + Inches(0.22), ky + Inches(0.22), icon, grund=thema.primaer_hell)
        kurz = p.get("kurz", "")
        textbreite = kb - Inches(0.44)
        if kurz:
            kopfbreite = textbreite - icon - Inches(0.06)
            kopf = _textfeld(folie, kx + Inches(0.22) + icon + Inches(0.06), ky + Inches(0.22), kopfbreite, icon, anker=MSO_ANCHOR.MIDDLE)
            kopfgroesse = _passend(kurz, thema.schrift_titel, kopfbreite / Inches(1), icon / Inches(1), 14, 10, fett=True, abstand=1.1)
            _absatz(kopf, kurz, groesse=kopfgroesse, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel, zeilenabstand=1.0)
            ty = ky + Inches(0.22) + icon + Inches(0.1)
            tx, tb = kx + Inches(0.22), textbreite
        else:
            ty = ky + Inches(0.22)
            tx, tb = kx + Inches(0.22) + icon + Inches(0.1), textbreite - icon - Inches(0.1)
        th = ky + kh - ty - (Inches(0.36) if p.get("gewicht") else Inches(0.16))
        groesse = _passend(p["punkt"], thema.schrift, tb / Inches(1), th / Inches(1), 15, 9, abstand=1.2)
        rahmen = _textfeld(folie, tx, ty, tb, th)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=True, abstand=0, schrift=thema.schrift, zeilenabstand=1.1)
        if p.get("gewicht"):
            _gewichtspunkte(folie, thema, kx + kb - Inches(0.12), ky + kh - Inches(0.26), int(p["gewicht"]))


def _schritte(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe, senkrecht: bool | None = None):
    n = len(punkte)
    if senkrecht is None:
        senkrecht = n > 4
    if not senkrecht:
        luecke = Inches(0.12)
        sb = int((breite - luecke * (n - 1)) / n)
        for i, p in enumerate(punkte):
            sx = x + i * (sb + luecke)
            form = MSO_SHAPE.PENTAGON if i == 0 else MSO_SHAPE.CHEVRON
            pfeil = _flaeche(folie, sx, y, sb, Inches(0.8), _mischen(thema.primaer, WEISS, 0.12 * i), form)
            if pfeil.adjustments:
                pfeil.adjustments[0] = 0.25
            farbe = TEXT if _hell(_mischen(thema.primaer, WEISS, 0.12 * i)) else WEISS
            label = f"{i + 1}  {p.get('kurz') or _kurz(p['punkt'], 28)}"
            _form_text(pfeil, label, groesse=12, farbe=farbe, schrift=thema.schrift, rand=Inches(0.3))
            _piktogramm(folie, thema, _icon_von(p, i), sx + Inches(0.2), y + Inches(1.05), Inches(0.5), grund=thema.primaer_hell)
            th = hoehe - Inches(1.7)
            groesse = _passend(p["punkt"], thema.schrift, (sb - Inches(0.3)) / Inches(1), th / Inches(1), 15, 10)
            rahmen = _textfeld(folie, sx + Inches(0.12), y + Inches(1.65), sb - Inches(0.3), th)
            _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=True, abstand=0, schrift=thema.schrift, zeilenabstand=1.1)
        return
    # Senkrechter Zeitstrahl
    zh = int(hoehe / n)
    kreis = Inches(0.42)
    _linie(folie, x + int(kreis / 2), y + Inches(0.1), x + int(kreis / 2), y + zh * (n - 1) + Inches(0.1), LINIE, 2)
    for i, p in enumerate(punkte):
        zy = y + i * zh
        _nummernkreis(folie, thema, x, zy, kreis, str(i + 1))
        tx = x + kreis + Inches(0.25)
        tb = breite - kreis - Inches(0.25)
        rahmen = _textfeld(folie, tx, zy - Inches(0.04), tb, zh - Inches(0.05))
        kurz = p.get("kurz")
        if kurz:
            _absatz(rahmen, kurz, groesse=14, farbe=thema.primaer, fett=True, erster=True, abstand=1, schrift=thema.schrift_titel)
        groesse = _passend(p["punkt"], thema.schrift, tb / Inches(1), (zh - Inches(0.36 if kurz else 0.1)) / Inches(1), 14, 9)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=not kurz, abstand=0, schrift=thema.schrift, zeilenabstand=1.1)


def _legende(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe, *, nummern=True):
    """Nummerierte Liste rechts neben Matrix oder Diagramm."""
    n = len(punkte)
    zh = int(hoehe / n)
    for i, p in enumerate(punkte):
        zy = y + i * zh
        if nummern:
            _nummernkreis(folie, thema, x, zy + Inches(0.02), Inches(0.36), str(i + 1), pt=10)
        else:
            _piktogramm(folie, thema, _icon_von(p, i), x, zy, Inches(0.42), grund=thema.primaer_hell)
        tx = x + Inches(0.52)
        tb = breite - Inches(0.52)
        rahmen = _textfeld(folie, tx, zy - Inches(0.04), tb, zh - Inches(0.04))
        kurz = p.get("kurz")
        if kurz:
            _absatz(rahmen, kurz, groesse=12, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
        groesse = _passend(p["punkt"], thema.schrift, tb / Inches(1), (zh - Inches(0.3 if kurz else 0.08)) / Inches(1), 12, 8)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=not kurz, abstand=0, schrift=thema.schrift, zeilenabstand=1.1)


def _risiken(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    seite = min(hoehe - Inches(0.5), Inches(4.4))
    mx, my = x + Inches(0.95), y + Inches(0.1)
    zelle = int(seite / 3)
    stufen = ("low", "medium", "high")
    for zeile in range(3):  # Zeile 0 oben = hohe Auswirkung
        for spalte in range(3):
            summe = (spalte + 1) + (3 - zeile)
            farbe = RISIKO["niedrig"] if summe <= 3 else RISIKO["mittel"] if summe == 4 else RISIKO["hoch"]
            _flaeche(folie, mx + spalte * zelle, my + zeile * zelle, zelle - Emu(19050), zelle - Emu(19050), farbe)
    # Achsen
    for i, stufe in enumerate(stufen):
        r = _textfeld(folie, mx + i * zelle, my + seite + Inches(0.02), zelle, Inches(0.3))
        _absatz(r, stufe, groesse=9, farbe=GRAU, erster=True, abstand=0, schrift=thema.schrift, mitte=True)
        r = _textfeld(folie, mx - Inches(0.62), my + (2 - i) * zelle, Inches(0.6), zelle, anker=MSO_ANCHOR.MIDDLE)
        _absatz(r, stufe, groesse=9, farbe=GRAU, erster=True, abstand=0, schrift=thema.schrift, rechts=True)
    r = _textfeld(folie, mx, my + seite + Inches(0.3), seite, Inches(0.3))
    _absatz(r, "LIKELIHOOD", groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True, sperrung=1)
    # Gedrehtes Feld: Mittelpunkt links neben den Skalenwerten
    achse = folie.shapes.add_textbox(mx - Inches(0.8) - int(seite / 2), my + int(seite / 2) - Inches(0.15), seite, Inches(0.3))
    achse.rotation = 270.0
    achse.text_frame.margin_top = achse.text_frame.margin_bottom = 0
    _absatz(achse.text_frame, "IMPACT", groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True, sperrung=1)
    # Marker; mehrere je Zelle in einem 2x2-Raster
    belegung: dict[tuple[int, int], int] = {}
    d = Inches(0.36)
    for i, p in enumerate(punkte):
        e = int(p.get("eintritt") or 2)
        a = int(p.get("auswirkung") or 2)
        spalte, zeile = e - 1, 3 - a
        k = belegung.get((spalte, zeile), 0)
        belegung[(spalte, zeile)] = k + 1
        dx = (k % 2) * (d + Inches(0.06))
        dy = (k // 2 % 2) * (d + Inches(0.06))
        cx = mx + spalte * zelle + int((zelle - d) / 2) - int((d + Inches(0.06)) / 2) + dx
        cy = my + zeile * zelle + int((zelle - d) / 2) - int((d + Inches(0.06)) / 2) + dy
        _nummernkreis(folie, thema, cx, cy, d, str(i + 1), pt=10)
    lx = mx + seite + Inches(0.5)
    _legende(folie, thema, punkte, lx, y, x + breite - lx, hoehe)


def _balkendiagramm(folie, thema: Thema, x, y, breite, hoehe, kategorien: list[str], werte: list[float], *, maximum=5, format="0", senkrecht=False):
    daten = CategoryChartData()
    daten.categories = kategorien
    daten.add_series("Importance", werte)
    grafik = folie.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED if senkrecht else XL_CHART_TYPE.BAR_CLUSTERED, x, y, breite, hoehe, daten)
    diagramm = grafik.chart
    diagramm.has_legend = False
    diagramm.has_title = False
    diagramm.font.size = Pt(11)
    diagramm.font.name = thema.schrift
    diagramm.font.color.rgb = TEXT
    plot = diagramm.plots[0]
    plot.gap_width = 60
    plot.vary_by_categories = False
    serie = plot.series[0]
    serie.format.fill.solid()
    serie.format.fill.fore_color.rgb = thema.primaer
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.number_format = format
    labels.number_format_is_linked = False
    labels.position = XL_LABEL_POSITION.OUTSIDE_END
    labels.font.size = Pt(11)
    labels.font.bold = True
    labels.font.color.rgb = thema.primaer
    kat = diagramm.category_axis
    kat.reverse_order = not senkrecht
    kat.has_major_gridlines = False
    kat.format.line.color.rgb = LINIE
    kat.tick_labels.font.size = Pt(11)
    kat.tick_labels.font.color.rgb = TEXT
    wert = diagramm.value_axis
    wert.minimum_scale = 0
    wert.maximum_scale = maximum
    wert.has_major_gridlines = False
    wert.visible = False
    return grafik


def _prioritaeten(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    geordnet = sorted(punkte, key=lambda p: -(p.get("gewicht") or 3))
    kategorien = [p.get("kurz") or _kurz(p["punkt"], 28) for p in geordnet]
    werte = [float(p.get("gewicht") or 3) for p in geordnet]
    db = int(breite * 0.5)
    _balkendiagramm(folie, thema, x, y, db, hoehe - Inches(0.3), kategorien, werte)
    r = _textfeld(folie, x, y + hoehe - Inches(0.3), db, Inches(0.3))
    _absatz(r, "IMPORTANCE 1 (LOW) – 5 (CRITICAL)", groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True, sperrung=1)
    _legende(folie, thema, geordnet, x + db + Inches(0.4), y, breite - db - Inches(0.4), hoehe, nummern=False)


def _palette(thema: Thema) -> list[RGBColor]:
    return [thema.primaer, _mischen(thema.primaer, WEISS, 0.3), thema.akzent, _mischen(thema.primaer, WEISS, 0.55),
            _mischen(thema.akzent, WEISS, 0.45), _mischen(thema.primaer, WEISS, 0.75), GRAU, HELLGRAU]


def _harvey(folie, thema: Thema, x, y, d, anteil: float):
    """Harvey Ball: Kreis, im Uhrzeigersinn von oben zu `anteil` gefüllt."""
    ring = _flaeche(folie, x, y, d, d, WEISS, MSO_SHAPE.OVAL)
    ring.line.color.rgb = thema.primaer
    ring.line.width = Pt(1)
    if anteil >= 0.99:
        _flaeche(folie, x, y, d, d, thema.primaer, MSO_SHAPE.OVAL)
    elif anteil > 0.01:
        tortenstueck = _flaeche(folie, x, y, d, d, thema.primaer, MSO_SHAPE.PIE)
        tortenstueck.adjustments[0] = 270 * 0.6  # Winkel in 60000stel Grad, normiert auf 1/100000
        tortenstueck.adjustments[1] = ((270 + 360 * anteil) % 360) * 0.6


def _nummern(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    """Zweispaltige Liste mit großen Nummern und Harvey Ball für das Gewicht."""
    n = len(punkte)
    spalten = 2 if n > 3 else 1
    je_spalte = math.ceil(n / spalten)
    luecke = Inches(0.6)
    sb = int((breite - luecke * (spalten - 1)) / spalten)
    zh = min(Inches(1.6), int(hoehe / je_spalte))
    for i, p in enumerate(punkte):
        spalte, zeile = divmod(i, je_spalte)
        zx = x + spalte * (sb + luecke)
        zy = y + zeile * zh
        r = _textfeld(folie, zx - Inches(0.08), zy, Inches(0.9), Inches(0.6))
        _absatz(r, f"{i + 1:02d}", groesse=26, farbe=thema.akzent_text, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
        ball = Inches(0.3)
        if p.get("gewicht"):
            _harvey(folie, thema, zx + sb - ball, zy + Inches(0.1), ball, p["gewicht"] / 5)
        tx = zx + Inches(0.85)
        tb = sb - Inches(0.85) - (ball + Inches(0.15) if p.get("gewicht") else 0)
        rahmen = _textfeld(folie, tx, zy, tb, zh - Inches(0.12))
        kurz = p.get("kurz")
        if kurz:
            _absatz(rahmen, kurz, groesse=14, farbe=thema.primaer, fett=True, erster=True, abstand=2, schrift=thema.schrift_titel)
        groesse = _passend(p["punkt"], thema.schrift, tb / Inches(1), (zh - Inches(0.45 if kurz else 0.15)) / Inches(1), 13, 9)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=not kurz, abstand=0, schrift=thema.schrift, zeilenabstand=1.1)
        if zeile < je_spalte - 1 and i < n - 1:
            _flaeche(folie, zx, zy + zh - Inches(0.06), sb, Emu(9525), LINIE)


def _kennzahlen(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    """Kacheln mit großer Zahl oben."""
    n = len(punkte)
    spalten = {1: 1, 2: 2, 3: 3, 4: 4, 5: 3, 6: 3}.get(n, 4)
    zeilen = math.ceil(n / spalten)
    luecke = Inches(0.25)
    kb = int((breite - luecke * (spalten - 1)) / spalten)
    kh = int((hoehe - luecke * (zeilen - 1)) / zeilen)
    if zeilen == 1:
        kh = min(kh, Inches(3.4))
    for i, p in enumerate(punkte):
        zeile, spalte = divmod(i, spalten)
        kx = x + spalte * (kb + luecke)
        ky = y + zeile * (kh + luecke)
        _karte(folie, kx, ky, kb, kh, thema.karte)
        _flaeche(folie, kx + Inches(0.22), ky + Inches(0.26), Inches(0.5), Inches(0.05), thema.akzent)
        wert = p.get("wert") or (f"{p['gewicht']}/5" if p.get("gewicht") else "–")
        r = _textfeld(folie, kx + Inches(0.14), ky + Inches(0.36), kb - Inches(0.28), Inches(0.9), anker=MSO_ANCHOR.MIDDLE)
        groesse = _passend(wert, thema.schrift_titel, (kb - Inches(0.28)) / Inches(1), 0.85, 34, 18, fett=True, abstand=1.0)
        _absatz(r, wert, groesse=groesse, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
        _piktogramm(folie, thema, _icon_von(p, i), kx + kb - Inches(0.62), ky + Inches(0.18), Inches(0.44), grund=thema.primaer_hell)
        rahmen = _textfeld(folie, kx + Inches(0.14), ky + Inches(1.3), kb - Inches(0.28), kh - Inches(1.42))
        kurz = p.get("kurz")
        if kurz:
            _absatz(rahmen, kurz, groesse=13, farbe=thema.primaer, fett=True, erster=True, abstand=3, schrift=thema.schrift_titel)
        groesse = _passend(p["punkt"], thema.schrift, (kb - Inches(0.28)) / Inches(1), (kh - Inches(1.42) - (Inches(0.35) if kurz else 0)) / Inches(1), 12, 8)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=not kurz, abstand=0, schrift=thema.schrift, zeilenabstand=1.1)


def _zeitplan(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    """Gantt: Wochen als Spalten, je Punkt ein Balken."""
    n = len(punkte)
    fenster = []
    for p in punkte:
        s, e = int(p.get("start") or 0), int(p.get("ende") or 0)
        s = s or e or 1
        e = max(e, s)
        fenster.append((s, e))
    w0 = min(s for s, _ in fenster)
    w1 = max(e for _, e in fenster)
    wochen = w1 - w0 + 1
    lb = Inches(3.1)
    gx = x + lb
    gb = breite - lb
    kopf = Inches(0.4)
    zh = min(Inches(0.9), int((hoehe - kopf) / n))
    sw = int(gb / wochen)
    palette = _palette(thema)
    for w in range(wochen):
        r = _textfeld(folie, gx + w * sw, y, sw, kopf, anker=MSO_ANCHOR.MIDDLE)
        _absatz(r, f"W{w0 + w}", groesse=10, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True)
        _flaeche(folie, gx + w * sw, y + kopf, Emu(9525), zh * n, LINIE)
    _flaeche(folie, gx + wochen * sw, y + kopf, Emu(9525), zh * n, LINIE)
    _flaeche(folie, x, y + kopf, breite, Emu(9525), LINIE)
    for i, (p, (s, e)) in enumerate(zip(punkte, fenster)):
        zy = y + kopf + i * zh
        if i % 2 == 1:
            _flaeche(folie, x, zy, breite, zh, _mischen(thema.karte, WEISS, 0.5))
        rahmen = _textfeld(folie, x, zy + Inches(0.04), lb - Inches(0.2), zh - Inches(0.08), anker=MSO_ANCHOR.MIDDLE)
        kurz = p.get("kurz")
        if kurz:
            _absatz(rahmen, kurz, groesse=12, farbe=thema.primaer, fett=True, erster=True, abstand=1, schrift=thema.schrift_titel)
        groesse = _passend(p["punkt"], thema.schrift, (lb - Inches(0.2)) / Inches(1), (zh - Inches(0.36 if kurz else 0.1)) / Inches(1), 10, 8)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=not kurz, abstand=0, schrift=thema.schrift, zeilenabstand=1.05)
        bx = gx + (s - w0) * sw + Inches(0.05)
        bb = (e - s + 1) * sw - Inches(0.1)
        bh = min(Inches(0.38), zh - Inches(0.2))
        balken = _flaeche(folie, bx, zy + int((zh - bh) / 2), bb, bh, palette[i % 2 * 1], MSO_SHAPE.ROUNDED_RECTANGLE, rundung=0.5)
        _form_text(balken, f"W{s}" if s == e else f"W{s}–W{e}", groesse=9, farbe=WEISS if not _hell(palette[i % 2]) else TEXT, schrift=thema.schrift)


def _trichter(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    """Stufen von breit nach eng, Legende rechts."""
    n = len(punkte)
    tb = Inches(6.0)
    luecke = Inches(0.06)
    sh = int((hoehe - luecke * (n - 1)) / n)
    cx = x + int(tb / 2)
    for i, p in enumerate(punkte):
        oben = 1.0 - 0.6 * i / n
        unten = 1.0 - 0.6 * (i + 1) / n
        sy = y + i * (sh + luecke)
        wo, wu = int(tb * oben), int(tb * unten)
        builder = folie.shapes.build_freeform(cx - int(wo / 2), sy, scale=1.0)
        builder.add_line_segments([(cx + int(wo / 2), sy), (cx + int(wu / 2), sy + sh), (cx - int(wu / 2), sy + sh)], close=True)
        stufe = builder.convert_to_shape()
        fuellung = _mischen(thema.primaer, WEISS, 0.55 - 0.55 * i / max(1, n - 1))
        stufe.fill.solid()
        stufe.fill.fore_color.rgb = fuellung
        stufe.line.fill.background()
        stufe.shadow.inherit = False
        r = _textfeld(folie, cx - int(wu / 2), sy, wu, sh, anker=MSO_ANCHOR.MIDDLE)
        label = f"{i + 1}  {p.get('kurz') or _kurz(p['punkt'], 24)}"
        _absatz(r, label, groesse=12, farbe=TEXT if _hell(fuellung) else WEISS, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True)
    _legende(folie, thema, punkte, x + tb + Inches(0.5), y, breite - tb - Inches(0.5), hoehe)


def _tabelle(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    n = len(punkte)
    mit_gewicht = any(p.get("gewicht") for p in punkte)
    spalten = [Inches(0.5), Inches(2.6), breite - Inches(3.1) - (Inches(1.3) if mit_gewicht else 0)] + ([Inches(1.3)] if mit_gewicht else [])
    kopfzeile = Inches(0.42)
    zh = min(Inches(0.95), int((hoehe - kopfzeile) / n))
    form = folie.shapes.add_table(n + 1, len(spalten), x, y, breite, kopfzeile + zh * n)
    tbl = form.table
    tblPr = tbl._tbl.tblPr
    stil = tblPr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}tableStyleId")
    if stil is None:
        stil = OxmlElement("a:tableStyleId")
        tblPr.append(stil)
    stil.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # No Style, No Grid
    tbl.first_row = False
    tbl.horz_banding = False
    for c, b in enumerate(spalten):
        tbl.columns[c].width = b
    tbl.rows[0].height = kopfzeile
    titel = ["#", "Topic", "Action"] + (["Importance"] if mit_gewicht else [])
    for c, t in enumerate(titel):
        zelle = tbl.cell(0, c)
        zelle.fill.solid()
        zelle.fill.fore_color.rgb = thema.primaer
        zelle.margin_left = zelle.margin_right = Inches(0.1)
        zelle.margin_top = zelle.margin_bottom = Inches(0.04)
        zelle.vertical_anchor = MSO_ANCHOR.MIDDLE
        _absatz(zelle.text_frame, t.upper(), groesse=10, farbe=TEXT if _hell(thema.primaer) else WEISS, fett=True, erster=True, abstand=0,
                schrift=thema.schrift, sperrung=1, mitte=(c == 0))
    for i, p in enumerate(punkte, start=1):
        tbl.rows[i].height = zh
        werte = [f"{i:02d}", p.get("kurz") or "", p["punkt"]]
        if mit_gewicht:
            g = int(p.get("gewicht") or 0)
            werte.append("●" * g + "○" * (5 - g))
        for c, t in enumerate(werte):
            zelle = tbl.cell(i, c)
            zelle.fill.solid()
            zelle.fill.fore_color.rgb = thema.karte if i % 2 == 0 else WEISS
            zelle.margin_left = zelle.margin_right = Inches(0.1)
            zelle.margin_top = zelle.margin_bottom = Inches(0.04)
            zelle.vertical_anchor = MSO_ANCHOR.MIDDLE
            if c == 2:
                groesse = _passend(t, thema.schrift, spalten[c] / Inches(1), zh / Inches(1), 12, 8)
                _absatz(zelle.text_frame, t, groesse=groesse, farbe=TEXT, erster=True, abstand=0, schrift=thema.schrift, zeilenabstand=1.05)
            elif c == 1:
                _absatz(zelle.text_frame, t, groesse=12, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
            elif c == 0:
                _absatz(zelle.text_frame, t, groesse=12, farbe=thema.akzent_text, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel, mitte=True)
            else:
                _absatz(zelle.text_frame, t, groesse=12, farbe=thema.primaer, erster=True, abstand=0, schrift="Calibri", mitte=True)
    return form


def _radar(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    daten = CategoryChartData()
    daten.categories = [p.get("kurz") or _kurz(p["punkt"], 20) for p in punkte]
    daten.add_series("Importance", [float(p.get("gewicht") or 3) for p in punkte])
    db = int(breite * 0.52)
    grafik = folie.shapes.add_chart(XL_CHART_TYPE.RADAR_MARKERS, x, y, db, hoehe, daten)
    diagramm = grafik.chart
    diagramm.has_legend = False
    diagramm.font.size = Pt(11)
    diagramm.font.name = thema.schrift
    diagramm.font.color.rgb = TEXT
    serie = diagramm.plots[0].series[0]
    serie.format.line.color.rgb = thema.primaer
    serie.format.line.width = Pt(2.25)
    serie.marker.format.fill.solid()
    serie.marker.format.fill.fore_color.rgb = thema.akzent
    serie.marker.format.line.color.rgb = thema.akzent
    serie.marker.size = 8
    wert = diagramm.value_axis
    wert.minimum_scale = 0
    wert.maximum_scale = 5
    wert.major_unit = 1
    wert.major_gridlines.format.line.color.rgb = LINIE
    wert.tick_labels.font.size = Pt(8)
    wert.tick_labels.font.color.rgb = HELLGRAU
    _legende(folie, thema, punkte, x + db + Inches(0.3), y, breite - db - Inches(0.3), hoehe, nummern=False)


def _kreis(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    palette = _palette(thema)
    daten = CategoryChartData()
    daten.categories = [p.get("kurz") or _kurz(p["punkt"], 20) for p in punkte]
    gewichte = [float(p.get("gewicht") or 3) for p in punkte]
    daten.add_series("Share", gewichte)
    db = int(breite * 0.46)
    grafik = folie.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, x, y, db, hoehe, daten)
    diagramm = grafik.chart
    diagramm.has_legend = False
    diagramm.font.size = Pt(11)
    diagramm.font.name = thema.schrift
    plot = diagramm.plots[0]
    plot.vary_by_categories = True
    loch = plot._element.find("{http://schemas.openxmlformats.org/drawingml/2006/chart}holeSize")
    if loch is not None:
        loch.set("val", "62")
    serie = plot.series[0]
    for i, punkt in enumerate(serie.points):
        punkt.format.fill.solid()
        punkt.format.fill.fore_color.rgb = palette[i % len(palette)]
        punkt.format.line.color.rgb = WEISS
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.show_percentage = True
    labels.show_value = False
    labels.show_category_name = False
    labels.number_format = "0%"
    labels.number_format_is_linked = False
    labels.font.size = Pt(10)
    labels.font.bold = True
    labels.font.color.rgb = WEISS
    # Legende rechts mit Farbpunkten
    lx = x + db + Inches(0.3)
    lb = breite - db - Inches(0.3)
    n = len(punkte)
    zh = int(hoehe / n)
    gesamt = sum(gewichte)
    for i, p in enumerate(punkte):
        zy = y + i * zh
        _flaeche(folie, lx, zy + Inches(0.08), Inches(0.26), Inches(0.26), palette[i % len(palette)], MSO_SHAPE.OVAL)
        rahmen = _textfeld(folie, lx + Inches(0.4), zy - Inches(0.04), lb - Inches(0.4), zh - Inches(0.04))
        kurz = f"{p.get('kurz') or _kurz(p['punkt'], 24)}  ·  {gewichte[i] / gesamt:.0%}"
        _absatz(rahmen, kurz, groesse=12, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
        groesse = _passend(p["punkt"], thema.schrift, (lb - Inches(0.4)) / Inches(1), (zh - Inches(0.3)) / Inches(1), 12, 8)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, abstand=0, schrift=thema.schrift, zeilenabstand=1.1)


def _achsenkreuz(folie, thema: Thema, mx, my, seite, x_label: str, y_label: str):
    r = _textfeld(folie, mx, my + seite + Inches(0.06), seite, Inches(0.3))
    _absatz(r, x_label, groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True, sperrung=1)
    achse = folie.shapes.add_textbox(mx - Inches(0.3) - int(seite / 2), my + int(seite / 2) - Inches(0.15), seite, Inches(0.3))
    achse.rotation = 270.0
    achse.text_frame.margin_top = achse.text_frame.margin_bottom = 0
    _absatz(achse.text_frame, y_label, groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True, sperrung=1)


def _matrix(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    """2x2: Nutzen (Gewicht) gegen Aufwand."""
    seite = min(hoehe - Inches(0.5), Inches(4.4))
    mx, my = x + Inches(0.45), y + Inches(0.1)
    halb = int(seite / 2)
    felder = [  # (spalte, zeile, Farbe, Beschriftung)
        (0, 0, _mischen(thema.primaer, WEISS, 0.8), "QUICK WINS"), (1, 0, thema.karte, "BIG BETS"),
        (0, 1, thema.karte, "FILL-INS"), (1, 1, _mischen(thema.karte, WEISS, 0.5), "DEPRIORITIZE"),
    ]
    for spalte, zeile, farbe, name in felder:
        fx, fy = mx + spalte * halb, my + zeile * halb
        _flaeche(folie, fx, fy, halb - Emu(19050), halb - Emu(19050), farbe)
        # Beschriftung in der Außenecke des Quadranten, weg von den Markern an der Mitte
        r = _textfeld(folie, fx + Inches(0.05), fy + (Inches(0.05) if zeile == 0 else halb - Inches(0.38)), halb - Inches(0.2), Inches(0.3))
        _absatz(r, name, groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, sperrung=1, rechts=(spalte == 1))
    _achsenkreuz(folie, thema, mx, my, seite, "EFFORT  low  →  high", "IMPACT  low  →  high")
    d = Inches(0.36)
    for i, p in enumerate(punkte):
        xr = ((p.get("aufwand") or 2) - 0.5) / 3
        yr = ((p.get("gewicht") or 3) - 0.5) / 5
        cx = mx + int(seite * xr) - int(d / 2) + (i % 3 - 1) * Inches(0.12)
        cy = my + int(seite * (1 - yr)) - int(d / 2) + (i % 2) * Inches(0.1)
        _nummernkreis(folie, thema, cx, cy, d, str(i + 1), pt=10)
    lx = mx + seite + Inches(0.5)
    _legende(folie, thema, punkte, lx, y, x + breite - lx, hoehe)


def _pyramide(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    """Spitze oben (erster Punkt), Fundament unten."""
    n = len(punkte)
    tb = Inches(6.0)
    luecke = Inches(0.06)
    sh = int((hoehe - luecke * (n - 1)) / n)
    cx = x + int(tb / 2)
    for i, p in enumerate(punkte):
        oben = 0.35 + 0.65 * i / n
        unten = 0.35 + 0.65 * (i + 1) / n
        sy = y + i * (sh + luecke)
        wo, wu = int(tb * oben), int(tb * unten)
        builder = folie.shapes.build_freeform(cx - int(wo / 2), sy, scale=1.0)
        builder.add_line_segments([(cx + int(wo / 2), sy), (cx + int(wu / 2), sy + sh), (cx - int(wu / 2), sy + sh)], close=True)
        stufe = builder.convert_to_shape()
        fuellung = _mischen(thema.primaer, WEISS, 0.6 * i / max(1, n - 1))
        stufe.fill.solid()
        stufe.fill.fore_color.rgb = fuellung
        stufe.line.fill.background()
        stufe.shadow.inherit = False
        r = _textfeld(folie, cx - int(wo / 2), sy, wo, sh, anker=MSO_ANCHOR.MIDDLE)
        label = f"{i + 1}  {p.get('kurz') or _kurz(p['punkt'], 24)}"
        groesse = _passend(label, thema.schrift, wo / Inches(1), sh / Inches(1), 12, 8, fett=True)
        _absatz(r, label, groesse=groesse, farbe=TEXT if _hell(fuellung) else WEISS, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True)
    _legende(folie, thema, punkte, x + tb + Inches(0.5), y, breite - tb - Inches(0.5), hoehe)


def _kreislauf(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    n = len(punkte)
    feld = Inches(6.2)
    cx, cy = x + int(feld / 2), y + int(hoehe / 2)
    r = int(min(hoehe, feld) / 2) - Inches(0.8)
    ring = _flaeche(folie, cx - r, cy - r, 2 * r, 2 * r, WEISS, MSO_SHAPE.OVAL)
    ring.fill.background()
    ring.line.color.rgb = LINIE
    ring.line.width = Pt(2.5)
    d = Inches(0.5)
    for i, p in enumerate(punkte):
        a = math.radians(-90 + 360 * i / n)
        nx, ny = cx + int(r * math.cos(a)), cy + int(r * math.sin(a))
        _nummernkreis(folie, thema, nx - int(d / 2), ny - int(d / 2), d, str(i + 1), pt=12)
        # Richtungspfeil zwischen den Knoten
        am = math.radians(-90 + 360 * (i + 0.5) / n)
        pfeil = _flaeche(folie, cx + int(r * math.cos(am)) - Inches(0.1), cy + int(r * math.sin(am)) - Inches(0.1), Inches(0.2), Inches(0.2), thema.akzent, MSO_SHAPE.CHEVRON)
        pfeil.rotation = math.degrees(am) + 90
        # Beschriftung außen
        lb, lh = Inches(1.7), Inches(0.5)
        ax = cx + int((r + Inches(0.95)) * math.cos(a))
        ay = cy + int((r + Inches(0.6)) * math.sin(a))
        t = _textfeld(folie, ax - int(lb / 2), ay - int(lh / 2), lb, lh, anker=MSO_ANCHOR.MIDDLE)
        _absatz(t, p.get("kurz") or _kurz(p["punkt"], 20), groesse=10, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel, mitte=True)
    _legende(folie, thema, punkte, x + feld + Inches(0.3), y, breite - feld - Inches(0.3), hoehe)


def _saeulen(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    kategorien = [p.get("kurz") or _kurz(p["punkt"], 20) for p in punkte]
    werte = [float(p.get("gewicht") or 3) for p in punkte]
    db = int(breite * 0.55)
    _balkendiagramm(folie, thema, x, y, db, hoehe - Inches(0.3), kategorien, werte, senkrecht=True)
    r = _textfeld(folie, x, y + hoehe - Inches(0.3), db, Inches(0.3))
    _absatz(r, "IMPORTANCE 1 (LOW) – 5 (CRITICAL)", groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True, sperrung=1)
    _legende(folie, thema, punkte, x + db + Inches(0.4), y, breite - db - Inches(0.4), hoehe, nummern=False)


def _gruppen_von(punkte: list[dict[str, Any]], hoechstens: int = 3) -> dict[str, list[dict[str, Any]]]:
    gruppen: dict[str, list[dict[str, Any]]] = {}
    for p in punkte:
        name = p.get("gruppe") or "Other"
        if name not in gruppen and len(gruppen) >= hoechstens:
            name = list(gruppen)[-1]
        gruppen.setdefault(name, []).append(p)
    return gruppen


def _spalten(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    gruppen = _gruppen_von(punkte)
    n = len(gruppen)
    luecke = Inches(0.3)
    sb = int((breite - luecke * (n - 1)) / n)
    meiste = max(len(v) for v in gruppen.values())
    kopf = Inches(0.46)
    zh = min(Inches(1.3), int((hoehe - kopf - Inches(0.1)) / meiste))
    for s, (name, eintraege) in enumerate(gruppen.items()):
        sx = x + s * (sb + luecke)
        bandfarbe = thema.primaer if s == 0 else _mischen(thema.primaer, WEISS, 0.25 * s)
        band = _flaeche(folie, sx, y, sb, kopf, bandfarbe)
        _form_text(band, name.upper(), groesse=11, farbe=TEXT if _hell(bandfarbe) else WEISS, schrift=thema.schrift, sperrung=1)
        _flaeche(folie, sx, y + kopf, sb, hoehe - kopf, thema.karte)
        for i, p in enumerate(eintraege):
            zy = y + kopf + Inches(0.1) + i * zh
            _piktogramm(folie, thema, _icon_von(p, i), sx + Inches(0.15), zy + Inches(0.06), Inches(0.42), grund=WEISS)
            tx = sx + Inches(0.7)
            tb = sb - Inches(0.85)
            rahmen = _textfeld(folie, tx, zy, tb, zh - Inches(0.06))
            kurz = p.get("kurz")
            if kurz:
                _absatz(rahmen, kurz, groesse=12, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
            groesse = _passend(p["punkt"], thema.schrift, tb / Inches(1), (zh - Inches(0.32 if kurz else 0.08)) / Inches(1), 11, 8)
            _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=not kurz, abstand=0, schrift=thema.schrift, zeilenabstand=1.05)


SWOT = (("strength", "S", "Strengths"), ("weakness", "W", "Weaknesses"), ("opportunit", "O", "Opportunities"), ("threat", "T", "Threats"))


def _swot_feld(p: dict[str, Any]) -> int | None:
    g = (p.get("gruppe") or "").lower()
    for i, (schluessel, buchstabe, _) in enumerate(SWOT):
        if g.startswith(schluessel) or g == buchstabe.lower():
            return i
    return None


def _swot(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    farben = (RISIKO["niedrig"], RISIKO["hoch"], thema.primaer_hell, RISIKO["mittel"])
    luecke = Inches(0.2)
    fb, fh = int((breite - luecke) / 2), int((hoehe - luecke) / 2)
    felder: list[list[dict[str, Any]]] = [[], [], [], []]
    for p in punkte:
        i = _swot_feld(p)
        felder[i if i is not None else 2].append(p)
    for i, (_, buchstabe, name) in enumerate(SWOT):
        fx = x + (i % 2) * (fb + luecke)
        fy = y + (i // 2) * (fh + luecke)
        _karte(folie, fx, fy, fb, fh, farben[i])
        r = _textfeld(folie, fx + Inches(0.1), fy + Inches(0.08), Inches(0.8), Inches(0.7), anker=MSO_ANCHOR.MIDDLE)
        _absatz(r, buchstabe, groesse=30, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
        r = _textfeld(folie, fx + Inches(0.85), fy + Inches(0.14), fb - Inches(1.0), Inches(0.5), anker=MSO_ANCHOR.MIDDLE)
        _absatz(r, name.upper(), groesse=11, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift, sperrung=1)
        eintraege = felder[i]
        if not eintraege:
            continue
        rahmen = _textfeld(folie, fx + Inches(0.2), fy + Inches(0.8), fb - Inches(0.4), fh - Inches(0.9))
        text = "\n".join(f"•  {p['punkt']}" for p in eintraege)
        groesse = _passend(text, thema.schrift, (fb - Inches(0.4)) / Inches(1), (fh - Inches(0.9)) / Inches(1), 12, 8, abstand=1.3)
        for j, p in enumerate(eintraege):
            _absatz(rahmen, f"•  {p['punkt']}", groesse=groesse, farbe=TEXT, erster=(j == 0), abstand=4, schrift=thema.schrift, zeilenabstand=1.05)


AMPEL = {"gruen": (RGBColor(0x3C, 0xB3, 0x71), "On track"), "gelb": (RGBColor(0xE8, 0xB7, 0x30), "At risk"), "rot": (RGBColor(0xD9, 0x53, 0x4F), "Critical"), "": (HELLGRAU, "Open")}


def _ampel(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    n = len(punkte)
    spalten = 2 if n > 5 else 1
    je_spalte = math.ceil(n / spalten)
    luecke = Inches(0.5)
    sb = int((breite - luecke * (spalten - 1)) / spalten)
    kopf = Inches(0.4)
    zh = min(Inches(1.1), int((hoehe - kopf) / je_spalte))
    # Legende der Farben oben
    lx = x
    for schluessel in ("gruen", "gelb", "rot"):
        farbe, name = AMPEL[schluessel]
        _flaeche(folie, lx, y + Inches(0.08), Inches(0.18), Inches(0.18), farbe, MSO_SHAPE.OVAL)
        r = _textfeld(folie, lx + Inches(0.2), y, Inches(1.2), Inches(0.34), anker=MSO_ANCHOR.MIDDLE)
        _absatz(r, name.upper(), groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, sperrung=1)
        lx += Inches(1.35)
    for i, p in enumerate(punkte):
        spalte, zeile = divmod(i, je_spalte)
        zx = x + spalte * (sb + luecke)
        zy = y + kopf + zeile * zh
        if zeile % 2 == 0:
            _flaeche(folie, zx, zy, sb, zh - Inches(0.04), thema.karte)
        farbe, _ = AMPEL.get(p.get("status") or "", AMPEL[""])
        _flaeche(folie, zx + Inches(0.2), zy + Inches(0.14), Inches(0.3), Inches(0.3), farbe, MSO_SHAPE.OVAL)
        tx = zx + Inches(0.7)
        tb = sb - Inches(0.85)
        rahmen = _textfeld(folie, tx, zy + Inches(0.04), tb, zh - Inches(0.1))
        kurz = p.get("kurz")
        if kurz:
            _absatz(rahmen, kurz, groesse=12, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
        groesse = _passend(p["punkt"], thema.schrift, tb / Inches(1), (zh - Inches(0.36 if kurz else 0.12)) / Inches(1), 11, 8)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=not kurz, abstand=0, schrift=thema.schrift, zeilenabstand=1.05)


def _meilensteine(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    n = len(punkte)
    wochen = [int(p.get("start") or p.get("ende") or (i + 1)) for i, p in enumerate(punkte)]
    w0, w1 = min(wochen), max(wochen)
    spanne = w1 - w0 + 1
    x0, x1 = x + Inches(0.3), x + breite - Inches(0.3)
    gb = x1 - x0
    linie_y = y + int(hoehe * 0.5)
    _linie(folie, x0, linie_y, x1, linie_y, LINIE, 2.5)
    for w in range(spanne):
        wx = x0 + int(gb * w / spanne)
        _flaeche(folie, wx, linie_y - Inches(0.08), Emu(9525), Inches(0.16), HELLGRAU)
        r = _textfeld(folie, wx, y + hoehe - Inches(0.3), int(gb / spanne), Inches(0.3))  # Wochenskala am unteren Rand
        _absatz(r, f"W{w0 + w}", groesse=9, farbe=HELLGRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True)
    _flaeche(folie, x0, y + hoehe - Inches(0.32), gb, Emu(9525), LINIE)
    d = Inches(0.42)
    sb = min(Inches(2.6), int(gb / max(1, math.ceil(n / 2))))
    for i, (p, w) in enumerate(zip(punkte, wochen)):
        cx = x0 + int(gb * (w - w0 + 0.5) / spanne)
        raute = _flaeche(folie, cx - int(d / 2), linie_y - int(d / 2), d, d, thema.akzent, MSO_SHAPE.DIAMOND)
        _form_text(raute, str(i + 1), groesse=10, farbe=TEXT if _hell(thema.akzent) else WEISS, schrift=thema.schrift, rand=0)
        oben = i % 2 == 0
        th = int(hoehe * 0.5) - Inches(0.7)
        ty = linie_y - int(d / 2) - Inches(0.12) - th if oben else linie_y + Inches(0.4)
        rahmen = _textfeld(folie, cx - int(sb / 2), ty, sb, th, anker=MSO_ANCHOR.BOTTOM if oben else MSO_ANCHOR.TOP)
        kurz = p.get("kurz")
        if kurz:
            _absatz(rahmen, kurz, groesse=12, farbe=thema.primaer, fett=True, erster=True, abstand=1, schrift=thema.schrift_titel, mitte=True)
        groesse = _passend(p["punkt"], thema.schrift, sb / Inches(1), (th - Inches(0.34 if kurz else 0.05)) / Inches(1), 11, 8)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=not kurz, abstand=0, schrift=thema.schrift, mitte=True, zeilenabstand=1.05)
        _linie(folie, cx, linie_y - int(d / 2) if oben else linie_y + int(d / 2), cx, ty + th if oben else ty - Inches(0.05), LINIE, 1)


def _treiber(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe, titel: str = "Goal"):
    n = len(punkte)
    wb, wh = Inches(2.9), Inches(1.5)
    wy = y + int((hoehe - wh) / 2)
    wurzel = _karte(folie, x, wy, wb, wh, thema.primaer)
    _form_text(wurzel, titel, groesse=14, farbe=TEXT if _hell(thema.primaer) else WEISS, schrift=thema.schrift_titel, rand=Inches(0.15))
    ax = x + Inches(3.7)
    ab = x + breite - ax
    luecke = Inches(0.12)
    ah = int((hoehe - luecke * (n - 1)) / n)
    mitte_x = x + wb + Inches(0.4)
    _linie(folie, x + wb, wy + int(wh / 2), mitte_x, wy + int(wh / 2), LINIE, 1.5)
    for i, p in enumerate(punkte):
        ay = y + i * (ah + luecke)
        cy = ay + int(ah / 2)
        _linie(folie, mitte_x, cy, ax, cy, LINIE, 1.5)
        if i == 0 or i == n - 1:
            _linie(folie, mitte_x, min(cy, wy + int(wh / 2)), mitte_x, max(cy, wy + int(wh / 2)), LINIE, 1.5)
        _karte(folie, ax, ay, ab, ah, thema.karte)
        icon = Inches(0.44)
        _piktogramm(folie, thema, _icon_von(p, i), ax + Inches(0.15), ay + int((ah - icon) / 2), icon, grund=thema.primaer_hell)
        tx = ax + Inches(0.75)
        tb = ab - Inches(0.9)
        rahmen = _textfeld(folie, tx, ay + Inches(0.04), tb, ah - Inches(0.08), anker=MSO_ANCHOR.MIDDLE)
        kurz = p.get("kurz")
        if kurz:
            _absatz(rahmen, kurz, groesse=12, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
        groesse = _passend(p["punkt"], thema.schrift, tb / Inches(1), (ah - Inches(0.36 if kurz else 0.1)) / Inches(1), 11, 8)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=not kurz, abstand=0, schrift=thema.schrift, zeilenabstand=1.05)


def _stufen(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    n = len(punkte)
    cw = int(breite / n)
    grund = y + Inches(2.9)
    for i, p in enumerate(punkte):
        sh = Inches(0.6) + int(Inches(2.2) * i / max(1, n - 1))
        sx = x + i * cw
        fuellung = _mischen(thema.primaer, WEISS, 0.55 - 0.55 * i / max(1, n - 1))
        _flaeche(folie, sx + Inches(0.03), grund - sh, cw - Inches(0.06), sh, fuellung)
        r = _textfeld(folie, sx + Inches(0.08), grund - sh + Inches(0.06), cw - Inches(0.16), Inches(0.75))
        label = f"{i + 1}  {p.get('kurz') or _kurz(p['punkt'], 22)}"
        groesse = _passend(label, thema.schrift, (cw - Inches(0.16)) / Inches(1), 0.7, 12, 8, fett=True)
        _absatz(r, label, groesse=groesse, farbe=TEXT if _hell(fuellung) else WEISS, fett=True, erster=True, abstand=0, schrift=thema.schrift)
        th = hoehe - Inches(3.1)
        rahmen = _textfeld(folie, sx + Inches(0.08), grund + Inches(0.15), cw - Inches(0.16), th)
        groesse = _passend(p["punkt"], thema.schrift, (cw - Inches(0.16)) / Inches(1), th / Inches(1), 12, 8)
        _absatz(rahmen, p["punkt"], groesse=groesse, farbe=TEXT, erster=True, abstand=0, schrift=thema.schrift, zeilenabstand=1.1)
    _flaeche(folie, x, grund, breite, Emu(19050), LINIE)


# ------------------------------------------------------------------ Gemeinsame Bausteine der weiteren Darstellungen (0.9.2)
def _freiform(folie, punkte: list[tuple[int, int]], farbe: RGBColor | None, *, linie: RGBColor | None = None, breite_pt: float = 1.0):
    """Gefülltes Polygon aus absoluten EMU-Punkten."""
    builder = folie.shapes.build_freeform(int(punkte[0][0]), int(punkte[0][1]), scale=1.0)
    builder.add_line_segments([(int(px), int(py)) for px, py in punkte[1:]], close=True)
    form = builder.convert_to_shape()
    if farbe is None:
        form.fill.background()
    else:
        form.fill.solid()
        form.fill.fore_color.rgb = farbe
    if linie is None:
        form.line.fill.background()
    else:
        form.line.color.rgb = linie
        form.line.width = Pt(breite_pt)
    form.shadow.inherit = False
    return form


def _etikett(folie, thema: Thema, text: str, x, y, breite, hoehe=Inches(0.3), *, mitte=False, rechts=False, farbe=None, anker=MSO_ANCHOR.TOP):
    """Kleine Beschriftung in Versalien (Achsen, Gruppen, Legenden)."""
    r = _textfeld(folie, x, y, breite, hoehe, anker=anker)
    _absatz(r, text.upper(), groesse=9, farbe=farbe or GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=mitte, rechts=rechts, sperrung=1)
    return r


def _punkttext(folie, thema: Thema, p: dict[str, Any], x, y, breite, hoehe, *, kurz_pt=12, von=12, bis=8, mitte=False,
               anker=MSO_ANCHOR.TOP, farbe=TEXT, kurzfarbe=None, nummer: int | None = None, ohne_kurz=False):
    """Schlagwort fett über dem Text, Schriftgröße nach Platz."""
    rahmen = _textfeld(folie, x, y, breite, hoehe, anker=anker)
    kurz = "" if ohne_kurz else (p.get("kurz") or "")
    if kurz and nummer is not None:
        kurz = f"{nummer}  {kurz}"
    if kurz:
        _absatz(rahmen, kurz, groesse=kurz_pt, farbe=kurzfarbe or thema.primaer, fett=True, erster=True, abstand=1, schrift=thema.schrift_titel, mitte=mitte)
    reserve = Inches(0.1) + (Inches(kurz_pt * 1.9 / 72) if kurz else 0)
    groesse = _passend(p["punkt"], thema.schrift, breite / Inches(1), max(0.2, (hoehe - reserve) / Inches(1)), von, bis)
    _absatz(rahmen, p["punkt"], groesse=groesse, farbe=farbe, erster=not kurz, abstand=0, schrift=thema.schrift, mitte=mitte, zeilenabstand=1.05)
    return rahmen


def _reihen(folie, thema: Thema, punkte, x, y, breite, hoehe, spalten: int, *, ab: int = 1, zeile_max=Inches(1.2), ohne_kurz=False):
    """Nummerierte Zeilen in mehreren Spalten (kompakte Legende neben oder unter einer Grafik)."""
    n = len(punkte)
    if not n:
        return
    spalten = max(1, min(spalten, n))
    je = math.ceil(n / spalten)
    luecke = Inches(0.3)
    sb = int((breite - luecke * (spalten - 1)) / spalten)
    zh = min(zeile_max, int(hoehe / je))
    for i, p in enumerate(punkte):
        spalte, zeile = divmod(i, je)
        zx, zy = x + spalte * (sb + luecke), y + zeile * zh
        _nummernkreis(folie, thema, zx, zy + Inches(0.03), Inches(0.32), str(ab + i), pt=9)
        _punkttext(folie, thema, p, zx + Inches(0.42), zy - Inches(0.03), sb - Inches(0.42), zh - Inches(0.04), kurz_pt=11, von=11, bis=8, ohne_kurz=ohne_kurz)


def _aufzaehlung(rahmen, thema: Thema, eintraege, groesse: int, *, nummern: dict[int, int] | None = None, farbe=TEXT):
    """Absätze „•  Schlagwort: Text“ (oder nummeriert) in einem Rahmen."""
    for j, p in enumerate(eintraege):
        absatz = rahmen.paragraphs[0] if j == 0 else rahmen.add_paragraph()
        absatz.space_after = Pt(4)
        absatz.line_spacing = 1.05
        kurz = p.get("kurz")
        lauf = absatz.add_run()
        lauf.text = ("•  " if nummern is None else f"{nummern[id(p)]}  ") + (f"{kurz}: " if kurz else "")
        lauf.font.size, lauf.font.bold, lauf.font.name = Pt(groesse), True, thema.schrift_titel
        lauf.font.color.rgb = thema.primaer
        lauf = absatz.add_run()
        lauf.text = p["punkt"]
        lauf.font.size, lauf.font.name = Pt(groesse), thema.schrift
        lauf.font.color.rgb = farbe


def _bogenband(folie, cx, cy, r_aussen, r_innen, von: float, bis: float, farbe: RGBColor):
    """Ringsegment zwischen zwei Radien, Winkel in Grad (0 = rechts, 90 = unten)."""
    return _freiform(folie, _bogen(cx, cy, r_aussen, von, bis, 24) + _bogen(cx, cy, r_innen, bis, von, 24), farbe)


def _zahnrad_gross(zaehne: int = 10) -> list[tuple[float, float]]:
    """Zahnrad mit flachen Zähnen auf dem 0..1000-Raster (für große Räder; das Piktogramm nutzt _zahnrad)."""
    punkte = []
    schritt = 2 * math.pi / zaehne
    for i in range(zaehne):
        a = i * schritt
        for w, r in ((a, 400), (a + schritt * 0.08, 500), (a + schritt * 0.42, 500), (a + schritt * 0.5, 400)):
            punkte.append((500 + r * math.cos(w), 500 + r * math.sin(w)))
    return punkte


def _sechseck(cx, cy, r) -> list[tuple[int, int]]:
    return [(cx + int(r * math.cos(math.radians(-90 + 60 * k))), cy + int(r * math.sin(math.radians(-90 + 60 * k)))) for k in range(6)]


# ------------------------------------------------------------------ Diagramme und Bewertung
def _wasserfall(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Beiträge (Gewicht) stapeln sich zu einem Gesamtwert; Legende rechts."""
    n = len(punkte)
    werte = [int(p.get("gewicht") or 1) for p in punkte]
    gesamt = sum(werte)
    db = int(breite * 0.56)
    luecke = Inches(0.14)
    sb = int((db - luecke * n) / (n + 1))
    oben = y + Inches(0.4)
    grund = y + hoehe - Inches(0.8)
    skala = (grund - oben) / gesamt
    laufend = 0
    for i, (p, w) in enumerate(zip(punkte, werte)):
        sx = x + i * (sb + luecke)
        bh = int(w * skala)
        unten = grund - int(laufend * skala)
        _flaeche(folie, sx, unten - bh, sb, bh, _mischen(thema.primaer, WEISS, 0.1 * i))
        r = _textfeld(folie, sx, unten - bh - Inches(0.32), sb, Inches(0.3), anker=MSO_ANCHOR.BOTTOM)
        _absatz(r, f"+{w}", groesse=11, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True)
        _linie(folie, sx + sb, unten - bh, sx + sb + luecke, unten - bh, HELLGRAU, 0.75)
        r = _textfeld(folie, sx - int(luecke / 2), grund + Inches(0.05), sb + luecke, Inches(0.7))
        label = f"{i + 1}  {p.get('kurz') or _kurz(p['punkt'], 18)}"
        groesse = _passend(label, thema.schrift, (sb + luecke) / Inches(1), 0.65, 10, 8)
        _absatz(r, label, groesse=groesse, farbe=TEXT, erster=True, abstand=0, schrift=thema.schrift, mitte=True, zeilenabstand=1.0)
        laufend += w
    sx = x + n * (sb + luecke)
    th = int(gesamt * skala)
    _flaeche(folie, sx, grund - th, sb, th, thema.akzent)
    r = _textfeld(folie, sx, grund - th - Inches(0.32), sb, Inches(0.3), anker=MSO_ANCHOR.BOTTOM)
    _absatz(r, str(gesamt), groesse=11, farbe=thema.akzent_text, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True)
    _etikett(folie, thema, "Total", sx, grund + Inches(0.05), sb, mitte=True)
    _flaeche(folie, x, grund, db, Emu(9525), LINIE)
    _legende(folie, thema, punkte, x + db + Inches(0.4), y, breite - db - Inches(0.4), hoehe)


def _gestapelt(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Je Gruppe ein 100-%-Balken, Segmente nach Gewicht; Legende rechts."""
    gruppen = _gruppen_von(punkte, 4)
    palette = _palette(thema)
    nummer = {id(p): i for i, p in enumerate(punkte)}
    db = int(breite * 0.56)
    lb = Inches(1.5)
    bb = db - lb
    ng = len(gruppen)
    zh = min(Inches(1.2), int((hoehe - Inches(0.4)) / ng))
    bh = min(Inches(0.62), zh - Inches(0.2))
    for g, (name, eintraege) in enumerate(gruppen.items()):
        zy = y + g * zh + int((zh - bh) / 2)
        _etikett(folie, thema, name, x, zy, lb - Inches(0.1), bh, farbe=thema.primaer, anker=MSO_ANCHOR.MIDDLE)
        summe = sum(int(p.get("gewicht") or 1) for p in eintraege)
        bx = x + lb
        for p in eintraege:
            w = int(p.get("gewicht") or 1)
            sb = int(bb * w / summe)
            i = nummer[id(p)]
            farbe = palette[i % len(palette)]
            segment = _flaeche(folie, bx, zy, max(Inches(0.05), sb - Emu(19050)), bh, farbe)
            label = f"{i + 1}" if sb < Inches(1.1) else f"{i + 1}  ·  {w / summe:.0%}"
            _form_text(segment, label, groesse=10, farbe=TEXT if _hell(farbe) else WEISS, schrift=thema.schrift, rand=Inches(0.02))
            bx += sb
    sy = y + ng * zh + Inches(0.05)
    _flaeche(folie, x + lb, sy, bb, Emu(9525), LINIE)
    for anteil in (0, 0.5, 1):
        _etikett(folie, thema, f"{anteil:.0%}", x + lb + int(bb * anteil) - Inches(0.4), sy + Inches(0.04), Inches(0.8), mitte=True, farbe=HELLGRAU)
    _legende(folie, thema, punkte, x + db + Inches(0.4), y, breite - db - Inches(0.4), hoehe)


def _blasen(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Bedeutung (Gewicht) gegen Aufwand, Blasengröße = Auswirkung."""
    seite = min(hoehe - Inches(0.5), Inches(4.4))
    mx, my = x + Inches(0.45), y + Inches(0.1)
    _flaeche(folie, mx, my, seite, seite, thema.karte)
    for k in (1, 2):
        _flaeche(folie, mx + int(seite * k / 3), my, Emu(9525), seite, WEISS)
    for k in range(1, 5):
        _flaeche(folie, mx, my + int(seite * k / 5), seite, Emu(9525), WEISS)
    _achsenkreuz(folie, thema, mx, my, seite, "EFFORT  low  →  high", "IMPORTANCE  low  →  high")
    palette = _palette(thema)
    reihenfolge = sorted(range(len(punkte)), key=lambda i: -int(punkte[i].get("auswirkung") or punkte[i].get("eintritt") or 2))
    for i in reihenfolge:  # große Blasen zuerst, kleine liegen darüber
        p = punkte[i]
        xr = ((p.get("aufwand") or 2) - 0.5) / 3
        yr = ((p.get("gewicht") or 3) - 0.5) / 5
        stufe = int(p.get("auswirkung") or p.get("eintritt") or 2)
        d = Inches(0.45 + 0.22 * stufe)
        cx = mx + int(seite * xr) - int(d / 2) + (i % 3 - 1) * Inches(0.14)
        cy = my + int(seite * (1 - yr)) - int(d / 2) + (i % 2) * Inches(0.1)
        farbe = palette[i % len(palette)]
        blase = _flaeche(folie, cx, cy, d, d, farbe, MSO_SHAPE.OVAL)
        blase.line.color.rgb = WEISS
        blase.line.width = Pt(1.5)
        _form_text(blase, str(i + 1), groesse=11, farbe=TEXT if _hell(farbe) else WEISS, schrift=thema.schrift, rand=0)
    lx = mx + seite + Inches(0.5)
    _legende(folie, thema, punkte, lx, y, x + breite - lx, hoehe - Inches(0.35))
    _etikett(folie, thema, "Bubble size = impact (1–3)", lx, y + hoehe - Inches(0.3), x + breite - lx, farbe=HELLGRAU)


def _zielscheibe(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Konzentrische Ringe: Gewicht 5 im Kern, 1 am Rand."""
    feld = Inches(5.4)
    cx, cy = x + int(feld / 2), y + int(hoehe / 2)
    R = int(min(feld, hoehe) / 2) - Inches(0.05)
    for anteil, ton, name in ((1.0, 0.9, "Supporting"), (0.66, 0.75, "Important"), (0.33, 0.55, "Core")):
        r = int(R * anteil)
        ring = _flaeche(folie, cx - r, cy - r, 2 * r, 2 * r, _mischen(thema.primaer, WEISS, ton), MSO_SHAPE.OVAL)
        ring.line.color.rgb = WEISS
        ring.line.width = Pt(1.5)
        _etikett(folie, thema, name, cx - Inches(0.8), cy - r + Inches(0.05), Inches(1.6), mitte=True, farbe=thema.primaer)
    d = Inches(0.4)
    ringe_belegung: dict[int, list[int]] = {}
    for i, p in enumerate(punkte):
        ringe_belegung.setdefault(int(p.get("gewicht") or 3), []).append(i)
    for g, indizes in ringe_belegung.items():
        abstand = {5: 0.16, 4: 0.3, 3: 0.52, 2: 0.72, 1: 0.88}.get(g, 0.5)
        for k, i in enumerate(indizes):  # je Ring gleichmäßig verteilt, Ringe gegeneinander versetzt
            a = math.radians(-90 + 25 * g + 360 * k / len(indizes))
            px = cx + int(R * abstand * math.cos(a)) - int(d / 2)
            py = cy + int(R * abstand * math.sin(a)) - int(d / 2)
            _nummernkreis(folie, thema, px, py, d, str(i + 1), pt=10)
    _legende(folie, thema, punkte, x + feld + Inches(0.3), y, breite - feld - Inches(0.3), hoehe)


def _tacho(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Halbkreis-Anzeige je Punkt: Erfüllungsgrad aus dem Gewicht."""
    n = len(punkte)
    spalten = {1: 1, 2: 2, 3: 3, 4: 4, 5: 3, 6: 3}.get(n, 3)
    zeilen = math.ceil(n / spalten)
    luecke = Inches(0.25)
    kb = int((breite - luecke * (spalten - 1)) / spalten)
    kh = int((hoehe - luecke * (zeilen - 1)) / zeilen)
    if zeilen == 1:
        kh = min(kh, Inches(2.8))
    R = min(Inches(0.95), int(kb * 0.28), int(kh * 0.36))
    for i, p in enumerate(punkte):
        zeile, spalte = divmod(i, spalten)
        kx, ky = x + spalte * (kb + luecke), y + zeile * (kh + luecke)
        _karte(folie, kx, ky, kb, kh, thema.karte)
        g = int(p.get("gewicht") or 3)
        cx, cy = kx + int(kb / 2), ky + Inches(0.3) + R
        _bogenband(folie, cx, cy, R, int(R * 0.62), 180, 360, LINIE)
        _bogenband(folie, cx, cy, R, int(R * 0.62), 180, 180 + 180 * g / 5, thema.primaer)
        r = _textfeld(folie, cx - R, cy - int(R * 0.6), 2 * R, int(R * 0.62), anker=MSO_ANCHOR.BOTTOM)
        _absatz(r, f"{g}/5", groesse=20, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel, mitte=True)
        ty = cy + Inches(0.15)
        _punkttext(folie, thema, p, kx + Inches(0.18), ty, kb - Inches(0.36), ky + kh - ty - Inches(0.1), kurz_pt=12, von=12, bis=8, mitte=True)


def _skala(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Schieberegler: Position des Gewichts auf einer Skala von 1 bis 5."""
    n = len(punkte)
    tb = Inches(4.8)
    sx0 = x + tb + Inches(0.5)
    sb = breite - tb - Inches(0.7)
    kopf = Inches(0.35)
    for k in range(5):
        _etikett(folie, thema, str(k + 1), sx0 + int(sb * k / 4) - Inches(0.3), y, Inches(0.6), mitte=True, farbe=HELLGRAU)
    _etikett(folie, thema, "low", sx0 - Inches(0.6), y, Inches(0.5), rechts=True, farbe=HELLGRAU)
    _etikett(folie, thema, "high", sx0 + sb + Inches(0.08), y, Inches(0.6), farbe=HELLGRAU)
    zh = min(Inches(1.0), int((hoehe - kopf) / n))
    for i, p in enumerate(punkte):
        zy = y + kopf + i * zh
        if i % 2 == 0:
            _flaeche(folie, x, zy, breite, zh - Inches(0.04), thema.karte)
        _punkttext(folie, thema, p, x + Inches(0.1), zy + Inches(0.04), tb - Inches(0.2), zh - Inches(0.1), kurz_pt=12, von=11, bis=8, nummer=i + 1)
        cy = zy + int(zh / 2)
        g = int(p.get("gewicht") or 3)
        _linie(folie, sx0, cy, sx0 + sb, cy, LINIE, 3)
        pos = sx0 + int(sb * (g - 1) / 4)
        if g > 1:
            _linie(folie, sx0, cy, pos, cy, thema.primaer, 3)
        d = Inches(0.3)
        _flaeche(folie, pos - int(d / 2), cy - int(d / 2), d, d, thema.akzent, MSO_SHAPE.OVAL)


STUFEN = {1: "low", 2: "medium", 3: "high"}


def _bewertung(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Scorecard: Zeilen je Punkt, farbige Zellen für Gewicht, Aufwand und Status."""
    n = len(punkte)
    mit_aufwand = any(p.get("aufwand") for p in punkte)
    mit_status = any(p.get("status") for p in punkte)
    spalten = [("#", Inches(0.5)), ("Topic", Inches(2.5)), ("Importance", Inches(1.25))]
    if mit_aufwand:
        spalten.append(("Effort", Inches(1.1)))
    if mit_status:
        spalten.append(("Status", Inches(1.2)))
    spalten.insert(2, ("Action", breite - sum(b for _, b in spalten)))
    kopf = Inches(0.42)
    zh = min(Inches(0.9), int((hoehe - kopf) / n))
    cx = x
    kopfschrift = TEXT if _hell(thema.primaer) else WEISS
    for name, b in spalten:
        zelle = _flaeche(folie, cx, y, b - Emu(9525), kopf, thema.primaer)
        _form_text(zelle, name.upper(), groesse=10, farbe=kopfschrift, schrift=thema.schrift, sperrung=1, rand=Inches(0.08))
        cx += b
    for i, p in enumerate(punkte):
        zy = y + kopf + i * zh
        cx = x
        grund = thema.karte if i % 2 == 0 else WEISS
        for name, b in spalten:
            _flaeche(folie, cx, zy, b - Emu(9525), zh - Emu(9525), grund)
            innen = Inches(0.06)
            if name == "#":
                r = _textfeld(folie, cx, zy, b, zh, anker=MSO_ANCHOR.MIDDLE)
                _absatz(r, f"{i + 1:02d}", groesse=12, farbe=thema.akzent_text, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel, mitte=True)
            elif name == "Topic":
                r = _textfeld(folie, cx + Inches(0.04), zy, b - Inches(0.1), zh, anker=MSO_ANCHOR.MIDDLE)
                kurz = p.get("kurz") or ""
                groesse = _passend(kurz, thema.schrift_titel, (b - Inches(0.1)) / Inches(1), zh / Inches(1), 12, 9, fett=True)
                _absatz(r, kurz, groesse=groesse, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
            elif name == "Action":
                _punkttext(folie, thema, p, cx + Inches(0.04), zy, b - Inches(0.12), zh, von=11, bis=8, anker=MSO_ANCHOR.MIDDLE, ohne_kurz=True)
            else:
                text, farbe = "", None
                if name == "Importance" and p.get("gewicht"):
                    g = int(p["gewicht"])
                    text, farbe = f"{g} / 5", _mischen(thema.primaer_hell, thema.primaer, (g - 1) / 4)
                elif name == "Effort" and p.get("aufwand"):
                    a = int(p["aufwand"])
                    text, farbe = STUFEN.get(a, ""), (RISIKO["niedrig"], RISIKO["mittel"], RISIKO["hoch"])[min(3, a) - 1]
                elif name == "Status" and p.get("status"):
                    ampel, text = AMPEL.get(p["status"], AMPEL[""])
                    farbe = _mischen(ampel, WEISS, 0.65)
                if farbe is not None:
                    zelle = _flaeche(folie, cx + innen, zy + innen, b - 2 * innen - Emu(9525), zh - 2 * innen, farbe, MSO_SHAPE.ROUNDED_RECTANGLE, rundung=0.15)
                    _form_text(zelle, text, groesse=10, farbe=TEXT if _hell(farbe) else WEISS, schrift=thema.schrift, rand=0)
            cx += b


# ------------------------------------------------------------------ Listen und Vergleich
def _kaestchen(folie, thema: Thema, status: str, x, y, d):
    """Kästchen einer Checkliste: grün = Haken, gelb = Strich, rot = Kreuz, sonst leer."""
    farbe, _ = AMPEL.get(status, AMPEL[""])
    if status == "gruen":
        _flaeche(folie, x, y, d, d, farbe, MSO_SHAPE.ROUNDED_RECTANGLE, rundung=0.2)
        _piktogramm(folie, thema, "check", x, y, d, farbe=WEISS)
        return
    kasten = _flaeche(folie, x, y, d, d, WEISS, MSO_SHAPE.ROUNDED_RECTANGLE, rundung=0.2)
    kasten.line.color.rgb = farbe if status else HELLGRAU
    kasten.line.width = Pt(1.5)
    if status == "gelb":
        _flaeche(folie, x + int(d * 0.25), y + int(d * 0.44), int(d * 0.5), int(d * 0.12), farbe)
    elif status == "rot":
        _linie(folie, x + int(d * 0.3), y + int(d * 0.3), x + int(d * 0.7), y + int(d * 0.7), farbe, 2)
        _linie(folie, x + int(d * 0.7), y + int(d * 0.3), x + int(d * 0.3), y + int(d * 0.7), farbe, 2)


def _checkliste(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Kästchen je Punkt: erledigt (grün), in Arbeit (gelb), blockiert (rot), offen."""
    n = len(punkte)
    spalten = 2 if n > 5 else 1
    je = math.ceil(n / spalten)
    luecke = Inches(0.5)
    sb = int((breite - luecke * (spalten - 1)) / spalten)
    kopf = Inches(0.4)
    zh = min(Inches(1.0), int((hoehe - kopf) / je))
    lx = x
    for schluessel, name in (("gruen", "Done"), ("gelb", "In progress"), ("rot", "Blocked"), ("", "Open")):
        _kaestchen(folie, thema, schluessel, lx, y + Inches(0.04), Inches(0.24))
        _etikett(folie, thema, name, lx + Inches(0.3), y, Inches(1.3), Inches(0.32), anker=MSO_ANCHOR.MIDDLE)
        lx += Inches(1.45)
    for i, p in enumerate(punkte):
        spalte, zeile = divmod(i, je)
        zx, zy = x + spalte * (sb + luecke), y + kopf + zeile * zh
        _flaeche(folie, zx, zy + zh - Inches(0.06), sb, Emu(9525), LINIE)
        _kaestchen(folie, thema, p.get("status") or "", zx + Inches(0.1), zy + Inches(0.1), Inches(0.42))
        _punkttext(folie, thema, p, zx + Inches(0.7), zy + Inches(0.02), sb - Inches(0.8), zh - Inches(0.12), kurz_pt=12, von=11, bis=8)


def _waage(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Für und Wider: zwei Schalen an einem Balken; die schwerere Seite (Summe der Gewichte) ist hervorgehoben."""
    gruppen = list(_gruppen_von(punkte, 2).items())
    if len(gruppen) < 2:
        halb = math.ceil(len(punkte) / 2)
        gruppen = [("Pro", punkte[:halb]), ("Contra", punkte[halb:])]
    cx = x + int(breite / 2)
    boden = y + hoehe - Inches(0.15)
    balken_y = y + Inches(0.45)
    _freiform(folie, [(cx, boden - Inches(1.3)), (cx + Inches(0.5), boden), (cx - Inches(0.5), boden)], _mischen(thema.primaer, WEISS, 0.2))
    _flaeche(folie, cx - Inches(0.05), balken_y, Inches(0.1), boden - Inches(1.3) - balken_y, thema.primaer)
    arm = int(breite * 0.36)
    _flaeche(folie, cx - arm, balken_y - Inches(0.04), 2 * arm, Inches(0.08), thema.primaer)
    _flaeche(folie, cx - Inches(0.16), balken_y - Inches(0.16), Inches(0.32), Inches(0.32), thema.akzent, MSO_SHAPE.OVAL)
    gewichte = [sum(int(p.get("gewicht") or 1) for p in e) for _, e in gruppen]
    sb = int(breite * 0.42)
    sy = balken_y + Inches(0.7)
    sh = min(boden - sy - Inches(0.1), Inches(2.9))
    for s, (name, eintraege) in enumerate(gruppen):
        px = x if s == 0 else x + breite - sb
        aufhaengung = cx - arm if s == 0 else cx + arm
        _linie(folie, aufhaengung, balken_y, px + Inches(0.4), sy, HELLGRAU, 1)
        _linie(folie, aufhaengung, balken_y, px + sb - Inches(0.4), sy, HELLGRAU, 1)
        schwerer = gewichte[s] == max(gewichte) and gewichte.count(max(gewichte)) == 1
        band = thema.primaer if schwerer else _mischen(thema.primaer, WEISS, 0.35)
        kopf = _flaeche(folie, px, sy, sb, Inches(0.46), band)
        _form_text(kopf, f"{name.upper()}   ·   {gewichte[s]}", groesse=11, farbe=TEXT if _hell(band) else WEISS, schrift=thema.schrift, sperrung=1)
        _flaeche(folie, px, sy + Inches(0.46), sb, sh - Inches(0.46), thema.karte)
        if not eintraege:
            continue
        tb, th = sb - Inches(0.4), sh - Inches(0.7)
        text = "\n".join(f"•  {p.get('kurz') or ''}: {p['punkt']}" for p in eintraege)
        groesse = _passend(text, thema.schrift, tb / Inches(1), th / Inches(1), 12, 8, abstand=1.35)
        rahmen = _textfeld(folie, px + Inches(0.2), sy + Inches(0.58), tb, th)
        _aufzaehlung(rahmen, thema, eintraege, groesse)


GEMEINSAM = ("both", "shared", "all", "overlap", "common", "beide", "gemeinsam")


def _venn(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Zwei oder drei sich überschneidende Kreise; gemeinsame Punkte (gruppe both/shared/all) in der Mitte."""
    gemeinsam = [p for p in punkte if (p.get("gruppe") or "").lower() in GEMEINSAM]
    rest = [p for p in punkte if not any(p is g for g in gemeinsam)]
    gruppen = list(_gruppen_von(rest, 3).items())
    if len(gruppen) < 2:
        halb = math.ceil(len(rest) / 2)
        gruppen = [("A", rest[:halb]), ("B", rest[halb:])]
    nummer = {id(p): i + 1 for i, p in enumerate(punkte)}
    feld = Inches(6.6)
    cx, cy = x + int(feld / 2), y + int(hoehe / 2)
    R = Inches(1.75)
    farben = [thema.primaer, thema.akzent_text, GRAU]
    if len(gruppen) == 2:
        zentren = [(cx - int(R * 0.6), cy), (cx + int(R * 0.6), cy)]
    else:
        zentren = [(cx - int(R * 0.62), cy + int(R * 0.38)), (cx + int(R * 0.62), cy + int(R * 0.38)), (cx, cy - int(R * 0.62))]
    schwer = (sum(zx for zx, _ in zentren) // len(zentren), sum(zy for _, zy in zentren) // len(zentren))
    for k, (zx, zy) in enumerate(zentren):
        kreis = _flaeche(folie, zx - R, zy - R, 2 * R, 2 * R, WEISS, MSO_SHAPE.OVAL)
        kreis.fill.background()
        kreis.line.color.rgb = farben[k]
        kreis.line.width = Pt(2.5)
    for k, ((name, eintraege), (zx, zy)) in enumerate(zip(gruppen, zentren)):
        dx, dy = zx - schwer[0], zy - schwer[1]
        laenge = math.hypot(dx, dy) or 1
        tx, ty = zx + int(R * 0.38 * dx / laenge), zy + int(R * 0.38 * dy / laenge)
        tb, th = int(R * 1.1), int(R * 1.1)
        rahmen = _textfeld(folie, tx - int(tb / 2), ty - int(th / 2), tb, th, anker=MSO_ANCHOR.MIDDLE)
        _absatz(rahmen, name.upper(), groesse=9, farbe=farben[k], fett=True, erster=True, abstand=2, schrift=thema.schrift, mitte=True, sperrung=1)
        for p in eintraege:
            _absatz(rahmen, f"{nummer[id(p)]}  {p.get('kurz') or _kurz(p['punkt'], 22)}", groesse=10, farbe=TEXT, abstand=1, schrift=thema.schrift, mitte=True)
    if gemeinsam:
        tb, th = int(R * 0.9), int(R * 0.9)
        rahmen = _textfeld(folie, schwer[0] - int(tb / 2), schwer[1] - int(th / 2), tb, th, anker=MSO_ANCHOR.MIDDLE)
        for j, p in enumerate(gemeinsam):
            _absatz(rahmen, f"{nummer[id(p)]}  {p.get('kurz') or _kurz(p['punkt'], 22)}", groesse=10, farbe=thema.primaer, fett=True, erster=(j == 0), abstand=1, schrift=thema.schrift, mitte=True)
    _legende(folie, thema, punkte, x + feld + Inches(0.2), y, breite - feld - Inches(0.2), hoehe)


SICHTBAR = ("visible", "above", "symptom", "surface", "seen", "sichtbar")


def _eisberg(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Sichtbares über der Wasserlinie, Ursachen darunter."""
    oben: list[dict[str, Any]] = []
    unten: list[dict[str, Any]] = []
    if any(p.get("gruppe") for p in punkte):
        for p in punkte:
            (oben if (p.get("gruppe") or "").lower().startswith(SICHTBAR) else unten).append(p)
    if not oben or not unten:
        k = max(1, round(len(punkte) / 3))
        oben, unten = punkte[:k], punkte[k:]
    gb = Inches(4.0)
    wasser = y + int(hoehe * 0.42)
    _flaeche(folie, x, wasser, breite, y + hoehe - wasser, _mischen(thema.primaer, WEISS, 0.9))
    cx = x + int(gb / 2)
    i_ = Inches
    _freiform(folie, [(cx - i_(1.2), wasser), (cx - i_(0.7), y + i_(0.9)), (cx - i_(0.1), y + i_(0.15)), (cx + i_(0.4), y + i_(0.7)),
                      (cx + i_(0.9), y + i_(0.5)), (cx + i_(1.3), wasser)], KARTE, linie=HELLGRAU)
    _freiform(folie, [(cx - i_(1.2), wasser), (cx + i_(1.3), wasser), (cx + i_(1.9), wasser + i_(0.9)), (cx + i_(0.8), y + hoehe - i_(0.2)),
                      (cx - i_(0.8), y + hoehe - i_(0.35)), (cx - i_(1.8), wasser + i_(1.0))], _mischen(thema.primaer, WEISS, 0.55))
    _flaeche(folie, x, wasser, breite, Emu(19050), thema.primaer)
    tx, tb = x + gb + Inches(0.2), breite - gb - Inches(0.2)
    _etikett(folie, thema, "Visible", tx, y, tb, farbe=thema.primaer)
    _reihen(folie, thema, oben, tx, y + Inches(0.32), tb, wasser - y - Inches(0.4), 2 if len(oben) > 2 else 1)
    _etikett(folie, thema, "Beneath the surface", tx, wasser + Inches(0.1), tb, farbe=thema.primaer)
    _reihen(folie, thema, unten, tx, wasser + Inches(0.45), tb, y + hoehe - wasser - Inches(0.5), 2 if len(unten) > 3 else 1, ab=len(oben) + 1)


# ------------------------------------------------------------------ Struktur
def _fischgraete(folie, thema: Thema, punkte, x, y, breite, hoehe, titel: str = "Effect"):
    """Ursachen je Kategorie (Gräten) führen zur Wirkung (Kopf); Legende unten."""
    if any(p.get("gruppe") for p in punkte):
        gruppen = list(_gruppen_von(punkte, 6).items())
    else:
        gruppen = [(p.get("kurz") or _kurz(p["punkt"], 20), [p]) for p in punkte[:6]]
    nummer = {id(p): i + 1 for i, p in enumerate(punkte)}
    kopf_b, kopf_h = Inches(1.9), Inches(1.0)
    fh = int(hoehe * 0.6)
    ry = y + int(fh / 2)
    kopf = _karte(folie, x + breite - kopf_b, ry - int(kopf_h / 2), kopf_b, kopf_h, thema.primaer)
    _form_text(kopf, titel, groesse=12, farbe=TEXT if _hell(thema.primaer) else WEISS, schrift=thema.schrift_titel, rand=Inches(0.1))
    _linie(folie, x + Inches(0.25), ry, x + breite - kopf_b, ry, thema.primaer, 2.5)
    _freiform(folie, [(x, ry - Inches(0.3)), (x + Inches(0.3), ry), (x, ry + Inches(0.3))], thema.primaer)
    ng = len(gruppen)
    je_seite = math.ceil(ng / 2)
    laenge = breite - kopf_b - Inches(0.7)
    kb = min(Inches(2.6), int(laenge / je_seite) - Inches(0.25))
    kh = int(fh / 2) - Inches(0.35)
    for j, (name, eintraege) in enumerate(gruppen):
        seite, k = j % 2, j // 2
        anzahl = je_seite if seite == 0 else ng - je_seite
        slot = int(laenge / anzahl)
        kx = x + Inches(0.5) + k * slot + int((slot - kb) / 2)
        ky = y if seite == 0 else ry + Inches(0.35)
        _karte(folie, kx, ky, kb, kh, thema.karte)
        _etikett(folie, thema, name, kx + Inches(0.12), ky + Inches(0.08), kb - Inches(0.24), farbe=thema.primaer)
        rahmen = _textfeld(folie, kx + Inches(0.12), ky + Inches(0.36), kb - Inches(0.24), kh - Inches(0.42))
        zeilen = [f"{nummer[id(p)]}  {p.get('kurz') or _kurz(p['punkt'], 26)}" for p in eintraege]
        groesse = _passend("\n".join(zeilen), thema.schrift, (kb - Inches(0.24)) / Inches(1), (kh - Inches(0.42)) / Inches(1), 11, 8, abstand=1.3)
        for z, zeile in enumerate(zeilen):
            _absatz(rahmen, zeile, groesse=groesse, farbe=TEXT, erster=(z == 0), abstand=2, schrift=thema.schrift)
        ax = kx + int(kb / 2)
        ay = ky + kh if seite == 0 else ky
        _linie(folie, ax, ay, ax + Inches(0.5), ry, thema.primaer, 1.5)
    _reihen(folie, thema, punkte, x, y + fh + Inches(0.15), breite, hoehe - fh - Inches(0.15), 3 if len(punkte) > 4 else 2, zeile_max=Inches(0.8), ohne_kurz=True)


def _baum(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Ein Ganzes (erster Punkt) und seine Teile darunter."""
    wurzel, kinder = punkte[0], punkte[1:]
    wb, wh = Inches(4.2), Inches(1.3)
    wx = x + int((breite - wb) / 2)
    _karte(folie, wx, y, wb, wh, thema.primaer)
    schrift = TEXT if _hell(thema.primaer) else WEISS
    icon = Inches(0.5)
    _piktogramm(folie, thema, _icon_von(wurzel, 0), wx + Inches(0.2), y + int((wh - icon) / 2), icon, farbe=schrift)
    _punkttext(folie, thema, wurzel, wx + Inches(0.85), y + Inches(0.08), wb - Inches(1.0), wh - Inches(0.16), kurz_pt=13, von=11, bis=8,
               anker=MSO_ANCHOR.MIDDLE, farbe=schrift, kurzfarbe=schrift)
    n = len(kinder)
    if not n:
        return
    bus_y = y + wh + Inches(0.35)
    ky = y + wh + Inches(0.7)
    kh = hoehe - wh - Inches(0.7)
    luecke = Inches(0.2)
    kb = int((breite - luecke * (n - 1)) / n)
    _linie(folie, wx + int(wb / 2), y + wh, wx + int(wb / 2), bus_y, LINIE, 1.5)
    if n > 1:
        _linie(folie, x + int(kb / 2), bus_y, x + (n - 1) * (kb + luecke) + int(kb / 2), bus_y, LINIE, 1.5)
    for i, p in enumerate(kinder):
        kx = x + i * (kb + luecke)
        _linie(folie, kx + int(kb / 2), bus_y, kx + int(kb / 2), ky, LINIE, 1.5)
        _karte(folie, kx, ky, kb, kh, thema.karte)
        _piktogramm(folie, thema, _icon_von(p, i + 1), kx + Inches(0.18), ky + Inches(0.18), Inches(0.5), grund=WEISS)
        _punkttext(folie, thema, p, kx + Inches(0.15), ky + Inches(0.8), kb - Inches(0.3), kh - Inches(0.9), kurz_pt=12, von=12, bis=8)


def _netzwerk(folie, thema: Thema, punkte, x, y, breite, hoehe, titel: str = "Hub"):
    """Nabe in der Mitte, Knoten im Kreis; Strichstärke der Verbindung nach Gewicht."""
    n = len(punkte)
    feld = Inches(6.2)
    cx, cy = x + int(feld / 2), y + int(hoehe / 2)
    r = int(min(hoehe, feld) / 2) - Inches(0.8)
    nabe, knoten = Inches(1.5), Inches(0.52)
    for i, p in enumerate(punkte):
        a = math.radians(-90 + 360 * i / n)
        nx, ny = cx + int(r * math.cos(a)), cy + int(r * math.sin(a))
        _linie(folie, cx, cy, nx, ny, _mischen(thema.primaer, WEISS, 0.3), 0.75 + 0.6 * int(p.get("gewicht") or 3))
    hub = _flaeche(folie, cx - int(nabe / 2), cy - int(nabe / 2), nabe, nabe, thema.primaer, MSO_SHAPE.OVAL)
    groesse = _passend(titel, thema.schrift_titel, nabe / Inches(1) * 0.75, nabe / Inches(1) * 0.7, 13, 9, fett=True)
    _form_text(hub, titel, groesse=groesse, farbe=TEXT if _hell(thema.primaer) else WEISS, schrift=thema.schrift_titel, rand=Inches(0.12))
    for i, p in enumerate(punkte):
        a = math.radians(-90 + 360 * i / n)
        nx, ny = cx + int(r * math.cos(a)), cy + int(r * math.sin(a))
        node = _flaeche(folie, nx - int(knoten / 2), ny - int(knoten / 2), knoten, knoten, WEISS, MSO_SHAPE.OVAL)
        node.line.color.rgb = thema.primaer
        node.line.width = Pt(2)
        _form_text(node, str(i + 1), groesse=12, farbe=thema.primaer, schrift=thema.schrift, rand=0)
        lb, lh = Inches(1.7), Inches(0.5)
        ax = cx + int((r + Inches(1.0)) * math.cos(a))
        ay = cy + int((r + Inches(0.62)) * math.sin(a))
        t = _textfeld(folie, ax - int(lb / 2), ay - int(lh / 2), lb, lh, anker=MSO_ANCHOR.MIDDLE)
        _absatz(t, p.get("kurz") or _kurz(p["punkt"], 20), groesse=10, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel, mitte=True)
    _legende(folie, thema, punkte, x + feld + Inches(0.3), y, breite - feld - Inches(0.3), hoehe)


def _schichten(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Ebenen eines Aufbaus: erster Punkt oben, Fundament unten; Text rechts."""
    n = len(punkte)
    lb = Inches(3.8)
    luecke = Inches(0.08)
    sh = int((hoehe - luecke * (n - 1)) / n)
    for i, p in enumerate(punkte):
        sy = y + i * (sh + luecke)
        fuellung = _mischen(thema.primaer, WEISS, 0.62 * i / max(1, n - 1))
        einzug = int(Inches(0.35) * (n - 1 - i) / max(1, n - 1))
        block = _flaeche(folie, x + einzug, sy, lb - 2 * einzug, sh, fuellung)
        _form_text(block, f"{i + 1}  {p.get('kurz') or _kurz(p['punkt'], 26)}", groesse=12, farbe=TEXT if _hell(fuellung) else WEISS,
                   schrift=thema.schrift_titel, rand=Inches(0.15))
        _linie(folie, x + lb + Inches(0.05), sy + int(sh / 2), x + lb + Inches(0.35), sy + int(sh / 2), LINIE, 1.5)
        _punkttext(folie, thema, p, x + lb + Inches(0.45), sy, breite - lb - Inches(0.45), sh, von=13, bis=8, anker=MSO_ANCHOR.MIDDLE, ohne_kurz=True)
        if i < n - 1:
            _flaeche(folie, x + lb + Inches(0.45), sy + sh + int(luecke / 2), breite - lb - Inches(0.45), Emu(9525), LINIE)


def _bruecke(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Von heute (erster Punkt) über Pfeiler (mittlere Punkte) zum Ziel (letzter Punkt)."""
    heute, ziel, pfeiler = punkte[0], punkte[-1], punkte[1:-1] if len(punkte) > 1 else []
    kb, kh = Inches(2.7), hoehe - Inches(0.2)
    ky = y + Inches(0.1)
    zielschrift = TEXT if _hell(thema.primaer) else WEISS
    for s, (p, name, grund, schrift) in enumerate(((heute, "Today", thema.karte, TEXT), (ziel, "Target", thema.primaer, zielschrift))):
        px = x if s == 0 else x + breite - kb
        _karte(folie, px, ky, kb, kh, grund)
        _etikett(folie, thema, name, px + Inches(0.2), ky + Inches(0.15), kb - Inches(0.4), farbe=schrift if s else thema.akzent_text)
        _punkttext(folie, thema, p, px + Inches(0.2), ky + Inches(0.5), kb - Inches(0.4), kh - Inches(0.6), kurz_pt=13, von=12, bis=8,
                   farbe=schrift, kurzfarbe=schrift if s else None)
    deck_y = ky + Inches(0.7)
    dx0, dx1 = x + kb + Inches(0.15), x + breite - kb - Inches(0.15)
    pfeil = _flaeche(folie, dx0, deck_y, dx1 - dx0, Inches(0.55), _mischen(thema.primaer, WEISS, 0.25), MSO_SHAPE.PENTAGON)
    if pfeil.adjustments:
        pfeil.adjustments[0] = 0.3
    m = len(pfeiler)
    pb = dx1 - dx0 - Inches(0.9)
    luecke = Inches(0.25)
    pw = int((pb - luecke * (m - 1)) / max(1, m))
    py, ph = deck_y + Inches(0.55), Inches(1.0)
    boden = py + ph
    for i, p in enumerate(pfeiler):
        px = dx0 + Inches(0.3) + i * (pw + luecke)
        saeule = _flaeche(folie, px, py, pw, ph, thema.primaer)
        _form_text(saeule, f"{i + 1}  {p.get('kurz') or _kurz(p['punkt'], 22)}", groesse=11, farbe=zielschrift, schrift=thema.schrift_titel, rand=Inches(0.08))
        _punkttext(folie, thema, p, px - Inches(0.05), boden + Inches(0.15), pw + Inches(0.1), y + hoehe - boden - Inches(0.2), von=11, bis=8, ohne_kurz=True, mitte=True)
    _flaeche(folie, dx0, boden, dx1 - dx0, Emu(19050), LINIE)


def _wabe(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Sechsecke als Bausteine, bei sieben als Blüte um eine Mitte; Legende rechts."""
    n = len(punkte)
    feld = Inches(6.6)
    cx0, cy0 = x + int(feld / 2), y + int(hoehe / 2)
    if n == 7:
        r = Inches(0.86)
        d = int(r * math.sqrt(3) * 1.03)
        zentren = [(cx0, cy0)] + [(cx0 + int(d * math.cos(math.radians(60 * k))), cy0 + int(d * math.sin(math.radians(60 * k)))) for k in range(6)]
    else:
        r = Inches(0.95)
        d = int(r * math.sqrt(3) * 1.03)
        if n <= 3:
            zentren = [(cx0 + int(d * (k - (n - 1) / 2)), cy0) for k in range(n)]
        else:
            oben, unten = math.ceil(n / 2), n - math.ceil(n / 2)
            zy = int(r * 1.5 * 1.03)
            versatz = int(d / 2) if oben == unten else 0
            zentren = [(cx0 + int(d * (k - (oben - 1) / 2)) - int(versatz / 2), cy0 - int(zy / 2)) for k in range(oben)]
            zentren += [(cx0 + int(d * (k - (unten - 1) / 2)) + int(versatz / 2), cy0 + int(zy / 2)) for k in range(unten)]
    for i, (p, (cx, cy)) in enumerate(zip(punkte, zentren)):
        fuellung = _mischen(thema.primaer, WEISS, (0.0, 0.18, 0.36, 0.5)[i % 4])
        _freiform(folie, _sechseck(cx, cy, r), fuellung, linie=WEISS, breite_pt=2)
        schrift = TEXT if _hell(fuellung) else WEISS
        icon = Inches(0.5)
        _piktogramm(folie, thema, _icon_von(p, i), cx - int(icon / 2), cy - int(r * 0.62), icon, farbe=schrift)
        rahmen = _textfeld(folie, cx - int(r * 0.72), cy - int(r * 0.05), int(r * 1.44), int(r * 0.7))
        label = f"{i + 1}  {p.get('kurz') or _kurz(p['punkt'], 20)}"
        groesse = _passend(label, thema.schrift, r * 1.44 / Inches(1), r * 0.66 / Inches(1), 11, 8, fett=True)
        _absatz(rahmen, label, groesse=groesse, farbe=schrift, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True)
    _legende(folie, thema, punkte, x + feld + Inches(0.2), y, breite - feld - Inches(0.2), hoehe)


def _zahnraeder(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Ineinandergreifende Zahnräder (3 bis 5); Legende rechts."""
    n = len(punkte)
    feld = Inches(7.0)
    radien = [Inches(0.85 if i % 2 == 0 else 0.62) for i in range(n)]
    gesamt = int(sum(2 * r for r in radien) * 0.9)
    cx = x + int((feld - gesamt) / 2) + radien[0]
    cy0 = y + int(hoehe / 2)
    for i, (p, r) in enumerate(zip(punkte, radien)):
        if i:
            cx += int((radien[i - 1] + r) * 0.9)
        cy = cy0 + (-1 if i % 2 == 0 else 1) * Inches(0.55)
        zahn = _zahnrad_gross(12 if i % 2 == 0 else 9)
        _freiform(folie, [(cx + int((px - 500) / 500 * r), cy + int((py - 500) / 500 * r)) for px, py in zahn], _mischen(thema.primaer, WEISS, 0.15 * i))
        nabe = int(r * 0.7)
        kreis = _flaeche(folie, cx - int(nabe / 2), cy - int(nabe / 2), nabe, nabe, WEISS, MSO_SHAPE.OVAL)
        _form_text(kreis, str(i + 1), groesse=14, farbe=thema.primaer, schrift=thema.schrift_titel, rand=0)
        oben = i % 2 == 0
        ly = cy - r - Inches(0.5) if oben else cy + r + Inches(0.05)
        rahmen = _textfeld(folie, cx - Inches(1.0), ly, Inches(2.0), Inches(0.45), anker=MSO_ANCHOR.BOTTOM if oben else MSO_ANCHOR.TOP)
        _absatz(rahmen, p.get("kurz") or _kurz(p["punkt"], 20), groesse=11, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel, mitte=True)
    _legende(folie, thema, punkte, x + feld + Inches(0.2), y, breite - feld - Inches(0.2), hoehe)


# ------------------------------------------------------------------ Ablauf und Zeit
def _zeitachse(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Ereignisse als Karten abwechselnd über und unter einer Linie."""
    n = len(punkte)
    linie_y = y + int(hoehe / 2)
    _linie(folie, x, linie_y, x + breite - Inches(0.3), linie_y, thema.primaer, 2.5)
    spitze = _flaeche(folie, x + breite - Inches(0.32), linie_y - Inches(0.16), Inches(0.32), Inches(0.32), thema.primaer, MSO_SHAPE.CHEVRON)
    if spitze.adjustments:
        spitze.adjustments[0] = 0.5
    sb = int((breite - Inches(0.4)) / n)
    kb = min(Inches(3.4), 2 * sb - Inches(0.3)) if n > 1 else Inches(4.0)
    kh = int(hoehe / 2) - Inches(0.5)
    d = Inches(0.46)
    for i, p in enumerate(punkte):
        cx = x + sb * i + int(sb / 2)
        oben = i % 2 == 0
        ky = linie_y - Inches(0.4) - kh if oben else linie_y + Inches(0.4)
        kx = min(max(x, cx - int(kb / 2)), x + breite - kb)
        _linie(folie, cx, linie_y - int(d / 2) if oben else linie_y + int(d / 2), cx, ky + kh if oben else ky, LINIE, 1.5)
        _karte(folie, kx, ky, kb, kh, thema.karte)
        _nummernkreis(folie, thema, cx - int(d / 2), linie_y - int(d / 2), d, str(i + 1), pt=12)
        _punkttext(folie, thema, p, kx + Inches(0.15), ky + Inches(0.1), kb - Inches(0.3), kh - Inches(0.2), kurz_pt=12, von=12, bis=8)


def _fahrplan(folie, thema: Thema, punkte, x, y, breite, hoehe):
    """Roadmap: Bahnen je Gruppe, Wochen als Spalten, Balken mit Schlagwort; Legende unten."""
    gruppen = _gruppen_von(punkte, 4)
    nummer = {id(p): i + 1 for i, p in enumerate(punkte)}
    fenster: dict[int, tuple[int, int]] = {}
    for p in punkte:
        s, e = int(p.get("start") or 0), int(p.get("ende") or 0)
        s = s or e or 1
        fenster[id(p)] = (s, max(e, s))
    w0 = min(s for s, _ in fenster.values())
    w1 = max(e for _, e in fenster.values())
    wochen = w1 - w0 + 1
    lb = Inches(1.7)
    gx, gb = x + lb, breite - lb
    kopf = Inches(0.38)
    bahnen_h = int(hoehe * 0.6) - kopf
    ng = len(gruppen)
    zh = int(bahnen_h / ng)
    sw = int(gb / wochen)
    palette = _palette(thema)
    for g in range(ng):
        if g % 2:
            _flaeche(folie, gx, y + kopf + g * zh, wochen * sw, zh, _mischen(thema.karte, WEISS, 0.5))
    for w in range(wochen):
        _etikett(folie, thema, f"W{w0 + w}", gx + w * sw, y, sw, kopf, mitte=True, anker=MSO_ANCHOR.MIDDLE)
        _flaeche(folie, gx + w * sw, y + kopf, Emu(9525), zh * ng, LINIE)
    _flaeche(folie, gx + wochen * sw, y + kopf, Emu(9525), zh * ng, LINIE)
    _flaeche(folie, x, y + kopf, breite, Emu(9525), LINIE)
    for g, (name, eintraege) in enumerate(gruppen.items()):
        zy = y + kopf + g * zh
        bandfarbe = _mischen(thema.primaer, WEISS, 0.15 * g)
        band = _flaeche(folie, x, zy + Inches(0.04), lb - Inches(0.1), zh - Inches(0.08), bandfarbe)
        _form_text(band, name, groesse=11, farbe=TEXT if _hell(bandfarbe) else WEISS, schrift=thema.schrift_titel, rand=Inches(0.1))
        belegt: list[list[tuple[int, int]]] = []
        reihen: list[int] = []
        for p in eintraege:
            s, e = fenster[id(p)]
            for k, reihe in enumerate(belegt):
                if all(e < a or s > b for a, b in reihe):
                    reihe.append((s, e))
                    reihen.append(k)
                    break
            else:
                belegt.append([(s, e)])
                reihen.append(len(belegt) - 1)
        rh = int((zh - Inches(0.12)) / len(belegt))
        bh = min(Inches(0.42), rh - Inches(0.06))
        for p, k in zip(eintraege, reihen):
            s, e = fenster[id(p)]
            bx = gx + (s - w0) * sw + Inches(0.04)
            bb = (e - s + 1) * sw - Inches(0.08)
            by = zy + Inches(0.06) + k * rh + int((rh - bh) / 2)
            i = nummer[id(p)]
            farbe = palette[(i - 1) % len(palette)]
            balken = _flaeche(folie, bx, by, bb, bh, farbe, MSO_SHAPE.ROUNDED_RECTANGLE, rundung=0.5)
            label = f"{i}  {p.get('kurz') or ''}" if bb > Inches(1.2) else str(i)
            _form_text(balken, label, groesse=9, farbe=TEXT if _hell(farbe) else WEISS, schrift=thema.schrift, rand=Inches(0.08))
    ly = y + kopf + bahnen_h + Inches(0.2)
    _reihen(folie, thema, punkte, x, ly, breite, y + hoehe - ly, 3 if len(punkte) > 4 else 2, ohne_kurz=True)


def _storyline(folie, thema: Thema, abschnitte: list[dict[str, Any]], erste_nr: int, x, y, breite, hoehe):
    n = len(abschnitte)
    if not n:
        return
    luecke = Inches(0.08)
    sb = int((breite - luecke * (n - 1)) / n)
    for i, a in enumerate(abschnitte):
        form = MSO_SHAPE.PENTAGON if i == 0 else MSO_SHAPE.CHEVRON
        fuellung = _mischen(thema.primaer, WEISS, 0.1 * i)
        pfeil = _flaeche(folie, x + i * (sb + luecke), y, sb, hoehe, fuellung, form)
        if pfeil.adjustments:
            pfeil.adjustments[0] = 0.22
        text = f"{erste_nr + i:02d}  {a['titel']}"
        groesse = _passend(text, thema.schrift, (sb - Inches(0.6)) / Inches(1), hoehe / Inches(1), 12, 8, fett=True, abstand=1.1)
        _form_text(pfeil, text, groesse=groesse, farbe=TEXT if _hell(fuellung) else WEISS, schrift=thema.schrift, rand=Inches(0.3))


def _zeitstrahl(folie, thema: Thema, schritte: list[dict[str, str]], x, y, breite, hoehe):
    n = len(schritte)
    d = Inches(0.46)
    x0, x1 = x + Inches(0.9), x + breite - Inches(0.9)
    mitte_y = y + int(hoehe * 0.45)
    _linie(folie, x0, mitte_y, x1, mitte_y, LINIE, 2.5)
    abstand = int((x1 - x0) / (n - 1)) if n > 1 else 0
    spalte = min(Inches(3.2), abstand if n > 1 else Inches(6))
    wechsel = n >= 5
    for i, s in enumerate(schritte):
        cx = x0 + i * abstand if n > 1 else int((x0 + x1) / 2)
        _nummernkreis(folie, thema, cx - int(d / 2), mitte_y - int(d / 2), d, str(i + 1), pt=12)
        oben = wechsel and i % 2 == 1
        zeit = _textfeld(folie, cx - int(spalte / 2), mitte_y - int(d / 2) - Inches(0.42) if not oben else mitte_y + int(d / 2) + Inches(0.06), spalte, Inches(0.36))
        _absatz(zeit, s.get("zeitpunkt", ""), groesse=11, farbe=thema.akzent_text, fett=True, erster=True, abstand=0, schrift=thema.schrift, mitte=True)
        th = Inches(1.5)
        ty = mitte_y + int(d / 2) + Inches(0.12) if not oben else mitte_y - int(d / 2) - Inches(0.48) - th
        groesse = _passend(s["schritt"], thema.schrift, spalte / Inches(1), th / Inches(1), 13, 9)
        rahmen = _textfeld(folie, cx - int(spalte / 2), ty, spalte, th, anker=MSO_ANCHOR.BOTTOM if oben else MSO_ANCHOR.TOP)
        _absatz(rahmen, s["schritt"], groesse=groesse, farbe=TEXT, erster=True, abstand=0, schrift=thema.schrift, mitte=True, zeilenabstand=1.1)


# ------------------------------------------------------------------ Folien aus dem Plan
def _kernbotschaften(plan: dict[str, Any]) -> list[dict[str, str]]:
    kb = [k for k in plan.get("kernbotschaften") or [] if k.get("text")]
    if kb:
        return kb[:3]
    saetze = [s.strip() for s in re.split(r"(?<=[.!?])\s+", plan.get("zusammenfassung", "")) if s.strip()]
    return [{"titel": f"Key message {i + 1}", "text": s} for i, s in enumerate(saetze[:3])]


def _executive_summary(praes, thema: Thema, plan: dict[str, Any], nr: int, erste_abschnitt_nr: int, fuss: str):
    folie = _kopf(praes, thema, "What matters most", f"{nr:02d} · Executive summary")
    botschaften = _kernbotschaften(plan)
    breite = praes.slide_width - 2 * RAND
    if botschaften:
        n = len(botschaften)
        luecke = Inches(0.3)
        kb = int((breite - luecke * (n - 1)) / n)
        kh = Inches(3.15)
        for i, k in enumerate(botschaften):
            kx = RAND + i * (kb + luecke)
            _karte(folie, kx, INHALT_OBEN, kb, kh, thema.karte)
            _flaeche(folie, kx, INHALT_OBEN + Inches(0.3), Inches(0.07), Inches(0.5), thema.akzent)
            r = _textfeld(folie, kx + Inches(0.22), INHALT_OBEN + Inches(0.2), kb - Inches(0.44), Inches(0.7), anker=MSO_ANCHOR.MIDDLE)
            _absatz(r, f"{i + 1:02d}", groesse=28, farbe=thema.akzent_text, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
            r = _textfeld(folie, kx + Inches(0.22), INHALT_OBEN + Inches(0.95), kb - Inches(0.44), kh - Inches(1.1))
            titel = k.get("titel", "")
            if titel:
                _absatz(r, titel, groesse=16, farbe=thema.primaer, fett=True, erster=True, abstand=6, schrift=thema.schrift_titel, zeilenabstand=1.05)
            groesse = _passend(k["text"], thema.schrift, (kb - Inches(0.44)) / Inches(1), (kh - Inches(1.1) - (Inches(0.6) if titel else 0)) / Inches(1), 14, 10)
            _absatz(r, k["text"], groesse=groesse, farbe=TEXT, erster=not titel, abstand=0, schrift=thema.schrift, zeilenabstand=1.15)
    abschnitte = plan.get("abschnitte", [])
    if abschnitte:
        r = _textfeld(folie, RAND - Inches(0.08), INHALT_OBEN + Inches(3.4), Inches(6), Inches(0.3))
        _absatz(r, "STORYLINE", groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, sperrung=1)
        _storyline(folie, thema, abschnitte, erste_abschnitt_nr, RAND, INHALT_OBEN + Inches(3.75), breite, Inches(0.95))
    folie.notes_slide.notes_text_frame.text = text_ohne_marken(plan.get("ausarbeitung", ""))
    _fuss(praes, folie, thema, fuss)
    return folie


def _fokus(praes, thema: Thema, plan: dict[str, Any], nr: int, erste_abschnitt_nr: int, fuss: str) -> bool:
    """Balkendiagramm der mittleren Gewichte je Abschnitt plus die drei wichtigsten Punkte. Entfällt ohne Gewichte."""
    abschnitte = plan.get("abschnitte", [])
    alle = [p for a in abschnitte for p in a.get("punkte", [])]
    if not any(p.get("gewicht") for p in alle):
        return False
    folie = _kopf(praes, thema, "Where to focus: importance by workstream", f"{nr:02d} · Executive summary")
    kategorien, werte = [], []
    for i, a in enumerate(abschnitte):
        gewichte = [p["gewicht"] for p in a.get("punkte", []) if p.get("gewicht")]
        kategorien.append(_kurz(f"{erste_abschnitt_nr + i:02d}  {a['titel']}", 34))
        werte.append(round(sum(gewichte) / len(gewichte), 1) if gewichte else 0.0)
    db = Inches(7.0)
    _balkendiagramm(folie, thema, RAND, INHALT_OBEN, db, INHALT_HOEHE - Inches(0.3), kategorien, werte, format="0.0")
    r = _textfeld(folie, RAND, INHALT_OBEN + INHALT_HOEHE - Inches(0.3), db, Inches(0.3))
    _absatz(r, "AVERAGE IMPORTANCE OF THE ACTIONS, 1 (LOW) – 5 (CRITICAL)", groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0,
            schrift=thema.schrift, mitte=True, sperrung=1)
    oben = sorted((p for p in alle if p.get("gewicht")), key=lambda p: -p["gewicht"])[:3]
    lx = RAND + db + Inches(0.5)
    lb = praes.slide_width - RAND - lx
    r = _textfeld(folie, lx - Inches(0.08), INHALT_OBEN - Inches(0.05), lb, Inches(0.3))
    _absatz(r, "TOP PRIORITIES", groesse=9, farbe=GRAU, fett=True, erster=True, abstand=0, schrift=thema.schrift, sperrung=1)
    _legende(folie, thema, oben, lx, INHALT_OBEN + Inches(0.4), lb, INHALT_HOEHE - Inches(0.6), nummern=False)
    _fuss(praes, folie, thema, fuss)
    return True


# Welche Darstellung stattdessen, wenn die gewünschte im Deck schon vorkam (Abwechslung)
ERSATZ = {
    "kacheln": ("nummern", "wabe", "tabelle", "treiber"), "nummern": ("tabelle", "treiber", "kacheln"), "tabelle": ("bewertung", "nummern", "kacheln"),
    "schritte_h": ("zeitachse", "schritte_v", "bruecke", "stufen"), "schritte_v": ("schritte_h", "zeitachse", "kreislauf", "meilensteine"),
    "prioritaeten": ("skala", "kreis", "saeulen", "radar", "tabelle"), "kreis": ("gestapelt", "radar", "saeulen", "prioritaeten"),
    "radar": ("zielscheibe", "kreis", "saeulen", "prioritaeten"), "saeulen": ("wasserfall", "prioritaeten", "kreis", "radar"),
    "kennzahlen": ("tacho", "tabelle", "nummern"), "zeitplan": ("fahrplan", "meilensteine", "schritte_v", "tabelle"),
    "trichter": ("pyramide", "stufen", "schritte_v"), "pyramide": ("schichten", "trichter", "stufen"), "stufen": ("schichten", "schritte_h", "pyramide"),
    "risiken": ("matrix", "blasen", "tabelle", "ampel"), "matrix": ("blasen", "risiken", "tabelle"), "kreislauf": ("zahnraeder", "schritte_v", "treiber"),
    "spalten": ("waage", "tabelle", "swot", "kacheln"), "swot": ("spalten", "kacheln"), "ampel": ("checkliste", "bewertung", "tabelle", "nummern"),
    "meilensteine": ("zeitachse", "zeitplan", "fahrplan", "schritte_h"), "treiber": ("netzwerk", "baum", "kacheln", "nummern"),
    # seit 0.9.2
    "wasserfall": ("saeulen", "gestapelt", "prioritaeten"), "gestapelt": ("kreis", "wasserfall", "spalten"),
    "blasen": ("matrix", "risiken", "zielscheibe"), "zielscheibe": ("radar", "blasen", "kreis"),
    "tacho": ("skala", "kennzahlen", "saeulen"), "skala": ("tacho", "prioritaeten", "bewertung"),
    "bewertung": ("tabelle", "skala", "ampel"), "checkliste": ("ampel", "bewertung", "nummern"),
    "waage": ("spalten", "venn", "swot"), "venn": ("waage", "spalten", "wabe"), "eisberg": ("baum", "fischgraete", "kacheln"),
    "fischgraete": ("baum", "treiber", "netzwerk"), "baum": ("treiber", "netzwerk", "schichten"), "netzwerk": ("treiber", "kreislauf", "wabe"),
    "schichten": ("pyramide", "stufen", "baum"), "bruecke": ("schritte_h", "zeitachse", "stufen"), "wabe": ("kacheln", "netzwerk", "zahnraeder"),
    "zahnraeder": ("wabe", "kreislauf", "netzwerk"), "zeitachse": ("meilensteine", "schritte_h", "bruecke"),
    "fahrplan": ("zeitplan", "meilensteine", "zeitachse"),
}
BAUSTEINE = {
    "kacheln": _kacheln, "nummern": _nummern, "tabelle": _tabelle, "kennzahlen": _kennzahlen, "zeitplan": _zeitplan,
    "trichter": _trichter, "risiken": _risiken, "prioritaeten": _prioritaeten, "kreis": _kreis, "radar": _radar,
    "schritte_h": lambda *a: _schritte(*a, senkrecht=False), "schritte_v": lambda *a: _schritte(*a, senkrecht=True),
    "saeulen": _saeulen, "matrix": _matrix, "pyramide": _pyramide, "kreislauf": _kreislauf, "spalten": _spalten,
    "swot": _swot, "ampel": _ampel, "meilensteine": _meilensteine, "treiber": _treiber, "stufen": _stufen,
    "wasserfall": _wasserfall, "gestapelt": _gestapelt, "blasen": _blasen, "zielscheibe": _zielscheibe, "tacho": _tacho,
    "skala": _skala, "bewertung": _bewertung, "checkliste": _checkliste, "waage": _waage, "venn": _venn, "eisberg": _eisberg,
    "fischgraete": _fischgraete, "baum": _baum, "netzwerk": _netzwerk, "schichten": _schichten, "bruecke": _bruecke,
    "wabe": _wabe, "zahnraeder": _zahnraeder, "zeitachse": _zeitachse, "fahrplan": _fahrplan,
}
MIT_TITEL = ("treiber", "fischgraete", "netzwerk")  # Bausteine, die den Abschnittstitel als Ziel, Wirkung oder Nabe zeigen
PUNKTE_JE_FOLIE = {
    "kacheln": 6, "nummern": 8, "tabelle": 8, "kennzahlen": 8, "zeitplan": 8, "trichter": 6, "risiken": 8,
    "prioritaeten": 8, "kreis": 8, "radar": 8, "schritte_h": 6, "schritte_v": 6, "saeulen": 8, "matrix": 8,
    "pyramide": 6, "kreislauf": 8, "spalten": 9, "swot": 12, "ampel": 10, "meilensteine": 8, "treiber": 6, "stufen": 6,
    "wasserfall": 7, "gestapelt": 8, "blasen": 8, "zielscheibe": 8, "tacho": 6, "skala": 8, "bewertung": 8, "checkliste": 10,
    "waage": 8, "venn": 9, "eisberg": 8, "fischgraete": 10, "baum": 7, "netzwerk": 8, "schichten": 6, "bruecke": 6,
    "wabe": 7, "zahnraeder": 5, "zeitachse": 6, "fahrplan": 8,
}
# Rückfall, wenn die Daten für die gewünschte Darstellung nicht reichen
RUECKFALL = {
    "zeitplan": "schritte_v", "meilensteine": "schritte_v", "trichter": "schritte_v", "pyramide": "schritte_v",
    "stufen": "schritte_v", "kreislauf": "schritte_v", "treiber": "kacheln", "kennzahlen": "kacheln",
    "matrix": "nummern", "risiken": "nummern", "spalten": "kacheln", "swot": "kacheln", "ampel": "nummern",
    "prioritaeten": "nummern", "saeulen": "nummern", "kreis": "nummern", "radar": "nummern",
    "wasserfall": "nummern", "gestapelt": "nummern", "blasen": "nummern", "zielscheibe": "nummern", "tacho": "nummern",
    "skala": "nummern", "bewertung": "nummern", "checkliste": "nummern", "waage": "kacheln", "venn": "kacheln",
    "eisberg": "kacheln", "fischgraete": "kacheln", "baum": "kacheln", "netzwerk": "kacheln", "wabe": "kacheln",
    "zahnraeder": "kacheln", "schichten": "schritte_v", "bruecke": "schritte_v", "zeitachse": "schritte_v", "fahrplan": "schritte_v",
}


def _gruppenzahl(punkte: list[dict[str, Any]]) -> int:
    return len({p.get("gruppe") for p in punkte if p.get("gruppe")})


def _passt(darstellung: str, punkte: list[dict[str, Any]]) -> bool:
    """Hat der Abschnitt die Daten für diese Darstellung?"""
    n = len(punkte)
    mit_gewicht = any(p.get("gewicht") for p in punkte)
    if darstellung == "kennzahlen":
        return sum(bool(p.get("wert")) for p in punkte) * 2 >= n
    if darstellung in ("zeitplan", "fahrplan"):
        return any(p.get("ende") or p.get("start") for p in punkte)
    if darstellung == "meilensteine":
        return any(p.get("start") for p in punkte)
    if darstellung == "risiken":
        return any(p.get("eintritt") and p.get("auswirkung") for p in punkte)
    if darstellung in ("matrix", "blasen"):
        return any(p.get("aufwand") for p in punkte)
    if darstellung in ("kreis", "radar", "zielscheibe", "gestapelt"):
        return n >= 3 and mit_gewicht
    if darstellung in ("prioritaeten", "saeulen", "skala"):
        return n >= 2 and len({p.get("gewicht") for p in punkte}) > 1
    if darstellung == "wasserfall":
        return 2 <= n <= 7 and mit_gewicht
    if darstellung == "tacho":
        return n <= 6 and mit_gewicht
    if darstellung == "bewertung":
        return mit_gewicht
    if darstellung in ("trichter", "pyramide", "stufen", "treiber", "schichten"):
        return 2 <= n <= 6
    if darstellung in ("kreislauf", "netzwerk"):
        return 3 <= n <= 8
    if darstellung in ("baum", "wabe"):
        return 3 <= n <= 7
    if darstellung in ("bruecke", "zeitachse"):
        return 3 <= n <= 6
    if darstellung == "zahnraeder":
        return 3 <= n <= 5
    if darstellung == "fischgraete":
        return n >= 3
    if darstellung == "eisberg":
        return n >= 2
    if darstellung == "schritte_h":
        return n <= 6
    if darstellung in ("spalten", "waage", "venn"):
        return _gruppenzahl(punkte) >= 2
    if darstellung == "swot":
        return len({_swot_feld(p) for p in punkte if _swot_feld(p) is not None}) >= 2
    if darstellung in ("ampel", "checkliste"):
        return any(p.get("status") for p in punkte)
    return True


def darstellung_waehlen(abschnitt: dict[str, Any], benutzt: dict[str, int]) -> str:
    """Gewünschte Darstellung, sofern die Daten reichen; eine Wiederholung weicht auf eine noch ungenutzte aus."""
    punkte = abschnitt.get("punkte", [])
    gewuenscht = abschnitt.get("darstellung") or "kacheln"
    if gewuenscht == "schritte":
        gewuenscht = "schritte_h" if len(punkte) <= 4 else "schritte_v"
    if gewuenscht not in BAUSTEINE or not _passt(gewuenscht, punkte):
        gewuenscht = RUECKFALL.get(gewuenscht, "kacheln")
        if not _passt(gewuenscht, punkte):
            gewuenscht = "kacheln"
    if benutzt.get(gewuenscht):
        for ersatz in ERSATZ.get(gewuenscht, ()):
            if not benutzt.get(ersatz) and _passt(ersatz, punkte):
                gewuenscht = ersatz
                break
    benutzt[gewuenscht] = benutzt.get(gewuenscht, 0) + 1
    return gewuenscht


def _abschnittsfolien(praes, thema: Thema, abschnitt: dict[str, Any], nr: int, fuss: str, darstellung: str):
    punkte = abschnitt.get("punkte", [])
    je = PUNKTE_JE_FOLIE[darstellung]
    teile = [punkte[i:i + je] for i in range(0, len(punkte), je)] or [[]]
    titel = abschnitt.get("kernaussage") or abschnitt.get("titel", "")
    breite = praes.slide_width - 2 * RAND
    for t, teil in enumerate(teile, start=1):
        kicker = f"{nr:02d} · {abschnitt.get('titel', '')}" + (f" ({t}/{len(teile)})" if len(teile) > 1 else "")
        folie = _kopf(praes, thema, titel, kicker)
        if darstellung in MIT_TITEL and teil:
            BAUSTEINE[darstellung](folie, thema, teil, RAND, INHALT_OBEN, breite, INHALT_HOEHE, titel=abschnitt.get("titel", "") or "Goal")
        elif teil:
            BAUSTEINE[darstellung](folie, thema, teil, RAND, INHALT_OBEN, breite, INHALT_HOEHE)
        _fuss(praes, folie, thema, fuss)


def _kachelfolien(praes, thema: Thema, titel: str, kicker: str, punkte: list[dict[str, Any]], fuss: str, notizen: str = "", baustein=_kacheln):
    breite = praes.slide_width - 2 * RAND
    teile = [punkte[i:i + 6] for i in range(0, len(punkte), 6)]
    for t, teil in enumerate(teile, start=1):
        folie = _kopf(praes, thema, titel, kicker + (f" ({t}/{len(teile)})" if len(teile) > 1 else ""))
        baustein(folie, thema, teil, RAND, INHALT_OBEN, breite, INHALT_HOEHE)
        if notizen and t == 1:
            folie.notes_slide.notes_text_frame.text = notizen
        _fuss(praes, folie, thema, fuss)


def briefing_pptx(
    situation: str, plan: dict[str, Any], lessons: dict[str, Any], erstellt_am: str = "",
    marke: Marke | None = None, logo: bytes | None = None,
) -> bytes:
    """lessons bleibt für die Signatur erhalten; die Folien weisen keine Quellen aus. marke/logo: Erscheinungsbild."""
    thema = Thema.aus(marke, logo)
    praes = Presentation()
    praes.slide_width, praes.slide_height = BREITE, HOEHE
    titel = plan.get("titel") or _kurz(situation, 60)  # alte Pläne ohne Decktitel: Situation gekürzt
    untertitel = plan.get("untertitel") or ""
    fuss = _kurz(titel, 70)
    datum = erstellt_am[:10] if erstellt_am else datetime.now().strftime("%Y-%m-%d")

    abschnitte = plan.get("abschnitte", [])
    alle = [p for a in abschnitte for p in a.get("punkte", [])]
    besonderheiten = [b for b in plan.get("besonderheiten", []) if b.get("punkt")]
    luecken = plan.get("luecken") or []
    schritte = [s for s in plan.get("naechste_schritte") or [] if s.get("schritt")]
    mit_fokus = any(p.get("gewicht") for p in alle)

    # Kapitel = Agenda; Planabschnitte bekommen Kapitelfolien
    kapitel: list[dict[str, str]] = [{"titel": "Executive summary", "sub": "Key messages, storyline" + (", where to focus" if mit_fokus else "")}]
    erste_abschnitt_nr = len(kapitel) + 1
    for a in abschnitte:
        kapitel.append({"titel": a.get("titel", ""), "sub": a.get("kernaussage", "")})
    if besonderheiten:
        kapitel.append({"titel": "Watch-outs", "sub": "Where practice differs from the textbook"})
    if luecken:
        kapitel.append({"titel": "Further topics", "sub": "Aspects to cover beyond the plan"})
    if schritte:
        kapitel.append({"titel": "Next steps", "sub": "Way forward and timing"})

    _titelfolie(praes, thema, titel, untertitel, datum)
    _agenda(praes, thema, kapitel, fuss)
    _executive_summary(praes, thema, plan, 1, erste_abschnitt_nr, fuss)
    if mit_fokus:
        _fokus(praes, thema, plan, 1, erste_abschnitt_nr, fuss)
    nr = erste_abschnitt_nr
    benutzt: dict[str, int] = {}
    for a in abschnitte:
        _kapitelfolie(praes, thema, nr, a.get("titel", ""), a.get("kernaussage", ""), kapitel)
        _abschnittsfolien(praes, thema, a, nr, fuss, darstellung_waehlen(a, benutzt))
        nr += 1
    if besonderheiten:
        _kachelfolien(praes, thema, "Watch-outs: where practice differs from the textbook", f"{nr:02d} · Watch-outs",
                      [{"punkt": b["punkt"], "icon": "warning"} for b in besonderheiten], fuss, baustein=_nummern)
        nr += 1
    if luecken:
        notizen = "\n\n".join(
            f"{l.get('titel', '')}\n{l.get('wissen', '')}" + (f"\nApply: {l['anwendung']}" if l.get("anwendung") else "") for l in luecken
        )
        _kachelfolien(praes, thema, "Further topics to cover beyond the plan", f"{nr:02d} · Further topics",
                      [{"punkt": l.get("kern", ""), "kurz": l.get("titel", ""), "icon": "idea"} for l in luecken], fuss, notizen)
        nr += 1
    if schritte:
        folie = _kopf(praes, thema, "Next steps", f"{nr:02d} · Way forward")
        _zeitstrahl(folie, thema, schritte, RAND, INHALT_OBEN, praes.slide_width - 2 * RAND, INHALT_HOEHE)
        _fuss(praes, folie, thema, fuss)

    puffer = io.BytesIO()
    praes.save(puffer)
    return puffer.getvalue()


def dateiname(situation: str) -> str:
    kurz = re.sub(r"[^\w\- ]", "", situation, flags=re.UNICODE).strip()[:50].strip() or "Briefing"
    return f"Briefing {kurz}.pptx"
