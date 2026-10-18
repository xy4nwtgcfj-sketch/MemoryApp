import io

import pytest
from PIL import Image

from lessons_vault.images import BildFehler, Bildspeicher, Texterkennung, text_bereinigen

from .bilder import folie_jpeg

ocr = Texterkennung()
braucht_ocr = pytest.mark.skipif(not ocr.verfuegbar, reason="Tesseract mit Deutsch nicht installiert")


def test_metadaten_entfernt_und_groessen(tmp_path):
    roh = folie_jpeg()
    with Image.open(io.BytesIO(roh)) as img:
        assert img.getexif().get(0x8825) is not None  # Testbild hat GPS
    speicher = Bildspeicher(tmp_path)
    bild = speicher.speichern(roh)
    for variante in ("voll", "vorschau"):
        with Image.open(speicher.pfad(bild.id, variante)) as img:
            assert len(img.getexif()) == 0
    with Image.open(speicher.pfad(bild.id, "vorschau")) as img:
        assert max(img.size) == 400
    assert speicher.vorhandene_ids() == {bild.id}
    block = speicher.fuer_claude(bild.id)
    assert block["type"] == "image" and block["source"]["media_type"] == "image/jpeg"
    speicher.loeschen(bild.id)
    assert speicher.vorhandene_ids() == set()


def test_ausrichtung_angewendet(tmp_path):
    speicher = Bildspeicher(tmp_path)
    bild = speicher.speichern(folie_jpeg(drehen=True))
    # Gedrehtes Hochformat mit Orientation-Tag wird zurück ins Querformat gedreht
    assert bild.breite > bild.hoehe


def test_ungueltig(tmp_path):
    speicher = Bildspeicher(tmp_path)
    with pytest.raises(BildFehler):
        speicher.speichern(b"kein bild")
    with pytest.raises(BildFehler):
        speicher.pfad("../../etc/passwd")


@braucht_ocr
def test_texterkennung_echte_folie(tmp_path):
    speicher = Bildspeicher(tmp_path)
    bild = speicher.speichern(folie_jpeg())
    text = ocr.erkennen(speicher.pfad(bild.id))
    assert "Lessons Learned" in text
    assert "Schichtleiter" in text and "Datenmigration" in text


def test_ohne_tesseract():
    t = Texterkennung(befehl="/gibt/es/nicht")
    assert not t.verfuegbar and t.status()[1]
    with pytest.raises(BildFehler):
        t.erkennen(__file__)  # type: ignore[arg-type]


def test_text_bereinigen():
    assert text_bereinigen("•\nHallo   Welt \n-\nZeile") == "Hallo Welt\nZeile"
    assert text_bereinigen("Hallo   Welt\n\n\n\nZeile") == "Hallo Welt\n\nZeile"


def test_nur_erlaubte_formate(tmp_path):
    from PIL import Image as PILImage
    puffer = io.BytesIO()
    PILImage.new("RGB", (50, 50), "white").save(puffer, "TIFF")
    with pytest.raises(BildFehler):
        Bildspeicher(tmp_path).speichern(puffer.getvalue())


def test_zu_viele_pixel(tmp_path):
    from PIL import Image as PILImage
    puffer = io.BytesIO()
    PILImage.new("1", (6000, 6000)).save(puffer, "PNG")  # 36 MP, klein komprimiert
    with pytest.raises(BildFehler):
        Bildspeicher(tmp_path).speichern(puffer.getvalue())


def test_fremde_dateien_im_ordner(tmp_path):
    speicher = Bildspeicher(tmp_path)
    (tmp_path / "urlaub_voll.jpg").write_bytes(b"x")
    assert speicher.vorhandene_ids() == set()
