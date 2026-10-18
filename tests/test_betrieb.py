import os

import pytest

from lessons_vault import db
from lessons_vault.config import _load_dotenv
from lessons_vault.einzelinstanz import Instanzsperre, LaeuftBereits
from lessons_vault.repository import Repository
from lessons_vault.sicherung import pruefen, sichern

from .bilder import folie_jpeg
from .conftest import beispiel


def test_sicherung_mit_fotos_und_wiederherstellung(tmp_path):
    pfad = tmp_path / "data" / "lessons.db"
    conn = db.connect(pfad)
    Repository(conn).anlegen(beispiel())
    bilder = tmp_path / "data" / "bilder"
    bilder.mkdir()
    (bilder / "abc_voll.jpg").write_bytes(folie_jpeg())
    ziel = tmp_path / "ziel"
    letzte = sichern(pfad, bilder, ziel)
    assert pruefen(letzte) == {"integritaet": "ok", "version": len(db.MIGRATIONS), "lessons": 1}
    assert (ziel / "bilder" / "abc_voll.jpg").exists()
    # Wiederherstellung: Sicherung als Datenbank öffnen
    wieder = Repository(db.connect(letzte))
    assert wieder.alle()[0].titel == beispiel().titel


def test_rotation_behaelt_neueste(tmp_path):
    pfad = tmp_path / "x.db"
    db.connect(pfad).close()
    ziel = tmp_path / "ziel"
    ziel.mkdir()
    for name in ["lessons-20260101-000000.db", "lessons-20260102-000000.db", "lessons-20260103-000000.db"]:
        (ziel / name).write_bytes(b"")
    sichern(pfad, tmp_path / "keine-bilder", ziel, behalten=2)
    namen = sorted(p.name for p in ziel.glob("lessons-*.db"))
    assert len(namen) == 2 and "lessons-20260101-000000.db" not in namen


def test_einzelinstanz(tmp_path):
    a = Instanzsperre(tmp_path)
    a.erwerben()
    b = Instanzsperre(tmp_path)
    with pytest.raises(LaeuftBereits):
        b.erwerben()
    a.freigeben()
    b.erwerben()
    b.freigeben()


@pytest.mark.parametrize("kodierung", ["utf-16", "utf-8-sig", "utf-8"])
def test_env_kodierungen(tmp_path, monkeypatch, kodierung):
    monkeypatch.delenv("LV_TEST_WERT", raising=False)
    datei = tmp_path / ".env"
    datei.write_text("# Kommentar äöü\nLV_TEST_WERT=Grüße\n", encoding=kodierung)
    _load_dotenv(datei)
    assert os.environ["LV_TEST_WERT"] == "Grüße"
