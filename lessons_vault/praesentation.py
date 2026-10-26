"""PowerPoint aus einem Briefing-Plan im Beratungsstil (lokal erzeugt, kein weiterer Claude-Aufruf).

Aufbau: Titel, Agenda, Executive Summary (drei Kernbotschaften + Storyline), "Where to focus" (Balkendiagramm
der Gewichte je Abschnitt), je Planabschnitt eine Kapitelfolie und eine Inhaltsfolie in der vom Plan gewählten
Darstellung (Kacheln mit Piktogrammen, Prozessschritte, Risikomatrix oder Prioritäten-Diagramm), Watch-outs,
weitere Themen, nächste Schritte als Zeitstrahl. Der zusammenhängende Text steht in den Notizen.

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
PUNKTE_JE_FOLIE = {"kacheln": 6, "schritte": 6, "risiken": 8, "prioritaeten": 8}
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
def _titelfolie(praes, thema: Thema, situation: str, datum: str):
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
        rahmen = _textfeld(folie, Inches(0.9), Inches(2.4), textbreite, Inches(3.6))
        groesse = _passend(situation, thema.schrift_titel, textbreite / Inches(1), 2.4, 34, 22, fett=True, abstand=1.1)
        _absatz(rahmen, "BRIEFING", groesse=11, farbe=thema.akzent_text, fett=True, erster=True, abstand=14, schrift=s, sperrung=2)
        _absatz(rahmen, situation, groesse=groesse, farbe=thema.titel_schrift, fett=True, abstand=14, schrift=thema.schrift_titel, zeilenabstand=1.05)
        _absatz(rahmen, datum, groesse=14, farbe=thema.titel_nebenschrift, schrift=s)
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
    rahmen = _textfeld(folie, Inches(0.9), Inches(2.4), textbreite, Inches(3.4))
    groesse = _passend(situation, thema.schrift_titel, textbreite / Inches(1), 2.2, 36, 24, fett=True, abstand=1.1)
    _absatz(rahmen, "BRIEFING", groesse=14, farbe=thema.akzent, fett=True, erster=True, abstand=10, schrift=s, sperrung=2)
    _absatz(rahmen, situation, groesse=groesse, farbe=thema.titel_schrift, fett=True, abstand=16, schrift=thema.schrift_titel, zeilenabstand=1.05)
    if unterzeile:
        _absatz(rahmen, unterzeile, groesse=16, farbe=thema.titel_nebenschrift, schrift=s)
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
        _form_text(pille, _kurz(f"{i + 1:02d}  {k['titel']}", 26), groesse=9, farbe=farbe, schrift=thema.schrift, fett=aktiv)
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
            kopf = _textfeld(folie, kx + Inches(0.22) + icon + Inches(0.06), ky + Inches(0.22), textbreite - icon - Inches(0.06), icon, anker=MSO_ANCHOR.MIDDLE)
            _absatz(kopf, kurz, groesse=14, farbe=thema.primaer, fett=True, erster=True, abstand=0, schrift=thema.schrift_titel)
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


def _schritte(folie, thema: Thema, punkte: list[dict[str, Any]], x, y, breite, hoehe):
    n = len(punkte)
    if n <= 4:
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


def _balkendiagramm(folie, thema: Thema, x, y, breite, hoehe, kategorien: list[str], werte: list[float], *, maximum=5, format="0"):
    daten = CategoryChartData()
    daten.categories = kategorien
    daten.add_series("Importance", werte)
    grafik = folie.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, x, y, breite, hoehe, daten)
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
    kat.reverse_order = True
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


def _abschnittsfolien(praes, thema: Thema, abschnitt: dict[str, Any], nr: int, fuss: str):
    darstellung = abschnitt.get("darstellung") or "kacheln"
    if darstellung not in PUNKTE_JE_FOLIE:
        darstellung = "kacheln"
    punkte = abschnitt.get("punkte", [])
    je = PUNKTE_JE_FOLIE[darstellung]
    teile = [punkte[i:i + je] for i in range(0, len(punkte), je)] or [[]]
    titel = abschnitt.get("kernaussage") or abschnitt.get("titel", "")
    breite = praes.slide_width - 2 * RAND
    for t, teil in enumerate(teile, start=1):
        kicker = f"{nr:02d} · {abschnitt.get('titel', '')}" + (f" ({t}/{len(teile)})" if len(teile) > 1 else "")
        folie = _kopf(praes, thema, titel, kicker)
        if not teil:
            pass
        elif darstellung == "schritte":
            _schritte(folie, thema, teil, RAND, INHALT_OBEN, breite, INHALT_HOEHE)
        elif darstellung == "risiken":
            _risiken(folie, thema, teil, RAND, INHALT_OBEN, breite, INHALT_HOEHE)
        elif darstellung == "prioritaeten":
            _prioritaeten(folie, thema, teil, RAND, INHALT_OBEN, breite, INHALT_HOEHE)
        else:
            _kacheln(folie, thema, teil, RAND, INHALT_OBEN, breite, INHALT_HOEHE)
        _fuss(praes, folie, thema, fuss)


def _kachelfolien(praes, thema: Thema, titel: str, kicker: str, punkte: list[dict[str, Any]], fuss: str, notizen: str = ""):
    breite = praes.slide_width - 2 * RAND
    teile = [punkte[i:i + 6] for i in range(0, len(punkte), 6)]
    for t, teil in enumerate(teile, start=1):
        folie = _kopf(praes, thema, titel, kicker + (f" ({t}/{len(teile)})" if len(teile) > 1 else ""))
        _kacheln(folie, thema, teil, RAND, INHALT_OBEN, breite, INHALT_HOEHE)
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
    fuss = f"Briefing  ·  {_kurz(situation, 70)}"
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

    _titelfolie(praes, thema, situation, datum)
    _agenda(praes, thema, kapitel, fuss)
    _executive_summary(praes, thema, plan, 1, erste_abschnitt_nr, fuss)
    if mit_fokus:
        _fokus(praes, thema, plan, 1, erste_abschnitt_nr, fuss)
    nr = erste_abschnitt_nr
    for a in abschnitte:
        _kapitelfolie(praes, thema, nr, a.get("titel", ""), a.get("kernaussage", ""), kapitel)
        _abschnittsfolien(praes, thema, a, nr, fuss)
        nr += 1
    if besonderheiten:
        _kachelfolien(praes, thema, "Watch-outs: where practice differs from the textbook", f"{nr:02d} · Watch-outs",
                      [{"punkt": b["punkt"], "icon": "warning"} for b in besonderheiten], fuss)
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
