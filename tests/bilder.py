"""Testbilder: gerenderte Folie mit GPS-Metadaten."""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FOLIE_ZEILEN = [
    "Lessons Learned Welle 3",
    "- Cutover-Plan zu spät mit dem Lager abgestimmt",
    "- Schichtleiter nicht eingeplant, Inventur verzögert",
    "- Datenmigration doppelt so lange wie geschätzt",
]


def folie_jpeg(zeilen=FOLIE_ZEILEN, breite=1400, hoehe=800, gps=True, drehen=False) -> bytes:
    img = Image.new("RGB", (breite, hoehe), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT), 40) if FONT.exists() else ImageFont.load_default()
    for i, zeile in enumerate(zeilen):
        draw.text((60, 60 + i * 90), zeile, fill="black", font=font)
    if drehen:
        img = img.rotate(90, expand=True)
    exif = Image.Exif()
    exif[0x010F] = "Testkamera"  # Make
    if gps:
        exif[0x8825] = {1: "N", 2: (51.0, 15.0, 0.0), 3: "E", 4: (7.0, 10.0, 0.0)}  # GPS-IFD
    if drehen:
        exif[0x0112] = 8  # Orientation: 90° gegen den Uhrzeigersinn anzeigen
    puffer = io.BytesIO()
    img.save(puffer, "JPEG", exif=exif.tobytes())
    return puffer.getvalue()
